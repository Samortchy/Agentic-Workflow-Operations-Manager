# Debug Session — Agentic Workflow Operations Manager
**Date:** 2026-05-08  
**Focus:** Execution agent — PowerPoint Agent (Agent 06) escalation bug + full system audit

---

## How to Run a Live Test

The server is NOT in the default Python PATH. Always use the `llms` conda environment:

```powershell
cd D:\projects-last-semester\Agentic-Workflow-Operations-Manager\agents
C:\Users\User\.conda\envs\llms\Scripts\uvicorn.exe api:app --host 0.0.0.0 --port 8000 --reload
```

Then in a second terminal:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/orchestrate" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{
    "raw_text": "Create a PowerPoint presentation (.pptx file) for the Q1 2026 Finance Strategy Review. Department: Finance. Requester: alice@company.com. Deadline: 2026-05-10. Include slides for title, agenda, KPI dashboard, revenue analysis, and strategic recommendations."
  }'
```

---

## Request Flow (what should happen)

```
POST /api/orchestrate
  → run_pipeline (intake → task → priority)
  → resolve_config (LLM picks 06_powerpoint_agent.json)
  → ExecutionRunner executes 5 steps:
      1. select_template   (DBFetcher)
      2. generate_slide_json (LLMGenerator)
      3. write_pptx        (PPTXWriter)
      4. draft_email       (LLMGenerator)
      5. email_file        (EmailDispatcher)  ← approval gate fires here
  → returns envelope with execution.status = "approval_pending"
```

---

## What's Actually Happening (escalation path)

```
POST /api/orchestrate
  → run_pipeline (intake → task → priority)    ← may fail if keys missing
  → resolve_config                              ← may fall back to escalation on LLM error
  → powerpoint agent runs
      1. select_template — passes (empty rows, DB file absent)
      2. generate_slide_json — may fail (model unavailable / no API key)
      3. write_pptx — FAILS → python-pptx not installed
  → on_failure = "escalate" → escalation_router runs
  → execution.status = "escalated"
```

---

## Bugs Found — Prioritized

---

### BUG 1 — CRITICAL | `python-pptx` not installed → immediate escalation

**File:** `agents/execution_agent/executors/steps/custom/pptx_writer.py:11–18`

**What happens:**
```python
try:
    from pptx import Presentation
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False   # ← this is what's happening
```

Then in `PPTXWriter.run()`:
```python
if not PPTX_AVAILABLE:
    return StepResult(success=False, data={},
                      error="PPTXWriter: python-pptx is not installed.")
