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

_SYSTEM_PROMPT = """
You are a routing agent for an autonomous office workflow system.
Your only job is to select the best execution agent for the given task.

Available agents:

1. 01_escalation_router.json
   Escalates tasks to a human reviewer when something has gone wrong or needs urgent approval.
   Use for: failed processes, policy violations, compliance issues, anything explicitly marked as an incident or emergency.
   Do NOT use for: report generation, presentations, summaries, scheduling, or any routine automated task.

2. 02_document_summarizer.json
   Summarises documents using a map-reduce strategy.
   Use for: document digests, file summaries, attachment summarisation, quarterly report summaries.

3. 03_report_generator.json
   Generates formatted reports from data and metrics.
   Use for: report generation, analytics summaries, budget overviews, KPI reports, finance reports.

4. 04_leave_checker.json
   Looks up employee leave balance and answers leave-related questions.
   Use for: leave balance checks, PTO inquiries, annual leave questions.

5. 05_email_agent.json
   Drafts and sends email replies.
   Use for: email replies, FAQ answers, IT confirmations (password reset, access requests, software info).

6. 06_powerpoint_agent.json
   Generates PowerPoint (.pptx) presentation files from an LLM-produced slide spec.
   Use for: slide decks, strategy presentations, pitch decks, board packs, finance reviews, leadership presentations.
   This is the correct agent whenever a .pptx or presentation file is requested, regardless of audience.

7. 07_meeting_scheduler.json
   Books meetings and sends calendar invites.
   Use for: scheduling meetings, interview slots, calendar bookings.

8. 08_expense_tracker.json
   Tracks and reports on expense submissions.
   Use for: expense status checks, reimbursement inquiries, expense report requests.

9. 09_onboarding_coordinator.json
   Coordinates new-hire onboarding workflows.
   Use for: onboarding information requests, new employee setup, onboarding process questions.

ROUTING RULES (apply in order, stop at first match):
1. Task mentions creating a presentation, slide deck, or .pptx file → 06_powerpoint_agent.json
2. Task mentions summarising a document, file, or report → 02_document_summarizer.json
3. Task mentions generating a report, KPI, analytics, or budget overview → 03_report_generator.json
4. Task mentions leave, PTO, or time off → 04_leave_checker.json
5. Task mentions drafting or sending an email → 05_email_agent.json
6. Task mentions scheduling a meeting or calendar invite → 07_meeting_scheduler.json
7. Task mentions expense, reimbursement, or cost claim → 08_expense_tracker.json
8. Task mentions onboarding, new hire, or employee setup → 09_onboarding_coordinator.json
9. Task is an explicit incident, failure, violation, or needs urgent human approval → 01_escalation_router.json
10. Nothing matches any of the above → 01_escalation_router.json

VALID CONFIG VALUES — your response MUST use one of these exactly:
- 01_escalation_router.json
- 02_document_summarizer.json
- 03_report_generator.json
- 04_leave_checker.json
- 05_email_agent.json
- 06_powerpoint_agent.json
- 07_meeting_scheduler.json
- 08_expense_tracker.json
- 09_onboarding_coordinator.json

STRICT OUTPUT RULES:
- You MUST always return a config value — never return null.
- Return ONLY this JSON object and nothing else:

{
  "config": "<one of the nine filenames above>",
  "reasoning": "<one sentence explaining your choice>"
}

No markdown. No backticks. No explanation outside the JSON.
""".strip()


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

        raw = llm.complete(
            system_prompt=_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
            max_tokens=128,
        )

        result   = json.loads(raw)
        chosen   = result.get("config", "")
        reasoning = result.get("reasoning", "")

        logger.info("LLM router chose %r — %s", chosen, reasoning)

        agent_name = _FILENAME_TO_AGENT.get(chosen)
        if not agent_name:
            logger.warning("LLM returned unknown config %r — falling back to escalation_router", chosen)
            return _FALLBACK

        return agent_name

    except Exception as exc:
        logger.error("LLM router failed (%s) — falling back to escalation_router", exc)
        return _FALLBACK
