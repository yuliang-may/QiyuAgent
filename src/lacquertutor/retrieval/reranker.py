"""Cross-encoder reranker using gte-rerank via DashScope API.

Takes candidate results from hybrid search and reranks them
using a cross-encoder model for more accurate relevance scoring.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

DEFAULT_RERANK_MODEL = "gte-rerank-v2"


class Reranker:
    """Cross-encoder reranker via DashScope rerank API.

    DashScope exposes reranking as a separate endpoint.
    Falls back to score-based passthrough if API unavailable.
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str = DEFAULT_RERANK_MODEL,
    ) -> None:
        self.client = client
        self.model = model

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        """Rerank candidates by cross-encoder relevance.

        Args:
            query: The original search query.
            candidates: List of dicts with 'summary_en' and other fields.
            top_k: Number of results to return after reranking.

        Returns:
            Top-k candidates sorted by reranked relevance.
        """
        if not candidates:
            return []

        if len(candidates) <= top_k:
            return candidates

        try:
            import httpx

            rerank_url = self._resolve_rerank_url()
            headers = {
                "Authorization": f"Bearer {self.client.api_key}",
                "Content-Type": "application/json",
            }

            documents = [c["summary_en"] for c in candidates]
            payload = {
                "model": self.model,
                "input": {
                    "query": query,
                    "documents": documents,
                },
                "parameters": {
                    "top_n": top_k,
                    "return_documents": False,
                },
            }

            async with httpx.AsyncClient() as http:
                resp = await http.post(
                    rerank_url,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )

            if resp.status_code == 200:
                data = resp.json()
                results_order = data.get("output", {}).get("results", [])
                reranked = []
                for item in results_order[:top_k]:
                    idx = item["index"]
                    candidate = candidates[idx].copy()
                    candidate["rerank_score"] = item.get("relevance_score", 0)
                    reranked.append(candidate)
                logger.debug("reranked %d → %d candidates", len(candidates), len(reranked))
                return reranked
            else:
                logger.warning("Rerank API returned %d, falling back to score-based", resp.status_code)

        except Exception as e:
            logger.warning("Reranker failed (%s), falling back to score-based", e)

        # Fallback: return top-k by original score
        sorted_candidates = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)
        return sorted_candidates[:top_k]

    def _resolve_rerank_url(self) -> str:
        base_url = str(self.client.base_url).rstrip("/")
        if "/compatible-mode/v1" in base_url:
            host = base_url.split("/compatible-mode/v1", 1)[0]
            return f"{host}/api/v1/services/rerank/text-rerank/text-rerank"
        if base_url.endswith("/api/v1"):
            return f"{base_url}/services/rerank/text-rerank/text-rerank"
        return f"{base_url}/api/v1/services/rerank/text-rerank/text-rerank"
