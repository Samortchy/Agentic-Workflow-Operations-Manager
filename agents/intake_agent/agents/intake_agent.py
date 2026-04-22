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

SYSTEM_PROMPT = """
You are an intake classifier for an office workflow system.
Given a request, you must return a JSON object with exactly these fields:
- department: one of "IT", "Finance", "HR"
- task_type: a short snake_case string describing the task
- isAutonomous: true or false based on the taxonomy below
- reasoning: one sentence explaining your decision
- confidence: a float between 0.0 and 1.0

AUTONOMY TAXONOMY:
- Password reset / access request → IT, true
- Software info / FAQ lookup → IT, true
- Laptop / equipment procurement → IT, false
- Server outage / critical failure → IT, false
- Expense report status check → Finance, true
- Budget inquiry / policy question → Finance, true
- Invoice approval / payment release → Finance, false
- Payroll / salary dispute → Finance, false
- Leave balance inquiry → HR, true
- Onboarding info request → HR, true
- Hiring / termination / promotion → HR, false
- Payroll change / raise request → HR, false
- Workplace complaint / dispute → HR, false

Ambiguous cases default to isAutonomous: false.
Return ONLY valid JSON, no extra text, no markdown, no backticks.
"""

def _call_llm(raw_text: str, temperature: float = 0.1) -> str:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Request: {raw_text}"}
        ],
        temperature=temperature
    )
    return response.choices[0].message.content.strip()


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
            confidence = result["confidence"]

            envelope["intake"] = {
                "department": result["department"],
                "task_type": result["task_type"],
                "isAutonomous": result["isAutonomous"],
                "reasoning": result["reasoning"],
                "confidence": confidence,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }

            # Spec: confidence < 0.60 → override to human review
            if confidence < 0.60:
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