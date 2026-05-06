from executors.core.base_agent import ExecutionRunner

AGENT_REGISTRY = {
    "escalation":         "configs/01_escalation_router.json",
    "document_summary":   "configs/02_document_summarizer.json",
    "report":             "configs/03_report_generator.json",
    "leave_check":        "configs/04_leave_checker.json",
    "email":              "configs/05_email_agent.json",
    "presentation":       "configs/06_powerpoint_agent.json",
    "meeting_scheduler":  "configs/07_meeting_minutes_agent.json",
    "expense_check":      "configs/08_expense_tracker.json",
    "onboarding":         "configs/09_onboarding_agent.json",

}

class Orchestrator:

    def route(self, envelope: dict) -> dict:
        task_type = (
            envelope.get("task", {}).get("task_type")
            or envelope.get("intake", {}).get("task_type")
        )

        if not task_type:
            return {"error": "No task_type found in envelope"}

        config_path = AGENT_REGISTRY.get(task_type)

        if not config_path:
            return {"error": f"No agent registered for task_type: '{task_type}'"}

        runner = ExecutionRunner(config_path)
        return runner.execute(envelope)