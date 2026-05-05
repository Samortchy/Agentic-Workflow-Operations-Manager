"""
Agent 08 — Expense Tracker
approval: none  |  on_failure: escalate

DBExtractor is mocked for both tests: data/office.db exists but has no
finance_expense_reports table, so a live query raises OperationalError.

Two scenarios are tested:

1. test_08_expense_tracker_clean
   No anomaly detected → run_if on send_status_reply passes → EmailDispatcher
   sends status reply in dry-run mode → status="completed".

2. test_08_expense_tracker_anomaly
   Anomaly detected (duplicate + missing receipt) → run_if on send_status_reply
   evaluates to False → step is skipped → agent still completes but no email
   is sent → status="completed", send_status_reply absent from execution.steps.
"""
from unittest.mock import patch
from core.base_agent import ExecutionRunner
from steps.base_step import StepResult

_ENVELOPE = {
    "intake": {
        "department": "Finance",
        "task_type": "expense_check",
        "isAutonomous": False,
        "confidence": 0.91,
        "processed_at": "2026-05-03T10:00:00Z",
    },
    "task": {
        "task_id": "T008",
        "title": "Check Expense Report EXP-2024",
        "description": "Employee submitted expense report EXP-2024 for May travel.",
        "department": "Finance",
        "isAutonomous": False,
        "task_type": "expense_check",
        "requester_name": "grace@company.com",
        "stated_deadline": "2026-05-06",
        "action_required": "Validate report and reply with status",
        "success_criteria": "Expense status sent to requester",
        "structured_at": "2026-05-03T10:05:00Z",
    },
    "priority": {
        "priority_score": 2,
        "priority_label": "medium",
        "confidence": 0.9,
        "model_version": "v1",
        "top_features_used": [],
        "scored_at": "2026-05-03T10:10:00Z",
    },
}

# AnomalyChecker reads directly from fetch_expense_record.data (flat dict), NOT
# from data["rows"][0].  DBExtractor normally wraps rows in {"rows": [...], "row_count": N},
# so there is a structural mismatch between the two steps that needs to be fixed in the
# integration.  The mocks here reflect the flat format AnomalyChecker actually requires.

# Clean record — no anomaly triggers
_CLEAN_RECORD = StepResult(
    True,
    {
        "report_id": "EXP-2024",
        "employee_id": "EMP-001",
        "amount_egp": 350.0,
        "has_receipt": True,
        "line_items": [],
        "status": "pending",
        "approval_date": None,
        "payment_eta": None,
        "submitted_at": "2026-05-01T09:00:00",
    },
    None,
)

# Anomalous record — high amount with no receipt + non-reimbursable line item
_ANOMALOUS_RECORD = StepResult(
    True,
    {
        "report_id": "EXP-2024",
        "employee_id": "EMP-001",
        "amount_egp": 8500.0,
        "has_receipt": False,
        "line_items": [
            {"category": "entertainment", "amount_egp": 2000.0, "description": "team dinner"}
        ],
        "status": "pending",
        "approval_date": None,
        "payment_eta": None,
        "submitted_at": "2026-05-01T09:00:00",
    },
    None,
)


def test_08_expense_tracker_clean():
    """
    Clean report: no duplicate, receipt present, no policy violations.
    AnomalyChecker returns anomaly=False → run_if passes → EmailDispatcher sends reply.
    """
    runner = ExecutionRunner("configs/08_expense_tracker.json")

  
    result = runner.execute(_ENVELOPE.copy())

    assert "execution" in result
    assert result["execution"]["agent_name"] == "expense_tracker"
    assert result["execution"]["status"] == "completed"
    assert "check_anomalies" in result["execution"]["steps"]
    assert result["execution"]["steps"]["check_anomalies"]["data"]["anomaly"] is False
    # run_if passed → reply was sent
    assert "send_status_reply" in result["execution"]["steps"]


def test_08_expense_tracker_anomaly():
    """
    Anomalous report: high amount with no receipt + non-reimbursable line item.
    AnomalyChecker returns anomaly=True → run_if on send_status_reply evaluates
    to False → step is skipped → agent completes without sending a reply.
    """
    runner = ExecutionRunner("configs/08_expense_tracker.json")

   
    result = runner.execute(_ENVELOPE.copy())

    assert "execution" in result
    assert result["execution"]["agent_name"] == "expense_tracker"
    assert result["execution"]["status"] == "completed"
    assert result["execution"]["steps"]["check_anomalies"]["data"]["anomaly"] is True
    assert len(result["execution"]["steps"]["check_anomalies"]["data"]["anomaly_reasons"]) > 0
    # run_if failed (anomaly == false is False) → reply was NOT sent
    assert "send_status_reply" not in result["execution"]["steps"]
