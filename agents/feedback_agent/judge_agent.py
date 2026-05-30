"""
agents/feedback_agent/judge_agent.py
=====================================
THE LLM JUDGE AGENT — evaluates the output quality of other agents.

WHAT THIS FILE DOES:
    Uses an LLM (via Groq) to evaluate whether the Intake Agent and
    Priority Agent made correct decisions, producing a confidence score
    and a suggested correct label. These scores become the "actual_priority"
    and "actual_type" labels that feed the retraining loop — replacing
    the need for a human to manually verify every task.

WHY IT EXISTS:
    Without verified labels, the Priority Agent can NEVER retrain because
    actual_priority stays None forever. This agent fills that gap automatically.

THE 3 EVALUATION MODES (from LLM-as-Judge pattern):
    1. SCORE-BASED     — rate the agent's output 1–5 on correctness
    2. GOLDEN DATASET  — compare against known correct answers
    3. AGENT-EVALUATES-AGENT — this agent evaluates Intake + Priority outputs

HOW IT FITS IN THE PIPELINE:
    Execution → FeedbackAgent.process() → JudgeAgent.evaluate_priority()
                                        → JudgeAgent.evaluate_intake()
                                        → verified labels stored
                                        → retraining loop unblocked

IMPORTANT: The judge is an EVALUATOR, not a predictor.
    - Intake Agent   → fast TF-IDF + LR prediction   (cheap, always runs)
    - Priority Agent → fast Random Forest prediction  (cheap, always runs)
    - Judge Agent    → slow LLM evaluation            (only runs in background
                                                       to build training data)

PROVIDER: Groq (https://console.groq.com)
    - Free tier: no credit card required
    - 30 requests/min, 14,400 requests/day
    - Models: llama-3.3-70b-versatile (primary), llama3-8b-8192 (fallback)
    - Get your key at: https://console.groq.com/keys
    - Set it: $env:GROQ_API_KEY = "gsk_..."
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────
# GROQ CLIENT IMPORT
# Install with: pip install groq
# ─────────────────────────────────────────────────────────────────────────
try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [JudgeAgent] %(levelname)s %(message)s",
)
logger = logging.getLogger("JudgeAgent")


# ═════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═════════════════════════════════════════════════════════════════════════

@dataclass
class JudgeVerdict:
    """
    The output of ONE evaluation by the LLM judge.

    task_id           — which task was evaluated
    agent_evaluated   — "priority" | "intake" | "structuring"
    predicted_value   — what the agent actually predicted
    suggested_value   — what the judge thinks it SHOULD have been
    score             — 1 (very wrong) to 5 (perfect)
    confidence        — "high" | "medium" | "low"
    reason            — one-sentence explanation from the judge
    auto_accepted     — True if score was high enough to auto-accept as label
    timestamp         — when this verdict was produced
    evaluation_mode   — "score_based" | "golden_dataset" | "agent_eval"
    """
    task_id: str
    agent_evaluated: str
    predicted_value: str
    suggested_value: str
    score: int
    confidence: str
    reason: str
    auto_accepted: bool
    evaluation_mode: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class GoldenExample:
    """
    A known-correct example used for golden dataset evaluation.

    request_text     — the raw text of the request
    correct_type     — the correct category label (for Intake Agent)
    correct_priority — the correct urgency label  (for Priority Agent)
    notes            — why this example is important / edge case info
    """
    request_text: str
    correct_type: str
    correct_priority: str
    notes: str = ""


@dataclass
class JudgeConfig:
    """
    All tunable settings for the Judge Agent.

    api_key_env_var      — environment variable name holding the Groq API key
    primary_model        — best quality model (used first)
    fallback_model       — faster/lighter model (used if primary fails)
    auto_accept_score    — score >= this value → auto-accept as verified label
    auto_reject_score    — score <= this value → flag for human review
    request_timeout      — seconds before API call times out
    max_retries          — how many times to retry a failed API call
    verdicts_dir         — where to save verdict history JSON files
    enable_golden_eval   — whether to run golden dataset evaluation each cycle
    golden_batch_size    — how many unlabelled tasks to auto-label per cycle
    """
    api_key_env_var: str  = "GROQ_API_KEY"
    primary_model: str    = "llama-3.3-70b-versatile"   # best free-tier model
    fallback_model: str   = "llama3-8b-8192"            # fast fallback
    auto_accept_score: int  = 4       # score 4 or 5 → auto-accept
    auto_reject_score: int  = 2       # score 1 or 2 → flag for human
    request_timeout: int    = 30      # seconds
    max_retries: int        = 2
    verdicts_dir: str       = "artefacts/judge_verdicts"
    enable_golden_eval: bool = True
    golden_batch_size: int   = 20     # max tasks to auto-label per cycle


# ═════════════════════════════════════════════════════════════════════════
# GOLDEN DATASET
# Pre-defined examples where we KNOW the correct answer.
# Used to benchmark both Intake and Priority agents every evaluation cycle.
# Extend this list as you discover edge cases in production.
# ═════════════════════════════════════════════════════════════════════════

GOLDEN_DATASET: list[GoldenExample] = [
    # IT Support — High priority (system down / many users affected)
    GoldenExample("Server is completely down, no one can access the system",       "IT Support",  "High",   "System-wide outage"),
    GoldenExample("VPN is broken for the entire department since this morning",    "IT Support",  "High",   "Department-wide blockage"),
    GoldenExample("Email server not sending or receiving — all staff affected",    "IT Support",  "High",   "Communication blocked"),
    GoldenExample("My laptop won't turn on at all, I have a meeting in 1 hour",   "IT Support",  "High",   "Time-sensitive + hardware failure"),
    GoldenExample("Cannot access any company files, getting access denied error",  "IT Support",  "High",   "Data access blocked"),

    # IT Support — Medium priority (one person affected, workaround exists)
    GoldenExample("Outlook keeps crashing when I open attachments",                "IT Support",  "Medium", "Single user, workaround possible"),
    GoldenExample("Need to install Adobe Acrobat for my project work",             "IT Support",  "Medium", "Software install, not urgent"),
    GoldenExample("My second monitor is not being detected by my computer",        "IT Support",  "Medium", "Hardware issue, single user"),
    GoldenExample("Printer on floor 2 is showing offline status",                  "IT Support",  "Medium", "Shared resource, workaround exists"),

    # IT Support — Low priority (cosmetic / non-blocking)
    GoldenExample("Can you change my desktop wallpaper to the company logo",       "IT Support",  "Low",    "Cosmetic, no impact on work"),
    GoldenExample("I forgot my WiFi password for the guest network",               "IT Support",  "Low",    "Easy fix, not urgent"),

    # HR Request — various priorities
    GoldenExample("I need to report a workplace harassment incident urgently",     "HR Request",  "High",   "Serious HR matter"),
    GoldenExample("My payroll was incorrect this month, I was underpaid",          "HR Request",  "High",   "Financial impact on employee"),
    GoldenExample("I want to apply for 3 days of annual leave next month",         "HR Request",  "Low",    "Routine admin, ample notice"),
    GoldenExample("Can I get a copy of my employment contract for a visa",         "HR Request",  "Medium", "Moderate urgency for external deadline"),
    GoldenExample("I need to update my emergency contact information",             "HR Request",  "Low",    "Admin update, not time-sensitive"),

    # Facilities — various priorities
    GoldenExample("There is a water leak in the ceiling of the main office",       "Facilities",  "High",   "Safety risk"),
    GoldenExample("The fire exit on floor 3 is blocked by storage boxes",          "Facilities",  "High",   "Safety / compliance issue"),
    GoldenExample("The air conditioning in room 204 is broken, it is very hot",   "Facilities",  "Medium", "Comfort issue, affects productivity"),
    GoldenExample("We need extra chairs for the board meeting tomorrow morning",   "Facilities",  "Medium", "Time-sensitive logistical request"),
    GoldenExample("Can we get a new coffee machine for the break room",            "Facilities",  "Low",    "Nice-to-have, not essential"),

    # Finance — various priorities
    GoldenExample("Supplier invoice overdue, they are threatening to stop service","Finance",     "High",   "Operational risk if unpaid"),
    GoldenExample("I need a purchase order approved for emergency server hardware","Finance",     "High",   "Blocking IT operations"),
    GoldenExample("Expense reimbursement for last month's business trip to Cairo", "Finance",     "Medium", "Routine but employee is owed money"),
    GoldenExample("Need budget approval for Q3 marketing campaign planning",       "Finance",     "Low",    "Planning, not immediately needed"),
]


# ═════════════════════════════════════════════════════════════════════════
# MAIN JUDGE AGENT CLASS
# ═════════════════════════════════════════════════════════════════════════

class JudgeAgent:
    """
    The LLM Judge Agent — now powered by Groq.

    USAGE (called by FeedbackLearningAgent):

        judge = JudgeAgent()

        # Evaluate Priority Agent's label on one task:
        verdict = judge.evaluate_priority(
            task_id            = "task_001",
            request_text       = "Server is down for everyone",
            task_type          = "IT Support",
            predicted_priority = "Low",        # what Priority Agent said
            status             = "success",
            duration_seconds   = 45.0,
            deadline_seconds   = 60.0,
            retries            = 0,
        )

        # Evaluate Intake Agent's classification:
        verdict = judge.evaluate_intake(
            task_id        = "task_001",
            request_text   = "I need annual leave next week",
            predicted_type = "IT Support",     # what Intake Agent said (wrong!)
        )

        # Run golden dataset benchmark:
        results = judge.run_golden_evaluation()

    SETUP:
        1. pip install groq
        2. Get free key at https://console.groq.com/keys
        3. $env:GROQ_API_KEY = "gsk_..."
    """

    def __init__(self, config: Optional[JudgeConfig] = None):
        """
        Initialise the Judge Agent.

        Checks for the Groq API key in environment variables.
        Creates the verdicts directory for logging all evaluations.
        """
        self.config = config or JudgeConfig()

        # Get API key from environment — never hardcode it
        self._api_key = os.environ.get(self.config.api_key_env_var, "")

        if not _GROQ_AVAILABLE:
            logger.warning(
                "[JudgeAgent] groq package not installed. "
                "Run: pip install groq"
            )

        if not self._api_key:
            logger.warning(
                f"[JudgeAgent] No API key found in env var "
                f"'{self.config.api_key_env_var}'. "
                f"Judge will return fallback verdicts (score=3, confidence=low). "
                f"Get a free key at https://console.groq.com/keys"
            )

        # Initialise Groq client
        self._client: Optional[Groq] = None
        if _GROQ_AVAILABLE and self._api_key:
            self._client = Groq(api_key=self._api_key)

        # Create directory to store all verdict history
        self._verdicts_dir = Path(self.config.verdicts_dir)
        self._verdicts_dir.mkdir(parents=True, exist_ok=True)

        # In-memory verdict log (also saved to disk)
        self._verdicts: list[JudgeVerdict] = []

        logger.info("JudgeAgent initialised.")

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC API — 4 methods the FeedbackLearningAgent calls
    # ─────────────────────────────────────────────────────────────────────

    def evaluate_priority(
        self,
        task_id: str,
        request_text: str,
        task_type: str,
        predicted_priority: str,
        status: str,
        duration_seconds: float,
        deadline_seconds: float,
        retries: int,
    ) -> JudgeVerdict:
        """
        SCORE-BASED EVALUATION of the Priority Agent's output.

        Asks the LLM: "Given this request, was 'High' the right priority?"
        Returns a JudgeVerdict with a score 1–5 and a suggested correct label.

        WHEN auto_accepted=True: the suggested_value becomes actual_priority
        in the FeedbackAgent, unblocking the retraining loop without
        waiting for a human.

        Parameters:
            task_id           — unique task identifier
            request_text      — the original raw request text
            task_type         — the category (from Intake Agent)
            predicted_priority— what Priority Agent labelled it
            status            — execution outcome: "success"|"partial"|"failure"
            duration_seconds  — actual time taken
            deadline_seconds  — time allowed
            retries           — number of retry attempts
        """
        prompt = self._build_priority_prompt(
            request_text, task_type, predicted_priority,
            status, duration_seconds, deadline_seconds, retries
        )

        raw = self._call_llm(prompt)

        verdict = JudgeVerdict(
            task_id         = task_id,
            agent_evaluated = "priority",
            predicted_value = predicted_priority,
            suggested_value = raw.get("suggested_priority", predicted_priority),
            score           = int(raw.get("score", 3)),
            confidence      = raw.get("confidence", "low"),
            reason          = raw.get("reason", "Judge evaluation"),
            auto_accepted   = (
                int(raw.get("score", 3)) >= self.config.auto_accept_score
                and raw.get("confidence", "low") == "high"
            ),
            evaluation_mode = "score_based",
        )

        self._save_verdict(verdict)
        logger.info(
            f"[evaluate_priority] task={task_id} "
            f"predicted={predicted_priority} suggested={verdict.suggested_value} "
            f"score={verdict.score} auto_accepted={verdict.auto_accepted}"
        )
        return verdict

    def evaluate_intake(
        self,
        task_id: str,
        request_text: str,
        predicted_type: str,
    ) -> JudgeVerdict:
        """
        SCORE-BASED EVALUATION of the Intake Agent's classification.

        Asks the LLM: "Was 'IT Support' the right category for this request?"
        Returns a verdict with correctness score and suggested correct type.

        Parameters:
            task_id       — unique task identifier
            request_text  — the original raw request text
            predicted_type— what Intake Agent classified it as
        """
        prompt = self._build_intake_prompt(request_text, predicted_type)
        raw    = self._call_llm(prompt)

        verdict = JudgeVerdict(
            task_id         = task_id,
            agent_evaluated = "intake",
            predicted_value = predicted_type,
            suggested_value = raw.get("suggested_type", predicted_type),
            score           = int(raw.get("score", 3)),
            confidence      = raw.get("confidence", "low"),
            reason          = raw.get("reason", "Judge evaluation"),
            auto_accepted   = (
                int(raw.get("score", 3)) >= self.config.auto_accept_score
                and raw.get("confidence", "low") == "high"
            ),
            evaluation_mode = "score_based",
        )

        self._save_verdict(verdict)
        logger.info(
            f"[evaluate_intake] task={task_id} "
            f"predicted={predicted_type} suggested={verdict.suggested_value} "
            f"score={verdict.score} auto_accepted={verdict.auto_accepted}"
        )
        return verdict

    def run_golden_evaluation(self) -> dict:
        """
        GOLDEN DATASET EVALUATION — benchmark both agents against known answers.

        Runs the Intake + Priority predictions from the judge against all
        examples in GOLDEN_DATASET and measures accuracy.

        Returns a dict with:
            intake_accuracy  — fraction of golden examples correctly classified
            priority_accuracy— fraction of golden examples with correct priority
            failures         — list of examples where the judge disagreed
            total            — total examples evaluated
        """
        logger.info(f"[golden_eval] Running on {len(GOLDEN_DATASET)} examples...")

        intake_correct   = 0
        priority_correct = 0
        failures         = []

        for i, example in enumerate(GOLDEN_DATASET):
            task_id = f"golden_{i:03d}"

            intake_verdict = self.evaluate_intake(
                task_id        = task_id,
                request_text   = example.request_text,
                predicted_type = example.correct_type,
            )
            if intake_verdict.score >= 4:
                intake_correct += 1
            else:
                failures.append({
                    "example":    example.request_text,
                    "agent":      "intake",
                    "expected":   example.correct_type,
                    "judge_says": intake_verdict.suggested_value,
                    "reason":     intake_verdict.reason,
                })

            priority_verdict = self.evaluate_priority(
                task_id            = task_id,
                request_text       = example.request_text,
                task_type          = example.correct_type,
                predicted_priority = example.correct_priority,
                status             = "success",
                duration_seconds   = 30.0,
                deadline_seconds   = 60.0,
                retries            = 0,
            )
            if priority_verdict.score >= 4:
                priority_correct += 1
            else:
                failures.append({
                    "example":    example.request_text,
                    "agent":      "priority",
                    "expected":   example.correct_priority,
                    "judge_says": priority_verdict.suggested_value,
                    "reason":     priority_verdict.reason,
                })

            # Small pause to respect Groq free-tier rate limits (30 RPM)
            time.sleep(0.3)

        total = len(GOLDEN_DATASET)
        result = {
            "intake_accuracy":   round(intake_correct   / total, 4),
            "priority_accuracy": round(priority_correct / total, 4),
            "failures":          failures,
            "total":             total,
            "timestamp":         datetime.now(timezone.utc).isoformat(),
        }

        path = self._verdicts_dir / f"golden_eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(result, indent=2))

        logger.info(
            f"[golden_eval] intake_acc={result['intake_accuracy']:.1%} "
            f"priority_acc={result['priority_accuracy']:.1%} "
            f"failures={len(failures)}"
        )
        return result

    def get_verdict_history(self) -> list[dict]:
        """
        Return all saved verdicts as a list of dicts.
        Used by the dashboard to show judge activity over time.
        """
        verdicts = []
        for f in sorted(self._verdicts_dir.glob("verdict_*.json")):
            try:
                verdicts.append(json.loads(f.read_text()))
            except Exception:
                pass
        return verdicts

    def get_auto_accepted_labels(self) -> list[dict]:
        """
        Return all verdicts that were auto-accepted (score >= 4, confidence=high).
        These are the pseudo-labels that feed the retraining loop.
        """
        return [
            asdict(v) for v in self._verdicts
            if v.auto_accepted
        ]

    # ─────────────────────────────────────────────────────────────────────
    # INTERNAL — PROMPT BUILDERS
    # ─────────────────────────────────────────────────────────────────────

    def _build_priority_prompt(
        self,
        request_text: str,
        task_type: str,
        predicted_priority: str,
        status: str,
        duration_seconds: float,
        deadline_seconds: float,
        retries: int,
    ) -> str:
        """
        Build the priority evaluation prompt.

        Gives the judge:
        - The raw request text (what the user wrote)
        - The task category (from Intake Agent)
        - What the Priority Agent predicted
        - How the task actually went (status, timing, retries)

        IMPORTANT: The prompt explicitly asks for ONLY JSON output.
        Any preamble or markdown breaks our json.loads() parsing.
        """
        deadline_met = "YES" if duration_seconds <= deadline_seconds else "NO"
        return f"""You are an expert evaluator for an office workflow automation system.
