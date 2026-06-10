"""
anomaly_checker.py
Custom step — Expense Tracker (Agent 08)
P5 responsibility

What it does:
    Receives an expense report record fetched by the preceding DBExtractor step.
    Runs three anomaly checks:
        1. Duplicate submission — same employee, same amount, within duplicate_window_days
        2. Missing receipt    — amount exceeds receipt_threshold_egp and no receipt attached
        3. Policy violation   — any line item flagged as outside expense policy

Returns:
    StepResult.data = {
        "anomaly":        bool,
        "anomaly_reasons": list[str],   # empty if anomaly == False
        "report_id":      str,
        "amount_egp":     float,
        "status":         str,          # expense report status from DB
        "approval_date":  str | None,
        "payment_eta":    str | None,
    }

If anomaly == True:
    The runner reads data["anomaly"] == True and, per the config's approval value
    "single_confirm_if_anomaly", the approval_gate escalates before any dispatcher runs.
    This step itself never escalates — it only reports what it found.

Spec compliance:
    - Inherits BaseStep
    - run() signature: (self, envelope: dict, config: dict) -> StepResult
    - Never raises — all exceptions caught and returned as StepResult(success=False)
    - Never modifies envelope directly
    - Never adds fields to StepResult
    - Never writes to SQLite — runner does that
    - Uses resolve_path() from core.envelope for all envelope reads
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from ..base_step import BaseStep, StepResult
from ...core.envelope import resolve_path

# parents[2] == executors/ (custom → steps → executors); the DB lives in executors/data/.
_DEFAULT_DB_PATH = Path(__file__).parents[2] / "data" / "office.db"


class AnomalyChecker(BaseStep):

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            # ── 1. Read config thresholds ─────────────────────────────────
            duplicate_window_days  = config.get("duplicate_window_days", 30)
            receipt_threshold_egp  = config.get("receipt_threshold_egp", 500)
            db_path                = config.get("db_path") or os.environ.get("DB_PATH") or str(_DEFAULT_DB_PATH)

            # ── 2. Read the expense record fetched by the previous step ───
            # DBExtractor ("fetch_expense_record") returns {rows, row_count, record}.
            # `record` is the lone row when exactly one matched; otherwise fall back
            # to rows[0] when unambiguous, else escalate (can't anomaly-check a set).
            data = resolve_path(
                envelope,
                "execution.steps.fetch_expense_record.data"
            )
            record = data.get("record")
            if record is None:
                rows = data.get("rows", [])
                if len(rows) == 1:
                    record = rows[0]
                else:
                    return StepResult(
                        success=False,
                        data={},
                        error=(
                            f"AnomalyChecker: expected exactly one expense record but the "
                            f"fetch returned {len(rows)}. Ensure 'report_id' was extracted so "
                            f"the lookup is unambiguous."
                        ),
                    )

            report_id     = record.get("report_id", "")
            employee_id   = record.get("employee_id", "")
            amount_egp    = float(record.get("amount_egp", 0))
            has_receipt   = bool(record.get("has_receipt", False))
            status        = record.get("status", "unknown")
            approval_date = record.get("approval_date", None)
            payment_eta   = record.get("payment_eta", None)
            submitted_at  = record.get("submitted_at", None)

            # line_items is stored as JSON text in SQLite — parse to a list.
            line_items = record.get("line_items", [])
            if isinstance(line_items, str):
                try:
                    line_items = json.loads(line_items)
                except (ValueError, TypeError):
                    line_items = []

            # ── 3. Run anomaly checks ─────────────────────────────────────
            anomaly_reasons = []

            # Check 1 — duplicate submission
            duplicate = self._check_duplicate(
                db_path, employee_id, amount_egp,
                submitted_at, duplicate_window_days
            )
            if duplicate:
                anomaly_reasons.append(
                    f"Duplicate submission: another report of {amount_egp} EGP "
                    f"found within the last {duplicate_window_days} days."
                )

            # Check 2 — missing receipt
            if amount_egp > receipt_threshold_egp and not has_receipt:
                anomaly_reasons.append(
                    f"Missing receipt: amount {amount_egp} EGP exceeds threshold "
                    f"{receipt_threshold_egp} EGP but no receipt is attached."
                )

            # Check 3 — policy violations in line items
            violations = self._check_line_item_policy(line_items)
            if violations:
                anomaly_reasons.append(
                    f"Policy violation in line items: {', '.join(violations)}"
                )

            anomaly_detected = len(anomaly_reasons) > 0

            return StepResult(
                success=True,
                data={
                    "anomaly":         anomaly_detected,
                    "anomaly_reasons": anomaly_reasons,
                    "report_id":       report_id,
                    "amount_egp":      amount_egp,
                    "status":          status,
                    "approval_date":   approval_date,
                    "payment_eta":     payment_eta,
                },
                error=None
            )

        except KeyError as e:
            # resolve_path raised because a previous step's data is missing
            return StepResult(
                success=False,
                data={},
                error=(
                    f"AnomalyChecker could not find required envelope path: {e}. "
                    f"Ensure 'fetch_expense_record' step ran successfully before this step."
                )
            )
        except Exception as e:
            return StepResult(
                success=False,
                data={},
                error=f"AnomalyChecker unexpected error: {str(e)}"
            )

    # ── private helpers ───────────────────────────────────────────────────────

    def _check_duplicate(
        self,
        db_path: str,
        employee_id: str,
        amount_egp: float,
        submitted_at: str | None,
        window_days: int
    ) -> bool:
        """
        Queries the finance_expense_reports table for another report from the
        same employee with the same amount within the duplicate window.
        Returns True if a duplicate is found, False otherwise.
        If the DB is unreachable, returns False (do not block legitimate reports
        due to a DB connectivity issue — anomaly_reasons will be empty).
        """
        if not submitted_at:
            return False
        try:
            cutoff = (
                datetime.fromisoformat(submitted_at) - timedelta(days=window_days)
            ).isoformat()

            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM finance_expense_reports
                WHERE employee_id = ?
                  AND amount_egp  = ?
                  AND submitted_at >= ?
                  AND submitted_at <  ?
                """,
                (employee_id, amount_egp, cutoff, submitted_at)
            )
            count = cur.fetchone()[0]
            con.close()
            return count > 0
        except Exception:
            # DB unreachable — fail open (do not falsely flag as duplicate)
            return False

    def _check_line_item_policy(self, line_items: list) -> list[str]:
        """
        Checks each line item against a hard-coded policy ruleset.
        Returns a list of violation descriptions. Empty list means no violations.

        Policy rules (extend this list as org policy evolves):
            - Category "entertainment" is not reimbursable
            - Category "personal" is not reimbursable
            - Any single line item above 10,000 EGP requires a separate approval note
              (flagged here as a soft anomaly — not a hard block)
        """
        NON_REIMBURSABLE = {"entertainment", "personal"}
        HIGH_VALUE_THRESHOLD = 10_000

        violations = []
        for item in line_items:
            category = str(item.get("category", "")).lower().strip()
            amount   = float(item.get("amount_egp", 0))
            desc     = item.get("description", "unnamed item")

            if category in NON_REIMBURSABLE:
                violations.append(
                    f"'{desc}' — category '{category}' is not reimbursable"
                )
            if amount > HIGH_VALUE_THRESHOLD:
                violations.append(
                    f"'{desc}' — single line item {amount} EGP exceeds "
                    f"{HIGH_VALUE_THRESHOLD} EGP, requires separate approval note"
                )

        return violations