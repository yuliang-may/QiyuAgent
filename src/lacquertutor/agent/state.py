"""Conversation state tracking with full audit log."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from lacquertutor.models.contract import PlanContract
from lacquertutor.models.evidence import EvidenceCard
from lacquertutor.models.execution import (
    ExecutionCheckpointState,
    ExecutionRecord,
    ExecutionStepState,
)
from lacquertutor.models.attachment import AttachmentMeta
from lacquertutor.models.memory import (
    LearnedPlaybook,
    RecalledSession,
    RememberedPreference,
)
from lacquertutor.models.slots import SlotState, create_slot_state
from lacquertutor.modules.verifier import VerificationResult
from lacquertutor.modules.voi_scorer import VoIScoringRecord


class DialogueTurn(BaseModel):
    """A single turn in the conversation."""

    turn: int
    role: str  # "user", "assistant", or "system"
    content: str
    slot_name: str | None = None  # which slot was targeted (if system question)


class ConversationState(BaseModel):
    """Complete state of a LacquerTutor conversation.

    Tracks all information needed to resume the pipeline at any point
    and provides a full audit trail for evaluation.
    """

    # Core state
    slot_state: SlotState = Field(default_factory=create_slot_state)
    task_type: str = ""
    stage: str = ""
    failure_mode: str | None = None
    original_query: str = ""
    scene_key: str = ""
    session_mode: str = "agent"
    user_id: str = ""
    parent_session_id: str | None = None
    parent_message_id: int | None = None

    # Dialogue tracking
    questions_asked: int = 0
    dialogue_history: list[DialogueTurn] = Field(default_factory=list)
    voi_logs: list[VoIScoringRecord] = Field(default_factory=list)
    pending_slot_name: str | None = None
    pending_question: str = ""
    pending_question_reason: str = ""

    # Evidence & output
    retrieved_evidence: list[EvidenceCard] = Field(default_factory=list)
    final_contract: PlanContract | None = None
    verification_result: VerificationResult | None = None
    remembered_preferences: list[RememberedPreference] = Field(default_factory=list)
    recalled_sessions: list[RecalledSession] = Field(default_factory=list)
    learned_playbooks: list[LearnedPlaybook] = Field(default_factory=list)
    module_artifact: dict[str, Any] = Field(default_factory=dict)
    agent_memories: list[dict[str, Any]] = Field(default_factory=list)
    execution_steps: list[ExecutionStepState] = Field(default_factory=list)
    execution_checkpoints: list[ExecutionCheckpointState] = Field(default_factory=list)
    execution_records: list[ExecutionRecord] = Field(default_factory=list)
    attachments: list[AttachmentMeta] = Field(default_factory=list)
    chat_references: list[dict[str, Any]] = Field(default_factory=list)
    chat_suggested_scene_keys: list[str] = Field(default_factory=list)

    # Revision tracking
    revision_count: int = 0
    stop_reason: str = ""

    def add_user_turn(self, content: str) -> None:
        turn = len(self.dialogue_history)
        self.dialogue_history.append(
            DialogueTurn(turn=turn, role="user", content=content)
        )

    def add_system_turn(self, content: str, slot_name: str | None = None) -> None:
        turn = len(self.dialogue_history)
        self.dialogue_history.append(
            DialogueTurn(
                turn=turn, role="system", content=content, slot_name=slot_name
            )
        )

    def add_assistant_turn(self, content: str) -> None:
        turn = len(self.dialogue_history)
        self.dialogue_history.append(
            DialogueTurn(turn=turn, role="assistant", content=content)
        )

    def fill_slots(
        self, extracted: dict[str, Any], source: str = "user"
    ) -> None:
        """Fill multiple slots from an extraction result."""
        for name, value in extracted.items():
            self.slot_state.fill(
                name=name,
                value=value,
                source=source,
                confirmed=source == "user",
                turn=self.questions_asked,
            )

    def to_audit_dict(self) -> dict[str, Any]:
        """Export state as a dict suitable for audit logging."""
        return {
            "original_query": self.original_query,
            "session_mode": self.session_mode,
            "user_id": self.user_id,
            "task_type": self.task_type,
            "stage": self.stage,
            "failure_mode": self.failure_mode,
            "scene_key": self.scene_key,
            "questions_asked": self.questions_asked,
            "stop_reason": self.stop_reason,
            "revision_count": self.revision_count,
            "filled_slots": self.slot_state.filled_dict,
            "unfilled_slots": self.slot_state.unfilled,
            "unfilled_hard_gates": self.slot_state.unfilled_hard_gates,
            "voi_logs": [log.model_dump() for log in self.voi_logs],
            "dialogue_turns": len(self.dialogue_history),
            "pending_slot_name": self.pending_slot_name,
            "pending_question": self.pending_question,
            "pending_question_reason": self.pending_question_reason,
            "remembered_preferences": [item.model_dump() for item in self.remembered_preferences],
            "recalled_sessions": [item.model_dump() for item in self.recalled_sessions],
            "learned_playbooks": [item.model_dump() for item in self.learned_playbooks],
            "module_artifact": self.module_artifact,
            "agent_memories": self.agent_memories,
            "execution_steps": [item.model_dump() for item in self.execution_steps],
            "execution_checkpoints": [item.model_dump() for item in self.execution_checkpoints],
            "execution_records": [item.model_dump() for item in self.execution_records],
            "attachments": [item.model_dump() for item in self.attachments],
            "chat_references": self.chat_references,
            "chat_suggested_scene_keys": self.chat_suggested_scene_keys,
            "parent_session_id": self.parent_session_id,
            "parent_message_id": self.parent_message_id,
        }

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data: str) -> "ConversationState":
        return cls.model_validate_json(data)
