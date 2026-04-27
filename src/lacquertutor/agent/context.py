"""Shared context object for the LacquerTutor agent.

The context is passed to every tool, guardrail, and handoff via
RunContextWrapper[LacquerTutorContext]. It holds all mutable state
that tools need to read and write during an agent run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from lacquertutor.models.evidence import EvidenceCard, EvidenceStore
from lacquertutor.models.slots import SlotState, create_slot_state
from lacquertutor.modules.voi_scorer import VoIScoringRecord

# Callback type: (question_text, slot_name) → user_answer
AnswerFn = Callable[[str, str], Awaitable[str]]


@dataclass
class LacquerTutorContext:
    """Dependency-injection context shared across all tools.

    This is NOT sent to the LLM — it's local state that tools
    read from and write to during the agent run.
    """

    # Dependencies
    evidence_store: EvidenceStore
    answer_fn: AnswerFn | None = None  # Interactive user callback
    vector_store: Any | None = None  # VectorEvidenceStore when Qdrant is available

    # Slot state
    slot_state: SlotState = field(default_factory=create_slot_state)

    # Task metadata
    task_type: str = ""
    stage: str = ""
    failure_mode: str | None = None
    original_query: str = ""

    # Dialogue tracking
    questions_asked: int = 0
    max_questions: int = 6
    voi_logs: list[VoIScoringRecord] = field(default_factory=list)

    # Evidence
    retrieved_evidence: list[EvidenceCard] = field(default_factory=list)
    evidence_top_k: int = 4

    # Revision tracking
    revision_count: int = 0
    max_revisions: int = 2
    stop_reason: str = ""

    @property
    def filled_slots_json(self) -> str:
        import json
        return json.dumps(self.slot_state.filled_dict, ensure_ascii=False)

    @property
    def unfilled_list(self) -> str:
        return ", ".join(self.slot_state.unfilled) or "无"

    @property
    def unfilled_hard_gates_list(self) -> str:
        return ", ".join(self.slot_state.unfilled_hard_gates) or "无"

    def to_audit_dict(self) -> dict[str, Any]:
        """Export state for audit logging."""
        return {
            "original_query": self.original_query,
            "task_type": self.task_type,
            "stage": self.stage,
            "failure_mode": self.failure_mode,
            "questions_asked": self.questions_asked,
            "filled_slots": self.slot_state.filled_dict,
            "unfilled_slots": self.slot_state.unfilled,
            "unfilled_hard_gates": self.slot_state.unfilled_hard_gates,
            "voi_logs": [log.model_dump() for log in self.voi_logs],
            "revision_count": self.revision_count,
        }

    def to_json(self) -> str:
        """Serialize context to JSON for session persistence."""
        import json
        return json.dumps(self.to_audit_dict(), ensure_ascii=False)

    @classmethod
    def from_json(
        cls,
        data: str,
        evidence_store: EvidenceStore,
        answer_fn: AnswerFn | None = None,
    ) -> "LacquerTutorContext":
        """Restore context from JSON. Requires evidence_store injection."""
        import json
        d = json.loads(data)
        ctx = cls(evidence_store=evidence_store, answer_fn=answer_fn)
        ctx.original_query = d.get("original_query", "")
        ctx.task_type = d.get("task_type", "")
        ctx.stage = d.get("stage", "")
        ctx.failure_mode = d.get("failure_mode")
        ctx.questions_asked = d.get("questions_asked", 0)
        ctx.revision_count = d.get("revision_count", 0)
        for name, value in d.get("filled_slots", {}).items():
            ctx.slot_state.fill(name, value, source="restored")
        return ctx
