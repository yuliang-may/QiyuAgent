from __future__ import annotations

import json
import re
import shutil
import zipfile
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = REPO_ROOT / "kb"
OUTPUT_DIR = KB_ROOT / "image_mirror"
MANIFEST_PATH = KB_ROOT / "image_mirror_manifest.json"

DIFY_UPLOAD_ROOT = Path(r"D:\dify\docker\volumes\app\storage\upload_files\fdc4d43d-c6c1-47b6-819a-8f9e82a27176")

URL_PATTERN = re.compile(
    r"!\[[^\]]*\]\((?P<target>http://172\.22\.32\.1:18080/[^)\s]+|images/[^)\s]+)\)",
    re.IGNORECASE,
)
NON_WORD_PATTERN = re.compile(r"[\s\W_]+", re.UNICODE)

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}

SOURCE_SETS = [
    {
        "name": "zhitai",
        "markdown": DIFY_UPLOAD_ROOT / "30d03207-f1b8-4d04-baaf-4e6851bd3b30.md",
        "category": "zhitai",
        "docx": [
            DIFY_UPLOAD_ROOT / "4eda1794-71cf-41b3-a456-d7dd909d09d1.docx",
            DIFY_UPLOAD_ROOT / "890861f5-b1be-4104-817b-da458af69015.docx",
        ],
    },
    {
        "name": "xiushi",
        "markdown": DIFY_UPLOAD_ROOT / "ca08c2fe-267b-44bc-8fdf-74178c01f45e.md",
        "category": "xiushi",
        "docx": [DIFY_UPLOAD_ROOT / "f7d8472b-511a-4b4d-851a-b68d12727701.docx"],
    },
    {
        "name": "chujian",
        "markdown": DIFY_UPLOAD_ROOT / "32e16981-faea-46e7-8a48-f47d451eb52a.md",
        "category": "chujian",
        "docx": [
            DIFY_UPLOAD_ROOT / "f02088b6-7704-4ede-afc4-b4a9ad757774.docx",
            DIFY_UPLOAD_ROOT / "3d6ebe84-61c3-4bfe-b223-402a35f8a4da.docx",
            DIFY_UPLOAD_ROOT / "981ce8d6-3faf-4170-a223-d4c5c0a45ef5.docx",
        ],
    },
    {
        "name": "qicailiao",
        "markdown": DIFY_UPLOAD_ROOT / "14870544-403e-4042-a428-4f5aeb33a3b8.md",
        "category": "qicailiao",
        "docx": [
            DIFY_UPLOAD_ROOT / "21335b9f-cf0a-4f15-a4ac-9b88275b61e2.docx",
            DIFY_UPLOAD_ROOT / "f7d8472b-511a-4b4d-851a-b68d12727701.docx",
        ],
    },
    {
        "name": "zhiqi",
        "markdown": DIFY_UPLOAD_ROOT / "6c740ec1-cd30-4805-a777-82a1456f96f0.md",
        "category": "zhiqi",
        "docx": [DIFY_UPLOAD_ROOT / "21335b9f-cf0a-4f15-a4ac-9b88275b61e2.docx"],
    },
    {
        "name": "xiuqi",
        "markdown": DIFY_UPLOAD_ROOT / "6aab3f92-ec02-4553-b8e8-6e5cd27f53cb.md",
        "category": "xiuqi",
        "docx": [DIFY_UPLOAD_ROOT / "f7d8472b-511a-4b4d-851a-b68d12727701.docx"],
    },
    {
        "name": "qingtongqi",
        "markdown": DIFY_UPLOAD_ROOT / "da597188-0933-48f6-a949-e394ea6d9dba.md",
        "category": "qingtongqi",
        "docx": [
            DIFY_UPLOAD_ROOT / "f02088b6-7704-4ede-afc4-b4a9ad757774.docx",
            DIFY_UPLOAD_ROOT / "3d6ebe84-61c3-4bfe-b223-402a35f8a4da.docx",
            DIFY_UPLOAD_ROOT / "981ce8d6-3faf-4170-a223-d4c5c0a45ef5.docx",
        ],
    },
]


