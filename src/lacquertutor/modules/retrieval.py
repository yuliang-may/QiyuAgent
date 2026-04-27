"""Evidence retrieval module — Module 2.

Provides metadata-based evidence retrieval from the benchmark
evidence card catalog. This is a simplified mock replacing what
would be a full BM25 + dense embedding + reranking pipeline.
"""

from __future__ import annotations

from typing import Any

import structlog

from lacquertutor.models.evidence import EvidenceCard, EvidenceStore

logger = structlog.get_logger(__name__)


class EvidenceRetriever:
    """Retrieves relevant evidence cards by metadata filtering."""

    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def retrieve(
        self,
        stage: str,
        failure_mode: str | None = None,
        slot_state: dict[str, Any] | None = None,
        k: int = 4,
    ) -> list[EvidenceCard]:
        """Retrieve top-k evidence cards for the given context.

        Delegates to EvidenceStore.retrieve() which scores by:
        - Stage match: +2, general: +1
        - Failure mode match: +3
        - Safety cards: +1
        """
        results = self.store.retrieve(
            stage=stage,
            failure_mode=failure_mode,
            slot_state=slot_state,
            k=k,
        )

        logger.info(
            "evidence_retrieved",
            stage=stage,
            failure_mode=failure_mode,
            count=len(results),
            ids=[c.evidence_id for c in results],
        )

        return results

    @staticmethod
    def format_evidence_summaries(cards: list[EvidenceCard]) -> str:
        """Format evidence cards as text for LLM prompt injection."""
        if not cards:
            return "（无可用证据卡）"

        lines: list[str] = []
        for card in cards:
            fm = f"/{card.failure_mode}" if card.failure_mode else ""
            lines.append(
                f"- {card.evidence_id} [{card.stage}{fm}]: {card.summary_en}"
            )
        return "\n".join(lines)
