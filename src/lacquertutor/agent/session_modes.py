"""Shared session mode presets for CLI and web chat flows."""

from __future__ import annotations

from typing import Any

SESSION_MODES = {"workflow", "agent"}
DEFAULT_SESSION_MODE = "agent"


def normalize_session_mode(mode: str | None) -> str:
    """Normalize a user-provided session mode."""
    normalized = (mode or DEFAULT_SESSION_MODE).strip().lower()
    if normalized not in SESSION_MODES:
        raise ValueError(
            f"Unsupported session mode '{mode}'. Expected one of: {', '.join(sorted(SESSION_MODES))}."
        )
    return normalized


def get_session_mode_options(mode: str | None) -> dict[str, Any]:
    """Return pipeline runtime options for a chat session mode."""
    normalized = normalize_session_mode(mode)

    if normalized == "workflow":
        return {
            "enable_dialogue": True,
            "enable_verifier": True,
            "enable_retrieval": True,
            "slot_selection": "prompt",
        }

    return {
        "enable_dialogue": True,
        "enable_verifier": True,
        "enable_retrieval": True,
        "slot_selection": "voi",
    }