def _canonicalize_url(target: str, category: str) -> str:
    if target.startswith("http://172.22.32.1:18080/"):
        return target
    if target.startswith("images/"):
        return f"http://172.22.32.1:18080/{category}/auto/{target}"
    raise ValueError(f"unsupported image target: {target}")


def _normalize_text(text: str) -> str:
    return NON_WORD_PATTERN.sub("", text or "").lower()


def _caption_score(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return 1.0
    return SequenceMatcher(None, left_norm[:160], right_norm[:160]).ratio()


def _extract_markdown_blocks(path: Path, *, category: str) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = list(URL_PATTERN.finditer(text))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = match.end()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        tail = text[end:next_start]
        lines = [line.strip() for line in tail.splitlines() if line.strip()]
        caption = " ".join(lines[:3]).strip()
        blocks.append((_canonicalize_url(match.group("target"), category), caption))
    return blocks


def _build_anchor_pairs(
    markdown_blocks: list[tuple[str, str]],
    media_blocks: list[tuple[str, bytes, str]],
) -> list[tuple[int, int]]:
    anchors: list[tuple[int, int, float]] = []
    used_doc_indices: set[int] = set()
    for md_index, (_url, caption) in enumerate(markdown_blocks):
        if len(_normalize_text(caption)) < 4:
            continue
        best_doc_index = -1
        best_score = 0.0
        for doc_index, (_suffix, _payload, doc_caption) in enumerate(media_blocks):
            if doc_index in used_doc_indices:
                continue
            score = _caption_score(caption, doc_caption)
            if score > best_score:
                best_doc_index = doc_index
                best_score = score
        if best_doc_index >= 0 and best_score >= 0.85:
            anchors.append((md_index, best_doc_index, best_score))
            used_doc_indices.add(best_doc_index)

    anchors.sort(key=lambda item: (item[0], item[1]))
    monotonic: list[tuple[int, int]] = []
    last_doc_index = -1
    for md_index, doc_index, _score in anchors:
        if doc_index <= last_doc_index:
            continue
        monotonic.append((md_index, doc_index))
        last_doc_index = doc_index
    return monotonic


def _build_exact_matches(
    markdown_blocks: list[tuple[str, str]],
    media_blocks: list[tuple[str, bytes, str]],
) -> dict[int, int]:
    matches: dict[int, int] = {}
    for md_index, (_url, caption) in enumerate(markdown_blocks):
        if len(_normalize_text(caption)) < 4:
            continue
        best_doc_index = -1
        best_score = 0.0
        for doc_index, (_suffix, _payload, doc_caption) in enumerate(media_blocks):
            score = _caption_score(caption, doc_caption)
            if score > best_score:
                best_doc_index = doc_index
                best_score = score
        if best_doc_index >= 0 and best_score == 1.0:
            matches[md_index] = best_doc_index
    return matches


def _map_block_indices(
    markdown_blocks: list[tuple[str, str]],
    media_blocks: list[tuple[str, bytes, str]],
) -> dict[int, int]:
    mapping = _build_exact_matches(markdown_blocks, media_blocks)
    anchors = _build_anchor_pairs(markdown_blocks, media_blocks)
    if not anchors:
        return mapping

    first_md, first_doc = anchors[0]
    for offset in range(0, min(first_md, first_doc) + 1):
        mapping[first_md - offset] = first_doc - offset

    for (left_md, left_doc), (right_md, right_doc) in zip(anchors, anchors[1:], strict=False):
        mapping[left_md] = left_doc
        md_cursor = left_md + 1
        doc_cursor = left_doc + 1
        while md_cursor < right_md and doc_cursor < right_doc:
            mapping[md_cursor] = doc_cursor
            md_cursor += 1
            doc_cursor += 1

    last_md, last_doc = anchors[-1]
    mapping[last_md] = last_doc
    md_cursor = last_md + 1
    doc_cursor = last_doc + 1
    while md_cursor < len(markdown_blocks) and doc_cursor < len(media_blocks):
        mapping[md_cursor] = doc_cursor
        md_cursor += 1
        doc_cursor += 1
    return mapping


def _extract_docx_image_blocks(path: Path) -> list[tuple[str, bytes, str]]:
    with zipfile.ZipFile(path) as archive:
        rels_root = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
        rels = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels_root.findall("pr:Relationship", NS)
            if rel.attrib.get("Type", "").endswith("/image")
        }

        document_root = ET.fromstring(archive.read("word/document.xml"))
        body = document_root.find("w:body", NS)
        if body is None:
            return []

        flow: list[dict[str, list[str] | str]] = []
        for child in list(body):
            texts = [node.text for node in child.findall(".//w:t", NS) if node.text]
            paragraph_text = "".join(texts).strip()
            embeds = [
                node.attrib[f"{{{NS['r']}}}embed"]
                for node in child.findall(".//a:blip", NS)
                if f"{{{NS['r']}}}embed" in node.attrib
            ]
            flow.append({"text": paragraph_text, "embeds": embeds})

        blocks: list[tuple[str, bytes, str]] = []
        for index, item in enumerate(flow):
            embeds = item["embeds"]
            if not embeds:
                continue
            for embed in embeds:
                target = rels.get(embed, "")
                if not target:
                    continue
                media_path = target if target.startswith("word/") else f"word/{target}"
                suffix = Path(media_path).suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                    continue

                caption_parts: list[str] = []
                current_text = str(item["text"] or "").strip()
                if current_text:
                    caption_parts.append(current_text)

                cursor = index + 1
                while cursor < len(flow) and len(caption_parts) < 3:
                    next_item = flow[cursor]
                    if next_item["embeds"]:
                        break
                    next_text = str(next_item["text"] or "").strip()
                    if next_text:
                        caption_parts.append(next_text)
                    cursor += 1

                blocks.append(
                    (
                        suffix,
                        archive.read(media_path),
                        " ".join(caption_parts).strip(),
                    )
                )
        return blocks


