"""VoI scoring data models and deterministic logic.

The LLM-based scoring is now handled by SDK agents in agent/tools.py.
This module provides the VoIScoringRecord model and the deterministic
hard-gate floor adjustment formula.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from lacquertutor.models.slots import HARD_GATE_SLOTS


class VoIScoringRecord(BaseModel):
    """Audit record for a single VoI scoring turn."""

    turn: int = 0
    raw_scores: dict[str, int] = Field(default_factory=dict)
    adjusted_scores: dict[str, int] = Field(default_factory=dict)
    reasons: dict[str, str] = Field(default_factory=dict)
    ranked_list: list[tuple[str, int]] = Field(default_factory=list)
    selected_slot: str | None = None
    decision: str = ""  # "ask" or "stop"
    stop_reason: str = ""


def adjust_scores(raw_scores: dict[str, int]) -> dict[str, int]:
    """Apply hard-gate floor: ã(s) = max(r(s), 2·g(s)).

    Ensures hard-gate slots never drop below score 2.
    """
    return {
        s: max(score, 2 * (1 if s in HARD_GATE_SLOTS else 0))
        for s, score in raw_scores.items()
    }


def rank_scores(scores: dict[str, int]) -> list[tuple[str, int]]:
    """Sort slots by adjusted score (desc), hard-gate first on ties."""
    hard_set = set(HARD_GATE_SLOTS)
    return sorted(
        scores.items(),
        key=lambda x: (-x[1], -(1 if x[0] in hard_set else 0), x[0]),
    )
