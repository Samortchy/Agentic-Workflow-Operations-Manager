import os

from dotenv import load_dotenv
load_dotenv()

from ..base_step import BaseStep, StepResult


# Step data keys that carry scheduling outputs from prior steps.
_SLOT_KEYS        = ("proposed_slots", "selected_slot", "available_slots")
_PARTICIPANT_KEYS = ("participant_names", "participants", "attendees")


class CalendarDispatcher(BaseStep):
    """
    Mock calendar invite dispatcher (Phase 2 — no real Outlook/GCal API).

    Reads proposed slots and participant lists from prior step data and
    returns a realistic mock response so the pipeline can continue.

    Config fields
    -------------
    monitor_rsvp : bool   Whether to track RSVPs (stored in result, not acted on).
    template     : str    Email template path (informational, not rendered here).
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            steps = envelope.get("execution", {}).get("steps", {})

            selected_slot: str | None = None
            participants:  list       = []

            for step_obj in reversed(list(steps.values())):
                data = step_obj.get("data", {})

                if selected_slot is None:
                    # Prefer an explicitly selected slot; fall back to first proposed.
                    selected_slot = data.get("selected_slot")
                    if selected_slot is None:
                        slots = data.get("proposed_slots") or data.get("available_slots")
                        if slots and isinstance(slots, list) and slots:
                            selected_slot = slots[0]

                if not participants:
                    for key in _PARTICIPANT_KEYS:
                        raw = data.get(key)
                        if raw:
                            participants = raw if isinstance(raw, list) else [raw]
                            break

                if selected_slot and participants:
                    break

            return StepResult(
                success=True,
                data={
                    "invite_sent":   True,
                    "selected_slot": selected_slot or "TBD",
                    "participants":  participants,
                    "monitor_rsvp":  config.get("monitor_rsvp", False),
                    "note":          "Calendar API not connected — mock response",
                },
                error=None,
            )

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))
