"""
slot_ranker.py
Custom step — Meeting Scheduler (Agent 07)
P5 responsibility

What it does:
    Receives calendar availability data fetched by the preceding DBExtractor step.
    Scores each available time slot by participant overlap — how many of the required
    participants are free for that slot. Returns the top N ranked proposals.

    Scoring logic:
        overlap_score = free_participants / total_participants
        Slots are ranked descending by overlap_score.
        Ties are broken by time of day preference (earlier in working hours = higher rank).
        Slots with overlap_score < 1.0 are included but marked as partial.
        Only slots with at least one free participant are returned.

Returns:
    StepResult.data = {
        "proposed_slots": list[dict],   # ranked, max length = config.max_proposals
        "total_slots_evaluated": int,
        "all_free_slot_found": bool,    # True if any slot has overlap_score == 1.0
    }

    Each slot dict:
        {
            "slot_start":      "ISO8601",
            "slot_end":        "ISO8601",
            "overlap_score":   float,       # 0.0 – 1.0
            "free_count":      int,
            "total_count":     int,
            "partial":         bool,        # True if overlap_score < 1.0
            "busy_participants": list[str], # names of participants who are busy
        }

Spec compliance:
    - Inherits BaseStep
    - run() signature: (self, envelope: dict, config: dict) -> StepResult
    - Never raises — all exceptions caught and returned as StepResult(success=False)
    - Never modifies envelope directly
    - Never adds fields to StepResult
    - Never writes to SQLite — runner does that
    - Uses resolve_path() from core.envelope for all envelope reads
"""

from datetime import datetime
from ..base_step import BaseStep, StepResult
from ...core.envelope import resolve_path


class SlotRanker(BaseStep):

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            # ── 1. Read config ────────────────────────────────────────────
            max_proposals         = config.get("max_proposals", 3)
            scoring               = config.get("scoring", "participant_overlap")
            preferred_hour_start  = config.get("preferred_hour_start", 9)   # 9 AM
            preferred_hour_end    = config.get("preferred_hour_end",   17)  # 5 PM

            # ── 2. Read availability data from previous extractor step ────
            # The DBExtractor step named "fetch_availability" produced this.
            # Shape expected:
            #   {
            #     "participants": ["Ali", "Ismail", "Menna"],
            #     "slots": [
            #       {
            #         "slot_start": "ISO8601",
            #         "slot_end":   "ISO8601",
            #         "availability": {
            #           "Ali": true, "Ismail": false, "Menna": true
            #         }
            #       },
            #       ...
            #     ]
            #   }
            availability_data = resolve_path(
                envelope,
                "execution.steps.fetch_availability.data"
            )

            participants = availability_data.get("participants", [])
            slots        = availability_data.get("slots", [])

            if not participants:
                return StepResult(
                    success=False,
                    data={},
                    error="SlotRanker: no participants found in availability data."
                )

            if not slots:
                return StepResult(
                    success=False,
                    data={},
                    error="SlotRanker: no time slots found in availability data."
                )

            total_participants = len(participants)

            # ── 3. Score each slot ────────────────────────────────────────
            scored_slots = []
            for slot in slots:
                availability = slot.get("availability", {})
                slot_start   = slot.get("slot_start", "")
                slot_end     = slot.get("slot_end", "")

                free_participants = [
                    p for p in participants
                    if availability.get(p, False) is True
                ]
                busy_participants = [
                    p for p in participants
                    if availability.get(p, False) is False
                ]

                free_count    = len(free_participants)
                overlap_score = free_count / total_participants if total_participants > 0 else 0.0

                # Skip slots where nobody is free
                if free_count == 0:
                    continue

                # Tiebreaker: prefer slots earlier in the working day
                # Lower tiebreaker_score = higher preference
                tiebreaker = self._working_hour_tiebreaker(
                    slot_start, preferred_hour_start, preferred_hour_end
                )

                scored_slots.append({
                    "slot_start":        slot_start,
                    "slot_end":          slot_end,
                    "overlap_score":     round(overlap_score, 4),
                    "free_count":        free_count,
                    "total_count":       total_participants,
                    "partial":           overlap_score < 1.0,
                    "busy_participants": busy_participants,
                    "_tiebreaker":       tiebreaker,   # internal — stripped before output
                })

            # ── 4. Rank — descending overlap_score, ascending tiebreaker ─
            scored_slots.sort(
                key=lambda s: (-s["overlap_score"], s["_tiebreaker"])
            )

            # ── 5. Take top N, strip internal tiebreaker field ───────────
            top_slots = []
            for s in scored_slots[:max_proposals]:
                s_clean = {k: v for k, v in s.items() if k != "_tiebreaker"}
                top_slots.append(s_clean)

            all_free_slot_found = any(
                s["overlap_score"] == 1.0 for s in top_slots
            )

            return StepResult(
                success=True,
                data={
                    "proposed_slots":        top_slots,
                    "total_slots_evaluated": len(scored_slots),
                    "all_free_slot_found":   all_free_slot_found,
                },
                error=None
            )

        except KeyError as e:
            return StepResult(
                success=False,
                data={},
                error=(
                    f"SlotRanker could not find required envelope path: {e}. "
                    f"Ensure 'fetch_availability' step ran successfully before this step."
                )
            )
        except Exception as e:
            return StepResult(
                success=False,
                data={},
                error=f"SlotRanker unexpected error: {str(e)}"
            )

    # ── private helpers ───────────────────────────────────────────────────────

    def _working_hour_tiebreaker(
        self,
        slot_start: str,
        preferred_hour_start: int,
        preferred_hour_end: int
    ) -> float:
        """
        Returns a float tiebreaker score for sorting.
        Slots that start within working hours and earlier in the day
        get a lower score (= higher preference).

        Outside working hours gets a penalty of 100 to push them to the bottom
        of same-overlap-score groups.
        """
        try:
            dt   = datetime.fromisoformat(slot_start)
            hour = dt.hour + dt.minute / 60.0

            if preferred_hour_start <= hour < preferred_hour_end:
                return hour                      # earlier in working day = better
            else:
                return 100.0 + hour              # outside working hours = penalised
        except Exception:
            return 999.0                         # unparseable = lowest preference