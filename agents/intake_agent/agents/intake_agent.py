import os
import json
import time
from groq import Groq, RateLimitError
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
# max_retries=0: disable the SDK's internal retry/sleep so our own retry loop
# (with visible print output) handles 429s instead of silently blocking.
# timeout=30.0: prevent indefinite hangs on slow or stalled connections.
client = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0, timeout=30.0)

import sys
_AG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _AG not in sys.path:
    sys.path.insert(0, _AG)
from prompts import INTAKE_SYSTEM

# Centralized in agents/prompts/ (verbatim) — see that package.
SYSTEM_PROMPT = INTAKE_SYSTEM

_or_client = None


def _get_openrouter():
    global _or_client
    if _or_client is None:
        from openai import OpenAI
        _or_client = OpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            timeout=30.0, max_retries=0,
        )
    return _or_client


def _call_llm(raw_text: str, temperature: float = 0.1) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Request: {raw_text}"},
    ]
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile", messages=messages, temperature=temperature)
        content = (response.choices[0].message.content or "").strip()
        if content:
            return content
        raise RuntimeError("empty Groq response")
    except Exception:
        # Fall back to OpenRouter so a Groq outage / decommissioned model never
        # breaks intake classification.
        r = _get_openrouter().chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct", messages=messages, temperature=temperature)
        return (r.choices[0].message.content or "").strip()


def run(envelope: dict, max_retries: int = 4) -> dict:
    for attempt in range(max_retries):
        try:
            # On retry, use temperature=0 for deterministic output (per spec)
            temperature = 0.0 if attempt > 0 else 0.1
            text = _call_llm(envelope["raw_text"], temperature=temperature)

            # Clean markdown if model adds it anyway
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            result = json.loads(text)
            confidence = float(result["confidence"])

            envelope["intake"] = {
                "department": result["department"],
                "task_type": result["task_type"],
                "isAutonomous": result["isAutonomous"],
                "reasoning": result["reasoning"],
                "confidence": confidence,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }

            # Spec: confidence < 0.60 → override to human review.
            # FIXME(P0-2): threshold intentionally kept at 0.1 for now (owner decision, 2026-06-06).
            #   Per spec this should be 0.60 — revert before real use. Tracked in PLAN.md §2/§5 (P0-2).
            if confidence < 0.1:
                envelope["intake"]["isAutonomous"] = False
                envelope["intake"]["reasoning"] += " [Low confidence — routed to human review]"

            return envelope

        except RateLimitError:
            wait = 30 * (2 ** attempt)  # 30s, 60s, 120s, 240s
            print(f"Rate limited (attempt {attempt+1}). Waiting {wait}s...")
            time.sleep(wait)

        except json.JSONDecodeError as e:
            if attempt == 0:
                # Retry once with temperature=0 per spec
                continue
            envelope["intake"] = {
                "department": "Unknown",
                "task_type": "parse_error",
                "isAutonomous": False,
                "reasoning": f"Failed to parse model response: {e}",
                "confidence": 0.0,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
            return envelope

    # All retries exhausted
    envelope["intake"] = {
        "department": "Unknown",
        "task_type": "rate_limit_error",
        "isAutonomous": False,
        "reasoning": "API rate limit exceeded after all retries.",
        "confidence": 0.0,
        "processed_at": datetime.now(timezone.utc).isoformat()
    }
    return envelope