import json
import os
from openai import OpenAI
from steps.base_step import BaseStep, StepResult


OPENROUTER_API_KEY = os.environ.get("OPEN_ROUTER_KEY")
_BASE_URL = "https://openrouter.ai/api/v1"

# Model selected per agent; document_summarizer is handled separately (see _select_model).
# All models use the :free tier confirmed via OpenRouter API (May 2026).
_MODEL_MAP: dict[str, str] = {
    "escalation_router":      "meta-llama/llama-3.3-70b-instruct:free",
    "report_generator":       "openai/gpt-oss-120b:free",
    "leave_checker":          "meta-llama/llama-3.3-70b-instruct:free",
    "email_agent":            "nousresearch/hermes-3-llama-3.1-405b:free",
    "powerpoint_agent":       "nousresearch/hermes-3-llama-3.1-405b:free",
    "meeting_scheduler":      "meta-llama/llama-3.3-70b-instruct:free",
    "expense_tracker":        "openai/gpt-oss-120b:free",
    "onboarding_coordinator": "nousresearch/hermes-3-llama-3.1-405b:free",
}
_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

# Named prompt library — keys match the prompt_template values in agent configs.
_PROMPTS = {
    "summarise_chunk": (
        "Summarise the following document chunk concisely. "
        "Retain key facts, decisions, and action items. Omit filler text.\n\n"
        "Chunk:\n{text}"
    ),
    "reduce_summaries": (
        "Merge these partial summaries into one coherent, concise final summary.\n\n"
        "Partial summaries:\n{summaries}"
    ),
    "extract_entities": (
        "Extract the following entities from the text: {fields}.\n"
        "Return a valid JSON object with exactly those keys. Use null for any not found.\n\n"
        "Text:\n{text}"
    ),
    "summarise_attachment": (
        "Summarise the document referenced in this task. "
        "Focus on the main request, key figures, and deadlines.\n\n"
        "Task description:\n{description}\n\nRaw text:\n{raw_text}"
    ),
    "draft_email_reply": (
        "Draft a professional email reply for the following request. "
        "Tone: {tone}.\n\n"
        "Task description:\n{description}\n"
        "Requester: {requester_name}\n\n"
        "Return only the email body — no subject line."
    ),
    "self_rate_confidence": (
        "You just drafted this email reply:\n{draft_reply}\n\n"
        "Rate your confidence that this reply is correct, complete, and appropriate "
        "on a scale from 0.0 to 1.0.\n"
        "Return only valid JSON: {{\"confidence_score\": <float>}}"
    ),
    "generate_report": (
        "Generate a professional report using the data below.\n\n"
        "Report type: {report_type}\n"
        "Department: {department}\n"
        "Date range: {date_range}\n\n"
        "Data:\n{metrics}\n\n"
        "Structure the report with clear sections and return the full report text."
    ),
}


