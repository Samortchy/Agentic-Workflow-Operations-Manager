# core/approval_gate.py
# FROZEN — do not modify without full team review and a change log entry in spec.md
#
# The approval gate is NOT a step. It fires automatically before the first
# dispatcher step runs, based on the top-level `approval` field in the config.
# No agent config needs to explicitly include it — the runner calls it.
#
# Spec reference: section 6.3

from datetime import datetime, timezone


# ── Allowed approval values (spec section 5.3) ────────────────────────────────
ALLOWED_APPROVAL_VALUES = {
    "none",
    "single_confirm",
    "single_confirm_if_low_confidence",
    "manager_sign_off",
}

# Confidence threshold default — used when config does not specify one
_DEFAULT_CONFIDENCE_THRESHOLD = 85


def check(envelope: dict, agent_config: dict) -> dict:
    """
    Evaluates the approval mode and decides whether execution should pause.

    Parameters
    ----------
    envelope     : the full current envelope dict (will NOT be modified here —
                   the runner applies the returned patch)
    agent_config : the full agent config dict (top-level, not a step config)

    Returns
    -------
    A dict with two keys:
      "pause"  : bool   — True if the runner must pause and wait for a signal
      "status" : str    — the status value to write to execution.status if pausing
                          (one of the allowed values from spec 3.3)
                          None if not pausing.
      "action" : str    — human-readable description of what the gate did,
                          written to execution.steps for traceability.
    """
    approval = agent_config.get("approval", "none")

    if approval not in ALLOWED_APPROVAL_VALUES:
        # Treat unknown approval values as a hard gate — safer than ignoring
        return _pause(
            status="failed",
            action=f"approval_gate: unknown approval value '{approval}' — execution blocked"
        )

    # ── none ──────────────────────────────────────────────────────────────────
    if approval == "none":
        return _no_pause(action="approval_gate: approval=none, continuing")

    # ── single_confirm ────────────────────────────────────────────────────────
    if approval == "single_confirm":
        return _pause(
            status="approval_pending",
            action="approval_gate: waiting for user confirmation in UI"
        )

    # ── single_confirm_if_low_confidence ──────────────────────────────────────
    if approval == "single_confirm_if_low_confidence":
        threshold = agent_config.get("confidence_threshold", _DEFAULT_CONFIDENCE_THRESHOLD)

        # Read draft_confidence from execution.result — spec section 6.3
        try:
            draft_confidence = (
                envelope
                .get("execution", {})
                .get("result", {})
                .get("draft_confidence")
            )
        except Exception:
            draft_confidence = None

        if draft_confidence is None:
            # Cannot evaluate — treat as low confidence, pause to be safe
            return _pause(
                status="approval_pending",
                action=(
                    "approval_gate: draft_confidence not found in execution.result "
                    "— pausing as a precaution"
                )
            )

        if draft_confidence < threshold:
            return _pause(
                status="approval_pending",
                action=(
                    f"approval_gate: draft_confidence {draft_confidence} "
                    f"is below threshold {threshold} — waiting for user confirmation"
                )
            )
        else:
            return _no_pause(
                action=(
                    f"approval_gate: draft_confidence {draft_confidence} "
                    f">= threshold {threshold}, continuing"
                )
            )

    # ── manager_sign_off ──────────────────────────────────────────────────────
    if approval == "manager_sign_off":
        return _pause(
            status="approval_pending",
            action=(
                "approval_gate: manager sign-off required — "
                "approval email dispatched, waiting for reply"
            )
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _pause(status: str, action: str) -> dict:
    return {
        "pause":     True,
        "status":    status,
        "action":    action,
        "fired_at":  _now(),
    }


def _no_pause(action: str) -> dict:
    return {
        "pause":    False,
        "status":   None,
        "action":   action,
        "fired_at": _now(),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()