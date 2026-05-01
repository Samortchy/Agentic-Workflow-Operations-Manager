# Autonomous Office Agent System — Phase 2 Spec
**Version:** 1.0 — Locked after Day 2  
**Owner:** Ali Abdallah (P1)  
**Status:** LOCKED — no changes without team review and a written reason below  
**Last updated:** April 2026

---

> **If you are using AI to generate code for this project, paste this entire document into your prompt before writing a single line. Every constraint here is non-negotiable. The AI must follow this spec exactly — do not let it invent field names, step types, status values, or method signatures.**

---

## Change log
> All post-lock changes must be recorded here with a reason before the change is merged.

| Date | Changed by | What changed | Why |
|------|-----------|--------------|-----|
| — | — | — | — |

---

## 1. Team map

| Person | Role | Owns |
|--------|------|------|
| Ali (P1) | Factory skeleton | `core/`, `steps/base_step.py`, `spec.md` |
| P2 | Extractors | `steps/extractors/`, configs 01 + 04 |
| P3 | Processors | `steps/processors/`, configs 02 + 03 + 05 |
| P4 | Dispatchers | `steps/dispatchers/`, configs 03 + 07 |
| P5 | Custom steps | `steps/custom/`, configs 06 + 08 + 09 |

**Frozen files** — nobody modifies these without a full team review and a change log entry:
- `core/base_agent.py`
- `core/step_registry.py`
- `core/envelope.py`
- `core/approval_gate.py`
- `core/outcome_emitter.py`
- `steps/base_step.py`

**Free to modify without review:**
- Anything under `steps/custom/`
- Anything under `configs/`
- Anything under `templates/`
- Your own step class files under `steps/extractors/`, `steps/processors/`, `steps/dispatchers/`

---

## 2. Folder structure

```
execution_agents/
├── core/
│   ├── base_agent.py          # runner loop
│   ├── step_registry.py       # config type → class mapping
│   ├── envelope.py            # read/write + path resolution helpers
│   ├── approval_gate.py       # approval logic
│   └── outcome_emitter.py     # signals outcome tracker
├── steps/
│   ├── base_step.py           # abstract base — everyone inherits this
│   ├── extractors/
│   │   ├── nlp_extractor.py
│   │   ├── file_extractor.py
│   │   └── db_extractor.py
│   ├── processors/
│   │   ├── llm_generator.py
│   │   ├── template_renderer.py
│   │   └── db_fetcher.py
│   ├── dispatchers/
│   │   ├── email_dispatcher.py
│   │   ├── file_dispatcher.py
│   │   └── calendar_dispatcher.py
│   └── custom/
│       ├── anomaly_checker.py
│       ├── slot_ranker.py
│       ├── queue_injector.py
│       └── pptx_writer.py
├── configs/
│   ├── 01_escalation_router.json
│   ├── 02_document_summarizer.json
│   ├── 03_report_generator.json
│   ├── 04_leave_checker.json
│   ├── 05_email_agent.json
│   ├── 06_powerpoint_agent.json
│   ├── 07_meeting_scheduler.json
│   ├── 08_expense_tracker.json
│   └── 09_onboarding_coordinator.json
├── templates/
│   ├── email/
│   ├── pptx/
│   ├── reports/
│   └── onboarding/
├── data/
│   ├── routing_table.json
│   └── tooling_list.json
├── output/                    # gitignored
│   ├── reports/
│   └── presentations/
└── tests/
    ├── test_base_agent.py
    └── test_leave_checker.py
```

---

## 3. Envelope contract

### 3.1 Envelope entering an execution agent

Before the runner starts, it validates the incoming envelope has all three of these sections populated. If any are missing, the runner writes `status: failed` and exits — it does not run a single step.

