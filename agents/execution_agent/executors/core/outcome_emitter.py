# core/outcome_emitter.py
# FROZEN — do not modify without full team review and a change log entry in spec.md

import logging

logger = logging.getLogger(__name__)

def emit(envelope: dict) -> None:
    """
    Signals the outcome tracker with the final envelope state.
    
    This function is called by the runner loop (base_agent.py) after all steps 
    complete and the full envelope has been atomically written to SQLite.
    
    Args:
        envelope (dict): The complete envelope dict containing intake, task, 
                         priority, and execution sections.
    """
    execution = envelope.get("execution", {})
    
    # Extract key execution details to signal
    agent_name = execution.get("agent_name", "unknown")
    agent_version = execution.get("agent_version", "unknown")
    status = execution.get("status", "unknown")
    
    # Emit the outcome signal.
    # Note: As per spec.md (v1.0), the exact implementation of the outcome tracker
    # backend is not detailed (e.g., HTTP webhook, Kafka, or plain logging).
    # We log the outcome signal here.
    logger.info(
        f"[OUTCOME_SIGNAL] Agent: {agent_name} ({agent_version}) | "
        f"Status: {status}"
    )
