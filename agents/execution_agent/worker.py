"""
worker.py — polls the Node.js backend for queued tasks and executes them.

Run from the agents/ directory:
    python -m execution_agent.worker

The worker picks up tasks with status=queued, runs them through the appropriate
execution agent (config loaded from the backend DB), and writes all results back.
"""

import sys
from pathlib import Path

# ssl_patch must run before any HTTP client import
_AGENTS_DIR_EARLY = Path(__file__).parent.parent
if str(_AGENTS_DIR_EARLY) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR_EARLY))
import ssl_patch  # noqa: F401

import logging
import time

# ── path bootstrap ────────────────────────────────────────────────────────────
# agents/            — top-level root; execution_agent, main_pipeline importable
# agents/task_agent/ — llm_provider importable (flat package)
_AGENTS_DIR     = Path(__file__).parent.parent
_TASK_AGENT_DIR = _AGENTS_DIR / "task_agent"
for _p in [str(_AGENTS_DIR), str(_TASK_AGENT_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)
# ─────────────────────────────────────────────────────────────────────────────

from execution_agent.executors.core import backend_client as bc
from execution_agent.orchestration_agent.routing_table import resolve_agent_name
from execution_agent.executors.core.base_agent import ExecutionRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

POLL_INTERVAL = 5  # seconds between polls
_PROCESSING: set[str] = set()  # guard against double-processing


def process_task(task: dict) -> None:
    task_id    = task.get("task_id", "")
    company_id = task.get("company_id", "")
    envelope   = task.get("envelope") or {}

    if task_id in _PROCESSING:
        return
    _PROCESSING.add(task_id)

    try:
        _run(task_id, company_id, envelope)
    finally:
        _PROCESSING.discard(task_id)


def _run(task_id: str, company_id: str, envelope: dict) -> None:
    # Inject context so steps (file_dispatcher, db_extractor, etc.) can read it
    envelope["_ctx"] = {"company_id": company_id, "task_id": task_id}

    # Validate required envelope sections
    for section in ("intake", "task", "priority"):
        if section not in envelope:
            logger.error("Task %s missing section '%s' — marking failed", task_id, section)
            _fail(task_id, company_id, "unknown", f"Missing envelope section: {section}")
            return

    is_resume  = bool(envelope.get("resume"))
    task_type  = envelope.get("intake", {}).get("task_type", "")
    department = envelope.get("intake", {}).get("department", "")

    # On resume, agent_name is already stored in execution section
    if is_resume:
        agent_name = envelope.get("execution", {}).get("agent_name") or "escalation_router"
        logger.info("Resuming task %s → agent=%s", task_id, agent_name)
    else:
        agent_name = resolve_agent_name(task_type, department, envelope)
        logger.info("Processing task %s → agent=%s (type=%s dept=%s)",
                    task_id, agent_name, task_type, department)

    # Mark in-progress
    try:
        bc.update_task_status(task_id, "in_progress", agent_name=agent_name)
        bc.create_audit_log(agent_name, "task_picked_up", task_id, company_id,
                            details={"task_type": task_type, "department": department})
    except Exception as e:
        logger.warning("Could not update task status: %s", e)

    # Fetch config from backend DB
    try:
        config = bc.get_agent_config(agent_name, company_id=company_id)
    except Exception as e:
        logger.error("Config fetch failed for agent '%s': %s", agent_name, e)
        _fail(task_id, company_id, agent_name, str(e))
        return

    # Execute
    try:
        runner = ExecutionRunner(config, task_id=task_id)
        result = runner.execute(envelope)
    except Exception as e:
        logger.error("Execution error for task %s: %s", task_id, e)
        _fail(task_id, company_id, agent_name, str(e))
        return

    # Write results back to backend
    execution     = result.get("execution", {})
    final_status  = execution.get("status", "completed")
    backend_status = final_status if final_status in {
        "completed", "escalated", "failed", "approval_pending", "pending_human_review"
    } else "completed"

    try:
        bc.update_task_envelope(task_id, execution)
        bc.update_task_status(task_id, backend_status, agent_name=agent_name)
        logger.info("Task %s → %s", task_id, backend_status)
    except Exception as e:
        logger.error("Failed to write results for task %s: %s", task_id, e)


def _fail(task_id: str, company_id: str, agent_name: str, error: str) -> None:
    try:
        bc.update_task_status(task_id, "failed")
        bc.create_audit_log(agent_name, "agent_failed", task_id, company_id,
                            details={"error": error})
    except Exception as e:
        logger.error("Could not mark task %s as failed: %s", task_id, e)


def poll_forever() -> None:
    logger.info("Worker started — backend=%s  poll_interval=%ds",
                bc.BACKEND_URL, POLL_INTERVAL)

    while True:
        try:
            tasks = bc.get_queued_tasks()
            for task in tasks:
                process_task(task)
        except Exception as e:
            logger.error("Poll cycle error: %s", e)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    poll_forever()