```json
{
  "envelope_id": "ENV-001",
  "raw_text": "string",
  "received_at": "ISO8601",
  "intake": {
    "department": "IT | Finance | HR | cross-dept",
    "task_type": "string",
    "isAutonomous": "bool",
    "confidence": "float 0.0–1.0",
    "processed_at": "ISO8601"
  },
  "task": {
    "task_id": "string",
    "title": "string",
    "description": "string",
    "department": "string",
    "isAutonomous": "bool",
    "task_type": "string",
    "requester_name": "string",
    "stated_deadline": "string",
    "action_required": "string",
    "success_criteria": "string",
    "structured_at": "ISO8601"
  },
  "priority": {
    "priority_score": "int 1–4",
    "priority_label": "low | medium | high | critical",
    "confidence": "float 0.0–1.0",
    "model_version": "string",
    "top_features_used": "list[string]",
    "scored_at": "ISO8601"
  }
}
```

### 3.2 Execution section — written by the runner

Every agent writes to `execution`. No agent writes to `intake`, `task`, or `priority` — those are read-only from the Phase 1 pipeline.

```json
{
  "execution": {
    "agent_name": "string",
    "agent_version": "string",
    "status": "see allowed values below",
    "started_at": "ISO8601",
    "completed_at": "ISO8601 | null",
    "approval": "string — mirrors config top-level approval field",
    "result": {},
    "agent_calls": {},
    "errors": []
  }
}
```

### 3.3 Allowed status values — complete list, no additions without team review

| Value | When it is set |
|-------|---------------|
| `completed` | Agent finished all steps successfully |
| `paused` | Agent waiting for user input mid-execution |
| `pending_human_review` | Escalation Router handed off to a human |
| `approval_pending` | Approval gate fired, waiting for user confirm |
| `escalated` | Anomaly or compliance issue, routed to a human |
| `failed` | Agent hit an unrecoverable error |

### 3.4 Error object shape — every item in `errors[]` has exactly these fields

```json
{
  "step": "step_name_from_config",
  "message": "human readable description of what went wrong",
  "timestamp": "ISO8601"
}
```

No other fields. Do not add `code`, `trace`, `severity`, or anything else to error objects.

### 3.5 Agent call results

When a step of type `agent_call` completes, its result is written under `execution.agent_calls.{step_name}` — not inside `execution.result`. This prevents collisions between the calling agent's own result and the called agent's result.

```json
{
  "execution": {
    "result": { "...calling agent result..." },
    "agent_calls": {
      "summarise_attachment": {
        "agent_name": "document_summarizer",
        "status": "completed",
        "result": { "...document summarizer result..." }
      }
    }
  }
}
```

---

## 4. Step interface contract

### 4.1 Base step — everyone inherits this, nobody modifies it

```python
# steps/base_step.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class StepResult:
    success: bool
    data:    dict
    error:   str | None

class BaseStep(ABC):

    @abstractmethod
    def run(self, envelope: dict, config: dict) -> StepResult:
        """
        envelope — full current envelope as a plain dict. READ ONLY.
                   never modify envelope directly inside a step.
        config   — this step's config block from the agent JSON (the dict
                   inside the step entry, not the full agent config).
        returns  — StepResult always. NEVER raise an exception out of run().
        """
        pass
```

### 4.2 Rules every step must follow

**Steps never raise.** Every exception must be caught inside `run()` and returned as:
```python
return StepResult(success=False, data={}, error=str(e))
```
If a step raises and the runner crashes, that is the step author's bug.

**Steps never modify the envelope directly.** Return data in `StepResult.data`. The runner writes it to the envelope. This preserves the append-only contract from Phase 1.

**Steps receive the full envelope.** Do not slice or copy it before passing — steps read whatever fields they need directly from the full dict.

**StepResult has exactly three fields.** Do not add fields to `StepResult`. If a step needs to signal a special state like `paused`, it puts `"status": "paused"` inside `data` and the runner checks for it.

### 4.3 Minimal valid step implementation

```python
from steps.base_step import BaseStep, StepResult

class MyExtractor(BaseStep):

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            value = envelope["task"]["requester_name"]
            result = self._do_work(value, config)
            return StepResult(success=True, data=result, error=None)
        except Exception as e:
            return StepResult(success=False, data={}, error=str(e))

    def _do_work(self, value, config):
        # actual logic here
        return {}
```

---

## 5. Config file contract

### 5.1 Required top-level fields — all must be present or the runner rejects the config on load

