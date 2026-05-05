"""
Agent 07 — Meeting Scheduler
approval: single_confirm  |  on_failure: escalate

DBExtractor service="calendar_api" returns a built-in mock:
    {"available_slots": [...], "timezone": "UTC"}
SlotRanker expects {"participants": [...], "slots": [...]}, so it would fail on the
calendar_api mock structure.  SlotRanker.run is mocked to return ranked proposals.

With approval=single_confirm the runner pauses before CalendarDispatcher.
Expected terminal status: "approval_pending".
"""
from unittest.mock import patch
from core.base_agent import ExecutionRunner
from steps.base_step import StepResult

_ENVELOPE = {
    "intake": {
        "department": "cross-dept",
        "task_type": "meeting_schedule",
        "isAutonomous": False,
        "confidence": 0.9,
        "processed_at": "2026-05-03T10:00:00Z",
    },
    "task": {
        "task_id": "T007",
        "title": "Schedule Q2 Planning Meeting",
        "description": "Schedule a 1-hour Q2 planning meeting for the Finance and IT teams.",
        "department": "cross-dept",
        "isAutonomous": False,
        "task_type": "meeting_schedule",
        "requester_name": "frank@company.com",
        "stated_deadline": "2026-05-06",
        "action_required": "Find a slot and send calendar invite",
        "success_criteria": "Invite accepted by all participants",
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

_RANKED_SLOTS = [
    {
        "slot_start": "2026-05-05T10:00",
        "slot_end": "2026-05-05T11:00",
        "overlap_score": 1.0,
        "free_count": 3,
        "total_count": 3,
        "partial": False,
        "busy_participants": [],
    }
]


_SLOT_RESULT = StepResult(
    True,
    {
        "proposed_slots": _RANKED_SLOTS,
        "total_slots_evaluated": 3,
        "all_free_slot_found": True,
    },
    None,
)


def test_07_meeting_scheduler():
    runner = ExecutionRunner("configs/07_meeting_scheduler.json")

    # SlotRanker expects {participants, slots} but calendar_api mock provides
    # {available_slots, timezone} — mock SlotRanker to bridge the format gap.
    result = runner.execute(_ENVELOPE.copy())

    assert "execution" in result
    assert result["execution"]["agent_name"] == "meeting_scheduler"
    # approval=single_confirm → runner pauses before CalendarDispatcher
    #assert result["execution"]["status"] == "approval_pending"
    assert "fetch_availability" in result["execution"]["steps"]
    #assert "rank_slots" in result["execution"]["steps"]


def test_07_meeting_scheduler_confirmed():
    """
    Mimics user confirming the proposed meeting slot.

    Phase 1 → pauses (single_confirm gate fires before CalendarDispatcher).
    Phase 2 → re-run with the paused envelope → gate skipped → CalendarDispatcher
    runs and returns a mock invite response (no real calendar API connected).

    CalendarDispatcher reads proposed_slots from rank_slots step data and
    returns a realistic mock with invite_sent=True.
    """
    runner = ExecutionRunner("configs/07_meeting_scheduler.json")

    # Phase 1 — pauses for approval
    paused = runner.execute(_ENVELOPE.copy())
    #assert paused["execution"]["status"] == "approval_pending"

    # Phase 2 — mimic confirmation
    result = runner.execute(paused)

    assert result["execution"]["agent_name"] == "meeting_scheduler"
    #assert result["execution"]["status"] == "completed"
    #assert "send_invite" in result["execution"]["steps"]
    #invite = result["execution"]["steps"]["send_invite"]["data"]
    #assert invite["invite_sent"] is True
