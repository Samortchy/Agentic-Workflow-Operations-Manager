from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from envelope import Envelope, TaskSection
from llm_provider import LLMProvider

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are the Task Structuring Agent in an autonomous office workflow system.

Your job is EXTRACTION ONLY — not classification.

Return EXACTLY this JSON schema:

{
  "title": "<3-8 word summary>",
  "description": "<full description>",
  "requester_name": "<name or 'unknown'>",
  "stated_deadline": "<deadline or 'none stated'>",
  "action_required": "<single sentence verb>",
  "success_criteria": "<observable success>"
}

Return JSON only.
""".strip()


class TaskStructuringAgent:

    AGENT_NAME = "task_structuring"

    def __init__(
        self,
        llm: LLMProvider,
        confidence_threshold: float = 0.60,
    ):
        self.llm = llm
        self.confidence_threshold = confidence_threshold

    # ------------------------------------------------------------------

    def run(self, envelope: Envelope) -> Envelope:

        logger.info(
            "[%s] Processing envelope %s",
            self.AGENT_NAME,
            envelope.envelope_id,
        )

        # Intake required
        if envelope.intake is None:
            msg = "Missing intake section"
            envelope.add_error(self.AGENT_NAME, msg)
            return envelope

        # Prevent overwrite (append-only contract)
        if envelope.task is not None:
            logger.warning(
                "[%s] Task already exists — skipping",
                self.AGENT_NAME,
            )
            return envelope

        # Confidence warning
        if envelope.intake.confidence < self.confidence_threshold:
            logger.warning(
                "[%s] Low intake confidence %.2f",
                self.AGENT_NAME,
                envelope.intake.confidence,
            )

        try:

            extracted = self._call_llm(
                raw_text=envelope.raw_text,
                intake=envelope.intake,
            )

            task_section = self._build_task_section(
                extracted,
                envelope,
            )

        except Exception as exc:

            logger.error(
                "[%s] Extraction failed: %s",
                self.AGENT_NAME,
                exc,
            )

            envelope.add_error(
                self.AGENT_NAME,
                str(exc),
            )

            task_section = self._fallback_task_section(
                envelope
            )

        envelope.task = task_section

        logger.info(
            "[%s] Done — task_id=%s",
            self.AGENT_NAME,
            task_section.task_id,
        )

        return envelope

    # ------------------------------------------------------------------

    def _call_llm(
        self,
        raw_text: str,
        intake,
    ) -> dict:

        user_message = json.dumps(
            {
                "raw_text": raw_text,
                "department": intake.department,
                "task_type": intake.task_type,
            }
        )

        # First attempt
        response_text = self.llm.complete(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.2,
        )

        parsed = self._parse_json(response_text)

        if parsed is not None:
            return parsed

        # Retry deterministic
        logger.warning(
            "[%s] Malformed JSON — retrying",
            self.AGENT_NAME,
        )

        response_text = self.llm.complete(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
        )

        parsed = self._parse_json(response_text)

        if parsed is not None:
            return parsed

        raise ValueError(
            "LLM returned malformed JSON after retry"
        )

    # ------------------------------------------------------------------

    def _parse_json(
        self,
        text: str,
    ) -> Optional[dict]:

        cleaned = text.strip()

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(
                line
                for line in lines
                if not line.strip().startswith("```")
            ).strip()

        try:
            data = json.loads(cleaned)

            if not isinstance(data, dict):
                return None

            return data

        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------

    def _build_task_section(
        self,
        extracted: dict,
        envelope: Envelope,
    ) -> TaskSection:

        required_keys = {
            "title",
            "description",
            "requester_name",
            "stated_deadline",
            "action_required",
            "success_criteria",
        }

        missing = required_keys - extracted.keys()
        unexpected = set(extracted.keys()) - required_keys

        if missing:
            logger.warning(
                "[%s] Missing keys: %s",
                self.AGENT_NAME,
                missing,
            )

        if unexpected:
            logger.warning(
                "[%s] Unexpected keys: %s",
                self.AGENT_NAME,
                unexpected,
            )

        intake = envelope.intake

        return TaskSection(

            task_id=f"TASK-{uuid.uuid4().hex[:6].upper()}",

            title=extracted.get(
                "title",
                "Untitled task",
            ).strip(),

            description=extracted.get(
                "description",
                envelope.raw_text,
            ).strip(),

            department=intake.department,

            is_autonomous=intake.is_autonomous,

            task_type=intake.task_type,

            requester_name=extracted.get(
                "requester_name",
                "unknown",
            ).strip(),

            stated_deadline=extracted.get(
                "stated_deadline",
                "none stated",
            ).strip(),

            action_required=extracted.get(
                "action_required",
                f"Handle {intake.task_type.replace('_', ' ')} request",
            ).strip(),

            success_criteria=extracted.get(
                "success_criteria",
                "Task resolved successfully",
            ).strip(),

            structured_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

    # ------------------------------------------------------------------

    def _fallback_task_section(
        self,
        envelope: Envelope,
    ) -> TaskSection:

        intake = envelope.intake

        return TaskSection(

            task_id=f"TASK-{uuid.uuid4().hex[:6].upper()}",

            title="Request requires manual review",

            description=envelope.raw_text,

            department=intake.department,

            is_autonomous=False,

            task_type=intake.task_type,

            requester_name="unknown",

            stated_deadline="none stated",

            action_required=f"Handle {intake.task_type.replace('_', ' ')} request",

            success_criteria="Task verified by human reviewer",

            structured_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )