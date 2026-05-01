import sqlite3
from pathlib import Path

from steps.base_step import BaseStep, StepResult

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

_DB_PATH = Path("data/execution_agent.db")


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
                         Values that start with "execution." are treated as envelope
                         path references and resolved at runtime via resolve_path().
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            table = config.get("table", "")
            if not table:
                return StepResult(success=False, data={}, error="config.table is required")

            output_field = config.get("output_field", "rows")
            columns = config.get("columns", ["*"])
            raw_filters = config.get("filters", {})

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
    def _resolve_filters(filters: dict, envelope: dict) -> dict:
        resolved = {}
        for col, value in filters.items():
            if isinstance(value, str) and "." in value:
                # Treat as an envelope path reference and resolve it.
                resolved[col] = _resolve_path(envelope, value)
            else:
                resolved[col] = value
        return resolved

    @staticmethod
    def _query(table: str, columns: list, filters: dict) -> list:
        if not _DB_PATH.exists():
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
