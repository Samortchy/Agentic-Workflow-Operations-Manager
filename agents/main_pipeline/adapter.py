import sys
import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_TASK_AGENT_DIR = os.path.join(_ROOT, "task_agent")

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _TASK_AGENT_DIR not in sys.path:
    sys.path.insert(0, _TASK_AGENT_DIR)

from task_agent.envelope import Envelope, IntakeSection


def dict_to_envelope(intake_dict: dict) -> Envelope:
    """Convert the plain-dict output of the intake agent into a typed Envelope."""
    env = Envelope.create(intake_dict["raw_text"])

    # Preserve the IDs assigned by the intake agent rather than generating new ones.
    env.envelope_id = intake_dict["envelope_id"]
    env.received_at = intake_dict["received_at"]

    i = intake_dict["intake"]
    env.intake = IntakeSection(
        department=i["department"],
        task_type=i["task_type"],
        is_autonomous=i["isAutonomous"],   # camelCase → snake_case
        reasoning=i["reasoning"],
        confidence=i["confidence"],
        processed_at=i["processed_at"],
    )

    return env
