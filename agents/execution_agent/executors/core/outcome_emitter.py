import logging
from . import backend_client as bc

logger = logging.getLogger(__name__)


def emit(envelope: dict, task_id: str | None = None, company_id: str | None = None) -> None:
    """
    Emit an outcome signal to the backend after all execution steps complete.
    Falls back to logging if the backend call fails.
    """
    execution  = envelope.get("execution", {})
    agent_name = execution.get("agent_name", "unknown")
    status     = execution.get("status", "unknown")

    signal_type = f"{agent_name}.{status}"
    value = {
        "agent_version": execution.get("agent_version"),
        "started_at":    execution.get("started_at"),
        "completed_at":  execution.get("completed_at"),
        "error_count":   len(execution.get("errors", [])),
    }

    tid = task_id or envelope.get("task", {}).get("task_id") or envelope.get("_ctx", {}).get("task_id")
    cid = company_id or envelope.get("_ctx", {}).get("company_id") or bc.get_company_id()

    if tid:
        try:
            bc.create_outcome_signal(
                task_id=tid,
                signal_type=signal_type,
                value=value,
                company_id=cid,
            )
            logger.info("[OUTCOME_SIGNAL] %s | task=%s | status=%s", agent_name, tid, status)
            return
        except Exception as e:
            logger.warning("Failed to emit outcome signal to backend: %s", e)

    # Fallback — no task_id or backend unavailable
    logger.info("[OUTCOME_SIGNAL] %s (%s) | status=%s", agent_name, execution.get("agent_version"), status)
