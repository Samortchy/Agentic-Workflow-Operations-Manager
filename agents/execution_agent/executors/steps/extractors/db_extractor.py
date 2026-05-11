import re
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv(override=False)

from ..base_step import BaseStep, StepResult
from ...core.envelope import resolve_path

# Absolute path anchored to this file — works regardless of CWD.
_DEFAULT_DB_PATH = Path(__file__).parents[3] / "data" / "office.db"

_TABLE_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')


def _safe_table(name: str) -> str:
    if not _TABLE_NAME_RE.match(name):
        raise ValueError(f"Invalid table name: '{name}'")
    return name


class DBExtractor(BaseStep):
    """
    Extracts records from a SQLite table or mocks an external service call.

    Config fields
    -------------
    table        : str        Table to query (required unless `service` is set).
    match_on     : list[str]  Column names for the WHERE clause. Values are
                              resolved in order:
                                1. Most recent execution step data
                                2. envelope["task"] block
    access       : str        Optional — "read_only" (informational only).
    service      : str        Optional — returns a mock for the named service
                              and skips the DB entirely. Supported services:
                              "calendar_api", "compliance_checker".
    look_ahead_days : int     calendar_api only — how many days ahead to generate
                              slots for (default 5).
    action_type  : str        compliance_checker only — passed through in the
                              mock response so downstream steps can see it.
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            service = config.get("service")
            if service:
                mock = self._build_mock(service, config)
                return StepResult(success=True, data=mock, error=None)

            table = config.get("table", "")
            if not table:
                return StepResult(
                    success=False, data={}, error="config.table is required"
                )

            try:
                table = _safe_table(table)
            except ValueError as e:
                return StepResult(success=False, data={}, error=str(e))

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
    # Service mocks
    # ------------------------------------------------------------------

    @staticmethod
    def _build_mock(service: str, config: dict) -> dict:
        if service == "calendar_api":
            look_ahead = int(config.get("look_ahead_days", 5))
            base = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
            slots = []
            for day_offset in range(look_ahead):
                day = base + timedelta(days=day_offset + 1)
                slots.append(day.strftime("%Y-%m-%dT09:00"))
                slots.append((day + timedelta(hours=5)).strftime("%Y-%m-%dT14:00"))
            return {
                "available_slots": slots,
                "timezone": "UTC",
                "look_ahead_days": look_ahead,
            }

        if service == "compliance_checker":
            return {
                "compliant": True,
                "flags": [],
                "action_type": config.get("action_type", "unspecified"),
                "checked_at": datetime.now(timezone.utc).isoformat() + "Z",
            }

        # Unknown service — return a generic stub so the pipeline continues.
        return {"service": service, "mocked": True}

    # ------------------------------------------------------------------
    # Envelope resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_match_values(match_on: list, envelope: dict) -> dict:
        """
        For each column in match_on, resolve its value from:
          1. Execution step data (most recent step wins).
          2. envelope["task"] block.
        Returns {column: value} for every column that resolved.
        """
        resolved: dict = {}
        steps_data = envelope.get("execution", {}).get("steps", {})
        task = envelope.get("task", {})

        for col in match_on:
            found = None
            for step_name in reversed(list(steps_data.keys())):
                try:
                    found = resolve_path(
                        envelope, f"execution.steps.{step_name}.data.{col}"
                    )
                    break
                except KeyError:
                    continue

            if found is None:
                found = task.get(col)

            if found is not None:
                resolved[col] = found

        return resolved

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @staticmethod
    def _query(table: str, match_on: list, match_values: dict) -> list:
        db_path = Path(os.environ.get("DB_PATH", str(_DEFAULT_DB_PATH)))

        if not db_path.exists():
            return []

        active_cols = [col for col in match_on if col in match_values]
        params = [match_values[col] for col in active_cols]

        # Refuse to full-scan when match_on was given but nothing resolved —
        # that means the preceding extraction step failed or the key is wrong.
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
