import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from steps.base_step import BaseStep, StepResult
from core.envelope import resolve_path


_DEFAULT_DB_PATH = "data/office.db"

# Mock responses keyed by service name.
# Extend this dict as new service integrations are added.
_SERVICE_MOCKS: dict[str, dict] = {
    "calendar_api": {
        "available_slots": ["2026-05-05T10:00", "2026-05-05T14:00", "2026-05-06T09:00"],
        "timezone": "UTC",
    },
    "compliance_checker": {
        "compliant": True,
        "flags": [],
        "checked_at": "2026-05-02T00:00:00Z",
    },
}


class DBExtractor(BaseStep):
    """
    Extracts records from a SQLite table or mocks a service call.

    Config fields
    -------------
    table      : str        Table to query (required unless service is set).
    match_on   : list[str]  Column names for the WHERE clause.
    access     : str        Optional — "read_only" (informational, not enforced).
    service    : str        Optional — if set, returns a mock response for the
                            named service and skips the DB entirely.

    match_on values are resolved in order:
      1. Most recent step data in execution.steps.*.data
      2. envelope["task"] block
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            # Service mock path — no DB access needed.
            service = config.get("service")
            if service:
                mock = _SERVICE_MOCKS.get(service, {"service": service, "mocked": True})
                return StepResult(success=True, data=mock, error=None)

            table = config.get("table", "")
            if not table:
                return StepResult(
                    success=False, data={}, error="config.table is required"
                )

            match_on: list = config.get("match_on", [])
            match_values = self._resolve_match_values(match_on, envelope)

            rows = self._query(table, match_on, match_values)
            return StepResult(
                success=True,
                data={"rows": rows, "row_count": len(rows)},
                error=None,
            )

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_match_values(match_on: list, envelope: dict) -> dict:
        """
        For each column in match_on, look up its value from:
          1. Accumulated step data (most recent step wins)
          2. envelope["task"]
        Returns a dict of {column: value} for columns that resolved.
        """
        resolved: dict = {}
        steps_data = envelope.get("execution", {}).get("steps", {})
        task = envelope.get("task", {})

        for col in match_on:
            # Walk steps in reverse via resolve_path (most recent first).
            found = None
            step_names = list(steps_data.keys())
            for step_name in reversed(step_names):
                try:
                    found = resolve_path(envelope, f"execution.steps.{step_name}.data.{col}")
                    break
                except KeyError:
                    continue

            if found is None:
                found = task.get(col)

            if found is not None:
                resolved[col] = found

        return resolved

    @staticmethod
    def _query(table: str, match_on: list, match_values: dict) -> list:
        db_path = Path(os.environ.get("DB_PATH", _DEFAULT_DB_PATH))
        if not db_path.exists():
            return []

        active_cols = [col for col in match_on if col in match_values]
        params = [match_values[col] for col in active_cols]

        # Refuse to full-scan if match_on was specified but nothing resolved.
        if match_on and not active_cols:
            return []

        where_clause = ""
        if active_cols:
            where_parts = [f"{col} = ?" for col in active_cols]
            where_clause = " WHERE " + " AND ".join(where_parts)

        sql = f"SELECT * FROM {table}{where_clause}"

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
