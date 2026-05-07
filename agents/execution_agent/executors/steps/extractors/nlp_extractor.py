import json
import os

from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from ..base_step import BaseStep, StepResult
from ...core.envelope import resolve_path


GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# Which envelope block each known field lives in.
_INTAKE_FIELDS = {"department", "task_type", "isAutonomous"}
_TASK_FIELDS = {
    "task_id", "title", "requester_name", "stated_deadline",
    "action_required", "success_criteria",
}
_PRIORITY_FIELDS = {"priority_score", "priority_label", "confidence"}

_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_MODEL_MAP: dict[str, str] = {
    "escalation_router":      "llama-3.3-70b-versatile",
    "leave_checker":          "llama-3.3-70b-versatile",
    "meeting_scheduler":      "llama-3.3-70b-versatile",
    "report_generator":       "llama3-70b-8192",
    "email_agent":            "llama3-70b-8192",
    "powerpoint_agent":       "llama3-70b-8192",
    "expense_tracker":        "llama3-70b-8192",
    "onboarding_coordinator": "llama3-70b-8192",
}

# Module-level cached client — created on first use, not at import time.
_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


class NLPExtractor(BaseStep):
    """
    Extracts named fields from the envelope.

    Resolution order for each requested field:
      1. Known block mapping  — intake / task / priority sections
      2. Accumulated step data — execution.steps.*.data (most recent wins)
      3. LLM extraction        — from envelope["raw_text"] via Groq
    """

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            fields_to_extract: list = config.get("fields_to_extract", [])
            if not fields_to_extract:
                return StepResult(success=True, data={}, error=None)

            result: dict = {}
            missing: list = []

            for field in fields_to_extract:
                value = self._resolve_from_envelope(field, envelope)
                if value is not None:
                    result[field] = value
                else:
                    missing.append(field)

            if missing:
                llm_values = self._extract_via_llm(missing, envelope)
                result.update(llm_values)

            return StepResult(success=True, data=result, error=None)

        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_from_envelope(field: str, envelope: dict):
        """Try known block mapping first, then accumulated step data."""
        if field in _INTAKE_FIELDS:
            value = envelope.get("intake", {}).get(field)
            if value is not None:
                return value

        if field in _TASK_FIELDS:
            value = envelope.get("task", {}).get(field)
            if value is not None:
                return value

        if field in _PRIORITY_FIELDS:
            value = envelope.get("priority", {}).get(field)
            if value is not None:
                return value

        # Walk accumulated step data via resolve_path — most recent step wins.
        step_names = list(envelope.get("execution", {}).get("steps", {}).keys())
        for step_name in reversed(step_names):
            try:
                return resolve_path(envelope, f"execution.steps.{step_name}.data.{field}")
            except KeyError:
                continue

        # Fallback: check task block for any field not in the known sets.
        value = envelope.get("task", {}).get(field)
        if value is not None:
            return value

        return None

    def _extract_via_llm(self, fields: list, envelope: dict) -> dict:
        """Call LLM to extract fields not found in the envelope blocks."""
        raw_text = envelope.get("raw_text", "")
        if not raw_text:
            return {f: None for f in fields}

        fields_str = ", ".join(fields)
        prompt = (
            f"Extract the following fields from the text: {fields_str}.\n"
            "Return a valid JSON object with exactly those keys. "
            "Use null for any field that cannot be determined.\n\n"
            f"Text:\n{raw_text}"
        )

        agent_name = envelope.get("execution", {}).get("agent_name", "")
        model = _MODEL_MAP.get(agent_name, _DEFAULT_MODEL)

        response = _get_client().chat.completions.create(
            model=model,
            max_tokens=512,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise office automation assistant. "
                        "Follow instructions exactly and be concise."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if the model wraps output in them.
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {f: parsed.get(f) for f in fields}
        except json.JSONDecodeError:
            pass

        return {f: None for f in fields}
