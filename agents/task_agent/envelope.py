"""
envelope.py
-----------
Shared envelope contract for the Autonomous Office Workflow pipeline.
Every agent imports this module and appends its own section.
No agent modifies another agent's section (append-only design).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import json
import uuid
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Sub-sections (one per agent)
# ---------------------------------------------------------------------------

@dataclass
class IntakeSection:
    """Populated by the Intake Agent."""
    department: str                  # "IT" | "Finance" | "HR"
    task_type: str                   # e.g. "hardware_procurement"
    is_autonomous: bool
    reasoning: str
    confidence: float                # 0.0 – 1.0
    processed_at: str                # ISO-8601

    def to_dict(self) -> dict:
        return {
            "department":    self.department,
            "task_type":     self.task_type,
            "isAutonomous":  self.is_autonomous,
            "reasoning":     self.reasoning,
            "confidence":    self.confidence,
            "processed_at":  self.processed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IntakeSection":
        return cls(
            department=d["department"],
            task_type=d["task_type"],
            is_autonomous=d["isAutonomous"],
            reasoning=d["reasoning"],
            confidence=d["confidence"],
            processed_at=d["processed_at"],
        )


@dataclass
class TaskSection:
    """Populated by the Task Structuring Agent."""
    task_id: str
    title: str
    description: str
    department: str          # copied from IntakeSection
    is_autonomous: bool      # copied from IntakeSection
    task_type: str           # copied from IntakeSection
    requester_name: str      # extracted or "unknown"
    stated_deadline: str     # extracted or "none stated"
    action_required: str     # single sentence
    success_criteria: str    # what "done" looks like
    structured_at: str       # ISO-8601

    def to_dict(self) -> dict:
        return {
            "task_id":          self.task_id,
            "title":            self.title,
            "description":      self.description,
            "department":       self.department,
            "isAutonomous":     self.is_autonomous,
            "task_type":        self.task_type,
            "requester_name":   self.requester_name,
            "stated_deadline":  self.stated_deadline,
            "action_required":  self.action_required,
            "success_criteria": self.success_criteria,
            "structured_at":    self.structured_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskSection":
        return cls(
            task_id=d["task_id"],
            title=d["title"],
            description=d["description"],
            department=d["department"],
            is_autonomous=d["isAutonomous"],
            task_type=d["task_type"],
            requester_name=d["requester_name"],
            stated_deadline=d["stated_deadline"],
            action_required=d["action_required"],
            success_criteria=d["success_criteria"],
            structured_at=d["structured_at"],
        )


@dataclass
class PrioritySection:
    """Populated by the Priority Agent (stub — not implemented yet)."""
    priority_score: int      # 1 (lowest) – 5 (critical)
    priority_label: str      # "low" | "medium" | "high" | "critical"
    confidence: float
    model_version: str
    top_features_used: list
    scored_at: str

    def to_dict(self) -> dict:
        return {
            "priority_score":     self.priority_score,
            "priority_label":     self.priority_label,
            "confidence":         self.confidence,
            "model_version":      self.model_version,
            "top_features_used":  self.top_features_used,
            "scored_at":          self.scored_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PrioritySection":
        return cls(
            priority_score=d["priority_score"],
            priority_label=d["priority_label"],
            confidence=d["confidence"],
            model_version=d["model_version"],
            top_features_used=d["top_features_used"],
            scored_at=d["scored_at"],
        )


# ---------------------------------------------------------------------------
# Root envelope
# ---------------------------------------------------------------------------

@dataclass
class Envelope:
    """
    The single JSON object that travels through the entire pipeline.
    Each agent appends its own section; no section is ever overwritten.
    """
    envelope_id: str
    raw_text: str
    received_at: str                          # ISO-8601
    errors: list = field(default_factory=list)

    # Agent sections — None until that agent has run
    intake:   Optional[IntakeSection]   = None
    task:     Optional[TaskSection]     = None
    priority: Optional[PrioritySection] = None

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, raw_text: str) -> "Envelope":
        """Create a brand-new envelope from raw request text."""
        return cls(
            envelope_id=f"ENV-{uuid.uuid4().hex[:6].upper()}",
            raw_text=raw_text,
            received_at=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        d: dict = {
            "envelope_id": self.envelope_id,
            "raw_text":    self.raw_text,
            "received_at": self.received_at,
            "errors":      self.errors,
        }
        if self.intake:
            d["intake"] = self.intake.to_dict()
        if self.task:
            d["task"] = self.task.to_dict()
        if self.priority:
            d["priority"] = self.priority.to_dict()
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict) -> "Envelope":
        env = cls(
            envelope_id=d["envelope_id"],
            raw_text=d["raw_text"],
            received_at=d["received_at"],
            errors=d.get("errors", []),
        )
        if "intake" in d:
            env.intake = IntakeSection.from_dict(d["intake"])
        if "task" in d:
            env.task = TaskSection.from_dict(d["task"])
        if "priority" in d:
            env.priority = PrioritySection.from_dict(d["priority"])
        return env

    @classmethod
    def from_json(cls, json_str: str) -> "Envelope":
        return cls.from_dict(json.loads(json_str))

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def add_error(self, agent: str, message: str) -> None:
        self.errors.append({
            "agent":     agent,
            "message":   message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def __repr__(self) -> str:  # pragma: no cover
        sections = [s for s in ("intake", "task", "priority") if getattr(self, s)]
        return (
            f"<Envelope id={self.envelope_id} "
            f"sections={sections} errors={len(self.errors)}>"
        )
