"""
Agent 04 — Leave Checker
approval: none  |  on_failure: escalate

No LLM calls needed: NLPExtractor resolves all fields without raw_text.
DBExtractor returns empty rows (DB absent) — success.
TemplateRenderer renders hr_reply.j2 (file exists, empty template) — success.
EmailDispatcher runs in dry-run mode writing to output/emails/.
Expected terminal status: "completed".
"""
from core.base_agent import ExecutionRunner

import pprint

_ENVELOPE = {
    "intake": {
        "department": "HR",
        "task_type": "leave_check",
        "isAutonomous": False,
        "confidence": 0.95,
        "processed_at": "2026-05-03T10:00:00Z",
    },
    "task": {
        "task_id": "T004",
        "title": "Check Annual Leave Balance",
        "description": "Alice wants to know her remaining annual leave balance.",
        "department": "HR",
        "isAutonomous": False,
        "task_type": "leave_check",
        "requester_name": "alice@company.com",
        "stated_deadline": "2026-05-04",
        "action_required": "Return leave balance to requester",
        "success_criteria": "Reply sent with leave balance info",
        "structured_at": "2026-05-03T10:05:00Z",
    },
    "priority": {
        "priority_score": 1,
        "priority_label": "low",
        "confidence": 0.95,
        "model_version": "v1",
        "top_features_used": [],
        "scored_at": "2026-05-03T10:10:00Z",
    },
}


def test_04_leave_checker():
    runner = ExecutionRunner("configs/04_leave_checker.json")

    result = runner.execute(_ENVELOPE.copy())

    pprint.pprint(result)

    assert "execution" in result
    assert result["execution"]["agent_name"] == "leave_checker"
    assert result["execution"]["status"] == "completed"
    assert "extract_intent" in result["execution"]["steps"]
    assert "fetch_leave_record" in result["execution"]["steps"]
    assert "render_reply" in result["execution"]["steps"]
    assert "send_reply" in result["execution"]["steps"]
