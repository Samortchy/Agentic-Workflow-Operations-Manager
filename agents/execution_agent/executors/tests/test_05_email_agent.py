"""
Agent 05 — Email Agent
approval: single_confirm_if_low_confidence  |  on_failure: escalate

Step 1 (summarise_attachments) is skipped via run_if: task.has_attachments not in envelope.
Steps 2-3 (draft_reply, score_confidence) are mocked LLMGenerator calls.
Step 4 (compliance_check) uses DBExtractor service mock — no DB needed.
Step 5 (send_email dispatcher): approval gate fires.
  - Gate reads execution.result.draft_confidence (never set by any step).
  - Missing confidence → gate pauses with "approval_pending".
Expected terminal status: "approval_pending".
"""
from unittest.mock import patch
from core.base_agent import ExecutionRunner

import pprint

_ENVELOPE = {
    "intake": {
        "department": "IT",
        "task_type": "email_reply",
        "isAutonomous": False,
        "confidence": 0.9,
        "processed_at": "2026-05-03T10:00:00Z",
    },
    "task": {
        "task_id": "T005",
        "title": "Reply to IT Support Request",
        "description": "User reported a VPN issue and needs a troubleshooting reply.",
        "department": "IT",
        "isAutonomous": False,
        "task_type": "email_reply",
        "requester_name": "dave@company.com",
        "stated_deadline": "2026-05-04",
        "action_required": "Draft and send reply email",
        "success_criteria": "Appropriate reply sent to requester",
        "structured_at": "2026-05-03T10:05:00Z",
    },
    "priority": {
        "priority_score": 2,
        "priority_label": "medium",
        "confidence": 0.88,
        "model_version": "v1",
        "top_features_used": [],
        "scored_at": "2026-05-03T10:10:00Z",
    },
}

# Call 1 → draft_reply (returns plain text, stored under output_field)
# Call 2 → score_confidence (returns JSON; _try_json parses it)
_LLM_RESPONSES = [
    "Dear Dave,\n\nPlease try reconnecting the VPN client and restarting the service.",
    '{"confidence_score": 0.91}',
]


def test_05_email_agent():
    runner = ExecutionRunner("configs/05_email_agent.json")

    with patch(
        "steps.processors.llm_generator.LLMGenerator._call",
        side_effect=_LLM_RESPONSES,
    ):
        result = runner.execute(_ENVELOPE.copy())

    assert "execution" in result
    assert result["execution"]["agent_name"] == "email_agent"
    # single_confirm_if_low_confidence: execution.result.draft_confidence is absent
    # → approval gate pauses as a precaution
    assert result["execution"]["status"] == "approval_pending"


def test_05_email_agent_confirmed():
    """
    Mimics user confirming the draft email reply.

    Phase 1 → pauses (draft_confidence absent → gate fires).
    Phase 2 → re-run with the paused envelope → gate skipped (status already
    'approval_pending') → EmailDispatcher runs in dry-run mode.

    Both runs call draft_reply + score_confidence (4 total LLM calls).
    return_value is used so the same mock response is returned every call.
    """
    runner = ExecutionRunner("configs/05_email_agent.json")

    _draft = "Dear Dave,\n\nPlease try reconnecting the VPN client and restarting the service."

   
    # Phase 1 — pauses for approval
    paused = runner.execute(_ENVELOPE.copy())
    assert paused["execution"]["status"] == "approval_pending"

    # Phase 2 — mimic confirmation
    result = runner.execute(paused)

    pprint.pprint(result["execution"])

    assert result["execution"]["agent_name"] == "email_agent"
    assert result["execution"]["status"] == "completed"
    assert "send_email" in result["execution"]["steps"]
