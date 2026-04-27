"""Standard RAG retriever for chat-first knowledge access.

Pipeline:
  pre-chunked KB segments
  -> dense retrieval in Qdrant
  -> lexical candidate retrieval
  -> reciprocal-rank fusion
  -> cross-encoder rerank
  -> top-k references
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from lacquertutor.config import Settings
from lacquertutor.retrieval.embedder import Embedder
from lacquertutor.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)

COLLECTION_NAME = "lacquertutor_kb_segments"
EMBED_BATCH_SIZE = 20
RRF_K = 60

STOPWORDS: set[str] = {
    "我是",
    "我们",
    "你们",
    "一下",
    "一个",
    "这个",
    "那个",
    "现在",
    "已经",
    "还有",
    "以及",
    "希望",
    "可以",
    "需要",
    "如何",
    "怎么",
    "什么",
    "哪些",
    "问题",
    "情况",
    "当前",
    "对象",
    "目标",
    "知道",
    "确认",
    "步骤",
    "关键",
    "信息",
    "模块",
    "场景",
    "引导",
    "系统",
    "智能体",
}


@dataclass(frozen=True)
class RAGDocument:
    segment_id: str
    source_label: str
    title: str
    content: str
    image_urls: list[str]

    @property
    def embedding_text(self) -> str:
        return f"{self.title}\n{self.content[:1800]}".strip()


class StandardRAGRetriever:
    """Dense + lexical + rerank retriever over pre-chunked KB segments."""

    def __init__(
        self,
        *,
        documents: list[RAGDocument],
        llm_client: AsyncOpenAI | None,
        settings: Settings,
    ) -> None:
        self.documents = documents
        self.settings = settings
        self.llm_client = llm_client
        self.embedder = (
            Embedder(llm_client, model=settings.embedding_model)
            if llm_client is not None and settings.llm_api_key
            else None
        )
        self.reranker = (
            Reranker(llm_client, model=settings.rerank_model)
            if llm_client is not None and settings.llm_api_key
            else None
        )
        self.index_dir = self._resolve_path(settings.rag_index_dir)
        self.state_path = self.index_dir / "state.json"
        self.collection_name = settings.rag_collection or COLLECTION_NAME
        self._qdrant = None
        self._prepared = False
        self._prepare_lock = asyncio.Lock()
        self._doc_by_id: dict[str, RAGDocument] = {doc.segment_id: doc for doc in documents}
        self._normalized_title: dict[str, str] = {
            doc.segment_id: _normalize_text(doc.title) for doc in documents
        }
        self._normalized_content: dict[str, str] = {
            doc.segment_id: _normalize_text(doc.content) for doc in documents
        }
        self._enabled = self.embedder is not None and self.reranker is not None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def prepare(self) -> None:
        if self._prepared or not self.enabled:
            return

        async with self._prepare_lock:
            if self._prepared:
                return

            from qdrant_client import QdrantClient

            self.index_dir.mkdir(parents=True, exist_ok=True)
            if self.settings.qdrant_url:
                self._qdrant = QdrantClient(url=self.settings.qdrant_url)
            else:
                self._qdrant = QdrantClient(
                    path=str(self.index_dir / "qdrant"),
                    force_disable_check_same_thread=True,
                )

            desired_state = {
                "collection": self.collection_name,
                "embedding_model": self.settings.embedding_model,
                "rerank_model": self.settings.rerank_model,
                "document_count": len(self.documents),
                "digest": self._corpus_digest(),
            }

            current_state = self._read_state()
            collection_exists = self._qdrant.collection_exists(self.collection_name)
            if not collection_exists or current_state != desired_state:
                await self._rebuild_index()
                self.state_path.write_text(
                    json.dumps(desired_state, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            self._prepared = True

    async def retrieve(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        if not query.strip():
            return []

        lexical_candidates = self._lexical_search(query, limit=max(limit * 3, self.settings.rag_dense_top_k))
        if not self.enabled:
            return lexical_candidates[:limit]

        await self.prepare()
        dense_candidates = await self._dense_search(query, top_k=self.settings.rag_dense_top_k)

        fused = self._rrf_fuse(dense_candidates, lexical_candidates)
        if not fused:
            return lexical_candidates[:limit]

        rerank_pool = fused[: self.settings.rag_candidate_pool]
        rerank_input = [
            {
                **item,
                "summary_en": self._doc_by_id[item["segment_id"]].content[:1000],
            }
            for item in rerank_pool
        ]

        try:
            reranked = await self.reranker.rerank(query, rerank_input, top_k=limit) if self.reranker else rerank_input[:limit]
        except Exception as exc:
            logger.warning("standard_rag_rerank_failed: %s", exc)
            reranked = rerank_input[:limit]

        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in reranked[:limit]:
            doc = self._doc_by_id[item["segment_id"]]
            excerpt = self._best_excerpt(doc.content, query)
            dedupe_key = (doc.title, excerpt)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            results.append(
                {
                    "segment_id": doc.segment_id,
                    "source_label": doc.source_label,
                    "title": doc.title,
                    "excerpt": excerpt,
                    "score": round(float(item.get("rerank_score", item.get("rrf_score", item.get("dense_score", item.get("lexical_score", 0.0))))), 4),
                    "image_urls": doc.image_urls[:4],
                }
            )
            if len(results) >= limit:
                break

        return results

    async def _rebuild_index(self) -> None:
        from qdrant_client.models import Distance, PointStruct, VectorParams

        assert self._qdrant is not None
        assert self.embedder is not None

        self._qdrant.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.embedder.dimensions, distance=Distance.COSINE),
        )

        texts = [doc.embedding_text for doc in self.documents]
        vectors = await self._embed_batched(texts)

        points = []
        for doc, vector in zip(self.documents, vectors):
            points.append(
                PointStruct(
                    id=doc.segment_id,
                    vector=vector,
                    payload={
                        "segment_id": doc.segment_id,
                        "source_label": doc.source_label,
                        "title": doc.title,
                        "content": doc.content[:4000],
                    },
                )
            )

        for offset in range(0, len(points), 128):
            self._qdrant.upsert(
                collection_name=self.collection_name,
                points=points[offset : offset + 128],
            )

        logger.info("standard_rag_index_built: %d docs", len(points))

    async def _dense_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        assert self._qdrant is not None
        assert self.embedder is not None

        response = self._qdrant.query_points(
            collection_name=self.collection_name,
            query=await self.embedder.embed_query(query),
            limit=top_k,
            with_payload=True,
        )

        points = getattr(response, "points", []) or []
        candidates: list[dict[str, Any]] = []
        for rank, point in enumerate(points, start=1):
            payload = point.payload or {}
            segment_id = str(payload.get("segment_id") or point.id)
            if segment_id not in self._doc_by_id:
                continue
            candidates.append(
                {
                    "segment_id": segment_id,
                    "dense_score": float(point.score or 0.0),
                    "dense_rank": rank,
                }
            )
        return candidates

    def _lexical_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        keywords = _extract_keywords(query)
        if not keywords:
            return []

        normalized_query = _normalize_text(query)
        candidates: list[dict[str, Any]] = []

        for doc in self.documents:
            title = self._normalized_title[doc.segment_id]
            content = self._normalized_content[doc.segment_id]
            score = 0.0
            matched_keywords: set[str] = set()

            for keyword in keywords:
                matched = False
                if keyword in title:
                    score += 4.0
                    matched = True
                if keyword in content:
                    score += 1.5 + min(content.count(keyword), 4) * 0.6
                    matched = True
                if matched:
                    matched_keywords.add(keyword)

            if normalized_query and normalized_query in content:
                score += 3.0

            score += len(matched_keywords) * 2.5

            if score <= 0:
                continue

            candidates.append(
                {
                    "segment_id": doc.segment_id,
                    "lexical_score": score,
                }
            )

        candidates.sort(key=lambda item: (-item["lexical_score"], item["segment_id"]))
        for rank, item in enumerate(candidates, start=1):
            item["lexical_rank"] = rank

        return candidates[:limit]

    def _rrf_fuse(
        self,
        dense_candidates: list[dict[str, Any]],
        lexical_candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        combined: dict[str, dict[str, Any]] = {}

        for item in dense_candidates:
            segment_id = item["segment_id"]
            combined.setdefault(segment_id, {"segment_id": segment_id})
            combined[segment_id].update(item)

        for item in lexical_candidates:
            segment_id = item["segment_id"]
            combined.setdefault(segment_id, {"segment_id": segment_id})
            combined[segment_id].update(item)

        for item in combined.values():
            dense_rank = int(item.get("dense_rank", 10_000))
            lexical_rank = int(item.get("lexical_rank", 10_000))
            item["rrf_score"] = (1.0 / (RRF_K + dense_rank)) + (1.0 / (RRF_K + lexical_rank))

        return sorted(combined.values(), key=lambda item: (-item["rrf_score"], item["segment_id"]))

    async def _embed_batched(self, texts: list[str]) -> list[list[float]]:
        assert self.embedder is not None

        vectors: list[list[float]] = []
        for offset in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[offset : offset + EMBED_BATCH_SIZE]
            vectors.extend(await self.embedder.embed_texts(batch))
        return vectors

    def _best_excerpt(self, text: str, query: str) -> str:
        keywords = _extract_keywords(query)
        sentences = re.split(r"(?<=[。！？；.!?])\s*", text)
        for keyword in keywords:
            for sentence in sentences:
                if keyword in _normalize_text(sentence):
                    return _summarize(sentence, limit=140)
        return _summarize(sentences[0] if sentences else text, limit=140)

    def _read_state(self) -> dict[str, Any] | None:
        if not self.state_path.exists():
            return None
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _corpus_digest(self) -> str:
        hasher = hashlib.sha256()
        for doc in self.documents:
            hasher.update(doc.segment_id.encode("utf-8"))
            hasher.update(doc.title.encode("utf-8"))
            hasher.update(doc.content.encode("utf-8"))
        return hasher.hexdigest()

    @staticmethod
    def _resolve_path(raw: str) -> Path:
        path = Path(raw)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        return path.resolve()


def _normalize_keyword_fragment(value: str) -> list[str]:
    lowered = str(value or "").strip().lower()
    if not lowered:
        return []

    fragments = [lowered]
    for stopword in sorted(STOPWORDS, key=len, reverse=True):
        if stopword and stopword in lowered:
            fragments.extend(part.strip() for part in lowered.split(stopword))

    keywords: list[str] = []
    for fragment in fragments:
        if len(fragment) < 2 or fragment in STOPWORDS:
            continue
        if fragment not in keywords:
            keywords.append(fragment)

        if re.fullmatch(r"[\u4e00-\u9fff]+", fragment) and len(fragment) > 2:
            for size in range(2, min(4, len(fragment)) + 1):
                for index in range(0, len(fragment) - size + 1):
                    gram = fragment[index : index + size]
                    if gram in STOPWORDS or len(gram) < 2:
                        continue
                    if gram not in keywords:
                        keywords.append(gram)

    return keywords


def _extract_keywords(query: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_+-]{2,}|[\u4e00-\u9fff]{2,}", query.lower())
    keywords: list[str] = []
    for token in tokens:
        for keyword in _normalize_keyword_fragment(token):
            if keyword not in keywords:
                keywords.append(keyword)
    return keywords[:12]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _summarize(text: str, limit: int = 140) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