```

`success=False` → `on_failure = "escalate"` in the config → execution escalates immediately.
None of the conda environments (`llms`, `anaconda3`, `tts_fastapi_env`) have `python-pptx`.

**Fix:**
```powershell
C:\Users\User\.conda\envs\llms\Scripts\pip.exe install python-pptx
```

---

### BUG 2 — CRITICAL | Missing `.env` file — both API keys not set

**Files:**
- `agents/intake_agent/agents/intake_agent.py:12` — uses `GROQ_API_KEY`
- `agents/execution_agent/executors/core/config.py:5` — uses `OPENROUTER_API_KEY`
- `agents/task_agent/llm_provider.py:23` — uses `OPENROUTER_API_KEY`

**What happens:**
Neither `GROQ_API_KEY` nor `OPENROUTER_API_KEY` is set as a system or user environment variable.
Without them:
- Intake agent (Groq) → throws authentication error → `run_pipeline` raises → HTTP 500
- Routing LLM (OpenRouter) → `resolve_config` catches exception → falls back to `01_escalation_router.json`
- Execution LLM (OpenRouter) → all `LLMGenerator` steps fail → `success=False` → escalation

**Fix:**
Create `D:\projects-last-semester\Agentic-Workflow-Operations-Manager\agents\.env`:
```
GROQ_API_KEY=sk-...your-groq-key...
OPENROUTER_API_KEY=sk-or-...your-openrouter-key...
EMAIL_DRY_RUN=true
```

The `dotenv` import is already in every relevant file — it just needs the file.

---

### BUG 3 — HIGH | `DBFetcher` uses wrong database filename

**File:** `agents/execution_agent/executors/steps/processors/db_fetcher.py:19`

```python
_DB_PATH = Path("data/execution_agent.db")   # ← wrong
```

The seed script (`seed_db.py`) creates `data/office.db`. These two filenames don't match.
Because `data/execution_agent.db` doesn't exist, `DBFetcher._query()` returns `[]` silently for every step.
This breaks:
- `escalation_router` → `select_reviewer` step returns no reviewer → email goes to nobody
- Any other agent that looks up DB records

**Fix:**
```python
# db_fetcher.py line 19
_DB_PATH = Path("data/office.db")
```

---

### BUG 4 — HIGH | `DBFetcher` ignores `match_on` config key — filters never applied

**File:** `agents/execution_agent/executors/steps/processors/db_fetcher.py:49`

All agent configs (01, 06) use `"match_on": [...]` but `DBFetcher` only reads:
```python
raw_filters = config.get("filters", {})   # ← "match_on" is silently ignored
```

Result: even when the DB exists, ALL rows are returned instead of the filtered match.

**Affected configs:**
- `configs/01_escalation_router.json` → `select_reviewer` step
- `configs/06_powerpoint_agent.json` → `select_template` step

**Fix option A — rename key in all configs to `filters` (simpler):**

In `01_escalation_router.json`:
```json
"config": {
    "table": "routing_table",
    "filters": {
        "department": "intake.department",
        "priority_label": "priority.priority_label"
    }
}
```

In `06_powerpoint_agent.json`:
```json
"config": {
    "table": "pptx_templates",
    "filters": {
        "task_type": "intake.task_type"
    }
}
```

**Fix option B — support both keys in DBFetcher:**
```python
raw_filters = config.get("filters") or {}
# support legacy match_on by building filters from the envelope
if not raw_filters and "match_on" in config:
    for field in config["match_on"]:
        raw_filters[field] = f"intake.{field}"
```

---

### BUG 5 — HIGH | `select_template` step uses a JSON file path as a SQLite table name

**File:** `agents/execution_agent/executors/configs/06_powerpoint_agent.json:10`

```json
"table": "templates/pptx/templates_meta.json"
```

This is a file path, not a SQLite table name. If the DB existed, `SELECT * FROM templates/pptx/templates_meta.json` would throw an SQL syntax error. The step currently "succeeds" only because the DB file is absent (returns `[]` silently).

**Fix:**
Create a SQLite table for templates OR replace the step with a JSON file loader.

Option A — add a `pptx_templates` table to `seed_db.py`:
```python
con.executescript("""
CREATE TABLE IF NOT EXISTS pptx_templates (
    task_type    TEXT,
    template_key TEXT,
    description  TEXT
);
INSERT INTO pptx_templates VALUES
    ('presentation', 'blank',   'Default blank widescreen template'),
    ('finance',      'finance', 'Navy/slate finance-focused template');
""")
```

And update the config:
```json
"config": {
    "table": "pptx_templates",
    "filters": { "task_type": "intake.task_type" }
}
```

Option B — since `PPTXWriter` already handles a missing template gracefully (defaults to blank),
remove the `select_template` step entirely from `06_powerpoint_agent.json`.

---

### BUG 6 — HIGH | `templates_meta.json` is empty

**File:** `agents/execution_agent/executors/templates/pptx/templates_meta.json`

The file exists but has no content (1 empty line). If `select_template` is kept,
this file needs to be populated or replaced by a proper DB table (see Bug 5).

**Fix:** Either populate the JSON or drop the step (see Bug 5 options).

---

### BUG 7 — MEDIUM | `LLMGenerator` ignores direct `tone` config key

**File:** `agents/execution_agent/executors/steps/processors/llm_generator.py:324–328`

The `draft_email` step in `06_powerpoint_agent.json` sets `"tone": "professional"`,
but `_build_context` only writes `ctx["tone"]` when `tone_rules` (a dict) is in the config:

```python
if "tone_rules" in config:          # ← only dict form is handled
    ctx["tone"] = config["tone_rules"].get(dept, "professional")
