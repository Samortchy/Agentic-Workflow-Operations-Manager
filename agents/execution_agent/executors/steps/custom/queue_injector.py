"""
queue_injector.py
Custom step — Onboarding Coordinator (Agent 09)
P5 responsibility

What it does:
    Reads the tooling list fetched by the preceding DBExtractor step.
    For each tool in the list, creates a new task envelope and inserts it into
    the SQLite task queue so the Account Manager agent can pick it up independently.

    This is the async connection pattern from spec Section 7.2.
    The Onboarding Coordinator does NOT wait for Account Manager to finish.
    It fires the tasks and moves on.

    One envelope is created per tool. Each envelope is a minimal valid Phase 1-style
    envelope that the Account Manager can process:
        - intake:   department=IT, task_type=access_provisioning, isAutonomous=True
        - task:     employee details + tool name + manager as requester
        - priority: score=3 (medium) by default for access provisioning tasks

Returns:
    StepResult.data = {
        "tasks_injected":  int,
        "task_ids":        list[str],   # one task_id per injected envelope
        "target_agent":    str,
        "tools_queued":    list[str],   # tool names that were successfully queued
        "tools_failed":    list[str],   # tool names that failed to queue (DB error)
    }

Spec compliance:
    - Inherits BaseStep
    - run() signature: (self, envelope: dict, config: dict) -> StepResult
    - Never raises — all exceptions caught and returned as StepResult(success=False)
    - Never modifies envelope directly
    - Never adds fields to StepResult
    - Writes to SQLite task queue ONLY — this is the one step permitted to write to
      the queue table because its entire purpose is async task injection.
      It does NOT write to the envelope table — that is still the runner's job.
    - Uses resolve_path() from core.envelope for all envelope reads
"""

import sqlite3
import uuid
import json
from datetime import datetime, timezone
from ..base_step import BaseStep, StepResult
from ...core.envelope import resolve_path


