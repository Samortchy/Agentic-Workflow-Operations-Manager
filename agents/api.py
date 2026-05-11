"""
api.py — FastAPI server exposing the pipeline as a REST endpoint.

Phase 1 (/api/pipeline): classifies, structures, and prioritises incoming text,
then registers the resulting task in the Node.js backend.

Phase 2 is handled by the polling worker (execution_agent/worker.py).

Usage:
    cd agents/
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

import ssl_patch  # noqa: F401 — must be first; disables SSL verification on Windows

import logging
import os
import sys

_ROOT = os.path.abspath(os.path.dirname(__file__))
_TASK_AGENT_DIR = os.path.join(_ROOT, "task_agent")
for _p in [_ROOT, _TASK_AGENT_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from main_pipeline.pipeline import run_pipeline
from execution_agent.orchestration_agent.orchestrator import Orchestrator
from execution_agent.executors.core.base_agent import ExecutionRunner
from execution_agent.executors.core import backend_client as bc

logger = logging.getLogger(__name__)
_orchestrator = Orchestrator()

app = FastAPI(title="AWOM Pipeline API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PipelineRequest(BaseModel):
    raw_text:   str
    company_id: str | None = None  # optional override; falls back to env / auto-discovery


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/pipeline")
def pipeline(body: PipelineRequest):
    """
    Run raw text through Phase 1 (intake → task → priority).
    Registers the resulting task in the Node.js backend (status=queued).
    Returns the full envelope — the worker will pick it up and execute.
    """
    if not body.raw_text or not body.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text must not be empty")

    try:
        envelope = run_pipeline(body.raw_text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Register task in backend
    company_id = body.company_id or bc.get_company_id()
    if not company_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "No company found in the backend. "
                "Register your company at http://localhost:3000/register first, "
                "or pass company_id explicitly in the request body."
            ),
        )

    try:
        bc.create_task(envelope, company_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline succeeded but task registration failed: {exc}",
        )

    return envelope


@app.post("/api/orchestrate")
def orchestrate(body: PipelineRequest):
    """
    Run Phase 1 AND immediately execute Phase 2 in-process.
    Useful for testing or single-shot flows without the worker.
    Results are written back to the backend before returning.
    """
    if not body.raw_text or not body.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text must not be empty")

    try:
        result = _orchestrator.run(body.raw_text, company_id=body.company_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@app.post("/api/confirm")
def confirm(body: dict):
    """
    Resume an approval_pending envelope after the user confirms in the frontend.
    The runner skips the approval gate (execution.status already == "approval_pending")
    and continues from the first dispatcher step.
    Config is fetched from the backend DB — no local JSON files needed.
    """
    envelope = body
    status   = envelope.get("execution", {}).get("status")
    if status != "approval_pending":
        raise HTTPException(
            status_code=400,
            detail=f"Expected approval_pending, got '{status}'.",
        )

    agent_name = envelope.get("execution", {}).get("agent_name", "")
    if not agent_name:
        raise HTTPException(status_code=400, detail="execution.agent_name is missing.")

    task_id    = envelope.get("task", {}).get("task_id") or envelope.get("_ctx", {}).get("task_id")
    company_id = envelope.get("_ctx", {}).get("company_id") or bc.get_company_id()

    try:
        config = bc.get_agent_config(agent_name, company_id=company_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Config not found for '{agent_name}': {exc}")

    try:
        runner = ExecutionRunner(config, task_id=task_id)
        result = runner.execute(envelope)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Write results back to backend
    if task_id:
        execution = result.get("execution", {})
        try:
            bc.update_task_envelope(task_id, execution)
            bc.update_task_status(task_id, execution.get("status", "completed"), agent_name=agent_name)
        except Exception as e:
            logger.warning("Failed to write confirm results to backend: %s", e)

    return result


@app.get("/api/envelopes")
def envelopes():
    return []
