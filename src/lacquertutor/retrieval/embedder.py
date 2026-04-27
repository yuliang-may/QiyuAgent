"""Embedding client using Qwen text-embedding-v3 via DashScope API.

DashScope provides an OpenAI-compatible embedding endpoint.
The model produces 1024-dim dense vectors suitable for Qdrant.
"""

from __future__ import annotations

import logging
from typing import Sequence

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "text-embedding-v3"
DEFAULT_DIMENSIONS = 1024
DEFAULT_MAX_BATCH_SIZE = 10


class Embedder:
    """Async embedding client wrapping DashScope's OpenAI-compatible API."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str = DEFAULT_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
    ) -> None:
        self.client = client
        self.model = model
        self.dimensions = dimensions
        self.max_batch_size = max_batch_size

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts into dense vectors.

        Args:
            texts: Strings to embed (max ~2048 tokens each for v3).

        Returns:
            List of float vectors, one per input text.
        """
        if not texts:
            return []

        if len(texts) > self.max_batch_size:
            vectors: list[list[float]] = []
            for offset in range(0, len(texts), self.max_batch_size):
                batch = texts[offset : offset + self.max_batch_size]
                vectors.extend(await self.embed_texts(batch))
            return vectors

        response = await self.client.embeddings.create(
            model=self.model,
            input=list(texts),
            dimensions=self.dimensions,
        )

        vectors = [item.embedding for item in response.data]
        logger.debug("embedded %d texts → %d-dim vectors", len(texts), self.dimensions)
        return vectors

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        result = await self.embed_texts([query])
        return result[0]
