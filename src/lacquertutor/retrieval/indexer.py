"""Qdrant indexer — builds and manages the evidence collection.

Indexes evidence cards (and optionally raw KB chunks from Dify exports)
into Qdrant with dense vectors and metadata payloads for hybrid search.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence

from lacquertutor.models.evidence import EvidenceCard, EvidenceStore
from lacquertutor.retrieval.embedder import Embedder

logger = logging.getLogger(__name__)

COLLECTION_NAME = "lacquertutor_evidence"

# ── Batch size for embedding API calls ────────────────────────────
EMBED_BATCH_SIZE = 20


class QdrantIndexer:
    """Builds a Qdrant collection from evidence cards and/or KB segments."""

    def __init__(
        self,
        embedder: Embedder,
        qdrant_client,  # qdrant_client.QdrantClient or AsyncQdrantClient
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self.embedder = embedder
        self.qdrant = qdrant_client
        self.collection_name = collection_name

    async def create_collection(self, vector_size: int = 1024) -> None:
        """Create or recreate the Qdrant collection."""
        from qdrant_client.models import Distance, VectorParams

        self.qdrant.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Created collection '%s' (%d-dim)", self.collection_name, vector_size)

    async def index_evidence_cards(self, cards: Sequence[EvidenceCard]) -> int:
        """Index evidence cards into Qdrant with embeddings."""
        from qdrant_client.models import PointStruct

        texts = [card.summary_en for card in cards]
        vectors = await self._embed_batched(texts)

        points = []
        for i, (card, vector) in enumerate(zip(cards, vectors)):
            payload = {
                "evidence_id": card.evidence_id,
                "stage": card.stage,
                "failure_mode": card.failure_mode or "",
                "summary_en": card.summary_en,
                "is_safety": card.is_safety,
                "is_general": card.is_general,
                "source": "evidence_card",
            }
            points.append(PointStruct(id=i, vector=vector, payload=payload))

        self.qdrant.upsert(collection_name=self.collection_name, points=points)
        logger.info("Indexed %d evidence cards", len(points))
        return len(points)

    async def index_kb_segments(
        self,
        segments: list[dict[str, Any]],
        id_offset: int = 10000,
        min_word_count: int = 20,
    ) -> int:
        """Index KB segments (from Dify export) into Qdrant.

        Args:
            segments: List of dicts with keys: segment_id, content, word_count, dataset_name.
            id_offset: Starting point ID (to avoid collision with evidence cards).
            min_word_count: Skip segments shorter than this.

        Returns:
            Number of indexed segments.
        """
        from qdrant_client.models import PointStruct

        # Filter out trivial/image-only segments
        valid = []
        for s in segments:
            content = s.get("content", "")
            word_count = s.get("word_count", 0)
            if word_count < min_word_count:
                continue
            # Strip image markdown for embedding (keep text only)
            text = _strip_images(content)
            if len(text) < 20:
                continue
            valid.append((s, text))

        if not valid:
            logger.warning("No valid segments to index")
            return 0

        logger.info("Indexing %d KB segments (filtered from %d)", len(valid), len(segments))

        texts = [text for _, text in valid]
        vectors = await self._embed_batched(texts)

        points = []
        for i, ((seg, text), vector) in enumerate(zip(valid, vectors)):
            payload = {
                "segment_id": seg.get("segment_id", ""),
                "content": text[:2000],  # Truncate for payload storage
                "word_count": seg.get("word_count", 0),
                "dataset_name": seg.get("dataset_name", ""),
                "source": "kb_segment",
                # These will be empty for KB segments; evidence cards have them
                "evidence_id": "",
                "stage": "",
                "failure_mode": "",
            }
            points.append(PointStruct(id=id_offset + i, vector=vector, payload=payload))

        # Upsert in batches to avoid memory issues
        batch_size = 100
        for batch_start in range(0, len(points), batch_size):
            batch = points[batch_start : batch_start + batch_size]
            self.qdrant.upsert(collection_name=self.collection_name, points=batch)

        logger.info("Indexed %d KB segments", len(points))
        return len(points)

    async def index_from_store(self, evidence_store: EvidenceStore) -> int:
        """Convenience: index all cards from an EvidenceStore."""
        cards = list(evidence_store._cards.values())
        await self.create_collection(self.embedder.dimensions)
        return await self.index_evidence_cards(cards)

    async def index_full(
        self,
        evidence_store: EvidenceStore,
        kb_dir: Path | None = None,
    ) -> dict[str, int]:
        """Index everything: evidence cards + KB segments from Dify exports.

        Args:
            evidence_store: In-memory evidence cards.
            kb_dir: Directory containing fuzi_kb_segments.json and tongyong_kb_segments.json.

        Returns:
            Dict with counts: {"evidence_cards": N, "fuzi_kb": N, "tongyong_kb": N}.
        """
        await self.create_collection(self.embedder.dimensions)
        counts = {}

        # Index evidence cards
        cards = list(evidence_store._cards.values())
        counts["evidence_cards"] = await self.index_evidence_cards(cards)

        # Index KB segments if available
        if kb_dir:
            offset = 10000
            for name in ["fuzi_kb_segments", "tongyong_kb_segments"]:
                path = kb_dir / f"{name}.json"
                if path.exists():
                    segments = json.loads(path.read_text(encoding="utf-8"))
                    n = await self.index_kb_segments(segments, id_offset=offset)
                    counts[name.replace("_segments", "")] = n
                    offset += n + 1000
                else:
                    logger.info("KB file not found: %s", path)

        return counts

    async def _embed_batched(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches to respect API limits."""
        all_vectors = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            vectors = await self.embedder.embed_texts(batch)
            all_vectors.extend(vectors)
            if i + EMBED_BATCH_SIZE < len(texts):
                logger.debug("Embedded %d/%d texts", i + len(batch), len(texts))
        return all_vectors


def _strip_images(text: str) -> str:
    """Remove markdown image links from text, keeping surrounding text."""
    import re
    # Remove ![alt](url) patterns
    cleaned = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", text)
    # Unescape \\n from PostgreSQL COPY
    cleaned = cleaned.replace("\\n", "\n")
    # Collapse multiple newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
