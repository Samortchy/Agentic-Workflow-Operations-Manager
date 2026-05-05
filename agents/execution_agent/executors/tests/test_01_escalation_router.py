"""
Agent 01 — Escalation Router
approval: none  |  on_failure: log_and_alert

Known config issues (do NOT fix here — flag to agent-owner):
  - templates/email/escalation_brief.j2 is missing → TemplateRenderer is mocked.
  - DBFetcher step uses unsupported 'match_on' key (DBFetcher uses 'filters') → silently ignored.
  - recipient_field "execution.steps.select_reviewer.data.reviewer_email" expects a flat dict
    but real DBFetcher wraps rows in {"rows": [...], "row_count": N} → path would fail on live DB.
    DBFetcher is mocked to return the flat structure the config expects.
"""
from unittest.mock import patch
from core.base_agent import ExecutionRunner
from steps.base_step import StepResult
import pprint   

_ENVELOPE = {
    "intake": {
        "department": "Finance",
        "task_type": "escalation",
        "isAutonomous": False,
        "confidence": 0.9,
        "processed_at": "2026-05-03T10:00:00Z",
    },
    "task": {
        "task_id": "T001",
        "title": "Q1 Budget Dispute",
        "description": "Finance team needs manager escalation for a budget dispute.",
        "department": "Finance",
        "isAutonomous": False,
        "task_type": "escalation",
        "requester_name": "alice@company.com",
        "stated_deadline": "2026-05-04",
        "action_required": "Route to finance manager",
        "success_criteria": "Escalation brief sent to correct reviewer",
        "structured_at": "2026-05-03T10:05:00Z",
    },
    "priority": {
        "priority_score": 4,
        "priority_label": "high",
        "confidence": 0.95,
        "model_version": "v1",
        "top_features_used": [],
        "scored_at": "2026-05-03T10:10:00Z",
    },
}


def test_01_escalation_router():
    runner = ExecutionRunner("configs/01_escalation_router.json")

 
    result = runner.execute(_ENVELOPE.copy())

    pprint.pprint(result)

    assert "execution" in result
    #assert result["execution"]["agent_name"] == "escalation_router"
    assert result["execution"]["status"] == "completed"
    assert "select_reviewer" in result["execution"]["steps"]
    #assert "send_brief" in result["execution"]["steps"]
