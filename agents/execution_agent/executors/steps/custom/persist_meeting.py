"""
persist_meeting.py
Custom step — Meeting Scheduler (Agent 07)

Persists the scheduled meeting to the backend `meetings` table so it appears on the
dashboard schedule.

Phase-2 behaviour (Option B — auto-book): books the top-ranked slot as a CONFIRMED
meeting straight away. The human-confirm lifecycle (Option A — create as `proposed`,
flip to `confirmed` when the user approves in the dashboard) is a documented future
enhancement; it ties into the approval/resume flow (PLAN.md P1-9).

Idempotent: if a meeting already exists for this task_id, it UPDATES that row instead
of creating a duplicate (protects against worker re-processing or step re-runs).

Spec compliance: inherits BaseStep; never raises; never mutates the envelope.
"""

from ..base_step import BaseStep, StepResult
from ...core import backend_client as bc


class PersistMeeting(BaseStep):

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            task       = envelope.get("task", {})
            task_id    = task.get("task_id")
            title      = task.get("title") or "Scheduled meeting"
            organizer  = task.get("requester_email") or None
            company_id = envelope.get("_ctx", {}).get("company_id")

            proposed_slots = _find_in_steps(envelope, "proposed_slots") or []
            participants   = _find_in_steps(envelope, "participants") or []

            if not proposed_slots:
                return StepResult(
                    success=False, data={},
                    error="PersistMeeting: no proposed_slots available from SlotRanker.",
                )

            top = proposed_slots[0]
            confirmed_slot = top.get("slot_start") if isinstance(top, dict) else top

            # Idempotent: reuse an existing meeting for this task if present.
            existing = []
            if task_id:
                try:
                    all_meetings = bc.get_meetings(company_id=company_id)
                    existing = [m for m in all_meetings if m.get("task_id") == task_id]
                except Exception:
                    existing = []

            if existing:
                meeting = bc.update_meeting(existing[0]["meeting_id"], {
                    "status":         "confirmed",
                    "confirmed_slot": confirmed_slot,
                    "participants":   participants,
                    "proposed_slots": proposed_slots,
                })
            else:
                meeting = bc.create_meeting(
                    title=title,
                    participants=participants,
                    proposed_slots=proposed_slots,
                    task_id=task_id,
                    organizer_email=organizer,
                    confirmed_slot=confirmed_slot,
                    status="confirmed",
                    company_id=company_id,
                )

            return StepResult(
                success=True,
                data={
                    "meeting_id":     meeting.get("meeting_id"),
                    "status":         meeting.get("status", "confirmed"),
                    "confirmed_slot": confirmed_slot,
                    "selected_slot":  confirmed_slot,   # consumed by CalendarDispatcher
                    "participants":   participants,
                    "title":          title,
                },
                error=None,
            )

        except Exception as e:
            return StepResult(success=False, data={}, error=f"PersistMeeting error: {e}")


def _find_in_steps(envelope: dict, key: str):
    """Return `key`'s value from the most recent prior step data that contains it."""
    steps = envelope.get("execution", {}).get("steps", {})
    for step_obj in reversed(list(steps.values())):
        data = step_obj.get("data", {})
        if key in data:
            return data[key]
    return None
