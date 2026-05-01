# steps/base_step.py
# FROZEN — do not modify without full team review and a change log entry in spec.md
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