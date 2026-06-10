"""
agents/feedback_loop/execution_judge.py
=========================================
PHASE 2 — EXECUTION JUDGE AGENT

EVALUATION DIMENSIONS:
    1. COMPLETION     — rule-based: did it finish? (completed/failed/escalated)
    2. TIMELINESS     — rule-based: did it meet the deadline?
    3. ROUTING        — rule-based: did orchestrator pick the right executor?
    4. ERROR QUALITY  — rule-based: were errors logged properly?
    5. APPROVAL GATE  — rule-based: did the gate fire when it should?
    6. OUTPUT QUALITY — LLM-based (Groq): was the actual output content good?
                        e.g. was the email well-written? was the summary accurate?
                        This is where LLM judgment genuinely adds value.

WHY MIXED APPROACH:
    Rule-based for structural checks (fast, free, deterministic).
    LLM only for content quality (needs language understanding).

    Rule-based  → "Did it send an email?"         (yes/no, no LLM needed)
    LLM         → "Was the email well-written?"   (needs understanding)

SETUP:
    Set GROQ_API_KEY for LLM output quality scoring.
    If key is missing, output_quality_score defaults to 3 (neutral).
    All other 5 dimensions work without any API key.

    pip install groq
    $env:GROQ_API_KEY = "gsk_..."

USAGE:
    from feedback_loop.execution_judge import create_execution_judge

    judge   = create_execution_judge()
    verdict = judge.evaluate(envelope, task_id="task_001")

    print(verdict.overall_score)         # 1–5
    print(verdict.output_quality_score)  # LLM score for content quality
    print(verdict.issues)                # list of problems found
    print(verdict.auto_flag)             # True = needs human review
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

try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ExecutionJudge] %(levelname)s %(message)s",
)
logger = logging.getLogger("ExecutionJudge")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ExecutionVerdict:
    """
    The output of ONE execution evaluation.

    task_id              — which task was evaluated
    agent_name           — which executor ran (e.g. "leave_checker")
    task_type            — the intake classification (e.g. "leave_check")
    final_status         — completed / failed / escalated / approval_pending

    completion_score     — 1–5 rule-based: did it finish correctly?
    timeliness_score     — 1–5 rule-based: did it meet the deadline?
    routing_score        — 1–5 rule-based: was the right executor chosen?
    error_quality_score  — 1–5 rule-based: were errors logged properly?
    approval_gate_score  — 1–5 rule-based: did the approval gate behave correctly?
    output_quality_score — 1–5 LLM-based (Groq): was the output content good?
    overall_score        — 1–5 weighted composite of all 6

    issues               — list of specific problems found
    recommendations      — list of suggested fixes
    auto_flag            — True if overall_score <= 2 (needs human review)
    timestamp            — when this verdict was produced
    """
    task_id:              str
    agent_name:           str
    task_type:            str
    final_status:         str

    completion_score:     int
    timeliness_score:     int
    routing_score:        int
    error_quality_score:  int
    approval_gate_score:  int
    output_quality_score: int
    overall_score:        int

    issues:          list
    recommendations: list
    auto_flag:       bool

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ExecutionJudgeConfig:
    """
    Tunable settings for the Execution Judge.

    api_key_env_var         — env var name for Groq key (output quality LLM)
    primary_model           — Groq model for output quality scoring
    fallback_model          — backup Groq model
    deadline_tolerance_pct  — how much over deadline is acceptable (0.1 = 10%)
    max_acceptable_errors   — more errors than this → deduct points
    auto_flag_score         — overall score <= this → auto_flag=True
    verdicts_dir            — where to save verdict JSON files
    expected_routing        — maps (task_type, department) → executor name
    """
    api_key_env_var:        str   = "GROQ_API_KEY"
    primary_model:          str   = "llama-3.3-70b-versatile"
    fallback_model:         str   = "llama-3.1-8b-instant"
    deadline_tolerance_pct: float = 0.1
    max_acceptable_errors:  int   = 1
    auto_flag_score:        int   = 2
    verdicts_dir:           str   = "agents/feedback_loop/output/execution_verdicts"

    expected_routing: dict = field(default_factory=lambda: {
        # (task_type, department) → expected executor name
        ("email",             "IT"):      "email_agent",
        ("email",             ""):        "email_agent",
        ("escalation",        "IT"):      "escalation_router",
        ("escalation",        "HR"):      "escalation_router",
        ("escalation",        "Finance"): "escalation_router",
        ("escalation",        ""):        "escalation_router",
        ("document_summary",  "HR"):      "document_summarizer",
        ("document_summary",  ""):        "document_summarizer",
        ("report",            "Finance"): "report_generator",
        ("report",            ""):        "report_generator",
        ("leave_check",       "HR"):      "leave_checker",
        ("leave_check",       ""):        "leave_checker",
        ("presentation",      "Finance"): "powerpoint_agent",
        ("presentation",      ""):        "powerpoint_agent",
        ("expense_check",     "Finance"): "expense_tracker",
        ("expense_check",     ""):        "expense_tracker",
        ("onboarding",        "IT"):      "onboarding_coordinator",
        ("onboarding",        "HR"):      "onboarding_coordinator",
        ("onboarding",        ""):        "onboarding_coordinator",
        ("meeting_scheduler", "Other"):   "meeting_scheduler",
        ("meeting_scheduler", ""):        "meeting_scheduler",
    })


_SUCCESSFUL_STATUSES = {"completed"}
_REVIEW_STATUSES     = {"queued_for_review", "approval_pending", "pending_human_review"}
_FAILURE_STATUSES    = {"failed", "escalated"}

# Intake now emits task_type values that ARE the executor names, so the correct
# routing is simply agent_name == task_type when task_type is a known agent.
_KNOWN_AGENTS = {
    "escalation_router", "document_summarizer", "report_generator", "leave_checker",
    "email_agent", "powerpoint_agent", "meeting_scheduler", "expense_tracker",
    "onboarding_coordinator",
}


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class ExecutionJudge:
    """
    Hybrid judge for the Execution Agent layer.

    5 rule-based dimensions  → fast, free, no API key needed
    1 LLM dimension (Groq)   → scores output content quality

    USAGE:
        judge   = ExecutionJudge()
        verdict = judge.evaluate(envelope, task_id="task_001")

        print(verdict.overall_score)         # 1–5
        print(verdict.output_quality_score)  # LLM score (or 3 if no key)
        print(verdict.issues)                # list of problems
        print(verdict.auto_flag)             # True = needs human review
    """

    def __init__(self, config: Optional[ExecutionJudgeConfig] = None):
        self.config = config or ExecutionJudgeConfig()

        self._api_key = os.environ.get(self.config.api_key_env_var, "")
        self._client: Optional[object] = None

        if _GROQ_AVAILABLE and self._api_key:
            self._client = Groq(api_key=self._api_key)
            logger.info("ExecutionJudge: Groq LLM enabled for output quality scoring.")
        else:
            logger.warning(
                "ExecutionJudge: No GROQ_API_KEY — output_quality_score defaults to 3 "
                "(neutral). Set GROQ_API_KEY to enable LLM content scoring."
            )

        self._verdicts_dir = Path(self.config.verdicts_dir)
        self._verdicts_dir.mkdir(parents=True, exist_ok=True)
        self._verdicts: list[ExecutionVerdict] = []
        logger.info("ExecutionJudge initialised. Verdicts dir: %s", self._verdicts_dir)

    # ── Public API ─────────────────────────────────────────────────────────────

    def evaluate(self, envelope: dict, task_id: str = "") -> ExecutionVerdict:
        """
        Evaluate a completed envelope from the Orchestrator / ExecutionRunner.

        Runs 5 rule-based checks + 1 Groq LLM content quality check.

        Parameters
        ----------
        envelope : full envelope dict returned by Orchestrator.run()
        task_id  : optional override; read from envelope.task.task_id if empty
        """
        intake    = envelope.get("intake",    {})
        priority  = envelope.get("priority",  {})
        execution = envelope.get("execution", {})

        task_id    = task_id or envelope.get("task", {}).get("task_id", "unknown")
        agent_name = execution.get("agent_name",  "unknown")
        task_type  = intake.get("task_type",      "unknown")
        department = intake.get("department",     "")
        status     = execution.get("status",      "unknown")
        errors     = execution.get("errors",      [])

        started_at   = execution.get("started_at",   "")
        completed_at = execution.get("completed_at", "")
        duration_sec = self._calc_duration(started_at, completed_at)
        deadline_sec = float(priority.get("deadline_seconds", 0) or 0)

        approval_mode   = execution.get("approval", "none")
        approval_action = (
            execution.get("steps", {})
                     .get("approval_gate", {})
                     .get("action", "")
        )

        issues:          list[str] = []
        recommendations: list[str] = []

        # ── 5 rule-based dimensions ────────────────────────────────────────────
        completion_score    = self._score_completion(status, errors, issues, recommendations)
        timeliness_score    = self._score_timeliness(duration_sec, deadline_sec, status, issues, recommendations)
        routing_score       = self._score_routing(agent_name, task_type, department, status, issues, recommendations)
        error_quality_score = self._score_error_quality(errors, status, issues, recommendations)
        approval_gate_score = self._score_approval_gate(approval_mode, approval_action, status, issues, recommendations)

        # ── 1 LLM dimension — output content quality (Groq) ───────────────────
        output_quality_score = self._score_output_quality(
            envelope, task_type, agent_name, status, issues, recommendations
        )

        # ── Weighted overall (completion 35%, timeliness 20%, output 20%,
        #    routing 15%, error quality 7%, approval gate 3%) ─────────────────
        overall_raw = (
            completion_score     * 0.35 +
            timeliness_score     * 0.20 +
            output_quality_score * 0.20 +
            routing_score        * 0.15 +
            error_quality_score  * 0.07 +
            approval_gate_score  * 0.03
        )
        overall_score = max(1, min(5, round(overall_raw)))
        auto_flag     = overall_score <= self.config.auto_flag_score

        verdict = ExecutionVerdict(
            task_id              = task_id,
            agent_name           = agent_name,
            task_type            = task_type,
            final_status         = status,
            completion_score     = completion_score,
            timeliness_score     = timeliness_score,
            routing_score        = routing_score,
            error_quality_score  = error_quality_score,
            approval_gate_score  = approval_gate_score,
            output_quality_score = output_quality_score,
            overall_score        = overall_score,
            issues               = issues,
            recommendations      = recommendations,
            auto_flag            = auto_flag,
        )

        self._save_verdict(verdict)
        logger.info(
            "task=%s agent=%s status=%s | overall=%d/5 output_quality=%d/5 "
            "auto_flag=%s issues=%d",
            task_id, agent_name, status, overall_score,
            output_quality_score, auto_flag, len(issues),
        )
        for issue in issues:
            logger.warning("  ISSUE: %s", issue)

        return verdict

    def evaluate_batch(self, envelopes: list[dict]) -> list[ExecutionVerdict]:
        """Evaluate a list of envelopes. Useful for auditing historical runs."""
        return [self.evaluate(env) for env in envelopes]

    def get_verdict_history(self) -> list[dict]:
        """Return all saved verdict JSON files from disk."""
        verdicts = []
        for f in sorted(self._verdicts_dir.glob("exec_verdict_*.json")):
            try:
                verdicts.append(json.loads(f.read_text()))
            except Exception:
                pass
        return verdicts

    def get_flagged_verdicts(self) -> list[dict]:
        """Return only verdicts with auto_flag=True from this session."""
        return [asdict(v) for v in self._verdicts if v.auto_flag]

    def summary_report(self) -> dict:
        """Summary stats for all verdicts evaluated this session."""
        if not self._verdicts:
            return {"total": 0, "message": "No verdicts yet."}

        scores     = [v.overall_score for v in self._verdicts]
        flagged    = [v for v in self._verdicts if v.auto_flag]
        all_issues = [i for v in self._verdicts for i in v.issues]

        issue_counts: dict[str, int] = {}
        for issue in all_issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        top_issues = sorted(issue_counts.items(), key=lambda x: -x[1])[:5]

        return {
            "total":         len(self._verdicts),
            "average_score": round(sum(scores) / len(scores), 2),
            "pass_rate":     round(len([s for s in scores if s >= 3]) / len(scores), 2),
            "flagged_count": len(flagged),
            "top_issues":    [{"issue": i, "count": c} for i, c in top_issues],
            "timestamp":     datetime.now(timezone.utc).isoformat(),
        }

    # ── Rule-based scoring ─────────────────────────────────────────────────────

    def _score_completion(self, status, errors, issues, recommendations) -> int:
        if status == "completed":
            if not errors:
                return 5
            elif len(errors) <= self.config.max_acceptable_errors:
                issues.append(f"Completed but had {len(errors)} error(s) during steps.")
                recommendations.append("Review step errors — some steps may have silently failed.")
                return 4
            else:
                issues.append(f"Completed but had {len(errors)} errors — too many step failures.")
                recommendations.append("Investigate recurring step failures and add retry logic.")
                return 3
        elif status in _REVIEW_STATUSES:
            return 3
        elif status == "escalated":
            issues.append("Task was escalated — executor could not handle it autonomously.")
            recommendations.append("Check if escalation_router is over-used for this task type.")
            return 2
        elif status == "failed":
            issues.append("Executor FAILED — task was not completed.")
            recommendations.append("Investigate root cause. Check errors list in envelope.")
            return 1
        else:
            issues.append(f"Unknown execution status: '{status}'.")
            recommendations.append("Ensure executor always sets a valid terminal status.")
            return 2

    def _score_timeliness(self, duration_sec, deadline_sec, status, issues, recommendations) -> int:
        if deadline_sec <= 0:
            return 3   # no deadline set — neutral
        if duration_sec <= 0:
            if status not in _SUCCESSFUL_STATUSES:
                issues.append("Task did not complete — no duration to measure.")
                return 1
            return 3

        ratio     = duration_sec / deadline_sec
        tolerance = 1.0 + self.config.deadline_tolerance_pct

        if status not in _SUCCESSFUL_STATUSES:
            if duration_sec > deadline_sec:
                issues.append(
                    f"Task failed AND exceeded deadline "
                    f"({duration_sec:.0f}s vs {deadline_sec:.0f}s)."
                )
                recommendations.append("High-priority tasks need faster executor paths.")
                return 1
            return 2

        if ratio < 0.8:      return 5
        elif ratio <= 1.0:   return 4
        elif ratio <= tolerance:
            issues.append(
                f"Slightly over deadline: {duration_sec:.0f}s vs {deadline_sec:.0f}s ({ratio:.0%})."
            )
            return 3
        else:
            issues.append(
                f"Deadline MISSED: {duration_sec:.0f}s vs {deadline_sec:.0f}s ({ratio:.0%})."
            )
            recommendations.append("Optimize slow steps or raise deadline for this task type.")
            return 2

    def _score_routing(self, agent_name, task_type, department, status, issues, recommendations) -> int:
        if agent_name == "unknown":
            issues.append("Agent name missing from envelope — cannot evaluate routing.")
            return 3

        expected = (
            task_type if task_type in _KNOWN_AGENTS
            else (self.config.expected_routing.get((task_type, department))
                  or self.config.expected_routing.get((task_type, "")))
        )

        if expected is None:
            return 3   # no expectation configured — neutral

        if agent_name == expected:
            return 5

        if agent_name == "escalation_router" and expected != "escalation_router":
            issues.append(
                f"Over-escalated: got 'escalation_router' but expected '{expected}' "
                f"for task_type='{task_type}'."
            )
            recommendations.append(
                f"Check routing_table.py — '{task_type}' should map to '{expected}'."
            )
            return 3

        issues.append(
            f"Wrong executor: got '{agent_name}' but expected '{expected}' "
            f"for task_type='{task_type}'."
        )
        recommendations.append(
            f"Fix routing_table.py to map '{task_type}' → '{expected}'."
        )
        return 1

    def _score_error_quality(self, errors, status, issues, recommendations) -> int:
        if not errors:
            if status == "failed":
                issues.append("Task FAILED but no errors were logged — silent failure.")
                recommendations.append("Ensure all exception paths write to execution.errors.")
                return 1
            return 5

        missing_step    = [e for e in errors if not e.get("step")]
        missing_message = [e for e in errors if not e.get("message")]
        quality_issues  = len(missing_step) + len(missing_message)

        if quality_issues == 0:
            return 4
        elif quality_issues <= 1:
            issues.append(f"{quality_issues} error(s) missing step name or message.")
            recommendations.append(
                "Ensure all errors include 'step', 'message', and 'timestamp'."
            )
            return 3
        else:
            issues.append(
                f"{quality_issues} error entries incomplete "
                f"(step={len(missing_step)}, msg={len(missing_message)})."
            )
            recommendations.append("Standardise error logging format across all step types.")
            return 2

    def _score_approval_gate(self, approval_mode, approval_action, status, issues, recommendations) -> int:
        requires_approval = approval_mode in {
            "single_confirm", "single_confirm_if_low_confidence", "manager_sign_off"
        }
        if approval_mode == "none":
            if status == "approval_pending":
                issues.append(
                    "approval=none but task ended in approval_pending — gate should not have fired."
                )
                recommendations.append(
                    "Check approval_gate.py — 'none' mode should never pause execution."
                )
                return 2
            return 5

        if requires_approval:
            if status in ("approval_pending",) or "approval_gate" in approval_action:
                return 5
            elif status == "completed":
                return 4
            else:
                issues.append(
                    f"Approval mode '{approval_mode}' but gate action unclear: "
                    f"'{approval_action[:80]}'."
                )
                return 3
        return 3

    # ── LLM scoring — output content quality (Groq) ───────────────────────────

    def _score_output_quality(
        self,
        envelope:    dict,
        task_type:   str,
        agent_name:  str,
        status:      str,
        issues:      list,
        recommendations: list,
    ) -> int:
        """
        Use Groq LLM to score the quality of what the executor actually produced.

        WHY LLM HERE (and not rule-based):
            Rule-based → "Did it send an email?"       (yes/no)
            LLM        → "Was the email well-written?" (needs understanding)

        Falls back to 3 (neutral) if:
        - No GROQ_API_KEY set
        - Task failed (nothing to evaluate)
        - No output content found in envelope steps
        """
        if status not in _SUCCESSFUL_STATUSES:
            return 3

        output_content = self._extract_output_content(envelope, agent_name)
        if not output_content:
            return 3

        if not self._client:
            logger.debug(
                "[output_quality] Skipped — no GROQ_API_KEY. "
                "Set it to enable LLM content scoring."
            )
            return 3

        request_text = envelope.get("raw_text", "") or envelope.get("intake", {}).get("request_text", "")
        prompt  = self._build_output_quality_prompt(task_type, agent_name, request_text, output_content)
        result  = self._call_llm(prompt)
        score   = max(1, min(5, int(result.get("score", 3))))
        reason  = result.get("reason", "")

        if score <= 2:
            issues.append(f"Output quality LOW (score={score}/5): {reason}")
            recommendations.append(
                result.get("improvement", "Review and improve output generation.")
            )
        elif score >= 4:
            logger.debug("[output_quality] High quality output (score=%d): %s", score, reason)

        return score

    # Output text can live under any of these keys in a step's data dict, across
    # all executor types (mirrors EmailDispatcher's body detection). Scanned
    # most-recent-step-first so the final produced artifact wins.
    _CONTENT_KEYS = (
        "body", "email_body", "rendered",
        "draft_email_reply", "draft_escalation_brief", "draft_report_ready", "draft_summary_ready",
        "summary", "content", "text", "message", "response", "assessment", "reasoning",
    )

    def _extract_output_content(self, envelope: dict, agent_name: str) -> str:
        """Extract the agent's produced text by scanning step data for known content keys."""
        steps = envelope.get("execution", {}).get("steps", {})

        for step in reversed(list(steps.values())):
            data = step.get("data", {})
            if not isinstance(data, dict):
                continue
            for key in self._CONTENT_KEYS:
                v = data.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()[:1000]

        # Last resort — stringify steps (truncated)
        if steps:
            return json.dumps(steps, default=str)[:500]
        return ""

    def _build_output_quality_prompt(
        self,
        task_type:      str,
        agent_name:     str,
        request_text:   str,
        output_content: str,
    ) -> str:
        return f"""You are a quality evaluator for an office workflow automation system.

A user submitted a request and an AI agent produced an output.
Evaluate whether the output is high quality, relevant, and helpful.

ORIGINAL REQUEST: "{request_text}"
TASK TYPE:        {task_type}
AGENT THAT RAN:   {agent_name}

AGENT OUTPUT:
{output_content}

EVALUATION CRITERIA:
- Is the output relevant to the original request?
- Is it professional and clear?
- Is it complete (the user gets a useful answer)?
- For emails: is the tone appropriate?
- For summaries: does it capture the key points?
- For decisions (leave, expense): is the reasoning clear?

Respond with ONLY valid JSON — no markdown, no preamble:
{{
  "score": <integer 1–5: 1=poor/irrelevant, 3=acceptable, 5=excellent>,
  "confidence": "<high | medium | low>",
  "reason": "<one sentence explaining your score>",
  "improvement": "<one sentence on how to improve — only needed if score <= 3>"
}}"""

    def _call_llm(self, prompt: str) -> dict:
        """Call Groq LLM with retry + fallback model. Returns neutral dict on failure."""
        _fallback = {
            "score": 3, "confidence": "low",
            "reason": "LLM evaluation unavailable.", "improvement": "",
        }
        if not self._client:
            return _fallback

        models = list(dict.fromkeys([self.config.primary_model, self.config.fallback_model]))

        for model in models:
            for attempt in range(3):
                try:
                    resp = self._client.chat.completions.create(
                        model       = model,
                        messages    = [{"role": "user", "content": prompt}],
                        max_tokens  = 200,
                        temperature = 0.1,
                    )
                    text   = resp.choices[0].message.content.strip()
                    text   = text.replace("```json", "").replace("```", "").strip()
                    result = json.loads(text)
                    logger.debug("[_call_llm] model=%s result=%s", model, result)
                    return result

                except json.JSONDecodeError as e:
                    logger.warning("[_call_llm] JSON parse error model=%s attempt=%d: %s", model, attempt + 1, e)
                    if attempt < 2:
                        time.sleep(1.0)

                except Exception as e:
                    err = str(e)
                    if "429" in err or "rate_limit" in err.lower():
                        wait = 2.0 * (attempt + 1)
                        logger.warning("[_call_llm] Rate limited model=%s, waiting %.1fs...", model, wait)
                        time.sleep(wait)
                    elif "404" in err or "model_not_found" in err.lower():
                        logger.warning("[_call_llm] Model '%s' not found — trying next.", model)
                        break
                    elif "401" in err or "403" in err:
                        logger.error("[_call_llm] Auth error — check GROQ_API_KEY.")
                        return _fallback
                    else:
                        logger.warning("[_call_llm] model=%s attempt=%d error: %s", model, attempt + 1, e)
                        if attempt < 2:
                            time.sleep(1.0)

        logger.error("[_call_llm] All models failed — returning neutral score.")
        return _fallback

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _calc_duration(self, started_at: str, completed_at: str) -> float:
        if not started_at or not completed_at:
            return 0.0
        try:
            start = datetime.fromisoformat(started_at)
            end   = datetime.fromisoformat(completed_at)
            return max(0.0, (end - start).total_seconds())
        except (ValueError, TypeError):
            return 0.0

    def _save_verdict(self, verdict: ExecutionVerdict) -> None:
        self._verdicts.append(verdict)
        filename = (
            f"exec_verdict_{verdict.task_id}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S%f')}.json"
        )
        path = self._verdicts_dir / filename
        try:
            path.write_text(json.dumps(asdict(verdict), indent=2))
            logger.debug("Verdict saved → %s", path)
        except Exception as e:
            logger.warning("Could not save verdict: %s", e)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

def create_execution_judge(
    verdicts_dir: str = "agents/feedback_loop/output/execution_verdicts",
) -> ExecutionJudge:
    """Create an ExecutionJudge with default config. Simplest entry point."""
    config = ExecutionJudgeConfig(verdicts_dir=verdicts_dir)
    return ExecutionJudge(config)