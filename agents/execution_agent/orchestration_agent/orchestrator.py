"""
orchestrator.py — ties Phase 1 (pipeline) and Phase 2 (execution agents) together.

Flow
----
1. Run raw text through the three-agent main pipeline (intake → task → priority).
2. Inspect the envelope:
   - isAutonomous == True  → look up the matching execution agent and run it.
   - isAutonomous == False → write to the human-review queue and return.
3. If no execution agent matches the task_type, fall back to the escalation router.
4. If the execution agent itself raises, mark the envelope failed and return it.
"""

#import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# # ── sys.path bootstrap ────────────────────────────────────────────────────────
# # agents/   → main_pipeline, task_agent, orchestration_agent are importable
# # executors/ → core.* and steps.* packages are importable by the runner
_AGENTS_DIR    = Path(__file__).parent
_EXECUTORS_DIR = _AGENTS_DIR  / "executors"
# _TASK_AGENT_DIR = _AGENTS_DIR / "task_agent"

# for _p in [str(_AGENTS_DIR), str(_TASK_AGENT_DIR), str(_EXECUTORS_DIR)]:
#     if _p not in sys.path:
#         sys.path.insert(0, _p)
# ─────────────────────────────────────────────────────────────────────────────

from main_pipeline.pipeline import run_pipeline          # Phase 1
from ..executors.core.base_agent import ExecutionRunner              # Phase 2 runner
from .routing_table import resolve_config

_ESCALATION_CONFIG = _EXECUTORS_DIR / "configs" / "01_escalation_router.json"
_REVIEW_QUEUE_DIR  = _AGENTS_DIR.parent / "output" / "review_queue"


class Orchestrator:
    """
    Single entry point for the full autonomous workflow.

    Usage
    -----
        orch = Orchestrator()
        result = orch.run("Can you check how many leave days I have left?")
        # result is the complete envelope dict with intake + task + priority + execution
    """

    @staticmethod
    def _is_truthy(val) -> bool:
        """Normalise isAutonomous values — the LLM occasionally returns the
        string "true"/"false" instead of a JSON boolean."""
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() == "true"
        return bool(val)

    def run(self, raw_text: str) -> dict:
        if not raw_text or not raw_text.strip():
            raise ValueError("raw_text must not be empty")

        # ── Phase 1: classify, structure, prioritize ──────────────────────────
        envelope = run_pipeline(raw_text)

        is_autonomous = (
            self._is_truthy(envelope.get("task", {}).get("isAutonomous", False))
            and self._is_truthy(envelope.get("intake", {}).get("isAutonomous", False))
        )
        task_type  = envelope.get("intake", {}).get("task_type", "")
        department = envelope.get("intake", {}).get("department", "")

        logger.info(
            "Orchestrator: envelope_id=%s task_type=%r department=%s autonomous=%s",
            envelope.get("envelope_id"), task_type, department, is_autonomous,
        )

        # ── Phase 2a: non-autonomous → human review queue ────────────────────
        if not is_autonomous:
            reason = envelope.get("intake", {}).get("reasoning", "not_autonomous")
            return self._queue_for_review(envelope, reason)

        # ── Phase 2b: resolve execution agent ────────────────────────────────
        config_path = resolve_config(task_type, department, envelope)

        if config_path is None or not config_path.exists():
            logger.warning(
                "No execution agent matched task_type=%r / department=%s — "
                "routing to escalation_router",
                task_type, department,
            )
            config_path = _ESCALATION_CONFIG

        return self._execute(envelope, config_path)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _execute(self, envelope: dict, config_path: Path) -> dict:
        logger.info("Running execution agent: %s", config_path.name)
        try:
            runner = ExecutionRunner(str(config_path))
            return runner.execute(envelope)
        except Exception as exc:
            logger.error("Execution agent failed: %s", exc)
            execution = envelope.setdefault("execution", {})
            execution["status"]    = "failed"
            execution["error"]     = str(exc)
            execution["failed_at"] = datetime.now(timezone.utc).isoformat()
            return envelope

    def _queue_for_review(self, envelope: dict, reason: str) -> dict:
        execution = envelope.setdefault("execution", {})
        execution["status"]        = "queued_for_review"
        execution["review_reason"] = reason
        execution["queued_at"]     = datetime.now(timezone.utc).isoformat()

        task_id = (
            envelope.get("task", {}).get("task_id")
            or envelope.get("envelope_id", "unknown")
        )

        _REVIEW_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        queue_file = _REVIEW_QUEUE_DIR / f"{task_id}.json"
        queue_file.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        logger.info("Queued for human review → %s", queue_file)

        return envelope
