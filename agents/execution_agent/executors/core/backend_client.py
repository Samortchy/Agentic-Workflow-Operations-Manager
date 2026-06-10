"""
backend_client.py — HTTP client for the Node.js backend + Supabase Storage.

All Python agents call this module to interact with the backend.
Loaded once at import time; env vars sourced from the root .env.
"""

import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parents[4] / ".env", override=False)

logger = logging.getLogger(__name__)

BACKEND_URL     = os.environ.get("BACKEND_URL", "http://localhost:4000").rstrip("/")
SUPABASE_URL    = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY    = os.environ.get("SUPABASE_SERVICE_KEY", "")
AGENT_API_KEY   = os.environ.get("AGENT_API_KEY", "")
STORAGE_BUCKET  = "task-outputs"

# Agents authenticate to the backend with the shared agent key (x-agent-api-key).
_HEADERS = {"Content-Type": "application/json"}
if AGENT_API_KEY:
    _HEADERS["x-agent-api-key"] = AGENT_API_KEY
_TIMEOUT = 15  # seconds for regular calls
_UPLOAD_TIMEOUT = 60  # seconds for file uploads

_company_id_cache: str | None = None


# ── Company discovery ─────────────────────────────────────────────────────────

def get_company_id() -> str | None:
    """Return the company UUID — from env, cache, or auto-discovered from backend."""
    global _company_id_cache
    if _company_id_cache:
        return _company_id_cache

    env_id = os.environ.get("COMPANY_ID", "").strip()
    if env_id:
        _company_id_cache = env_id
        return _company_id_cache

    try:
        r = requests.get(f"{BACKEND_URL}/api/companies", headers=_HEADERS, timeout=5)
        if r.ok:
            companies = r.json()
            if companies:
                _company_id_cache = companies[0].get("company_id")
                logger.info("Auto-discovered company_id: %s", _company_id_cache)
                return _company_id_cache
    except Exception as e:
        logger.warning("company_id auto-discovery failed: %s", e)

    return None


# ── Tasks ─────────────────────────────────────────────────────────────────────