```json
{
  "agent_name":     "string — must match filename without number prefix and extension",
  "agent_version":  "string — e.g. v1",
  "department":     "IT | Finance | HR | cross-dept",
  "risk_tier":      "low | medium | high",
  "approval":       "see allowed values in 5.3",
  "steps":          "array — see 5.2",
  "on_failure":     "escalate | log_and_alert | return_partial",
  "outcome_signal": "bool"
}
```

### 5.2 Step entry shape — every item in `steps[]` must have these fields

```json
{
  "name":   "string — unique within this config, used as the key in envelope path references",
  "type":   "see allowed types in 5.4",
  "class":  "string — must exist in step_registry.py or runner fails on load",
  "config": "dict — passed as the config argument to step.run()"
}
```

Step names must be unique within a single config. The runner validates this on load and fails fast.

### 5.3 Allowed approval values — complete list

| Value | Behaviour |
|-------|-----------|
| `none` | Runner never pauses, dispatches immediately |
| `single_confirm` | Runner pauses before any dispatcher step, waits for user confirm in UI |
| `single_confirm_if_low_confidence` | Runner checks `execution.result.draft_confidence`, pauses only if below `confidence_threshold` set in config |
| `manager_sign_off` | Runner pauses and emails manager, waits for reply before continuing |

### 5.4 Allowed step type values — complete list, nothing else is valid

| Type | Who writes it | What it does |
|------|--------------|--------------|
| `extractor` | P2 | Pulls data from DB, file, or NLP parse |
| `processor` | P3 | Transforms or generates via LLM or template |
| `dispatcher` | P4 | Sends output — email, file, calendar |
| `custom` | P5 | Logic that cannot be config-only |
| `agent_call` | P1 registers it | Runs another agent inline, synchronously |

### 5.5 run_if — conditional step execution

`run_if` is an optional field on any step entry. If present, the runner evaluates it before calling the step. If the condition is false, the step is skipped entirely — the step class never knows it was skipped.

**Syntax — dot-notation path on the envelope with a comparison operator:**
```
"run_if": "task.has_attachments == true"
"run_if": "execution.steps.check_anomalies.data.anomaly == false"
"run_if": "priority.priority_score > 2"
```

**Supported operators:** `==`, `!=`, `>`, `<`  
**No compound logic.** `and` / `or` are not supported. If you need compound conditions, split into two steps with separate `run_if` values.

`run_if` is evaluated by the runner using `resolve_path()` in `core/envelope.py`. Steps never evaluate it themselves.

### 5.6 Referencing earlier step outputs in config values

When a dispatcher or later step needs to reference the output of an earlier step, use this exact dot-notation syntax:

```
"execution.steps.{step_name}.data.{field_name}"
```

Examples:
```json
"recipient_field": "execution.steps.select_reviewer.data.reviewer_email"
"attach_field":    "execution.steps.write_pptx.data.output_path"
```

`resolve_path()` in `core/envelope.py` resolves these at runtime. If the path does not resolve, the step returns `StepResult(success=False)` with a clear error message — it never silently uses a null or default value.

### 5.7 Minimal valid config example — Leave Checker

```json
{
  "agent_name":     "leave_checker",
  "agent_version":  "v1",
  "department":     "HR",
  "risk_tier":      "low",
  "approval":       "none",
  "steps": [
    {
      "name":   "extract_intent",
      "type":   "extractor",
      "class":  "NLPExtractor",
      "config": { "fields_to_extract": ["employee_name", "leave_type", "date_range"] }
    },
    {
      "name":   "fetch_leave_record",
      "type":   "extractor",
      "class":  "DBExtractor",
      "config": { "table": "hr_leave_balances", "match_on": ["employee_name", "leave_type"] }
    },
    {
      "name":   "render_reply",
      "type":   "processor",
      "class":  "TemplateRenderer",
      "config": { "template": "templates/email/hr_reply.j2" }
    },
    {
      "name":   "send_reply",
      "type":   "dispatcher",
      "class":  "EmailDispatcher",
      "config": { "recipient_field": "task.requester_name" }
    }
  ],
  "on_failure":     "escalate",
  "outcome_signal": true
}
```

