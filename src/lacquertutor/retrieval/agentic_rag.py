"""Self-corrective agentic RAG loop.

After initial retrieval + reranking, grades the relevance of results.
If quality is low, rewrites the query and re-retrieves (max 2 iterations).
"""

from __future__ import annotations

import logging
from typing import Any

from agents import Agent, ModelSettings, Runner

from lacquertutor.retrieval.hybrid_search import HybridSearcher
from lacquertutor.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)


class AgenticRAG:
    """Self-corrective retrieval loop with query rewriting.

    Flow:
      1. Search (hybrid) → top-20 candidates
      2. Rerank → top-k
      3. Grade relevance (LLM)
      4. If poor → rewrite query → go to step 1 (max 2 retries)
    """

    def __init__(
        self,
        searcher: HybridSearcher,
        reranker: Reranker,
        model,  # OpenAIChatCompletionsModel for grading/rewriting agents
        max_retries: int = 2,
    ) -> None:
        self.searcher = searcher
        self.reranker = reranker
        self.model = model
        self.max_retries = max_retries

    async def retrieve(
        self,
        query: str,
        stage: str | None = None,
        failure_mode: str | None = None,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        """Run the full agentic RAG pipeline.

        Returns top-k evidence candidates with stable references.
        """
        current_query = query

        for attempt in range(self.max_retries + 1):
            # Step 1-2: Search and rerank
            candidates = await self.searcher.search(
                current_query, stage=stage, failure_mode=failure_mode, top_k=20
            )
            reranked = await self.reranker.rerank(current_query, candidates, top_k=top_k)

            if not reranked:
                logger.warning("No results for query: %s", current_query[:50])
                if attempt < self.max_retries:
                    current_query = await self._rewrite_query(current_query, stage, failure_mode)
                    continue
                break

            # Step 3: Grade relevance
            is_relevant = await self._grade_relevance(current_query, reranked)

            if is_relevant or attempt == self.max_retries:
                logger.info(
                    "agentic_rag: %d results after %d attempts (relevant=%s)",
                    len(reranked), attempt + 1, is_relevant,
                )
                return reranked

            # Step 4: Rewrite and retry
            logger.info("Low relevance, rewriting query (attempt %d)", attempt + 1)
            current_query = await self._rewrite_query(current_query, stage, failure_mode)

        return reranked if reranked else []

    async def _grade_relevance(self, query: str, results: list[dict]) -> bool:
        """Use LLM to grade whether results are relevant to the query."""
        summaries = "\n".join(
            f"- [{r['evidence_id']}] {r['summary_en'][:100]}" for r in results
        )
        prompt = (
            f"查询: {query}\n\n"
            f"检索结果:\n{summaries}\n\n"
            f"这些检索结果是否与查询相关？回答'yes'或'no'。"
        )

        grader = Agent(
            name="RelevanceGrader",
            model=self.model,
            model_settings=ModelSettings(temperature=0.0),
            instructions="你是检索质量评估员。判断检索结果是否与查询相关。只回答'yes'或'no'。",
        )

        try:
            result = await Runner.run(grader, prompt)
            answer = str(result.final_output).strip().lower()
            return "yes" in answer
        except Exception:
            return True  # Assume relevant on failure

    async def _rewrite_query(
        self,
        query: str,
        stage: str | None,
        failure_mode: str | None,
    ) -> str:
        """Use LLM to rewrite query for better retrieval."""
        context = f"阶段: {stage or '未知'}, 故障: {failure_mode or '无'}"
        prompt = (
            f"原始查询效果不佳: {query}\n"
            f"上下文: {context}\n\n"
            f"请改写查询以更好地检索漆艺工艺知识。只输出改写后的查询文本。"
        )

        rewriter = Agent(
            name="QueryRewriter",
            model=self.model,
            model_settings=ModelSettings(temperature=0.3),
            instructions="你是查询改写专家。改写查询以提高漆艺知识检索效果。只输出改写后的查询。",
        )

        try:
            result = await Runner.run(rewriter, prompt)
            rewritten = str(result.final_output).strip()
            logger.debug("query rewrite: %r → %r", query[:50], rewritten[:50])
            return rewritten
        except Exception:
            return query
