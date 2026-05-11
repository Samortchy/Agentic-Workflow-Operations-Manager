import logging
from datetime import datetime, timezone

from .envelope import resolve_path, write_step_result
from .step_registry import STEP_REGISTRY
from .approval_gate import check as check_approval
from .outcome_emitter import emit
from . import backend_client as bc

logger = logging.getLogger(__name__)

_RISK_LEVEL = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_APPROVAL_TYPE_MAP = {
    "single_confirm":                   "single_confirm",
    "single_confirm_if_low_confidence": "single_confirm",
    "manager_sign_off":                 "manager_sign_off",
}


class ExecutionRunner:

    def __init__(self, config: dict, task_id: str | None = None):
        """
        config   : the agent config dict (loaded from DB or passed directly).
        task_id  : optional — if not given, derived from envelope.task.task_id
                   at execute() time.
        """
        self.config   = config
        self._task_id = task_id
        self._validate_startup()

    @classmethod
    def from_agent_name(cls, agent_name: str, task_id: str | None = None, company_id: str | None = None) -> "ExecutionRunner":
        """Fetch the active config for agent_name from the backend DB."""
        config = bc.get_agent_config(agent_name, company_id=company_id)
        return cls(config, task_id=task_id)

    # ── validation ────────────────────────────────────────────────────────────

    def _validate_startup(self):
        required = ["agent_name", "agent_version", "department", "risk_tier",
                    "approval", "steps", "on_failure", "outcome_signal"]
        for field in required:
            if field not in self.config:
                raise ValueError(f"Missing required top-level field: {field}")

        seen = set()
        for step in self.config["steps"]:
            if step["type"] not in STEP_REGISTRY:
                raise ValueError(f"Invalid step type: {step['type']}")
            if step["class"] not in STEP_REGISTRY[step["type"]]:
                raise ValueError(f"Step class not in registry: {step['class']}")
            if step["name"] in seen:
                raise ValueError(f"Duplicate step name: {step['name']}")
            seen.add(step["name"])

    # ── execution ─────────────────────────────────────────────────────────────

    def execute(self, envelope: dict) -> dict:
        # Resolve identifiers from envelope context
        task_id    = self._task_id or envelope.get("task", {}).get("task_id") or envelope.get("_ctx", {}).get("task_id")
        company_id = envelope.get("_ctx", {}).get("company_id") or bc.get_company_id()

        # Validate required envelope sections
        for section in ["intake", "task", "priority"]:
            if section not in envelope:
                envelope.setdefault("execution", {})["status"] = "failed"
                logger.error("Missing envelope section: %s", section)
                return envelope

        execution = envelope.setdefault("execution", {})
        execution["agent_name"]    = self.config["agent_name"]
        execution["agent_version"] = self.config["agent_version"]
        execution["started_at"]    = datetime.now(timezone.utc).isoformat()
        execution["approval"]      = self.config["approval"]
        execution["errors"] = []  # reset per-run; don't accumulate across retries

        # Log agent_started to backend
        self._log(bc.create_audit_log, self.config["agent_name"], "agent_started",
                  task_id, company_id)

        # ── step loop ─────────────────────────────────────────────────────────
        for step_config in self.config["steps"]:
            step_name = step_config["name"]
            step_type = step_config["type"]
            step_cfg  = step_config.get("config", {})

            # 1. run_if guard
            if "run_if" in step_cfg:
                try:
                    if not resolve_path(envelope, step_cfg["run_if"]):
                        logger.debug("Skipping step %s (run_if=false)", step_name)
                        continue
                except Exception as e:
                    execution["errors"].append({
                        "step": step_name,
                        "message": f"run_if evaluation failed: {e}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    continue

            # 2. approval gate — fires before every dispatcher when not already pending
            if step_type == "dispatcher" and execution.get("status") != "approval_pending":
                gate = check_approval(envelope, self.config)
                execution.setdefault("steps", {}).setdefault("approval_gate", {})["action"] = gate["action"]

                if gate["pause"]:
                    execution["status"] = gate["status"]
                    self._register_approval(task_id, company_id, step_config, gate)
                    return envelope

            # 3. instantiate and run step
            step_class = STEP_REGISTRY[step_type][step_config["class"]]

            if step_type == "agent_call":
                # step_class is the agent_name string (e.g. "leave_checker")
                try:
                    nested_config = bc.get_agent_config(step_class, company_id=company_id)
                    nested_runner = ExecutionRunner(nested_config, task_id=task_id)
                    result_env = nested_runner.execute(envelope.copy())
                    success    = result_env.get("execution", {}).get("status") == "completed"
                    result_data = result_env.get("execution", {})
                    error = None if success else "Nested agent call did not complete"
                except Exception as e:
                    success, result_data, error = False, {}, str(e)
            else:
                step_instance = step_class()
                try:
                    step_result = step_instance.run(envelope, step_cfg)
                    success, result_data, error = step_result.success, step_result.data, step_result.error
                except Exception as e:
                    success, result_data, error = False, {}, str(e)

            # 4. handle failure
            if not success:
                execution["errors"].append({
                    "step":      step_name,
                    "message":   str(error),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                self._log(bc.create_audit_log, self.config["agent_name"], "step_failed",
                          task_id, company_id, details={"step": step_name, "error": str(error)})

                on_failure = self.config["on_failure"]
                if on_failure == "escalate":
                    execution["status"] = "escalated"
                    self._log(bc.create_audit_log, self.config["agent_name"], "escalated",
                              task_id, company_id, details={"step": step_name})
                    return envelope
                elif on_failure == "return_partial":
                    break
                # log_and_alert → continue
            else:
                write_step_result(envelope, step_name, step_type, result_data)

        # ── all steps done ────────────────────────────────────────────────────
        execution["status"]       = "completed"
        execution["completed_at"] = datetime.now(timezone.utc).isoformat()

        self._log(bc.create_audit_log, self.config["agent_name"], "agent_completed",
                  task_id, company_id)

        if self.config.get("outcome_signal"):
            emit(envelope, task_id=task_id, company_id=company_id)

        return envelope

    # ── helpers ───────────────────────────────────────────────────────────────

    def _register_approval(self, task_id, company_id, step_config, gate):
        """Create an approval request in the backend when the gate fires."""
        if not task_id:
            return
        try:
            preview = (
                f"{self.config['agent_name']} → "
                f"{step_config['class']} ({step_config['name']})"
            )
            bc.create_approval(
                task_id=task_id,
                agent_name=self.config["agent_name"],
                command_preview=preview,
                required_level=_RISK_LEVEL.get(self.config.get("risk_tier", "medium"), 2),
                approval_type=_APPROVAL_TYPE_MAP.get(self.config.get("approval"), "single_confirm"),
                company_id=company_id,
                context={"risk_tier": self.config.get("risk_tier"), "gate_action": gate.get("action")},
            )
            bc.create_audit_log(
                self.config["agent_name"], "approval_requested",
                task_id, company_id,
                details={"gate_action": gate.get("action")},
            )
        except Exception as e:
            logger.warning("Failed to register approval with backend: %s", e)

    @staticmethod
    def _log(fn, *args, **kwargs):
        """Call a backend_client function, swallowing errors so steps never fail due to logging."""
        try:
            fn(*args, **kwargs)
        except Exception as e:
            logger.warning("Backend log call failed: %s", e)
