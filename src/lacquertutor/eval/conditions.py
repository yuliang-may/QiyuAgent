"""Baseline condition configurations for evaluation experiments.

Six conditions matching the paper's ablation design:
- B0: Generic LLM (no KB, no dialogue, no verifier) — floor baseline
- B1: RAG-only (no dialogue, no verifier)
- B2-random: Random slot selection
- B2-prompt: LLM-chosen slot selection (raw scores, no VoI adjustment)
- B2-VoI: VoI-scored slot selection (with hard-gate floor)
- S2: Full system (VoI + verifier)
"""

from __future__ import annotations

from pydantic import BaseModel


class ConditionConfig(BaseModel):
    """Configuration for an evaluation condition."""

    name: str
    enable_dialogue: bool
    slot_selection: str  # "none", "random", "prompt", "voi"
    enable_retrieval: bool = True
    enable_verifier: bool = False


CONDITIONS: dict[str, ConditionConfig] = {
    "B0": ConditionConfig(
        name="B0",
        enable_dialogue=False,
        slot_selection="none",
        enable_retrieval=False,
        enable_verifier=False,
    ),
    "B1": ConditionConfig(
        name="B1",
        enable_dialogue=False,
        slot_selection="none",
        enable_verifier=False,
    ),
    "B2-random": ConditionConfig(
        name="B2-random",
        enable_dialogue=True,
        slot_selection="random",
        enable_verifier=False,
    ),
    "B2-prompt": ConditionConfig(
        name="B2-prompt",
        enable_dialogue=True,
        slot_selection="prompt",
        enable_verifier=False,
    ),
    "B2-VoI": ConditionConfig(
        name="B2-VoI",
        enable_dialogue=True,
        slot_selection="voi",
        enable_verifier=False,
    ),
    "S2": ConditionConfig(
        name="S2",
        enable_dialogue=True,
        slot_selection="voi",
        enable_verifier=True,
    ),
}

ALL_CONDITIONS = list(CONDITIONS.keys())


def get_condition(name: str) -> ConditionConfig:
    """Get a condition config by name, raising if not found."""
    if name not in CONDITIONS:
        raise ValueError(
            f"Unknown condition '{name}'. Available: {ALL_CONDITIONS}"
        )
    return CONDITIONS[name]
