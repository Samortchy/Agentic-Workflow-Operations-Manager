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
# parents[2] == executors/ (extractors → steps → executors); the DB lives in executors/data/.
_DEFAULT_DB_PATH = Path(__file__).parents[2] / "data" / "office.db"

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
                mock = self._build_mock(service, config, envelope)
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
                data={
                    "rows": rows,
                    "row_count": len(rows),
                    # Convenience for single-record consumers (e.g. the expense
                    # AnomalyChecker): the lone row when exactly one matched, else None.
                    # List consumers keep reading `rows`. See spec.md "DBExtractor output contract".
                    "record": rows[0] if len(rows) == 1 else None,
                },
                error=None,
            )

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))

    # ------------------------------------------------------------------
    # Service mocks
    # ------------------------------------------------------------------

    @staticmethod
    def _build_mock(service: str, config: dict, envelope: dict | None = None) -> dict:
        envelope = envelope or {}
        if service == "calendar_api":
            return DBExtractor._calendar_mock(config, envelope)

        if service == "compliance_checker":
            return {
                "compliant": True,
                "flags": [],
                "action_type": config.get("action_type", "unspecified"),
                "checked_at": datetime.now(timezone.utc).isoformat() + "Z",
            }

        # Unknown service — return a generic stub so the pipeline continues.
        return {"service": service, "mocked": True}

    @staticmethod
    def _calendar_mock(config: dict, envelope: dict) -> dict:
        """
        Mock calendar availability in the shape SlotRanker expects:
          {participants: [emails], slots: [{slot_start, slot_end, availability:{email:bool}}]}

        - participants come from the company directory (employees by department),
          per the Phase-2 decision; falls back to NLP-extracted participant emails.
        - slots are generated on upcoming weekdays during local working hours,
          EXCLUDING any slot already confirmed in the meetings table (real bookings win).
        - timezone-aware: slots carry the configured local offset so they persist and
          display at the right wall-clock time (e.g. 09:00 Africa/Cairo, not 12:00 from a
          naive-UTC value). Reads `timezone` from config (falls back to the ClockChecker
          step's timezone, then UTC).
        """
        from ...core import backend_client as bc  # lazy import keeps this step light

        task = envelope.get("task", {})
        intake = envelope.get("intake", {})
        department = config.get("department") or task.get("department") or intake.get("department")
        company_id = envelope.get("_ctx", {}).get("company_id")

        # Resolve the scheduling timezone: explicit config wins, else reuse whatever the
        # ClockChecker step recorded, else UTC. Keeps the agent's tz in one place (config).
        tzname = config.get("timezone")
        if not tzname:
            for step_obj in envelope.get("execution", {}).get("steps", {}).values():
                tzname = step_obj.get("data", {}).get("timezone")
                if tzname:
                    break
        tzname = tzname or "UTC"
        tz = timezone.utc
        try:
            from zoneinfo import ZoneInfo
            if tzname != "UTC":
                tz = ZoneInfo(tzname)
        except Exception:
            tzname, tz = "UTC", timezone.utc

        # Participants = directory for this department.
        participants: list[str] = []
        try:
            employees = bc.get_employees(department=department, company_id=company_id)
            participants = [e["email"] for e in employees if e.get("email")]
        except Exception:
            participants = []

        # Fallback: participant emails an NLP step extracted, if the directory is empty.
        if not participants:
            steps = envelope.get("execution", {}).get("steps", {})
            for step_obj in reversed(list(steps.values())):
                emails = step_obj.get("data", {}).get("participant_emails")
                if emails:
                    participants = emails if isinstance(emails, list) else [emails]
                    break

        # Already-booked slots (confirmed meetings) → unavailable. Compare on the
        # absolute instant so naive/aware mixes don't collide.
        booked: set = set()
        for ts in bc.get_confirmed_slots(company_id=company_id):
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=tz)
                booked.add(dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M"))
            except (ValueError, TypeError):
                continue

        look_ahead     = int(config.get("look_ahead_days", 5))
        duration_min   = int(config.get("duration_minutes", 60))
        working_hours  = config.get("working_hours", [9, 11, 14])
        # "Today" in the scheduling timezone, midnight local.
        base = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

        slots = []
        for day_offset in range(1, look_ahead + 1):
            day = base + timedelta(days=day_offset)
            if day.weekday() >= 5:  # skip Sat/Sun
                continue
            for hour in working_hours:
                start = day.replace(hour=hour)
                # Dedup key is the absolute UTC instant.
                key = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
                if key in booked:
                    continue
                end = start + timedelta(minutes=duration_min)
                slots.append({
                    # tz-aware ISO (carries the local offset, e.g. +03:00).
                    "slot_start":   start.isoformat(timespec="minutes"),
                    "slot_end":     end.isoformat(timespec="minutes"),
                    # Mock: everyone in the directory is free on non-booked slots.
                    "availability": {p: True for p in participants},
                })

        return {
            "participants":    participants,
            "slots":           slots,
            "timezone":        tzname,
            "booked_excluded": len(booked),
        }

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
