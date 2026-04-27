"""Evidence card catalog and mock retrieval store.

Loads evidence_cards_v0.json and provides metadata-based filtering
as a simplified replacement for a full retrieval pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EvidencePointer(BaseModel):
    """Pointer to source material (currently TBD placeholders)."""

    doc_id: str = "TBD"
    page: int | None = None
    figure: str | None = None
    chunk_id: str | None = None


class EvidenceCard(BaseModel):
    """A single evidence card from the benchmark catalog."""

    evidence_id: str
    stage: str
    failure_mode: str | None = None
    pointer: EvidencePointer = Field(default_factory=EvidencePointer)
    summary_en: str = ""

    @property
    def is_safety(self) -> bool:
        return self.evidence_id.startswith("E-SAFE")

    @property
    def is_general(self) -> bool:
        return self.stage == "general"


class EvidenceStore:
    """In-memory evidence store with metadata-based retrieval.

    Provides filtering by stage and failure_mode, plus relevance scoring
    to select top-k evidence cards for contract generation.
    """

    def __init__(self, cards: list[EvidenceCard]) -> None:
        self.cards = cards
        self._by_id: dict[str, EvidenceCard] = {c.evidence_id: c for c in cards}
        self._by_stage: dict[str, list[EvidenceCard]] = {}
        self._by_failure: dict[str, list[EvidenceCard]] = {}

        for card in cards:
            self._by_stage.setdefault(card.stage, []).append(card)
            if card.failure_mode:
                self._by_failure.setdefault(card.failure_mode, []).append(card)

    def get(self, evidence_id: str) -> EvidenceCard | None:
        return self._by_id.get(evidence_id)

    def filter_by_stage(self, stage: str) -> list[EvidenceCard]:
        return self._by_stage.get(stage, [])

    def filter_by_failure(self, failure_mode: str) -> list[EvidenceCard]:
        return self._by_failure.get(failure_mode, [])

    def retrieve(
        self,
        stage: str,
        failure_mode: str | None = None,
        slot_state: dict[str, Any] | None = None,
        k: int = 4,
    ) -> list[EvidenceCard]:
        """Retrieve top-k evidence cards by relevance scoring.

        Scoring rules:
        - Stage match: +2
        - General stage: +1 (always included as candidates)
        - Failure mode match: +3
        - Safety cards: +1 (always included as baseline)
        """
        scored: list[tuple[float, EvidenceCard]] = []

        for card in self.cards:
            score = 0.0

            # Stage relevance
            if card.stage == stage:
                score += 2.0
            elif card.is_general:
                score += 1.0
            else:
                # Different non-general stage — low relevance
                score += 0.1

            # Failure mode relevance
            if failure_mode and card.failure_mode == failure_mode:
                score += 3.0

            # Safety cards always get a boost
            if card.is_safety:
                score += 1.0

            scored.append((score, card))

        # Sort by score descending, then by evidence_id for stability
        scored.sort(key=lambda x: (-x[0], x[1].evidence_id))

        return [card for _, card in scored[:k]]

    @classmethod
    def from_json(cls, path: str | Path) -> EvidenceStore:
        """Load evidence cards from benchmark JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        cards = [EvidenceCard.model_validate(c) for c in data["evidence_cards"]]
        return cls(cards)

    def __len__(self) -> int:
        return len(self.cards)