def get_queued_tasks() -> list[dict]:
    """Poll backend for tasks with status=queued."""
    r = requests.get(
        f"{BACKEND_URL}/api/tasks",
        params={"status": "queued"},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("tasks", [])


def create_task(envelope: dict, company_id: str) -> dict:
    """Register a Phase 1 envelope as a new task (status=queued)."""
    body = {**envelope, "company_id": company_id}
    r = requests.post(
        f"{BACKEND_URL}/api/tasks",
        json=body,
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def update_task_status(task_id: str, status: str, agent_name: str | None = None) -> dict:
    """PATCH /api/tasks/:id/status"""
    body: dict = {"status": status}
    if agent_name:
        body["agent_name"] = agent_name
    r = requests.patch(
        f"{BACKEND_URL}/api/tasks/{task_id}/status",
        json=body,
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def update_task_envelope(task_id: str, execution: dict) -> dict:
    """PATCH /api/tasks/:id/envelope — appends execution section."""
    r = requests.patch(
        f"{BACKEND_URL}/api/tasks/{task_id}/envelope",
        json={"execution": execution},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def register_output_file(task_id: str, file_path: str, file_type: str) -> dict:
    """PATCH /api/tasks/:id/output-files"""
    r = requests.patch(
        f"{BACKEND_URL}/api/tasks/{task_id}/output-files",
        json={"file_path": file_path, "file_type": file_type},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ── Agent configs ─────────────────────────────────────────────────────────────

def get_agent_config(agent_name: str, company_id: str | None = None) -> dict:
    """
    GET /api/agent-configs/active/:agent_name
    Returns the config dict stored in the DB (the inner .config field).
    """
    cid = company_id or get_company_id()
    params = {}
    if cid:
        params["company_id"] = cid

    r = requests.get(
        f"{BACKEND_URL}/api/agent-configs/active/{agent_name}",
        params=params,
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    # The backend returns the full record; the agent needs the inner .config object
    return data.get("config") if isinstance(data.get("config"), dict) else data


# ── Audit logs ────────────────────────────────────────────────────────────────

def create_audit_log(
    agent_name: str,
    event_type: str,
    task_id: str | None = None,
    company_id: str | None = None,
    actor: str = "system",
    details: dict | None = None,
) -> dict:
    """POST /api/audit-logs"""
    body: dict = {
        "agent_name": agent_name,
        "event_type":  event_type,
        "actor":       actor,
        "details":     details or {},
        "company_id":  company_id or get_company_id(),
    }
    if task_id:
        body["task_id"] = task_id
    r = requests.post(
        f"{BACKEND_URL}/api/audit-logs",
        json=body,
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ── Approvals ─────────────────────────────────────────────────────────────────

def create_approval(
    task_id: str,
    agent_name: str,
    command_preview: str,
    required_level: int,
    approval_type: str,
    company_id: str | None = None,
    context: dict | None = None,
    timeout_minutes: int = 60,
) -> dict:
    """POST /api/approvals"""
    body = {
        "task_id":        task_id,
        "agent_name":     agent_name,
        "command_preview": command_preview,
        "required_level": required_level,
        "approval_type":  approval_type,
        "context":        context or {},
        "timeout_minutes": timeout_minutes,
        "company_id":     company_id or get_company_id(),
    }
    r = requests.post(
        f"{BACKEND_URL}/api/approvals",
        json=body,
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ── Outcome signals ───────────────────────────────────────────────────────────

def create_outcome_signal(
    task_id: str,
    signal_type: str,
    value: dict | None = None,
    company_id: str | None = None,
) -> dict:
    """POST /api/outcome-signals"""
    body = {
        "task_id":     task_id,
        "signal_type": signal_type,
        "value":       value or {},
        "company_id":  company_id or get_company_id(),
    }
    r = requests.post(
        f"{BACKEND_URL}/api/outcome-signals",
        json=body,
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ── Employees ─────────────────────────────────────────────────────────────────

def get_employees(
    department: str | None = None,
    company_id: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    """
    GET /api/employees — optionally filtered by department. Used to resolve
    meeting participants from the company directory.
    """
    params: dict = {"company_id": company_id or get_company_id()}
    if department:
        params["department"] = department
    if active_only:
        params["is_active"] = "true"
    r = requests.get(
        f"{BACKEND_URL}/api/employees", params=params, headers=_HEADERS, timeout=_TIMEOUT
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("employees", [])


# ── Meetings ──────────────────────────────────────────────────────────────────

def create_meeting(
    title: str,
    participants: list[str],
    proposed_slots: list,
    task_id: str | None = None,
    organizer_email: str | None = None,
    confirmed_slot: str | None = None,
    status: str = "proposed",
    company_id: str | None = None,
) -> dict:
    """POST /api/meetings — persist a proposed (or confirmed) meeting."""
    body = {
        "company_id":      company_id or get_company_id(),
        "task_id":         task_id,
        "title":           title,
        "organizer_email": organizer_email,
        "participants":    participants,
        "proposed_slots":  proposed_slots,
        "confirmed_slot":  confirmed_slot,
        "status":          status,
    }
    r = requests.post(
        f"{BACKEND_URL}/api/meetings", json=body, headers=_HEADERS, timeout=_TIMEOUT
    )
    r.raise_for_status()
    return r.json()


def get_meetings(status: str | None = None, company_id: str | None = None) -> list[dict]:
    """GET /api/meetings — optionally filtered by status."""
    params: dict = {"company_id": company_id or get_company_id()}
    if status:
        params["status"] = status
    r = requests.get(
        f"{BACKEND_URL}/api/meetings", params=params, headers=_HEADERS, timeout=_TIMEOUT
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("meetings", [])


def get_confirmed_slots(company_id: str | None = None) -> list[str]:
    """
    Return the already-booked slot timestamps (status=confirmed meetings) so the
    calendar mock can treat them as unavailable. Best-effort: returns [] on error.
    """
    try:
        meetings = get_meetings(status="confirmed", company_id=company_id)
    except Exception as e:
        logger.warning("get_confirmed_slots failed (treating none as booked): %s", e)
        return []
    return [m["confirmed_slot"] for m in meetings if m.get("confirmed_slot")]


def update_meeting(meeting_id: str, updates: dict) -> dict:
    """PATCH /api/meetings/:id — confirm / cancel / reschedule."""
    r = requests.patch(
        f"{BACKEND_URL}/api/meetings/{meeting_id}",
        json=updates,
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ── Supabase Storage ──────────────────────────────────────────────────────────

_CONTENT_TYPES = {
    ".pdf":  "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".json": "application/json",
    ".txt":  "text/plain",
    ".csv":  "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def upload_output_file(local_path: str, company_id: str, task_id: str) -> str:
    """
    Upload a local file to Supabase Storage at
    task-outputs/{company_id}/{task_id}/{filename}.

    Returns the storage path string.
    Raises on any HTTP or I/O error.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set — cannot upload file")

    fname = Path(local_path).name
    storage_path = f"{company_id}/{task_id}/{fname}"
    ext = Path(local_path).suffix.lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

    url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  content_type,
        "x-upsert":      "true",
    }

    with open(local_path, "rb") as fh:
        r = requests.post(url, data=fh, headers=headers, timeout=_UPLOAD_TIMEOUT)
    r.raise_for_status()

    logger.info("Uploaded %s → %s/%s", fname, STORAGE_BUCKET, storage_path)
    return storage_path


def upload_and_register(local_path: str, envelope: dict, file_type: str) -> str:
    """
    Best-effort: upload a produced file to the task-outputs bucket (under
    {company_id}/{task_id}/{filename}) and register it on the task. Returns the
    storage path on success, or the local path if context is missing / upload fails.
    Never raises — a storage hiccup must not fail the step.
    """
    task       = envelope.get("task", {})
    ctx        = envelope.get("_ctx", {})
    task_id    = task.get("task_id") or ctx.get("task_id")
    company_id = ctx.get("company_id") or task.get("company_id")

    if not company_id or not task_id or str(task_id).upper() in ("UNKNOWN", "TASK-UNKNOWN"):
        logger.info("upload_and_register skipped (no company_id/task_id) for %s", local_path)
        return local_path
    try:
        storage_path = upload_output_file(local_path, company_id, task_id)
        register_output_file(task_id, storage_path, file_type)
        return storage_path
    except Exception as e:
        logger.warning("upload_and_register failed for %s: %s", local_path, e)
        return local_path
