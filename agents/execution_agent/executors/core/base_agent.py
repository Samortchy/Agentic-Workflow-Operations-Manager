# core/base_agent.py
# FROZEN — do not modify without full team review and a change log entry in spec.md
import json
import logging
from datetime import datetime, timezone

from core.envelope import resolve_path, write_step_result
from core.step_registry import STEP_REGISTRY
from core.approval_gate import check as check_approval
from core.outcome_emitter import emit

logger = logging.getLogger(__name__)

class ExecutionRunner:
    def __init__(self, config_path: str):
        self.config_path = config_path
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
            
        self._validate_startup()
        
    def _validate_startup(self):
        # 1. Validate top-level fields
        required_fields = ["agent_name", "agent_version", "department", "risk_tier", "approval", "steps", "on_failure", "outcome_signal"]
        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Missing required top-level field: {field}")
                
        # 2. Validate step types & names
        step_names = set()
        for step in self.config["steps"]:
            if step["type"] not in ["extractor", "processor", "dispatcher", "custom", "agent_call"]:
                raise ValueError(f"Invalid step type: {step['type']}")
            if step["class"] not in STEP_REGISTRY[step["type"]]:
                raise ValueError(f"Step class not in registry: {step['class']}")
            if step["name"] in step_names:
                raise ValueError(f"Duplicate step name: {step['name']}")
            step_names.add(step["name"])

    def execute(self, envelope: dict) -> dict:
        # 6.1 Validate incoming envelope
        for section in ["intake", "task", "priority"]:
            if section not in envelope:
                envelope.setdefault("execution", {})
                envelope["execution"]["status"] = "failed"
                logger.error(f"Missing envelope section: {section}")
                return envelope

        execution = envelope.setdefault("execution", {})
        execution["agent_name"] = self.config["agent_name"]
        execution["agent_version"] = self.config["agent_version"]
        execution["started_at"] = datetime.now(timezone.utc).isoformat()
        execution["approval"] = self.config["approval"]
        execution.setdefault("errors", [])
        
        # execution loop
        for step_config in self.config["steps"]:
            # 1. evaluate run_if
            if "run_if" in step_config.get("config", {}):
                try:
                    if not resolve_path(envelope, step_config["config"]["run_if"]):
                        continue
                except Exception as e:
                    execution["errors"].append({
                        "step": step_config["name"], 
                        "message": f"run_if evaluation failed: {e}", 
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    continue
            
            # 2. approval gate
            if step_config["type"] == "dispatcher" and execution.get("status") != "approval_pending":
                gate_result = check_approval(envelope, self.config)
                if gate_result.get("action"):
                    steps_dict = execution.setdefault("steps", {})
                    steps_dict.setdefault("approval_gate", {})["action"] = gate_result["action"]
                if gate_result.get("pause"):
                    execution["status"] = gate_result["status"]
                    return envelope
                    
            # 3. instantiate step class from registry
            step_class = STEP_REGISTRY[step_config["type"]][step_config["class"]]
            if step_config["type"] == "agent_call":
                # For agent call, step_class is the config path string
                nested_runner = ExecutionRunner(step_class)
                result_envelope = nested_runner.execute(envelope.copy())
                success = result_envelope["execution"]["status"] == "completed"
                result_data = result_envelope["execution"]
                error = None if success else "Agent call failed"
            else:
                step_instance = step_class()
                try:
                    step_result = step_instance.run(envelope, step_config.get("config", {}))
                    success = step_result.success
                    result_data = step_result.data
                    error = step_result.error
                except Exception as e:
                    success = False
                    result_data = {}
                    error = str(e)
            
            # 5. if success == False
            if not success:
                execution["errors"].append({
                    "step": step_config["name"],
                    "message": str(error),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                on_failure = self.config["on_failure"]
                if on_failure == "escalate":
                    execution["status"] = "escalated"
                    return envelope
                elif on_failure == "return_partial":
                    break
                # if log_and_alert, continue
            else:
                write_step_result(envelope, step_config["name"], step_config["type"], result_data)

        # After all steps complete
        execution["status"] = "completed"
        execution["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        # 4. Call outcome_emitter
        if self.config.get("outcome_signal"):
            emit(envelope)
            
        return envelope