---

## 6. Runner behaviour — what base_agent.py does

This section documents the runner loop so every team member knows what P1 is building and can code their steps against it.

### 6.1 Startup validation — before any step runs

1. Load config JSON from `configs/{agent}.json`
2. Validate all required top-level fields are present — fail fast if not
3. Validate all step `type` values are in the allowed list — fail fast if not
4. Validate all step `class` values exist in `step_registry.py` — fail fast if not
5. Validate all step `name` values are unique within the config — fail fast if not
6. Validate incoming envelope has `intake`, `task`, `priority` all populated — fail fast if not

Fail fast means: write `status: failed` to the envelope, log the error, return. Do not proceed.

### 6.2 Execution loop order

```
for each step in config.steps:
    1. evaluate run_if — skip step if condition is false
    2. if step.type == "dispatcher" and approval not yet cleared:
           run approval_gate() — may pause execution
    3. instantiate step class from registry
    4. call step.run(envelope, step.config)
    5. if result.success == False:
           append to envelope.execution.errors
           if config.on_failure == "escalate": stop and escalate
           if config.on_failure == "log_and_alert": continue to next step
           if config.on_failure == "return_partial": stop and emit partial result
    6. if result.success == True:
           if step.type == "agent_call":
               write result under execution.agent_calls.{step.name}
           else:
               write result.data under execution.steps.{step.name}.data
```

### 6.3 Approval gate — not a step, always in the same position

The approval gate is not a step in the config. It fires automatically before the first dispatcher step runs, based on the top-level `approval` field. No agent config needs to explicitly include it.

- `none` — gate is a no-op, execution continues
- `single_confirm` — runner writes `status: approval_pending`, pauses, waits for UI confirm signal
- `single_confirm_if_low_confidence` — runner reads `execution.result.draft_confidence`, only pauses if value is below `config.confidence_threshold`
- `manager_sign_off` — runner writes `status: approval_pending`, fires email to manager, waits for reply signal

### 6.4 After all steps complete

1. Write `execution.status = completed`
2. Write `execution.completed_at = now()`
3. Write full envelope to SQLite as one atomic write — no partial writes mid-run
4. Call `outcome_emitter.emit(envelope)` to signal the outcome tracker

---

## 7. Inter-agent connections

### 7.1 Synchronous — agent_call step

Use when the calling agent needs the result before it can continue.

```json
{
  "name":   "summarise_attachment",
  "type":   "agent_call",
  "class":  "DocumentSummarizer",
  "config": {
    "run_if": "task.has_attachments == true"
  }
}
```

- The runner loads `configs/02_document_summarizer.json` and runs it as a nested execution
- Result is written to `execution.agent_calls.summarise_attachment`
- The calling agent's execution is blocked until the called agent completes
- If the called agent fails, it counts as a step failure in the calling agent

### 7.2 Asynchronous — QueueInjector custom step

Use when the calling agent does not need to wait for the result.

```json
{
  "name":   "inject_access_tasks",
  "type":   "custom",
  "class":  "QueueInjector",
  "config": {
    "target_agent":    "account_manager",
    "task_type":       "access_provisioning",
    "one_task_per_tool": true
  }
}
```

- QueueInjector writes new envelope rows to the SQLite task queue and returns immediately
- The target agent picks them up on its next poll cycle
- The calling agent does not wait, does not receive results
- This is the only async connection mechanism — do not invent others

### 7.3 The two mechanisms are never mixed

`agent_call` is always synchronous. `QueueInjector` is always asynchronous. There is no hybrid. If you are unsure which to use: if the calling agent needs the result to do its next step, use `agent_call`. If it does not, use `QueueInjector`.

---

## 8. Step registry — what P1 maintains

