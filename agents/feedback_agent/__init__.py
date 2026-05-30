"""
agents/feedback_agent/__init__.py
==================================
Package entry point — re-exports everything the rest of the project needs.
"""

from .feedback_learning_agent import (
    FeedbackLearningAgent,
    FeedbackAgentConfig,
    PerformanceReport,
    TaskOutcome,
    create_feedback_agent,
)
from .feedback_bridge import FeedbackBridge
from .judge_agent import (
    JudgeAgent,
    JudgeConfig,
    JudgeVerdict,
    GoldenExample,
    GOLDEN_DATASET,
    create_judge_agent,
)

__all__ = [
    # Core feedback agent
    "FeedbackLearningAgent",
    "FeedbackAgentConfig",
    "PerformanceReport",
    "TaskOutcome",
    "create_feedback_agent",
    # Bridge
    "FeedbackBridge",
    # Judge
    "JudgeAgent",
    "JudgeConfig",
    "JudgeVerdict",
    "GoldenExample",
    "GOLDEN_DATASET",
    "create_judge_agent",
]