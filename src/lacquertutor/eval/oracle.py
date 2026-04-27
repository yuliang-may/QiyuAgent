"""Oracle simulator for automated benchmark evaluation.

Replaces a human user by returning ground truth values from the
task's hidden_slot_values when asked about specific slots.
"""

from __future__ import annotations

from typing import Any

import structlog

from lacquertutor.models.slots import SLOT_SCHEMA

logger = structlog.get_logger(__name__)


class OracleSimulator:
    """Simulates user answers using hidden slot values from MER."""

    def __init__(self, hidden_slot_values: dict[str, Any]) -> None:
        self.hidden = hidden_slot_values

    async def answer_question(self, question: str, slot_name: str) -> str:
        """Generate a simulated user answer for a specific slot.

        Returns the hidden value wrapped in a natural sentence,
        or an "unknown" response if the value is not available.
        """
        value = self.hidden.get(slot_name)

        if value is None:
            answer = f"我不确定{self._slot_label(slot_name)}是什么。"
            logger.debug("oracle_unknown", slot=slot_name)
        else:
            label = self._slot_label(slot_name)
            answer = f"{label}是{value}。"
            logger.debug("oracle_answer", slot=slot_name, value=value)

        return answer

    @staticmethod
    def _slot_label(slot_name: str) -> str:
        """Get Chinese label for a slot name."""
        slot_def = SLOT_SCHEMA.get(slot_name)
        return slot_def.label_zh if slot_def else slot_name
