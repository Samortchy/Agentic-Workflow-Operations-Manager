import sys
import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_TASK_AGENT_DIR = os.path.join(_ROOT, "task_agent")

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# task_agent/ must be on sys.path so that bare imports inside
# task_structuring_agent.py (e.g. "from envelope import ...") resolve correctly.
if _TASK_AGENT_DIR not in sys.path:
    sys.path.insert(0, _TASK_AGENT_DIR)

from task_agent.llm_provider import get_provider
from task_agent.task_structuring_agent import TaskStructuringAgent
from task_agent.envelope import Envelope


def build_agent(backend: str = "openrouter", model: str = None) -> TaskStructuringAgent:
    if not os.getenv("OPENROUTER_API_KEY"):
        raise EnvironmentError("OPENROUTER_API_KEY environment variable is missing.")
    llm = get_provider(backend=backend, model=model)
    return TaskStructuringAgent(llm=llm)


def run(agent: TaskStructuringAgent, envelope: Envelope) -> Envelope:
    return agent.run(envelope)
