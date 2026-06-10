"""
eval_hook.py — score a finished execution run and persist the verdict.

Runs the (existing) ExecutionJudge on a completed envelope and writes the result to
the backend `outcome_signals` table as a `signal_type="execution_eval"` signal, so the
Phase-5 dashboard can read per-run scores. The judge also keeps its local JSON verdict.

Design notes
------------
- Best-effort: every path is wrapped — eval must NEVER break task execution.
- Only **terminal** runs are scored (completed/failed/escalated); approval_pending and
  pending_human_review are skipped (the run isn't done yet).
- `execution_judge.py` is loaded **standalone via importlib** to avoid triggering
  `feedback_agent/__init__.py`, which eager-imports the heavy ML learning agent (sklearn)
  that we deliberately deferred (PLAN.md Phase 3).
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from . import backend_client as bc

logger = logging.getLogger("eval_hook")

_TERMINAL_STATUSES = {"completed", "failed", "escalated"}
_AGENTS_ROOT = Path(__file__).parents[3]          # core → executors → execution_agent → agents
_JUDGE_PATH  = _AGENTS_ROOT / "feedback_agent" / "execution_judge.py"
_VERDICTS_DIR = str(_AGENTS_ROOT / "feedback_agent" / "output" / "execution_verdicts")
_CLS_JUDGE_PATH    = _AGENTS_ROOT / "feedback_agent" / "judge_agent.py"
_CLS_VERDICTS_DIR  = str(_AGENTS_ROOT / "feedback_agent" / "output" / "judge_verdicts")

_judge = None      # lazy singleton — ExecutionJudge
_cls_judge = None  # lazy singleton — classification JudgeAgent


def _get_judge():
    """Lazily build a single ExecutionJudge, loading the module without its package __init__."""
    global _judge
    if _judge is None:
        name = "execution_judge_standalone"
        spec = importlib.util.spec_from_file_location(name, _JUDGE_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod   # dataclasses needs the module registered before exec
        spec.loader.exec_module(mod)
        _judge = mod.ExecutionJudge(mod.ExecutionJudgeConfig(verdicts_dir=_VERDICTS_DIR))
    return _judge


def evaluate_and_record(envelope: dict, task_id: str | None = None, company_id: str | None = None) -> None:
    """Score a finished run and persist an `execution_eval` outcome signal. Never raises."""
    try:
        execution = envelope.get("execution", {})
        status = execution.get("status", "")
        if status not in _TERMINAL_STATUSES:
            return  # not done yet (e.g. approval_pending) — eval after the final resume

        tid = (task_id or envelope.get("task", {}).get("task_id")
               or envelope.get("_ctx", {}).get("task_id"))
        cid = (company_id or envelope.get("_ctx", {}).get("company_id") or bc.get_company_id())

        verdict = _get_judge().evaluate(envelope, task_id=tid or "")
        overall = getattr(verdict, "overall_score", 0)
        signal_verdict = "success" if overall >= 3 else "failure"

        if not tid:
            logger.info("[EVAL] overall=%s/5 verdict=%s (no task_id — not persisted)", overall, signal_verdict)
            return

        value = asdict(verdict)
        value["signal_verdict"] = signal_verdict  # success/failure (outcome_signals.verdict lives in jsonb for now)

        bc.create_outcome_signal(
            task_id=tid,
            signal_type="execution_eval",
            value=value,
            company_id=cid,
        )
        logger.info("[EVAL] task=%s overall=%s/5 verdict=%s auto_flag=%s",
                    tid, overall, signal_verdict, getattr(verdict, "auto_flag", None))

    except Exception as e:
        logger.warning("eval_hook: evaluation/persist skipped (%s)", e)


def _get_classifier():
    """Lazily build the classification JudgeAgent (loaded standalone, no package __init__)."""
    global _cls_judge
    if _cls_judge is None:
        name = "classification_judge_standalone"
        spec = importlib.util.spec_from_file_location(name, _CLS_JUDGE_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        _cls_judge = mod.JudgeAgent(mod.JudgeConfig(verdicts_dir=_CLS_VERDICTS_DIR))
    return _cls_judge


def _differs(suggested: str, predicted: str) -> bool:
    s = (suggested or "").strip().lower()
    p = (predicted or "").strip().lower()
    return bool(s) and s != p


def judge_classification_and_record(envelope: dict, task_id: str | None = None,
                                    company_id: str | None = None) -> None:
    """
    Safe-mode classification eval (Phase-3 / labeling): score whether Intake's
    department and Priority's label fit the request, store the judge's suggested
    labels + a `needs_review` flag as a `classification_eval` outcome signal.

    Labeling only — it does NOT retrain any model and never raises into the pipeline.
    """
    # Opt-out switch (used to cut Groq load during bulk execution-judge eval runs).
    if os.getenv("AWOM_SKIP_CLS_EVAL") == "1":
        return
    try:
        intake    = envelope.get("intake", {})
        priority  = envelope.get("priority", {})
        execution = envelope.get("execution", {})
        raw_text  = envelope.get("raw_text", "")

        tid = (task_id or envelope.get("task", {}).get("task_id")
               or envelope.get("_ctx", {}).get("task_id"))
        cid = (company_id or envelope.get("_ctx", {}).get("company_id") or bc.get_company_id())

        pred_dept  = intake.get("department", "")
        pred_label = priority.get("priority_label", "")
        task_type  = intake.get("task_type", "")

        judge = _get_classifier()
        i_v = judge.evaluate_intake(task_id=tid or "", request_text=raw_text, predicted_type=pred_dept)
        p_v = judge.evaluate_priority(
            task_id=tid or "", request_text=raw_text, task_type=task_type,
            predicted_priority=pred_label, status=execution.get("status", "unknown"),
            duration_seconds=0.0, deadline_seconds=0.0, retries=0,
        )

        # Flag for review on a low score, or a confident disagreement (ignore the
        # low-confidence/no-key fallback so it doesn't flag everything).
        needs_review = (
            i_v.score <= 2 or p_v.score <= 2
            or (i_v.confidence != "low" and _differs(i_v.suggested_value, pred_dept))
            or (p_v.confidence != "low" and _differs(p_v.suggested_value, pred_label))
        )

        value = {
            "intake":   {"predicted": pred_dept,  "suggested": i_v.suggested_value,
                         "score": i_v.score, "confidence": i_v.confidence, "reason": i_v.reason},
            "priority": {"predicted": pred_label, "suggested": p_v.suggested_value,
                         "score": p_v.score, "confidence": p_v.confidence, "reason": p_v.reason},
            "task_type": task_type,
            "needs_review": needs_review,   # human should confirm/correct the labels
        }

        if not tid:
            logger.info("[CLS-EVAL] needs_review=%s (no task_id — not persisted)", needs_review)
            return

        bc.create_outcome_signal(task_id=tid, signal_type="classification_eval",
                                 value=value, company_id=cid)
        logger.info("[CLS-EVAL] task=%s dept(%s->%s s%s) prio(%s->%s s%s) needs_review=%s",
                    tid, pred_dept, i_v.suggested_value, i_v.score,
                    pred_label, p_v.suggested_value, p_v.score, needs_review)

    except Exception as e:
        logger.warning("eval_hook: classification eval skipped (%s)", e)