Your job is to evaluate whether the AI Priority Agent made the correct urgency decision.

PRIORITY DEFINITIONS:
- High   : Affects multiple people, blocks work, safety risk, or has a very tight deadline
- Medium : Affects one person moderately, has a workaround, or has a moderate deadline
- Low    : Cosmetic, admin, nice-to-have, or has a flexible deadline

TASK INFORMATION:
  Request text      : "{request_text}"
  Task category     : {task_type}
  Predicted priority: {predicted_priority}
  Execution status  : {status}
  Time taken        : {duration_seconds:.0f} seconds
  Deadline          : {deadline_seconds:.0f} seconds
  Deadline met      : {deadline_met}
  Retries needed    : {retries}

EVALUATION TASK:
Was "{predicted_priority}" the correct priority for this request?
Consider the request text, its potential impact, and the execution outcome.

Respond with ONLY valid JSON — no preamble, no markdown, no explanation outside the JSON:
{{
  "suggested_priority": "High" or "Medium" or "Low",
  "score": integer 1 to 5 (1=completely wrong, 3=acceptable, 5=perfect),
  "confidence": "high" or "medium" or "low",
  "reason": "one sentence explaining your evaluation"
}}"""

    def _build_intake_prompt(
        self,
        request_text: str,
        predicted_type: str,
    ) -> str:
        """
        Build the intake classification evaluation prompt.

        Gives the judge:
        - The raw request text
        - What category the Intake Agent predicted

        The judge checks: was this the right bucket?
        """
        return f"""You are an expert evaluator for an office workflow automation system.