class LLMGenerator(BaseStep):
    """
    Processor that calls an LLM via OpenRouter and generates or transforms text.

    Model is selected per agent name read from envelope.execution.agent_name.
    For document_summarizer the map step uses Gemini and the reduce step uses DeepSeek.

    Strategies (config.strategy):
      single_pass  — builds one prompt from the envelope, calls LLM once.
      map_reduce   — maps LLM over chunks from a prior step, then reduces.

    Config fields
    -------------
    prompt_template : str   Key into _PROMPTS (required).
    strategy        : str   "single_pass" | "map_reduce"  (default: "single_pass").
    temperature     : float LLM sampling temperature      (default: 0.3).
    output_field    : str   StepResult.data key for plain-text output.
                            Omit when the LLM is expected to return JSON.
    fields          : list  Entity names for the extract_entities template.
    tone_rules      : dict  Department → tone string for the draft_email_reply template.
    """

    def __init__(self):
        self._client = OpenAI(base_url=_BASE_URL, api_key=OPENROUTER_API_KEY)

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            strategy = config.get("strategy", "single_pass")
            if strategy == "map_reduce":
                return self._map_reduce(envelope, config)
            return self._single_pass(envelope, config)
        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _single_pass(self, envelope: dict, config: dict) -> StepResult:
        template_key = config.get("prompt_template", "")
        ctx = self._build_context(envelope, config)
        prompt = self._render(template_key, ctx)
        text = self._call(prompt, config, envelope, phase="main")

        parsed = _try_json(text)
        if isinstance(parsed, dict):
            return StepResult(success=True, data=parsed, error=None)

        output_field = config.get("output_field", template_key or "output")
        return StepResult(success=True, data={output_field: text}, error=None)

    def _map_reduce(self, envelope: dict, config: dict) -> StepResult:
        chunks = _find_in_steps(envelope, "chunks")
        if chunks is None:
            return StepResult(
                success=False,
                data={},
                error="map_reduce: no 'chunks' key found in any prior step's data",
            )

        summaries = [
            self._call(self._render("summarise_chunk", {"text": chunk}), config, envelope, phase="map")
            for chunk in chunks
        ]
        combined = "\n\n---\n\n".join(summaries)
        final = self._call(self._render("reduce_summaries", {"summaries": combined}), config, envelope, phase="reduce")
        return StepResult(
            success=True,
            data={"summary": final, "chunk_count": len(chunks)},
            error=None,
        )

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def _build_context(self, envelope: dict, config: dict) -> dict:
        task = envelope.get("task", {})

        # Seed with fields the prompt templates reference by name.
        ctx: dict = {
            "raw_text":       envelope.get("raw_text", ""),
            "description":    task.get("description", ""),
            "requester_name": task.get("requester_name", ""),
            "department":     task.get("department", ""),
            "report_type":    task.get("task_type", ""),
            "date_range":     task.get("stated_deadline", ""),
            "metrics":        "",
        }

        if "tone_rules" in config:
            dept = task.get("department", "")
            ctx["tone"] = config["tone_rules"].get(dept, "professional")

        if "fields" in config:
            ctx["fields"] = ", ".join(config["fields"])

        # Merge all prior step outputs so templates can reference them by field key.
        exec_steps = envelope.get("execution", {}).get("steps", {})
        for step_name, step_obj in exec_steps.items():
            data = step_obj.get("data", {})
            ctx[step_name] = data   # accessible as {step_name} in templates
            ctx.update(data)        # each field also accessible directly

        # Template-specific overrides that need a targeted lookup.
        template_key = config.get("prompt_template", "")

        if template_key == "self_rate_confidence":
            draft = exec_steps.get("draft_reply", {}).get("data", {}).get("draft_reply", "")
            ctx["draft_reply"] = draft

        if template_key == "extract_entities":
            ctx["text"] = _find_latest_text(envelope)

        return ctx

    # ------------------------------------------------------------------
    # Rendering and API call
    # ------------------------------------------------------------------

    def _render(self, key: str, ctx: dict) -> str:
        template = _PROMPTS.get(key, key)
        try:
            return template.format_map(_SafeDict(ctx))
        except Exception:
            return template

    def _select_model(self, envelope: dict, config: dict, phase: str) -> str:
        agent_name = envelope.get("execution", {}).get("agent_name", "")
        if agent_name == "document_summarizer":
            # map step → Gemma 4 31B (fast, good at extraction)
            # reduce + entity steps → GPT-OSS 120B (stronger synthesis)
            if phase == "map" or config.get("prompt_template") == "summarise_chunk":
                return "google/gemma-4-31b-it:free"
            return "openai/gpt-oss-120b:free"
        return _MODEL_MAP.get(agent_name, _DEFAULT_MODEL)

    def _call(self, prompt: str, config: dict, envelope: dict, phase: str = "main") -> str:
        model = self._select_model(envelope, config, phase)
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=2048,
            temperature=config.get("temperature", 0.3),
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
        return response.choices[0].message.content.strip()


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _find_in_steps(envelope: dict, key: str):
    """Return the value of `key` from the most recent step that has it, or None."""
    for step_obj in reversed(list(envelope.get("execution", {}).get("steps", {}).values())):
        data = step_obj.get("data", {})
        if key in data:
            return data[key]
    return None


def _find_latest_text(envelope: dict) -> str:
    """Return the most recent text-like field from prior steps, fallback to raw_text."""
    for step_obj in reversed(list(envelope.get("execution", {}).get("steps", {}).values())):
        data = step_obj.get("data", {})
        for key in ("summary", "text", "raw_text", "content"):
            if key in data:
                return str(data[key])
    return envelope.get("raw_text", "")


def _try_json(text: str):
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    return None


class _SafeDict(dict):
    """Leaves unresolved {placeholders} intact instead of raising KeyError."""
    def __missing__(self, key):
        return f"{{{key}}}"
