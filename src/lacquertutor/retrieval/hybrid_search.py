"""Hybrid search combining dense vector similarity with metadata filtering.

Implements the paper's retrieval pipeline:
  Dense search (Qwen text-embedding-v3) → Metadata filter → Score fusion
"""

from __future__ import annotations

import logging
from typing import Any

from lacquertutor.models.evidence import EvidenceCard
from lacquertutor.retrieval.embedder import Embedder
from lacquertutor.retrieval.indexer import COLLECTION_NAME

logger = logging.getLogger(__name__)


class HybridSearcher:
    """Qdrant-backed hybrid search with metadata boosting."""

    def __init__(
        self,
        embedder: Embedder,
        qdrant_client,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self.embedder = embedder
        self.qdrant = qdrant_client
        self.collection_name = collection_name

    async def search(
        self,
        query: str,
        stage: str | None = None,
        failure_mode: str | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for evidence using dense vector similarity + metadata filtering.

        Args:
            query: Natural language search query.
            stage: Optional workflow stage filter (hard filter).
            failure_mode: Optional failure mode filter (hard filter).
            top_k: Number of candidates to retrieve before reranking.

        Returns:
            List of dicts with keys: evidence_id, score, stage, failure_mode, summary_en.
        """
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        query_vector = await self.embedder.embed_query(query)

        # Build metadata filter
        conditions = []
        if stage:
            # Include exact stage match OR general cards
            conditions.append(
                FieldCondition(key="stage", match=MatchValue(value=stage))
            )
        if failure_mode:
            conditions.append(
                FieldCondition(key="failure_mode", match=MatchValue(value=failure_mode))
            )

        search_filter = Filter(should=conditions) if conditions else None

        # Dense vector search with optional metadata filter
        results = self.qdrant.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=search_filter,
            limit=top_k,
            with_payload=True,
        )

        candidates = []
        for hit in results:
            candidates.append({
                "evidence_id": hit.payload.get("evidence_id", ""),
                "score": hit.score,
                "stage": hit.payload.get("stage", ""),
                "failure_mode": hit.payload.get("failure_mode", ""),
                "summary_en": hit.payload.get("summary_en", ""),
                "is_safety": hit.payload.get("is_safety", False),
            })

        logger.debug(
            "hybrid_search: query=%r, stage=%s, failure=%s → %d candidates",
            query[:50], stage, failure_mode, len(candidates),
        )
        return candidates