```python
# core/step_registry.py

from steps.extractors.nlp_extractor      import NLPExtractor
from steps.extractors.file_extractor     import FileExtractor
from steps.extractors.db_extractor       import DBExtractor
from steps.processors.llm_generator      import LLMGenerator
from steps.processors.template_renderer  import TemplateRenderer
from steps.processors.db_fetcher         import DBFetcher
from steps.dispatchers.email_dispatcher  import EmailDispatcher
from steps.dispatchers.file_dispatcher   import FileDispatcher
from steps.dispatchers.calendar_dispatcher import CalendarDispatcher
from steps.custom.anomaly_checker        import AnomalyChecker
from steps.custom.slot_ranker            import SlotRanker
from steps.custom.queue_injector         import QueueInjector
from steps.custom.pptx_writer            import PPTXWriter

STEP_REGISTRY = {
    "extractor": {
        "NLPExtractor":  NLPExtractor,
        "FileExtractor": FileExtractor,
        "DBExtractor":   DBExtractor,
    },
    "processor": {
        "LLMGenerator":     LLMGenerator,
        "TemplateRenderer": TemplateRenderer,
        "DBFetcher":        DBFetcher,
    },
    "dispatcher": {
        "EmailDispatcher":    EmailDispatcher,
        "FileDispatcher":     FileDispatcher,
        "CalendarDispatcher": CalendarDispatcher,
    },
    "custom": {
        "AnomalyChecker": AnomalyChecker,
        "SlotRanker":     SlotRanker,
        "QueueInjector":  QueueInjector,
        "PPTXWriter":     PPTXWriter,
    },
    "agent_call": {
        "DocumentSummarizer":    "configs/02_document_summarizer.json",
        "EscalationRouter":      "configs/01_escalation_router.json",
        "LeaveChecker":          "configs/04_leave_checker.json",
        "ExpenseTracker":        "configs/08_expense_tracker.json",
    },
}
```

To add a new class to the registry, submit the addition to Ali (P1) with the file path. Do not edit `step_registry.py` directly.

---

## 9. envelope.py utilities — what P1 provides

These are the only two utilities steps and configs should use to interact with the envelope. Do not write custom path resolution logic in your step files.

```python
# core/envelope.py

def resolve_path(envelope: dict, path: str):
    """
    Resolves a dot-notation path against the envelope dict.
    Example: resolve_path(env, "execution.steps.fetch_record.data.employee_id")
    Returns the value at the path, or raises KeyError with a clear message if not found.
    """

def write_step_result(envelope: dict, step_name: str, step_type: str, data: dict):
    """
    Writes a step result to the correct location in the envelope.
    - For agent_call steps: writes under execution.agent_calls.{step_name}
    - For all other steps:  writes under execution.steps.{step_name}.data
    Never call this from inside a step — the runner calls it after step.run() returns.
    """
```

---

## 10. What AI code generation must follow

If you are using Claude, Gemini, GPT, or any other AI to generate code for this project, include this spec in your prompt and enforce these rules explicitly:

**Envelope rules:**
- Never modify `intake`, `task`, or `priority` sections — read only
- Always write agent output to `execution` section only
- Always use the exact field names from Section 3 — no renaming
- Always use a status value from the allowed list in Section 3.3

**Step rules:**
- Always inherit from `BaseStep` in `steps/base_step.py`
- Always implement `run(self, envelope: dict, config: dict) -> StepResult`
- Never raise an exception out of `run()` — always catch and return `StepResult(success=False, ...)`
- Never modify the envelope dict directly inside a step
- Never add fields to `StepResult`

**Config rules:**
- Always include all required top-level fields from Section 5.1
- Always use a `type` value from the allowed list in Section 5.4
- Always use an `approval` value from the allowed list in Section 5.3
- Step names within a config must be unique
- `class` value must match exactly what is registered in `step_registry.py`
- Envelope path references must use the exact syntax: `execution.steps.{step_name}.data.{field}`

**What AI must never do:**
- Invent new step types not in the allowed list
- Invent new status values not in the allowed list
- Add fields to `StepResult`
- Modify any file in `core/` — those are frozen
- Modify `steps/base_step.py` — frozen
- Write custom path resolution logic — use `resolve_path()` from `core/envelope.py`
- Write directly to the SQLite DB from inside a step — only the runner does that
- Use `and` / `or` in `run_if` conditions

---

*End of spec — version 1.0*
