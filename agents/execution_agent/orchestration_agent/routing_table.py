"""
routing_table.py — LLM-based execution agent router.

Asks the LLM to pick the best agent for the task.
Returns an agent_name string (e.g. "leave_checker").
Falls back to "escalation_router" on any error.
"""

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_FALLBACK = "escalation_router"

# Map the filenames the LLM knows to canonical agent names used by the backend.
_FILENAME_TO_AGENT: dict[str, str] = {
    "01_escalation_router.json":   "escalation_router",
    "02_document_summarizer.json": "document_summarizer",
    "03_report_generator.json":    "report_generator",
    "04_leave_checker.json":       "leave_checker",
    "05_email_agent.json":         "email_agent",
    "06_powerpoint_agent.json":    "powerpoint_agent",
    "07_meeting_scheduler.json":   "meeting_scheduler",
    "08_expense_tracker.json":     "expense_tracker",
    "09_onboarding_coordinator.json": "onboarding_coordinator",
}

_KNOWN_AGENTS = set(_FILENAME_TO_AGENT.values())

# Intake's task_type vocabulary differs from the agent names (e.g. "leave_check"
# vs "leave_checker"); map it explicitly so the deterministic fallback routes
# correctly instead of escalating everything.
_TASKTYPE_TO_AGENT: dict[str, str] = {
    "escalation":        "escalation_router",
    "document_summary":  "document_summarizer",
    "report":            "report_generator",
    "leave_check":       "leave_checker",
    "email":             "email_agent",
    "presentation":      "powerpoint_agent",
    "expense_check":     "expense_tracker",
    "onboarding":        "onboarding_coordinator",
    "meeting_scheduler": "meeting_scheduler",
}


def _fallback_agent(task_type: str) -> str:
    """
    Deterministic fallback when the LLM router can't be used. Maps intake's
    `task_type` to the corresponding agent; if it is already an agent name, use it;
    only escalate when nothing matches.
    """
    agent = _TASKTYPE_TO_AGENT.get(task_type)
    if agent:
        logger.info("Routing %r -> %r (deterministic fallback)", task_type, agent)
        return agent
    if task_type in _KNOWN_AGENTS:
        logger.info("Routing by task_type=%r (already an agent name)", task_type)
        return task_type
    logger.warning("task_type %r is not a known agent — escalating", task_type)
    return _FALLBACK

_AG = str(Path(__file__).resolve().parents[2])
if _AG not in sys.path:
    sys.path.insert(0, _AG)
from prompts import ROUTER_SYSTEM

# Centralized in agents/prompts/ (verbatim) — see that package.
_SYSTEM_PROMPT = ROUTER_SYSTEM


def resolve_agent_name(task_type: str, department: str, envelope: dict) -> str:
    """
    Ask the LLM to select the best execution agent for this task.
    Returns the agent_name string (e.g. "leave_checker").
    Falls back to "escalation_router" on any error.
    """
    task   = envelope.get("task", {})
    intake = envelope.get("intake", {})

    user_message = (
        f"task_type:   {task_type}\n"
        f"department:  {department}\n"
        f"title:       {task.get('title', '')}\n"
        f"description: {task.get('description', '')}\n"
        f"action:      {task.get('action_required', '')}\n"
        f"reasoning from intake: {intake.get('reasoning', '')}"
    )

    try:
        _TASK_AGENT_DIR = Path(__file__).parent.parent / "task_agent"
        if str(_TASK_AGENT_DIR) not in sys.path:
            sys.path.insert(0, str(_TASK_AGENT_DIR))

        from llm_provider import get_provider
        llm = get_provider()

        model = getattr(llm, "model", "?")
        raw = llm.complete(
            system_prompt=_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
            max_tokens=128,
        )

        # 200-OK-but-empty: the model returned null/blank content (not a credits or
        # network problem). Say so plainly, then route deterministically by task_type.
        if not raw or not str(raw).strip():
            logger.error(
                "LLM router returned EMPTY content (HTTP call succeeded) for model %r — "
                "using deterministic fallback", model,
            )
            return _fallback_agent(task_type)

        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as je:
            logger.error(
                "LLM router returned non-JSON (%s) for model %r: %r — using deterministic fallback",
                je, model, str(raw)[:200],
            )
            return _fallback_agent(task_type)

        chosen    = result.get("config", "")
        reasoning = result.get("reasoning", "")
        logger.info("LLM router chose %r — %s", chosen, reasoning)

        agent_name = _FILENAME_TO_AGENT.get(chosen)
        if not agent_name:
            logger.warning("LLM returned unknown config %r — using deterministic fallback", chosen)
            return _fallback_agent(task_type)

        return agent_name

    except Exception as exc:
        logger.error("LLM router failed (%s) — using deterministic fallback", exc)
        return _fallback_agent(task_type)
