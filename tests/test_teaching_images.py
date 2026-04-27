from __future__ import annotations

import json

import pytest

from lacquertutor.web.teaching import (
    TeachingAssistantService,
    _clean_markdown,
    _extract_image_urls,
    ModuleReference,
)


def test_extract_image_urls_and_strip_links():
    raw = (
        "![](http://example.com/a.jpg)\n"
        "[封面](http://example.com/b.png)\n"
        "图表3 规尺\n"
    )

    assert _extract_image_urls(raw) == [
        "http://example.com/a.jpg",
        "http://example.com/b.png",
    ]
    assert _clean_markdown(raw) == "图表3 规尺"


def test_search_returns_reference_image_urls(tmp_path):
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()

    payload = [
        {
            "segment_id": "seg-1",
            "dataset_name": "tongyong-kb-cap",
            "position": 1,
            "content": "规 尺\n![](http://example.com/ruler.jpg)\n图表3 规尺\n规尺主要用来标记和测量。",
        }
    ]
    for filename in ("fuzi_kb_segments.json", "tongyong_kb_segments.json"):
        (kb_dir / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    service = TeachingAssistantService.from_repo(repo_root=tmp_path)

    refs = service.search("图表3 规尺", limit=1)

    assert len(refs) == 1
    assert refs[0].title == "规 尺"
    assert refs[0].image_urls == ["http://example.com/ruler.jpg"]
    assert "图表3 规尺" in refs[0].excerpt


def test_search_rewrites_image_urls_from_manifest(tmp_path):
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()

    payload = [
        {
            "segment_id": "seg-1",
            "dataset_name": "tongyong-kb-cap",
            "position": 1,
            "content": "规 尺\n![](http://172.22.32.1:18080/zhitai/auto/images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg)\n图表3 规尺",
        }
    ]
    for filename in ("fuzi_kb_segments.json", "tongyong_kb_segments.json"):
        (kb_dir / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    (kb_dir / "image_mirror_manifest.json").write_text(
        json.dumps(
            {
                "http://172.22.32.1:18080/zhitai/auto/images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg": "/kb-images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpeg"
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = TeachingAssistantService.from_repo(repo_root=tmp_path)

    refs = service.search("图表3 规尺", limit=1)

    assert len(refs) == 1
    assert refs[0].image_urls == [
        "/kb-images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpeg"
    ]


def test_search_splits_broad_chinese_query_into_useful_keywords(tmp_path):
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()

    payload = [
        {
            "segment_id": "seg-1",
            "dataset_name": "tongyong-kb-cap",
            "position": 1,
            "content": "木胎调整封固\n木胎处理前要先确认表面平整、干燥，再做封固。",
        }
    ]
    for filename in ("fuzi_kb_segments.json", "tongyong_kb_segments.json"):
        (kb_dir / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    service = TeachingAssistantService.from_repo(repo_root=tmp_path)

    refs = service.search("木胎如何处理", limit=1)

    assert len(refs) == 1
    assert refs[0].title == "木胎调整封固"
    assert "木胎处理前" in refs[0].excerpt


@pytest.mark.asyncio
async def test_retrieve_references_prefers_rag_results_when_available(tmp_path):
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()

    payload = [
        {
            "segment_id": "seg-1",
            "dataset_name": "tongyong-kb-cap",
            "position": 1,
            "content": "木胎调整封固\n木胎处理前要先确认表面平整、干燥，再做封固。",
        }
    ]
    for filename in ("fuzi_kb_segments.json", "tongyong_kb_segments.json"):
        (kb_dir / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    service = TeachingAssistantService.from_repo(repo_root=tmp_path)

    class FakeRAG:
        enabled = True

        async def retrieve(self, query: str, limit: int = 4):
            return [
                {
                    "segment_id": "rag-seg",
                    "source_label": "rag-store",
                    "title": "RAG 命中",
                    "excerpt": f"针对 {query} 的标准 RAG 结果",
                    "score": 0.98,
                    "image_urls": ["/kb-images/rag-demo.jpeg"],
                }
            ]

    service.rag = FakeRAG()

    refs = await service.retrieve_references("木胎如何处理", limit=1)

    assert len(refs) == 1
    assert isinstance(refs[0], ModuleReference)
    assert refs[0].title == "RAG 命中"
    assert "标准 RAG 结果" in refs[0].excerpt
    assert refs[0].image_urls == ["/kb-images/rag-demo.jpeg"]
