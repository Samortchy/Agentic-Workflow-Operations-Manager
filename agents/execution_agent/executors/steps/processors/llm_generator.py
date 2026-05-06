import json
import os
from openai import OpenAI
from steps.base_step import BaseStep, StepResult
from core.config import OPENROUTER_API_KEY



_BASE_URL = "https://openrouter.ai/api/v1"

# Model selected per agent; document_summarizer is handled separately (see _select_model).
# All models use the :free tier confirmed via OpenRouter API (May 2026).
_MODEL_MAP: dict[str, str] = {
    "escalation_router":      "meta-llama/llama-3.3-70b-instruct",
    "report_generator":       "openai/gpt-oss-120b:free",
    "leave_checker":          "meta-llama/llama-3.3-70b-instruct",
    "email_agent":            "nousresearch/hermes-3-llama-3.1-405b",
    "powerpoint_agent":       "nousresearch/hermes-3-llama-3.1-405b",
    "meeting_scheduler":      "meta-llama/llama-3.3-70b-instruct",
    "expense_tracker":        "openai/gpt-oss-120b:free",
    "onboarding_coordinator": "nousresearch/hermes-3-llama-3.1-405b",
}
_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"

# Named prompt library — keys match the prompt_template values in agent configs.
_PROMPTS = {
    # --------------------------------------------------
    # SUMMARIZATION
    # --------------------------------------------------

    "summarise_chunk": (
        "Summarise the following document chunk concisely. "
        "Retain key facts, decisions, and action items. Omit filler text.\n"
        "Return plain text only — no JSON, no markdown, no backticks.\n\n"
        "Chunk:\n{text}"
    ),
    "reduce_summaries": (
        "Merge these partial summaries into one coherent, concise final summary.\n"
        "Return plain text only — no JSON, no markdown, no backticks.\n\n"
        "Partial summaries:\n{summaries}"
    ),

    "summarise_attachment": (
        "Summarise the document.\n\n"
        "Task:\n{description}\n\n"
        "Text:\n{raw_text}\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        "  \"type\": \"summary\",\n"
        "  \"content\": \"<summary including key facts, deadlines, figures>\",\n"
        "  \"metadata\": {},\n"
        "  \"confidence\": null\n"
        "}"
    ),

    # --------------------------------------------------
    # EXTRACTION
    # --------------------------------------------------

    "extract_entities": (
        "Extract the following entities: {fields}\n\n"
        "Text:\n{text}\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        "  \"type\": \"entities\",\n"
        "  \"content\": {\n"
        "    \"<field_name>\": \"value or null\"\n"
        "  },\n"
        "  \"metadata\": {},\n"
        "  \"confidence\": null\n"
        "}"
    ),

    # --------------------------------------------------
    # EMAILS
    # --------------------------------------------------

    "draft_email_reply": (
        "Draft a professional email reply for the following request. "
        "Tone: {tone}.\n\n"
        "Task description:\n{description}\n"
        "Requester: {requester_name}\n\n"
        "Sender name: {sender_name}\n\n"
        "Return only the email body — no subject line."),

    "draft_email_attachment": (
        "Write an email notifying the requester that their file is ready.\n\n"
        "Task: {description}\n"
        "Requester: {requester_name}\n"
        "File: {presentation_title}\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        "  \"type\": \"email\",\n"
        "  \"content\": {\n"
        "    \"body\": \"<3-4 sentence email>\"\n"
        "  },\n"
        "  \"metadata\": {},\n"
        "  \"confidence\": null\n"
        "}"
    ),

    "draft_expense_status": (
        "Write a professional email about expense report status.\n\n"
        "Task: {description}\n"
        "Requester: {requester_name}\n"
        "Details:\n{metrics}\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        "  \"type\": \"email\",\n"
        "  \"content\": {\n"
        "    \"body\": \"<concise status email>\"\n"
        "  },\n"
        "  \"metadata\": {},\n"
        "  \"confidence\": null\n"
        "}"
    ),

    "draft_report_ready": (
        "Write a professional email notifying the requester that their report is ready.\n\n"
        "Task: {description}\n"
        "Requester: {requester_name}\n"
        "Department: {department}\n"
        "Report type: {report_type}\n\n"
        "Structure the email as follows:\n"
        "- A greeting line\n"
        "- 1-2 sentences confirming the report was generated and what period it covers\n"
        "- A sentence letting them know it is attached\n"
        "- A professional sign-off\n\n"
        "No subject line. No placeholder text. Return only the email body."
    ),

  "draft_escalation_brief": (
    "Write a professional urgent escalation email notifying a reviewer that a task requires their immediate attention.\n\n"
    "Task: {description}\n"
    "Department: {department}\n"
    "Requester: {requester_name}\n"
    "Priority: {priority_label}\n\n"
    "Structure the email as follows:\n"
    "- A greeting line\n"
    "- 2-3 sentences explaining the escalation and why it needs attention\n"
    "- A clear call to action\n"
    "- A professional sign-off\n\n"
    "No subject line. No placeholder text. Return only the email body."
),
    "draft_summary_ready": (
        "Write a professional email delivering a document summary directly to the requester.\n\n"
        "Task: {description}\n"
        "Requester: {requester_name}\n"
        "Department: {department}\n"
        "Summary:\n{summary}\n\n"
        "Structure the email as follows:\n"
        "- A greeting line\n"
        "- A sentence confirming the document was processed\n"
        "- The summary content presented cleanly in the body\n"
        "- A professional sign-off\n\n"
        "No subject line. No placeholder text. Return only the email body."
    ),

    # --------------------------------------------------
    # REPORTING
    # --------------------------------------------------

        "generate_report": (
            "Generate a professional report using the data below.\n\n"
            "Report type: {report_type}\n"
            "Department: {department}\n"
            "Date range: {date_range}\n\n"
            "Data:\n{metrics}\n\n"
            "Structure the report with clear sections and return the full report text."
        ),

    # --------------------------------------------------
    # PRESENTATIONS
    # --------------------------------------------------

       "generate_slides": (
        "You are a senior presentation designer. Generate a structured PowerPoint slide deck as valid JSON.\n\n"
        "Task: {description}\n"
        "Department: {department}\n"
        "Requester: {requester_name}\n"
        "Deadline: {stated_deadline}\n\n"
        "Return ONLY a valid JSON object with this exact structure — no markdown, no explanation:\n"
        "{{\n"
        "  \"presentation_title\": \"<concise deck title>\",\n"
        "  \"theme\": {{\n"
        "    \"primary\": \"<dominant hex color e.g. 1E2761>\",\n"
        "    \"secondary\": \"<supporting hex color e.g. CADCFC>\",\n"
        "    \"accent\": \"<sharp accent hex e.g. FFFFFF>\",\n"
        "    \"title_font\": \"<header font e.g. Georgia>\",\n"
        "    \"body_font\": \"<body font e.g. Calibri>\"\n"
        "  }},\n"
        "  \"slides\": [\n"
        "    {{\n"
        "      \"title\": \"<slide title>\",\n"
        "      \"layout\": \"<title_slide | bullets | stat_callout | two_column>\",\n"
        "      \"bullet_points\": [\"<point 1>\", \"<point 2>\", \"<point 3>\"],\n"
        "      \"stat\": {{\"value\": \"<big number e.g. 12.4M>\", \"label\": \"<short label>\"}},\n"
        "      \"speaker_notes\": \"<what the presenter should say>\"\n"
        "    }}\n"
        "  ],\n"
        "  \"template_path\": \"\",\n"
        "  \"paused_for_clarification\": false\n"
        "}}\n\n"
        "Rules:\n"
        "- minimum 5 slides max 30 slides total\n"
        "- First slide: layout must be 'title_slide' — executive summary, dark background feel\n"
        "- Last slide: layout must be 'bullets' — next steps or call to action\n"
        "- Use 'stat_callout' for slides with a key metric (revenue, growth %, etc.)\n"
        "- Use 'two_column' for comparison or breakdown slides\n"
        "- 3 to 5 bullet points per slide — concise, specific, no filler\n"
        "- stat field: only populate for stat_callout layout, set to null for others\n"
        "- theme: pick colors appropriate for the department and tone (Finance = authoritative navy/slate)\n"
        "- Speaker notes should add context not already in the bullets\n"
        "- If critical information is missing set paused_for_clarification to true and put your question in the first bullet\n"
        "- Return only the JSON object. Any extra text will break the pipeline."
    ),

    # --------------------------------------------------
    # META
    # --------------------------------------------------

    "self_rate_confidence": (
        "Evaluate the following output:\n\n{draft_reply}\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        "  \"type\": \"confidence\",\n"
        "  \"content\": {\n"
        "    \"confidence_score\": <float 0-1>\n"
        "  },\n"
        "  \"metadata\": {},\n"
        "  \"confidence\": null\n"
        "}"
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

    def _select_max_tokens(self, config: dict, envelope: dict, phase: str) -> int:
        template = config.get("prompt_template", "")

        # Map-reduce phases
        if phase == "map":
            return 800
        if phase == "reduce":
            return 2000

        # Prompt-based rules
        if template == "generate_slides":
            return 3500  # large JSON output

        if template == "generate_report":
            return 3000  # long structured text

        if template == "draft_email_reply":
            return 1200  # short email

        if template == "self_rate_confidence":
            return 100  # tiny JSON

        if template == "extract_entities":
            return 300  # small JSON

        if template == "summarise_chunk":
            return 800

        if template == "reduce_summaries":
            return 2000

        # fallback
        return 2048

    def _call(self, prompt: str, config: dict, envelope: dict, phase: str = "main") -> str:
        primary_model = self._select_model(envelope, config, phase)
        fallback_model = _DEFAULT_MODEL
        max_tokens = self._select_max_tokens(config, envelope, phase)

        def make_request(model: str):
            return self._client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
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

        try:
            response = make_request(primary_model)

        except Exception as e:
            error_msg = str(e)

            # Retry only on rate limit errors
            if "429" in error_msg or "rate limit" in error_msg.lower():
                try:
                    response = make_request(fallback_model)
                except Exception as fallback_error:
                    raise RuntimeError(
                        f"Primary model rate-limited and fallback failed: {fallback_error}"
                    )
            else:
                raise RuntimeError(f"LLM call failed: {error_msg}")

        # Validate response
        if not response or not response.choices:
            raise RuntimeError("Empty response from LLM")

        message = response.choices[0].message
        if not message or not message.content:
            raise RuntimeError("LLM returned empty content")

        return message.content.strip()

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