def _url_digest(url: str) -> str:
    filename = url.rsplit("/", 1)[-1]
    stem = Path(filename).stem
    if not re.fullmatch(r"[0-9a-f]{64}", stem):
        raise ValueError(f"unexpected image url digest format: {url}")
    return stem


def build_manifest() -> dict[str, str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}

    for source in SOURCE_SETS:
        markdown_blocks = _extract_markdown_blocks(source["markdown"], category=source["category"])
        media_blocks: list[tuple[str, bytes, str]] = []
        for docx in source["docx"]:
            media_blocks.extend(_extract_docx_image_blocks(docx))

        print(
            f"[{source['name']}] urls={len(markdown_blocks)} media={len(media_blocks)}"
        )

        mapped_indices = _map_block_indices(markdown_blocks, media_blocks)
        for md_index, doc_index in mapped_indices.items():
            url, _caption = markdown_blocks[md_index]
            suffix, payload, _docx_caption = media_blocks[doc_index]
            digest = _url_digest(url)
            target = OUTPUT_DIR / f"{digest}{suffix}"
            target.write_bytes(payload)
            manifest[url] = f"/kb-images/{target.name}"

        print(
            f"[{source['name']}] anchors={len(_build_anchor_pairs(markdown_blocks, media_blocks))} "
            f"mapped={len(mapped_indices)}"
        )

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def clean_output() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    if MANIFEST_PATH.exists():
        MANIFEST_PATH.unlink()


if __name__ == "__main__":
    clean_output()
    manifest = build_manifest()
    print(f"wrote {len(manifest)} image mappings to {MANIFEST_PATH}")
