import json
import logging
import os

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

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
    "report_generator":       "llama-3.3-70b-versatile",
    "email_agent":            "llama-3.3-70b-versatile",
    "powerpoint_agent":       "llama-3.3-70b-versatile",
    "expense_tracker":        "llama-3.3-70b-versatile",
    "onboarding_coordinator": "llama-3.3-70b-versatile",
}

# Module-level cached client — created on first use, not at import time.
_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


_or_client = None


def _get_openrouter():
    global _or_client
    if _or_client is None:
        from openai import OpenAI
        _or_client = OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            timeout=30.0, max_retries=0,
        )
    return _or_client


def _chat(messages, model, temperature=0.0, max_tokens=512):
    """Call Groq; on any failure or empty response, fall back to OpenRouter so a
    Groq outage or a decommissioned model never breaks extraction."""
    try:
        resp = _get_client().chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
        content = (resp.choices[0].message.content if resp.choices else None) or ""
        if content.strip():
            return content
        raise RuntimeError("empty Groq response")
    except Exception as e:
        logger.warning("Groq call failed (%s) — falling back to OpenRouter", e)
        resp = _get_openrouter().chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct", messages=messages,
            temperature=temperature, max_tokens=max_tokens)
        return (resp.choices[0].message.content if resp.choices else None) or ""


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
        # Time-awareness: if a ClockChecker step ran, give the model the current
        # date/time so it can resolve relative dates (e.g. "next Tuesday").
        now = self._resolve_from_envelope("current_datetime", envelope)
        time_line = (f"Current date and time: {now}. Resolve any relative dates "
                     f"(e.g. 'next Tuesday', 'tomorrow') against this.\n") if now else ""
        prompt = (
            f"Extract the following fields from the text: {fields_str}.\n"
            "Return a valid JSON object with exactly those keys. "
            "Use null for any field that cannot be determined.\n"
            f"{time_line}\n"
            f"Text:\n{raw_text}"
        )

        agent_name = envelope.get("execution", {}).get("agent_name", "")
        model = _MODEL_MAP.get(agent_name, _DEFAULT_MODEL)

        messages = [
            {"role": "system", "content": (
                "You are a precise office automation assistant. "
                "Follow instructions exactly and be concise.")},
            {"role": "user", "content": prompt},
        ]
        raw = _chat(messages, model).strip()

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