```

The `draft_email_reply` prompt template has `{tone}`:
```
"Tone: {tone}.\n\n"
```

Because `_SafeDict` leaves unresolved keys intact, the rendered prompt literally contains
`Tone: {tone}.` — the LLM sees the raw placeholder, not a real tone value.

**Fix in `_build_context`** (add before the `tone_rules` block):
```python
# Support direct tone string in config
if "tone" in config:
    ctx["tone"] = config["tone"]
```

---

### BUG 8 — MEDIUM | `draft_email_reply` references `{sender_name}` — never populated

**File:** `agents/execution_agent/executors/steps/processors/llm_generator.py:83`

The `draft_email_reply` prompt contains:
```
"Sender name: {sender_name}\n\n"
```

`_build_context` never sets `ctx["sender_name"]`. The rendered prompt contains the literal
`{sender_name}` placeholder, producing unprofessional/broken email drafts.

Additionally, `draft_email_reply` is the wrong template for the PowerPoint agent —
it should use `draft_email_attachment` which is purpose-built for notifying requesters
about generated files.

**Fix option A — add `sender_name` to context:**
```python
ctx["sender_name"] = "Office Automation System"
```

**Fix option B — switch the pptx agent's `draft_email` step to the correct template:**

In `06_powerpoint_agent.json`:
```json
{
    "name": "draft_email",
    "type": "processor",
    "class": "LLMGenerator",
    "config": {
        "prompt_template": "draft_email_attachment",
        "tone": "professional"
    }
}
```

`draft_email_attachment` uses `{description}`, `{requester_name}`, and `{presentation_title}`
which are all available in context. No `{tone}` or `{sender_name}` needed.

---

### BUG 9 — MEDIUM | No API endpoint to resume `approval_pending` workflow

**File:** `agents/api.py`

The PowerPoint agent has `"approval": "single_confirm"`. The first run pauses before
`EmailDispatcher` and returns `execution.status = "approval_pending"`.
To complete, the caller must re-submit the **paused envelope** (not raw text).

There is no `/api/confirm` or `/api/resume` endpoint. The only way to resume is
to manually call `ExecutionRunner.execute(paused_envelope)` — which is not exposed.

**Fix — add to `api.py`:**
```python
@app.post("/api/confirm")
def confirm(body: dict):
    """
    Re-submit a paused envelope for execution (approval_pending → completed).
    The body must be the full envelope dict returned by /api/orchestrate.
    """
    try:
        envelope = body
        config_path = ... # re-derive from envelope.execution.agent_name
        runner = ExecutionRunner(str(config_path))
        result = runner.execute(envelope)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result
```

Or, simpler interim fix: change `approval` to `"none"` in `06_powerpoint_agent.json`
during development so the full pipeline runs end-to-end in one call.

---

### BUG 10 — LOW | `DBFetcher` filter resolver misidentifies strings with `.` as envelope paths

**File:** `agents/execution_agent/executors/steps/processors/db_fetcher.py:68–73`

```python
if isinstance(value, str) and "." in value:
    resolved[col] = _resolve_path(envelope, value)   # ← treats "alice@company.com" as a path
```

Any filter value that contains a `.` (emails, file extensions, version strings) would be
incorrectly treated as an envelope path reference, causing `KeyError` or wrong lookups.

**Fix — use an explicit prefix for path references:**
```python
if isinstance(value, str) and value.startswith("@env:"):
    resolved[col] = _resolve_path(envelope, value[5:])
else:
    resolved[col] = value
