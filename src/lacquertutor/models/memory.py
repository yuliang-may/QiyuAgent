"""Memory and recall models for Hermes-inspired agent capabilities."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RememberedPreference(BaseModel):
    """A stable preference inferred from repeated past sessions."""

    slot_name: str
    value: str
    source_sessions: int = 0
    confidence: str = "low"
    last_seen_at: str = ""
    note: str = ""


class RecalledSession(BaseModel):
    """A past session recalled as relevant to the current task."""

    session_id: str
    task_type: str = ""
    stage: str = ""
    failure_mode: str | None = None
    overlap_score: float = 0.0
    matched_reasons: list[str] = Field(default_factory=list)
    summary: str = ""
    leading_step: str = ""
    has_contract: bool = False


class LearnedPlaybook(BaseModel):
    """A lightweight procedural playbook distilled from a solved session."""

    source_session_id: str
    title: str
    when_to_use: str = ""
    key_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
