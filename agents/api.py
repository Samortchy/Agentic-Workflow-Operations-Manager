"""
api.py — FastAPI server that exposes the pipeline as a REST endpoint.

Place this file at your project root (same level as main_pipeline/).

Usage:
    pip install fastapi uvicorn
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload

Then set API_URL=http://localhost:8000 in your Express environment.
"""

import sys
import traceback    
import os

# ── path bootstrap (mirrors pipeline.py) ────────────────────────────────────
_ROOT = os.path.abspath(os.path.dirname(__file__))
_TASK_AGENT_DIR = os.path.join(_ROOT, "task_agent")

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _TASK_AGENT_DIR not in sys.path:
    sys.path.insert(0, _TASK_AGENT_DIR)
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from main_pipeline.pipeline import run_pipeline
from execution_agent.orchestration_agent.orchestrator import Orchestrator

_orchestrator = Orchestrator()

app = FastAPI(title="AWOM Pipeline API", version="1.0.0")

# Allow the Express front-end (and local dev) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your Express origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── request / response models ────────────────────────────────────────────────

class PipelineRequest(BaseModel):
    raw_text: str


# ── endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Quick liveness check — Express can poll this on startup."""
    return {"status": "ok"}


@app.post("/api/pipeline")
def pipeline(body: PipelineRequest):
    """
    Run raw e-mail / request text through the full three-agent pipeline.

    Returns the fully-populated envelope as a JSON object.
    The shape matches what the Express mock already returns, so the
    front-end needs zero changes.
    """
    if not body.raw_text or not body.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text must not be empty")

    try:
        result = run_pipeline(body.raw_text)
    except Exception as exc:
        # Surface pipeline errors as 500 so Express falls back to mock if needed
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@app.post("/api/orchestrate")
def orchestrate(body: PipelineRequest):
    """
    Run raw text through the full pipeline AND automatically execute the
    appropriate agent.

    - Autonomous tasks are routed to the best-matching execution agent.
    - Non-autonomous tasks are written to output/review_queue/ and returned
      with execution.status = "queued_for_review".
    - Unknown task types fall back to the escalation router.

    Returns the complete envelope including the execution section.
    """
    if not body.raw_text or not body.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text must not be empty")

    try:
        result = _orchestrator.run(body.raw_text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@app.get("/api/envelopes")
def envelopes():
    """
    Optional: if you later want to serve a list of processed envelopes
    from a database, implement it here. For now returns an empty list
    so Express falls back to MOCK_ENVELOPES gracefully.
    """
    return []


