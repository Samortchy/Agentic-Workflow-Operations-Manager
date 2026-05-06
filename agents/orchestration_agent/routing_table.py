"""
routing_table.py — LLM-based execution agent router.

Sends the task context to an LLM with a menu of all available agents and asks
it to pick the best match. Falls back to the escalation router on any failure.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIGS_DIR = (
    Path(__file__).parent.parent
    / "execution_agent"
    / "executors"
    / "configs"
)

# All valid config filenames — used to validate the LLM's response
_VALID_CONFIGS = {
    "01_escalation_router.json",
    "02_document_summarizer.json",
    "03_report_generator.json",
    "04_leave_checker.json",
    "05_email_agent.json",
    "06_powerpoint_agent.json",
    "07_meeting_scheduler.json",
    "08_expense_tracker.json",
    "09_onboarding_coordinator.json",
}

_SYSTEM_PROMPT = """
You are a routing agent for an autonomous office workflow system.
Your only job is to select the best execution agent for the given task.

Available agents:

1. 01_escalation_router.json
   Escalates tasks to the right human reviewer via email.
   Use for: urgent issues, critical incidents, anything that needs manager sign-off.

2. 02_document_summarizer.json
   Summarises documents using a map-reduce strategy.
   Use for: document digests, file summaries, attachment summarisation.

3. 03_report_generator.json
   Generates formatted reports from data and metrics.
   Use for: report generation, analytics summaries, budget overviews, KPI reports.

4. 04_leave_checker.json
   Looks up employee leave balance and answers leave-related questions.
   Use for: leave balance checks, PTO inquiries, annual leave questions.

5. 05_email_agent.json
   Drafts and sends email replies.
   Use for: email replies, FAQ answers, IT confirmations (password reset, access requests, software info).

6. 06_powerpoint_agent.json
   Generates PowerPoint (.pptx) presentation files from an LLM-produced slide spec.
   Use for: slide decks, strategy presentations, pitch decks, board packs.

7. 07_meeting_scheduler.json
   Books meetings and sends calendar invites.
   Use for: scheduling meetings, interview slots, calendar bookings.

8. 08_expense_tracker.json
   Tracks and reports on expense submissions.
   Use for: expense status checks, reimbursement inquiries, expense report requests.

9. 09_onboarding_coordinator.json
   Coordinates new-hire onboarding workflows.
   Use for: onboarding information requests, new employee setup, onboarding process questions.

Return ONLY a JSON object with exactly these two fields:
{
  "config": "<filename>.json",
  "reasoning": "<one sentence explaining your choice>"
}

If absolutely no agent fits, set "config" to null.
Return JSON only — no markdown, no extra text.
""".strip()


def resolve_config(task_type: str, department: str, envelope: dict) -> Path | None:
    """
    Ask the LLM to select the best execution agent for this task.
    Returns the absolute Path to the chosen config, or None if the LLM
    says no agent fits (caller will fall back to escalation or review queue).
    Falls back to 01_escalation_router.json on any LLM/parse error.
    """
    # Build a compact task context for the LLM
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
        # Re-use the task_agent's OpenRouter provider (same API key, same model)
        _TASK_AGENT_DIR = Path(__file__).parent.parent / "task_agent"
        if str(_TASK_AGENT_DIR) not in sys.path:
            sys.path.insert(0, str(_TASK_AGENT_DIR))

        from llm_provider import get_provider
        llm = get_provider()

        raw = llm.complete(
            system_prompt=_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
            max_tokens=128,
        )

        result = json.loads(raw)
        chosen = result.get("config")
        reasoning = result.get("reasoning", "")

        logger.info("LLM router chose %r — %s", chosen, reasoning)

        if chosen is None:
            return None

        if chosen not in _VALID_CONFIGS:
            logger.warning(
                "LLM router returned unknown config %r — falling back to escalation", chosen
            )
            return _CONFIGS_DIR / "01_escalation_router.json"

        return _CONFIGS_DIR / chosen

    except Exception as exc:
        logger.error("LLM router failed (%s) — falling back to escalation_router", exc)
        return _CONFIGS_DIR / "01_escalation_router.json"
