"""Wrapper around Mem0 OSS for user-scoped long-term memory."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MEM0_TELEMETRY", "False")

from mem0 import Memory
from pydantic import BaseModel, Field

from lacquertutor.config import Settings

logging.getLogger("mem0.utils.spacy_models").setLevel(logging.ERROR)
logging.getLogger("mem0.memory.telemetry").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)
DEFAULT_MEM0_COLLECTION = "lacquertutor_memories"
LOW_VALUE_MEMORY_PATTERNS = (
    "has not yet specified",
    "has not specified",
    "not yet specified",
    "did not specify",
    "has not yet indicated",
    "has not indicated",
    "is asking about",
    "current conversation indicates",
    "未说明",
    "未指定",
    "不清楚",
    "尚未确认",
    "缺少",
)


class Mem0MemoryRecord(BaseModel):
    memory_id: str = ""
    memory: str = ""
    score: float = 0.0
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Mem0MemoryService:
    """Stable internal interface over Mem0."""

    def __init__(self, memory: Memory, *, top_k: int = 5) -> None:
        self.memory = memory
        self.top_k = top_k

    @classmethod
    def from_settings(cls, settings: Settings) -> "Mem0MemoryService":
        data_dir = Path(settings.mem0_data_dir)
        if not data_dir.is_absolute():
            data_dir = Path(__file__).resolve().parents[3] / data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        qdrant_path = (data_dir / "qdrant").resolve()
        qdrant_path.mkdir(parents=True, exist_ok=True)
        history_db_path = (data_dir / "history.db").resolve()

        embedding_dims = _embedding_dims_for_model(settings.embedding_model)
        collection_name = _collection_name_for_settings(settings, embedding_dims)
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": collection_name,
                    "path": str(qdrant_path),
                    "on_disk": True,
                    "embedding_model_dims": embedding_dims,
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "api_key": settings.llm_api_key,
                    "model": settings.llm_model,
                    "openai_base_url": settings.llm_base_url,
                    "temperature": settings.llm_temperature,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "api_key": settings.llm_api_key,
                    "model": settings.embedding_model,
                    "openai_base_url": settings.llm_base_url,
                    "embedding_dims": embedding_dims,
                },
            },
            "history_db_path": str(history_db_path),
            "custom_instructions": (
                "只保留对漆艺教学、用户学习偏好、安全偏好、常用材料与稳定流程真正有长期价值的信息。"
                "不要记住用户尚未提供、待确认、缺失、不确定的信息。"
                "不要把一次性问题陈述、当前追问、临时阻塞条件当作长期记忆。"
            ),
        }
        memory = Memory.from_config(config)
        return cls(memory, top_k=settings.mem0_top_k)

    async def remember_turns(
        self,
        *,
        user_id: str,
        run_id: str,
        messages: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        if not user_id or not messages:
            return None
        payload_metadata = _build_memory_metadata(
            run_id=run_id,
            messages=messages,
            metadata=metadata or {},
        )
        try:
            return await asyncio.to_thread(
                self.memory.add,
                messages,
                user_id=user_id,
                run_id=run_id,
                metadata=payload_metadata,
            )
        except Exception as exc:
            logger.warning("mem0_remember_failed: %s", exc)
            return None

    async def search(
        self,
        *,
        query: str,
        user_id: str,
        limit: int | None = None,
    ) -> list[Mem0MemoryRecord]:
        if not user_id or not query.strip():
            return []

        try:
            result = await asyncio.to_thread(
                self.memory.search,
                query,
                top_k=limit or self.top_k,
                filters={"user_id": user_id},
            )
        except Exception:
            return []
        return _records_from_result(result, sort_by="score")

    async def get_all(self, *, user_id: str, limit: int | None = None) -> list[Mem0MemoryRecord]:
        if not user_id:
            return []
        try:
            result = await asyncio.to_thread(
                self.memory.get_all,
                top_k=limit or self.top_k,
                filters={"user_id": user_id},
            )
        except Exception:
            return []
        return _records_from_result(result, sort_by="created_at")

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        for attr_name in ("vector_store", "_telemetry_vector_store"):
            store = getattr(self.memory, attr_name, None)
            client = getattr(store, "client", None)
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
        try:
            self.memory.close()
        except Exception:
            pass


def _embedding_dims_for_model(model_name: str) -> int:
    normalized = str(model_name or "").strip().lower()
    if normalized == "text-embedding-v3":
        return 1024
    return 1536


def _collection_name_for_settings(settings: Settings, embedding_dims: int) -> str:
    base_name = str(settings.mem0_collection or "").strip() or DEFAULT_MEM0_COLLECTION
    if base_name == DEFAULT_MEM0_COLLECTION:
        return f"{base_name}_{embedding_dims}d"
    return base_name


def _build_memory_metadata(
    *,
    run_id: str,
    messages: list[dict[str, str]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(metadata)
    payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    payload.setdefault("run_id", run_id)
    digest_source = "\n".join(
        f"{item.get('role', '')}:{item.get('content', '')}"
        for item in messages
    )
    payload.setdefault(
        "message_digest",
        hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
    )
    return payload


def _memory_sort_key(record: Mem0MemoryRecord, *, sort_by: str) -> tuple[Any, ...]:
    if sort_by == "created_at":
        return (record.created_at or "", record.score)
    return (record.score, record.created_at or "")


def _normalize_memory_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _is_useful_memory_text(text: str) -> bool:
    normalized = _normalize_memory_text(text)
    if len(normalized) < 12:
        return False
    return not any(pattern in normalized for pattern in LOW_VALUE_MEMORY_PATTERNS)


def _records_from_result(result: Any, *, sort_by: str) -> list[Mem0MemoryRecord]:
    raw_items = result.get("results", result) if isinstance(result, dict) else result
    deduped: dict[str, Mem0MemoryRecord] = {}
    ordered_fallback: list[Mem0MemoryRecord] = []

    for item in raw_items or []:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") or {}
        record = Mem0MemoryRecord(
            memory_id=str(item.get("id", item.get("memory_id", ""))),
            memory=str(item.get("memory", item.get("text", ""))).strip(),
            score=float(item.get("score", 0.0) or 0.0),
            created_at=str(metadata.get("created_at", "")),
            metadata=metadata,
        )
        if not record.memory:
            continue
        if not _is_useful_memory_text(record.memory):
            continue

        key = _normalize_memory_text(record.memory) or record.memory_id
        existing = deduped.get(key)
        if existing is None or _memory_sort_key(record, sort_by=sort_by) > _memory_sort_key(existing, sort_by=sort_by):
            deduped[key] = record
        ordered_fallback.append(record)

    records = list(deduped.values()) if deduped else ordered_fallback
    records.sort(key=lambda item: _memory_sort_key(item, sort_by=sort_by), reverse=True)
    return records
