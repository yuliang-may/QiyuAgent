"""VectorEvidenceStore — Qdrant-backed evidence store.

Implements the same retrieve() interface as EvidenceStore (models/evidence.py)
but uses the full hybrid search + rerank + agentic RAG pipeline.

Falls back to in-memory EvidenceStore when Qdrant is not available.
"""

from __future__ import annotations

import logging
from typing import Any

from lacquertutor.models.evidence import EvidenceCard, EvidenceStore
from lacquertutor.retrieval.agentic_rag import AgenticRAG
from lacquertutor.retrieval.embedder import Embedder
from lacquertutor.retrieval.hybrid_search import HybridSearcher
from lacquertutor.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)


class VectorEvidenceStore:
    """Qdrant-backed evidence store with hybrid search.

    Provides the same interface as EvidenceStore.retrieve() but
    uses the paper's full retrieval pipeline.
    """

    def __init__(
        self,
        evidence_store: EvidenceStore,
        agentic_rag: AgenticRAG,
    ) -> None:
        self._fallback = evidence_store
        self._rag = agentic_rag
        # Map evidence_id → EvidenceCard for result hydration
        self._card_index: dict[str, EvidenceCard] = {
            card.evidence_id: card
            for card in evidence_store._cards.values()
        }

    async def retrieve(
        self,
        stage: str | None = None,
        failure_mode: str | None = None,
        slot_state: dict[str, Any] | None = None,
        k: int = 4,
    ) -> list[EvidenceCard]:
        """Retrieve evidence cards using the agentic RAG pipeline.

        Args:
            stage: Workflow stage for metadata filtering.
            failure_mode: Failure mode for metadata filtering.
            slot_state: Current slot state (used to build query).
            k: Number of results.

        Returns:
            List of EvidenceCard objects.
        """
        # Build query from context
        query_parts = []
        if stage:
            query_parts.append(f"漆艺{stage}阶段")
        if failure_mode:
            query_parts.append(f"故障: {failure_mode}")
        if slot_state:
            for name, value in slot_state.items():
                query_parts.append(f"{name}: {value}")
        if not query_parts:
            query_parts.append("漆艺工艺操作步骤")

        query = "，".join(query_parts)

        try:
            results = await self._rag.retrieve(
                query=query,
                stage=stage,
                failure_mode=failure_mode,
                top_k=k,
            )

            # Hydrate results into EvidenceCard objects
            cards = []
            for result in results:
                eid = result.get("evidence_id", "")
                card = self._card_index.get(eid)
                if card:
                    cards.append(card)
                else:
                    logger.warning("Evidence ID %s not found in card index", eid)

            if cards:
                return cards

        except Exception as e:
            logger.warning("Vector retrieval failed (%s), falling back to metadata", e)

        # Fallback to metadata-based retrieval
        return self._fallback.retrieve(
            stage=stage, failure_mode=failure_mode,
            slot_state=slot_state, k=k,
        )


def create_vector_store(
    evidence_store: EvidenceStore,
    openai_client,
    qdrant_client,
    model,
    embedding_model: str = "text-embedding-v3",
    rerank_model: str = "gte-rerank",
    collection_name: str = "lacquertutor_evidence",
) -> VectorEvidenceStore:
    """Factory function to create a fully-wired VectorEvidenceStore.

    Args:
        evidence_store: In-memory evidence store (for fallback + card index).
        openai_client: AsyncOpenAI client for DashScope API.
        qdrant_client: Qdrant client instance.
        model: OpenAIChatCompletionsModel for grading/rewriting agents.
        embedding_model: Model name for text embeddings.
        rerank_model: Model name for cross-encoder reranking.
        collection_name: Qdrant collection name.
    """
    embedder = Embedder(openai_client, model=embedding_model)
    searcher = HybridSearcher(embedder, qdrant_client, collection_name)
    reranker = Reranker(openai_client, model=rerank_model)
    rag = AgenticRAG(searcher, reranker, model=model)

    return VectorEvidenceStore(evidence_store, rag)