class QueueInjector(BaseStep):

    def run(self, envelope: dict, config: dict) -> StepResult:
        try:
            # ── 1. Read config ────────────────────────────────────────────
            target_agent      = config.get("target_agent", "account_manager")
            task_type         = config.get("task_type", "access_provisioning")
            one_task_per_tool = config.get("one_task_per_tool", True)
            db_path           = config.get("db_path", "data/office.db")
            default_priority  = config.get("default_priority_score", 3)

            # ── 2. Read employee details from the NLP extractor step ──────
            employee_data = resolve_path(
                envelope,
                "execution.steps.extract_employee_details.data"
            )
            employee_name  = employee_data.get("employee_name", "unknown")
            employee_email = employee_data.get("employee_email", "")
            role           = employee_data.get("role", "")
            department     = employee_data.get("department", "")
            manager_name   = employee_data.get("manager_name", "")
            start_date     = employee_data.get("start_date", "")

            # ── 3. Read tooling list from the DBExtractor step ────────────
            tooling_data = resolve_path(
                envelope,
                "execution.steps.fetch_tooling_list.data"
            )
            tools = tooling_data.get("tools", [])

            if not tools:
                # No tools to provision — not an error, just nothing to do
                return StepResult(
                    success=True,
                    data={
                        "tasks_injected": 0,
                        "task_ids":       [],
                        "target_agent":   target_agent,
                        "tools_queued":   [],
                        "tools_failed":   [],
                    },
                    error=None
                )

            # ── 4. Inject one envelope per tool ───────────────────────────
            tools_queued = []
            tools_failed = []
            task_ids     = []
            now          = datetime.now(timezone.utc).isoformat()

            con = sqlite3.connect(db_path)

            for tool in tools:
                tool_name = tool if isinstance(tool, str) else tool.get("name", str(tool))

                try:
                    task_id     = f"TASK-ACC-{uuid.uuid4().hex[:6].upper()}"
                    envelope_id = f"ENV-ACC-{uuid.uuid4().hex[:6].upper()}"

                    new_envelope = self._build_access_envelope(
                        envelope_id   = envelope_id,
                        task_id       = task_id,
                        tool_name     = tool_name,
                        employee_name = employee_name,
                        employee_email= employee_email,
                        role          = role,
                        department    = department,
                        manager_name  = manager_name,
                        start_date    = start_date,
                        task_type     = task_type,
                        priority_score= default_priority,
                        parent_task_id= envelope.get("task", {}).get("task_id", ""),
                        created_at    = now,
                    )

                    # Write to the task_queue table — NOT the envelopes table
                    con.execute(
                        """
                        INSERT INTO task_queue
                            (task_id, envelope_id, target_agent, envelope_json,
                             status, created_at, priority_score)
                        VALUES (?, ?, ?, ?, 'pending', ?, ?)
                        """,
                        (
                            task_id,
                            envelope_id,
                            target_agent,
                            json.dumps(new_envelope),
                            now,
                            default_priority,
                        )
                    )
                    con.commit()

                    task_ids.append(task_id)
                    tools_queued.append(tool_name)

                except Exception as tool_err:
                    # One tool failing must not block the others
                    tools_failed.append(tool_name)

            con.close()

            # If every tool failed to queue, that is a step failure
            if tools_failed and not tools_queued:
                return StepResult(
                    success=False,
                    data={},
                    error=(
                        f"QueueInjector: all {len(tools_failed)} tool envelopes failed "
                        f"to insert into task_queue. Tools: {tools_failed}"
                    )
                )

            return StepResult(
                success=True,
                data={
                    "tasks_injected": len(tools_queued),
                    "task_ids":       task_ids,
                    "target_agent":   target_agent,
                    "tools_queued":   tools_queued,
                    "tools_failed":   tools_failed,   # partial failures recorded, not fatal
                },
                error=None
            )

        except KeyError as e:
            return StepResult(
                success=False,
                data={},
                error=(
                    f"QueueInjector could not find required envelope path: {e}. "
                    f"Ensure 'extract_employee_details' and 'fetch_tooling_list' "
                    f"steps ran successfully before this step."
                )
            )
        except Exception as e:
            return StepResult(
                success=False,
                data={},
                error=f"QueueInjector unexpected error: {str(e)}"
            )

    # ── private helpers ───────────────────────────────────────────────────────

    def _build_access_envelope(
        self,
        envelope_id:    str,
        task_id:        str,
        tool_name:      str,
        employee_name:  str,
        employee_email: str,
        role:           str,
        department:     str,
        manager_name:   str,
        start_date:     str,
        task_type:      str,
        priority_score: int,
        parent_task_id: str,
        created_at:     str,
    ) -> dict:
        """
        Builds a minimal valid envelope for an access provisioning task.
        This envelope will be picked up by the Account Manager agent.
        It must have intake, task, and priority sections populated
        (spec Section 3.1 — runner validates these before executing).
        """
        priority_label_map = {1: "low", 2: "low", 3: "medium", 4: "high"}

        return {
            "envelope_id": envelope_id,
            "raw_text": (
                f"Provision {tool_name} access for {employee_name} "
                f"({role}, {department}). Start date: {start_date}. "
                f"Manager: {manager_name}. Parent task: {parent_task_id}."
            ),
            "received_at": created_at,
            "intake": {
                "department":    "IT",
                "task_type":     task_type,
                "isAutonomous":  True,
                "confidence":    1.0,
                "processed_at":  created_at,
            },
            "task": {
                "task_id":          task_id,
                "title":            f"Provision {tool_name} — {employee_name}",
                "description":      (
                    f"Grant {tool_name} access to {employee_name} ({role}) "
                    f"in the {department} department. Required before start date {start_date}."
                ),
                "department":       "IT",
                "isAutonomous":     True,
                "task_type":        task_type,
                "requester_name":   manager_name,
                "stated_deadline":  start_date,
                "action_required":  f"Create and configure {tool_name} account for {employee_name}",
                "success_criteria": f"{employee_name} can log in to {tool_name} by {start_date}",
                "structured_at":    created_at,
            },
            "priority": {
                "priority_score":    priority_score,
                "priority_label":    priority_label_map.get(priority_score, "medium"),
                "confidence":        1.0,
                "model_version":     "injected",
                "top_features_used": ["task_type", "is_autonomous"],
                "scored_at":         created_at,
            },
        }