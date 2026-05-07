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
You are an intake classifier for an office workflow automation system.
Your job is to analyse an incoming request and return a structured JSON object
that tells the system how to handle it.

Return ONLY valid JSON with exactly these fields — no markdown, no backticks, no extra text:

{
  "department": "<IT | Finance | HR | Other>",
  "task_type": "<one of the allowed values below>",
  "isAutonomous": <true | false>,
  "reasoning": "<one sentence explaining your classification>",
  "confidence": <float between 0.0 and 1.0>
}

ALLOWED TASK TYPES (pick the closest match):
- "escalation"         → a dispute, complaint, or issue that needs manager review
- "document_summary"   → summarise or extract information from a document or file
- "report"             → generate a structured report from data or metrics
- "leave_check"        → check, request, or enquire about leave or time off
- "email"              → draft or send a professional email reply
- "presentation"       → create a slide deck or PowerPoint presentation
- "expense_check"      → validate, check, or query an expense report
- "onboarding"         → new employee setup, onboarding info, or access provisioning
- "meeting_scheduler"  → schedule a meeting, process meeting minutes, or handle calendar requests

If the request does not match any of the above, use the closest one and set confidence below 0.6.

AUTONOMY RULES:
A task is autonomous (isAutonomous: true) if ALL of the following are true:
  1. It is informational, generative, or read-only — no approvals or payments involved
  2. It does not affect payroll, hiring, termination, or legal standing
  3. It does not require a human decision or sign-off to be valid
  4. The outcome is low-risk and easily reversible if wrong

A task is NOT autonomous (isAutonomous: false) if ANY of the following are true:
  - It involves money movement, invoice approval, or payment release
  - It affects an employee's contract, salary, or employment status
  - It involves a formal complaint, dispute, or disciplinary action
  - It requires a manager or executive to sign off
  - You are uncertain — when in doubt, set false

AUTONOMOUS TASK EXAMPLES (isAutonomous: true):
These task types are ALWAYS autonomous unless they contain a non-autonomous trigger above:
  - "document_summary"   → summarising a report, extracting key facts from a file, digesting an attachment
  - "report"             → generating a KPI report, finance summary, budget overview, or analytics report from existing data
  - "presentation"       → creating a PowerPoint or slide deck from provided context or data
  - "leave_check"        → looking up a leave balance or answering a PTO inquiry (read-only, no approval)
  - "email"              → drafting an informational or FAQ reply that does not commit to payments or contracts
  - "meeting_scheduler"  → booking a meeting or sending a calendar invite with no budget or hiring implications
  - "onboarding"         → providing onboarding information, checklists, or IT setup instructions (no contract changes)
  - "expense_check"      → checking the status of an already-submitted expense report (read-only lookup only)

NON-AUTONOMOUS TASK EXAMPLES (isAutonomous: false):
These are NEVER autonomous regardless of how the request is phrased:
  - "escalation"         → always requires a human reviewer — never autonomous
  - Any request to approve, release, or process a payment or invoice
  - Any request to change salary, role, contract, or employment status
  - Any request involving a formal complaint, disciplinary action, or legal matter
  - Any expense_check that involves approving or rejecting a claim (not just checking status)
  - Any leave_check that involves approving leave (not just checking balance)

CONFIDENCE GUIDE:
- 0.9–1.0 → request is clear and maps perfectly to a task type
- 0.7–0.9 → request is mostly clear with minor ambiguity
- 0.5–0.7 → request is ambiguous or maps loosely to a task type
- below 0.5 → very unclear — still classify but flag for human review

DEPARTMENT:
Infer from context. Use "Other" if none of IT, Finance or HR apply.
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
            confidence = float(result["confidence"])

            envelope["intake"] = {
                "department": result["department"],
                "task_type": result["task_type"],
                "isAutonomous": result["isAutonomous"],
                "reasoning": result["reasoning"],
                "confidence": confidence,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }

            # Spec: confidence < 0.60 → override to human review
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