"""
Agent 03 — Report Generator
approval: single_confirm  |  on_failure: log_and_alert

LLMGenerator._call is mocked to avoid real API calls.
With approval=single_confirm the runner pauses before the FileDispatcher step,
so the expected terminal status is "approval_pending".
"""
from unittest.mock import patch
from core.base_agent import ExecutionRunner

import pprint

_ENVELOPE = {
    "intake": {
        "department": "Finance",
        "task_type": "report",
        "isAutonomous": False,
        "confidence": 0.92,
        "processed_at": "2026-05-03T10:00:00Z",
    },
    "task": {
        "task_id": "T003",
        "title": "Weekly Finance Report",
        "description": "Generate the weekly finance department report for Q1 2026.",
        "department": "Finance",
        "isAutonomous": False,
        "task_type": "report",
        "requester_name": "carol@company.com",
        "stated_deadline": "2026-05-05",
        "action_required": "Generate and file report",
        "success_criteria": "Report saved to output/reports",
        "structured_at": "2026-05-03T10:05:00Z",
    },
    "priority": {
        "priority_score": 2,
        "priority_label": "medium",
        "confidence": 0.87,
        "model_version": "v1",
        "top_features_used": [],
        "scored_at": "2026-05-03T10:10:00Z",
    },
}


def test_03_report_generator():
    runner = ExecutionRunner("configs/03_report_generator.json")

  
    result = runner.execute(_ENVELOPE.copy())

    assert "execution" in result
    assert result["execution"]["agent_name"] == "report_generator"
    # approval=single_confirm → runner pauses before FileDispatcher
    assert result["execution"]["status"] == "approval_pending"


def test_03_report_generator_confirmed():
    """
    Mimics user clicking 'Confirm' in the UI.

    The runner's resume mechanism (base_agent.py:72) skips the approval gate
    when execution.status is already 'approval_pending'.  Passing the paused
    envelope back to execute() is all that is needed to resume.

    On the second run the pre-dispatcher steps re-execute (NLPExtractor,
    DBFetcher, LLMGenerator) and the gate is bypassed → FileDispatcher runs.
    """
    runner = ExecutionRunner("configs/03_report_generator.json")

    _report = "Weekly Finance Report\n\nRevenue: 12.4M EGP. Expenses within budget."

   
    # Phase 1 — runner pauses for approval
    paused = runner.execute(_ENVELOPE.copy())
    assert paused["execution"]["status"] == "approval_pending"

    # Phase 2 — mimic confirmation: re-run with the paused envelope.
    # execution.status == "approval_pending" → gate is skipped → FileDispatcher runs.
    result = runner.execute(paused)

    pprint.pprint(result)

    assert result["execution"]["agent_name"] == "report_generator"
    assert result["execution"]["status"] == "completed"
    #assert "write_report_file" in result["execution"]["steps"]