```

And update all filter configs to use the `@env:` prefix:
```json
"filters": { "department": "@env:intake.department" }
```

---

### BUG 11 — LOW | `generate_slide_json` config has unimplemented `required_fields` / `pause_if_missing`

**File:** `agents/execution_agent/executors/configs/06_powerpoint_agent.json:22–25`

```json
"required_fields": ["audience", "purpose", "key_message"],
"pause_if_missing": true
```

`LLMGenerator` reads neither of these config keys. They have zero effect.
The actual pausing logic is handled by the LLM itself (it sets `paused_for_clarification: true`
in the JSON output if information is missing).

**Fix:** Remove the dead config keys to avoid confusion, or implement them in `LLMGenerator`.

---

### BUG 12 — LOW | `PPTXWriter` writes to a relative `output/presentations` path

**File:** `agents/execution_agent/executors/steps/custom/pptx_writer.py:64`

`output_dir = config.get("output_dir", "output/presentations")` is relative to wherever
`uvicorn` is started from. If started from a different directory, the file lands somewhere unexpected.

**Fix:** Resolve relative to the agents directory:
```python
import os
_AGENTS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
output_dir_abs = os.path.join(_AGENTS_ROOT, output_dir)
```

---

## Escalation Path — Summary Diagram

```
Scenario A (keys missing):
  intake_agent → Groq auth error → pipeline raises → HTTP 500

Scenario B (keys set, model unavailable):
  resolve_config → LLM fails → catches exception → returns 01_escalation_router.json → escalation runs

Scenario C (keys set, routing works, python-pptx missing):
  powerpoint agent → select_template (pass) → generate_slide_json (pass) → write_pptx (FAIL: no library)
  → on_failure=escalate → escalation_router → status="escalated"   ← MOST LIKELY CURRENT BUG

Scenario D (everything installed, slide JSON malformed):
  write_pptx → slide_data.get("slides", []) == [] → FAIL → escalation
```

---

## Fix Priority Order

| # | Bug | Effort | Impact |
|---|-----|--------|--------|
| # | Bug | Status | Effort | Impact |
|---|-----|--------|--------|--------|
| 1 | Install `python-pptx` in the `llms` conda env | ✅ was already installed | — | — |
| 2 | Create `.env` with both API keys | ✅ keys were already set | — | — |
| 3 | Fix `DBFetcher._DB_PATH` to `data/office.db` | ✅ FIXED | 1 line | Correct DB path for when DB is seeded |
| 4 | Fix `DBFetcher` `match_on` support + filter heuristic | ✅ FIXED | ~40 lines | Filters work correctly when DB exists |
| 5 | Fix `select_template` table name OR remove the step | ⏳ pending — DB not implemented yet | config edit | Cleans up pptx agent |
| 6 | Add `tone` + `sender_name` to `_build_context` | ✅ FIXED | 3 lines | Email drafts no longer have raw placeholders |
| 7 | Switch `draft_email` to `draft_email_attachment` template | ⏳ pending | config edit | Better email body for file delivery |
| 8 | Add `/api/confirm` endpoint | ✅ FIXED | ~50 lines | Enables end-to-end approval flow via API |
| 9 | Remove dead config keys in `06_powerpoint_agent.json` | ⏳ pending | config edit | Cleaner config |

---

## Files to Edit (in fix order)

1. `pip install python-pptx` in `llms` env
2. `agents/.env` ← create this file
3. `agents/execution_agent/executors/steps/processors/db_fetcher.py` line 19
4. `agents/execution_agent/executors/configs/01_escalation_router.json` — rename `match_on` → `filters`
5. `agents/execution_agent/executors/configs/06_powerpoint_agent.json` — fix step 1 table + remove step if simpler
6. `agents/execution_agent/executors/steps/processors/llm_generator.py` — `_build_context` tone fix + sender_name
7. `agents/execution_agent/executors/configs/06_powerpoint_agent.json` — fix `draft_email` template
8. `agents/api.py` — add `/api/confirm` endpoint
9. `agents/execution_agent/executors/steps/processors/db_fetcher.py` — filter heuristic fix

---

*This file tracks what's broken and what to fix. Edit in-place as each bug is resolved.*