Your job is to evaluate whether the AI Intake Agent correctly classified an incoming request.

AVAILABLE CATEGORIES:
- IT Support  : Computer hardware, software, network, email, access issues
- HR Request  : Leave, payroll, contracts, employee records, workplace issues
- Facilities  : Office environment, equipment, safety, maintenance, rooms
- Finance     : Invoices, purchase orders, expense claims, budget approvals

REQUEST TEXT:
"{request_text}"

PREDICTED CATEGORY: {predicted_type}

EVALUATION TASK:
Was "{predicted_type}" the correct category for this request?

Respond with ONLY valid JSON — no preamble, no markdown, no explanation outside the JSON:
{{
  "suggested_type": one of "IT Support" / "HR Request" / "Facilities" / "Finance",
  "score": integer 1 to 5 (1=completely wrong, 3=acceptable, 5=perfect),
  "confidence": "high" or "medium" or "low",
  "reason": "one sentence explaining your evaluation"
}}"""

    # ─────────────────────────────────────────────────────────────────────
    # INTERNAL — LLM API CALL (Groq)
    # ─────────────────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> dict:
        """
        Call the Groq API and return the parsed JSON response.

        Tries primary_model first (llama-3.3-70b-versatile), then falls back
        to fallback_model (llama3-8b-8192) if the primary fails.

        Groq free tier limits (as of 2026):
            - 30 requests/minute
            - 14,400 requests/day
            - No credit card required
            - Get key at: https://console.groq.com/keys

        Returns a dict with keys:
            suggested_priority / suggested_type, score, confidence, reason
        """
        # Fallback response when judge is unavailable
        _fallback = {
            "suggested_priority": "Medium",
            "suggested_type":     "IT Support",
            "score":              3,
            "confidence":         "low",
            "reason":             "Judge unavailable — check GROQ_API_KEY and groq package.",
        }

        if not self._client:
            if not _GROQ_AVAILABLE:
                _fallback["reason"] = "groq package not installed. Run: pip install groq"
            else:
                _fallback["reason"] = "No GROQ_API_KEY set. Get one at https://console.groq.com/keys"
            return _fallback

        models_to_try = [self.config.primary_model, self.config.fallback_model]
        # Deduplicate while preserving order
        seen = set()
        models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]

        last_error = None

        for model in models_to_try:
            for attempt in range(self.config.max_retries + 1):
                try:
                    response = self._client.chat.completions.create(
                        model    = model,
                        messages = [{"role": "user", "content": prompt}],
                        max_tokens      = 300,
                        temperature     = 0.1,   # low temp for consistent JSON
                        timeout         = self.config.request_timeout,
                    )

                    text = response.choices[0].message.content.strip()
                    # Strip any accidental markdown fences
                    text = text.replace("```json", "").replace("```", "").strip()

                    result = json.loads(text)
                    logger.debug(f"[_call_llm] Model={model} parsed response: {result}")
                    return result

                except json.JSONDecodeError as e:
                    last_error = e
                    logger.warning(
                        f"[_call_llm] Model={model} attempt {attempt + 1} "
                        f"JSON parse failed: {e}. Raw: {text!r:.100}. "
                        f"{'Retrying...' if attempt < self.config.max_retries else 'Moving on.'}"
                    )
                    if attempt < self.config.max_retries:
                        time.sleep(1.0)

                except Exception as e:
                    last_error = e
                    err_str = str(e)

                    # Groq rate limit → back off and retry
                    if "429" in err_str or "rate_limit" in err_str.lower():
                        wait = 2.0 * (attempt + 1)
                        logger.warning(
                            f"[_call_llm] Model={model} attempt {attempt + 1} "
                            f"rate-limited (429). Waiting {wait}s..."
                        )
                        time.sleep(wait)

                    # Model not found → skip to next model immediately
                    elif "404" in err_str or "model_not_found" in err_str.lower():
                        logger.warning(
                            f"[_call_llm] Model '{model}' not found (404). "
                            f"Trying next model..."
                        )
                        break  # break retry loop, try next model

                    # Auth error → no point retrying
                    elif "401" in err_str or "403" in err_str or "invalid_api_key" in err_str.lower():
                        logger.error(
                            f"[_call_llm] Auth error ({e}). "
                            f"Check your GROQ_API_KEY at https://console.groq.com/keys"
                        )
                        return _fallback

                    else:
                        logger.warning(
                            f"[_call_llm] Model={model} attempt {attempt + 1} "
                            f"failed: {e}. "
                            f"{'Retrying...' if attempt < self.config.max_retries else 'Moving on.'}"
                        )
                        if attempt < self.config.max_retries:
                            time.sleep(1.5 ** attempt)

        logger.error(f"[_call_llm] All models and retries failed. Last error: {last_error}")
        _fallback["reason"] = f"API call failed after retries: {last_error}"
        return _fallback

    # ─────────────────────────────────────────────────────────────────────
    # INTERNAL — PERSISTENCE
    # ─────────────────────────────────────────────────────────────────────

    def _save_verdict(self, verdict: JudgeVerdict):
        """
        Save one verdict to disk as a JSON file.
        """
        self._verdicts.append(verdict)
        filename = (
            f"verdict_{verdict.task_id}_{verdict.agent_evaluated}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S%f')}.json"
        )
        path = self._verdicts_dir / filename
        path.write_text(json.dumps(asdict(verdict), indent=2))
        logger.debug(f"Verdict saved to {path}")


# ─────────────────────────────────────────────────────────────────────────
# CONVENIENCE FACTORY
# ─────────────────────────────────────────────────────────────────────────

def create_judge_agent(verdicts_dir: str = "artefacts/judge_verdicts") -> JudgeAgent:
    config = JudgeConfig(verdicts_dir=verdicts_dir)
    return JudgeAgent(config)