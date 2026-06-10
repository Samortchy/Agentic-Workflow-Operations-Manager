"""
orchestrator.py — ties Phase 1 (pipeline) and Phase 2 (execution agents) together.

Flow
----
1. Run raw text through the three-agent main pipeline (intake → task → priority).
2. Register the resulting task in the Node.js backend (status=queued).
3. Inspect the envelope:
   - isAutonomous == True  → route to the matching execution agent and run it.
   - isAutonomous == False → update task status to pending_human_review and return.
4. If no execution agent matches, fall back to escalation_router.
5. Write execution results back to the backend when done.
"""

import logging
from datetime import datetime, timezone

from main_pipeline.pipeline import run_pipeline
from ..executors.core.base_agent import ExecutionRunner
from ..executors.core import backend_client as bc
from ..executors.core.eval_hook import evaluate_and_record, judge_classification_and_record
from .routing_table import resolve_agent_name

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Single entry point for the full autonomous workflow.

    Usage
    -----
        orch = Orchestrator()
        result = orch.run("Can you check how many leave days I have left?")
    """

    @staticmethod
    def _is_truthy(val) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() == "true"
        return bool(val)

    def run(self, raw_text: str, company_id: str | None = None) -> dict:
        if not raw_text or not raw_text.strip():
            raise ValueError("raw_text must not be empty")

        cid = company_id or bc.get_company_id()

        # ── Phase 1 ───────────────────────────────────────────────────────────
        envelope = run_pipeline(raw_text)

        task_id = envelope.get("task", {}).get("task_id")

        # Register task in backend
        if not cid:
            raise RuntimeError(
                "No company_id available. Register at http://localhost:3000/register "
                "or pass company_id to Orchestrator.run()."
            )
        if task_id:
            try:
                bc.create_task(envelope, cid)
                logger.info("Registered task %s in backend", task_id)
            except Exception as e:
                logger.warning("Task registration failed: %s", e)

        # Inject context so steps can read company_id/task_id
        envelope["_ctx"] = {"company_id": cid, "task_id": task_id}

        # Classification eval (safe mode) — judge intake/priority labels, record a
        # classification_eval signal + needs_review flag (labeling only, no retraining).
        judge_classification_and_record(envelope, task_id=task_id, company_id=cid)

        is_autonomous = (
            self._is_truthy(envelope.get("task", {}).get("isAutonomous", False))
            and self._is_truthy(envelope.get("intake", {}).get("isAutonomous", False))
        )
        task_type  = envelope.get("intake", {}).get("task_type", "")
        department = envelope.get("intake", {}).get("department", "")

        logger.info(
            "Orchestrator: task_id=%s task_type=%r department=%s autonomous=%s",
            task_id, task_type, department, is_autonomous,
        )

        # ── Non-autonomous → pending human review ─────────────────────────────
        if not is_autonomous:
            reason = envelope.get("intake", {}).get("reasoning", "not_autonomous")
            return self._queue_for_review(envelope, task_id, cid, reason)

        # ── Autonomous → execute ──────────────────────────────────────────────
        agent_name = resolve_agent_name(task_type, department, envelope)
        return self._execute(envelope, agent_name, task_id, cid)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _execute(self, envelope: dict, agent_name: str, task_id: str | None, company_id: str | None) -> dict:
        logger.info("Running execution agent: %s", agent_name)
        try:
            if task_id and company_id:
                bc.update_task_status(task_id, "in_progress", agent_name=agent_name)
                bc.create_audit_log(agent_name, "task_picked_up", task_id, company_id)

            config = bc.get_agent_config(agent_name, company_id=company_id)
            runner = ExecutionRunner(config, task_id=task_id)
            result = runner.execute(envelope)

            execution     = result.get("execution", {})
            final_status  = execution.get("status", "completed")
            backend_status = final_status if final_status in (
                "completed", "escalated", "failed", "approval_pending"
            ) else "completed"

            if task_id:
                try:
                    bc.update_task_envelope(task_id, execution)
                    bc.update_task_status(task_id, backend_status, agent_name=agent_name)
                except Exception as e:
                    logger.warning("Failed to write results to backend: %s", e)

            # Score the finished run → outcome_signals (best-effort; never breaks the run)
            evaluate_and_record(result, task_id=task_id, company_id=company_id)

            return result

        except Exception as exc:
            logger.error("Execution agent failed: %s", exc)
            if task_id:
                try:
                    bc.update_task_status(task_id, "failed")
                    bc.create_audit_log(agent_name, "agent_failed", task_id, company_id, details={"error": str(exc)})
                except Exception:
                    pass
            execution = envelope.setdefault("execution", {})
            execution["status"]    = "failed"
            execution["error"]     = str(exc)
            execution["failed_at"] = datetime.now(timezone.utc).isoformat()
            return envelope

    def _queue_for_review(self, envelope: dict, task_id: str | None, company_id: str | None, reason: str) -> dict:
        execution = envelope.setdefault("execution", {})
        execution["status"]        = "pending_human_review"
        execution["review_reason"] = reason
        execution["queued_at"]     = datetime.now(timezone.utc).isoformat()

        if task_id:
            try:
                bc.update_task_status(task_id, "pending_human_review")
                bc.update_task_envelope(task_id, execution)
                logger.info("Task %s marked pending_human_review", task_id)
            except Exception as e:
                logger.warning("Failed to update task in backend: %s", e)

        return envelope
