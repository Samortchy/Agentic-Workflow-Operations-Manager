import logging
import sqlite3
from pathlib import Path

from ..base_step import BaseStep, StepResult

# Resolve path strings from config filter values.
# Falls back to simple dot-walking when core.envelope is not yet wired up.
try:
    from core.envelope import resolve_path as _resolve_path
except ImportError:
    def _resolve_path(envelope: dict, path: str):  # type: ignore[misc]
        obj = envelope
        for part in path.split("."):
            if not isinstance(obj, dict):
                return None
            obj = obj.get(part)
        return obj

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/office.db")

# Envelope sections searched (in order) when resolving a match_on field name.
_MATCH_ON_SECTIONS = ("intake", "task", "priority")


class DBFetcher(BaseStep):
    """
    Processor that runs a parameterised SELECT against the SQLite operational database
    and returns rows as a list of dicts for downstream steps to use.

    Unlike DBExtractor (which pulls source data at the start of a pipeline),
    DBFetcher is used mid-pipeline to enrich processing — e.g. pulling metrics
    for a report after the NLP extractor has identified the department and date range.

    Config fields
    -------------
    table        : str   Table to query (required).
    output_field : str   Key used in StepResult.data for the rows list (default: "rows").
    columns      : list  Columns to SELECT (default: all — ["*"]).
    filters      : dict  Column → value pairs for WHERE clause.
                         Values containing "." are treated as envelope dot-path references
                         and resolved at runtime. Literal values are used as-is.
    match_on     : list  Alternative to filters. List of field names whose values are
                         automatically resolved from the envelope's intake/task/priority
                         sections and used as equality filters. Use this when the filter
                         values live in the envelope rather than being hardcoded.
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            table = config.get("table", "")
            if not table:
                return StepResult(success=False, data={}, error="config.table is required")

            output_field = config.get("output_field", "rows")
            columns = config.get("columns", ["*"])

            # Support both 'filters' (explicit map) and 'match_on' (field list resolved
            # from the envelope). 'filters' takes priority if both are present.
            raw_filters = config.get("filters") or {}
            if not raw_filters and "match_on" in config:
                raw_filters = self._build_filters_from_match_on(
                    config["match_on"], envelope
                )

            resolved_filters = self._resolve_filters(raw_filters, envelope)
            rows = self._query(table, columns, resolved_filters)

            return StepResult(
                success=True,
                data={output_field: rows, "row_count": len(rows)},
                error=None,
            )

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filters_from_match_on(fields: list, envelope: dict) -> dict:
        """
        For each field name in match_on, search the standard envelope sections
        (intake → task → priority) and use the first value found as the filter value.
        Fields with no match in the envelope are skipped.
        """
        filters = {}
        for field in fields:
            for section in _MATCH_ON_SECTIONS:
                val = envelope.get(section, {}).get(field)
                if val is not None:
                    filters[field] = val
                    break
            else:
                logger.warning(
                    "DBFetcher: match_on field '%s' not found in envelope sections %s — skipped",
                    field, _MATCH_ON_SECTIONS,
                )
        return filters

    @staticmethod
    def _resolve_filters(filters: dict, envelope: dict) -> dict:
        """
        Resolve envelope path references in filter values.
        A value is treated as a path reference only when it contains '.' AND
        resolving it against the envelope succeeds. Plain strings are used as-is.
        """
        resolved = {}
        for col, value in filters.items():
            if isinstance(value, str) and "." in value:
                try:
                    resolved[col] = _resolve_path(envelope, value)
                except (KeyError, TypeError):
                    # Path didn't resolve — use the literal string value
                    resolved[col] = value
            else:
                resolved[col] = value
        return resolved

    @staticmethod
    def _query(table: str, columns: list, filters: dict) -> list:
        if not _DB_PATH.exists():
            logger.warning(
                "DBFetcher: database not found at '%s' — returning empty result set. "
                "Run seed_db.py to initialise the database.",
                _DB_PATH,
            )
            return []

        col_clause = ", ".join(columns) if columns != ["*"] else "*"

        active_filters = {k: v for k, v in filters.items() if v is not None}
        params: list = []
        where_clause = ""

        if active_filters:
            where_parts = [f"{col} = ?" for col in active_filters]
            params = list(active_filters.values())
            where_clause = " WHERE " + " AND ".join(where_parts)

        sql = f"SELECT {col_clause} FROM {table}{where_clause}"

        with sqlite3.connect(str(_DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
