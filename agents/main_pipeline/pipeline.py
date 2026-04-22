import sys
import os
import json

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_TASK_AGENT_DIR = os.path.join(_ROOT, "task_agent")
_THIS_DIR = os.path.abspath(os.path.dirname(__file__))

# When run as `python main_pipeline/pipeline.py`, Python inserts main_pipeline/
# into sys.path[0].  This causes `import intake_agent` to resolve to
# main_pipeline/intake_agent.py (a file) instead of the root intake_agent/
# package, breaking the sub-import.  Remove the script directory first.
if _THIS_DIR in sys.path:
    sys.path.remove(_THIS_DIR)

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _TASK_AGENT_DIR not in sys.path:
    sys.path.insert(0, _TASK_AGENT_DIR)

from main_pipeline.intake_agent import intake_agent
from main_pipeline.adapter import dict_to_envelope
from main_pipeline.task_agent import build_agent, run as run_task_agent
from priority_agent.validation import priority_prediction
from task_agent.envelope import PrioritySection


def run_pipeline(raw_text: str) -> dict:
    """
    Run raw request text through the full three-agent pipeline and return
    the final envelope as a plain dict.

    Flow:
      1. Intake Agent       — classifies department / task_type / isAutonomous
      2. dict_to_envelope() — converts plain dict to typed Envelope
      3. Task Agent         — extracts structured task fields
      4. Priority Agent     — scores priority 1-4 and deadline proximity
      5. Return             — fully-populated envelope.to_dict()
    """

    # Step 1 — Intake: returns a plain dict with envelope_id + intake section
    intake_dict = intake_agent(raw_text)

    # Step 2 — Convert to typed Envelope so the task agent can consume it
    envelope = dict_to_envelope(intake_dict)

    # Step 3 — Task structuring: Envelope gains a .task section
    agent = build_agent()
    envelope = run_task_agent(agent, envelope)

    # Step 4 — Priority scoring: returns full envelope dict + priority sub-dict
    priority_result = priority_prediction(envelope.to_dict())

    # Step 5 — Map priority sub-dict onto PrioritySection and attach to envelope
    envelope.priority = PrioritySection(**priority_result["priority"])

    # Step 6 — Return the fully-populated envelope as a plain dict
    return envelope.to_dict()


if __name__ == "__main__":
    inbox_dir = os.path.join(_ROOT, "inbox")

    for filename in ["email_001.txt", "email_002.txt"]:
        filepath = os.path.join(inbox_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            raw_text = f.read()

        print(f"\n{'=' * 60}")
        print(f"Processing: {filename}")
        print("=" * 60)

        result = run_pipeline(raw_text)
        print(json.dumps(result, indent=2))
