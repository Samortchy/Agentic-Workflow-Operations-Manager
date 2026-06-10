# Execution-agent data contracts

This file pins the shapes that steps hand to each other through the envelope, so consumers and
producers don't drift. (See `PLAN.md` §5 Phase 1 / P1-4 for the history.)

## DBExtractor output contract

`DBExtractor` runs in one of two modes, set by config.

### DB mode (`config.table` set)
Returns into `execution.steps.<step_name>.data`:

```jsonc
{
  "rows": [ { "<col>": <val>, ... }, ... ],   // every matched row, as dicts
  "row_count": <int>,                          // len(rows)
  "record": { ... } | null                     // rows[0] when row_count == 1, else null
}
```

- **List consumers** (e.g. Leave Checker's `hr_reply.j2`, Onboarding's `QueueInjector`) read **`rows`**.
- **Single-record consumers** (e.g. Expense Tracker's `AnomalyChecker`) read **`record`**; if it is
  `null` they should treat the result as "not a unique match" and fail/escalate rather than guess.
- `match_on` values resolve from the most recent step data first, then `envelope["task"]`. If
  `match_on` is given but nothing resolves, `rows` is empty (no full-table scans).

### Service-mock mode (`config.service` set)
Skips the DB and returns a per-service mock dict (shape depends on the service):
- `calendar_api` → `{ "available_slots": [...], "timezone": str, "look_ahead_days": int }`
  - ⚠️ **Known gap (Phase 2):** `SlotRanker` expects `{ participants, slots[{slot_start, slot_end,
    availability}] }`. These do not yet match — reconciled when the Meeting Scheduler / `meetings`
    table lands (PLAN.md §4.3 / Phase 2).
- `compliance_checker` → `{ "compliant": bool, "flags": [...], "action_type": str, "checked_at": iso }`

## Database path resolution

All SQLite readers/writers resolve the operational DB the same way:

```
DB_PATH env var  →  else  <executors>/data/office.db  (anchored to __file__, CWD-independent)
```

Applies to `DBExtractor`, `DBFetcher`, `AnomalyChecker`, and `QueueInjector`. Regenerate the DB with
`python agents/execution_agent/executors/data/seed_db.py` (use Python 3.10).

## finance_expense_reports (SQLite)

Columns consumed by `AnomalyChecker`:
`report_id, employee_id, employee_name, date, submitted_at, amount_egp, category, status,
has_receipt (0/1), line_items (JSON text), approval_date, payment_eta, description`.

- **Duplicate check** keys on `employee_id + amount_egp` within `duplicate_window_days` of `submitted_at`.
- **Missing-receipt check** flags `amount_egp > receipt_threshold_egp AND has_receipt == 0`.
- **Line-item policy check** parses `line_items` JSON; flags non-reimbursable categories
  (`entertainment`, `personal`) and single items > 10,000 EGP.

## task_queue (SQLite)

Written by `QueueInjector` (one access-provisioning task per onboarding tool):
`task_id, envelope_id, target_agent, envelope_json, status, created_at, priority_score`.
⚠️ Nothing consumes this yet — the `account_manager` agent does not exist (PLAN.md P2-14). The table
exists so onboarding completes instead of escalating; wiring a consumer is Phase-2 work.
