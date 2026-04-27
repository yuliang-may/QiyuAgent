"""Teaching-oriented module outputs backed by the local lacquer knowledge base."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from lacquertutor.config import Settings
from lacquertutor.web.rag import RAGDocument, StandardRAGRetriever
from lacquertutor.web.prompts import (
    feasibility_system_prompt,
    feasibility_user_prompt,
    teaching_refiner_system_prompt,
    teaching_refiner_user_prompt,
)

KB_FILENAMES: tuple[str, ...] = (
    "fuzi_kb_segments.json",
    "tongyong_kb_segments.json",
)

MODULE_TITLES: dict[str, str] = {
    "knowledge": "漆艺知识问答",
    "learning": "个性化学习路径",
    "safety": "安全护栏检查",
}

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
    "学习",
    "路径",
    "推荐",
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


def _extract_image_urls(text: str) -> list[str]:
    pattern = re.compile(
        r"(?:!\[[^\]]*\]|\[[^\]]*\])\((https?://[^)\s]+?\.(?:png|jpe?g|webp|gif)(?:\?[^)\s]*)?)\)",
        re.IGNORECASE,
    )
    seen: set[str] = set()
    urls: list[str] = []
    for match in pattern.finditer(text or ""):
        url = match.group(1).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _clean_markdown(text: str) -> str:
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text or "")
    cleaned = re.sub(r"\[[^\]]*\]\((https?://[^)\s]+)\)", " ", cleaned)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = cleaned.replace("\\n", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    return cleaned.strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；.!?])\s*", text)
    return [part.strip() for part in parts if part.strip()]


def _summarize_excerpt(text: str, limit: int = 120) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _extract_keywords(query: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_+-]{2,}|[\u4e00-\u9fff]{2,}", query.lower())
    keywords: list[str] = []
    for token in tokens:
        for keyword in _normalize_keyword_fragment(token):
            if keyword not in keywords:
                keywords.append(keyword)
    return keywords[:10]


@dataclass(frozen=True)
class KBSegment:
    segment_id: str
    dataset_name: str
    position: int
    title: str
    clean_content: str
    image_urls: list[str]


class ModuleReference(BaseModel):
    segment_id: str
    source_label: str
    title: str
    excerpt: str
    score: float
    image_urls: list[str] = Field(default_factory=list)


class LearningPhase(BaseModel):
    phase: str
    focus: str
    practice: str
    completion_signal: str


class ModuleArtifact(BaseModel):
    artifact_type: str
    title: str
    summary: str
    verdict: str = ""
    verdict_label: str = ""
    verdict_reason: str = ""
    highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    required_conditions: list[str] = Field(default_factory=list)
    blocking_factors: list[str] = Field(default_factory=list)
    phases: list[LearningPhase] = Field(default_factory=list)
    references: list[ModuleReference] = Field(default_factory=list)
    markdown: str = ""


class TeachingAssistantService:
    """Serve teaching-first module outputs from local KB segments."""

    def __init__(
        self,
        segments: list[KBSegment],
        *,
        settings: Settings | None = None,
        llm_client: AsyncOpenAI | None = None,
        llm_model: str = "",
        temperature: float = 0.0,
        image_manifest: dict[str, str] | None = None,
    ) -> None:
        self.segments = segments
        self.settings = settings or Settings()
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.temperature = temperature
        self.image_manifest = image_manifest or {}
        self.rag = StandardRAGRetriever(
            documents=[
                RAGDocument(
                    segment_id=segment.segment_id,
                    source_label=segment.dataset_name,
                    title=segment.title,
                    content=segment.clean_content,
                    image_urls=[
                        self.image_manifest.get(url, url)
                        for url in segment.image_urls[:4]
                    ],
                )
                for segment in segments
            ],
            llm_client=llm_client,
            settings=self.settings,
        )

    @classmethod
    def from_repo(
        cls,
        settings: Settings | None = None,
        repo_root: Path | None = None,
    ) -> "TeachingAssistantService":
        root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
        kb_root = root / "kb"
        image_manifest_path = kb_root / "image_mirror_manifest.json"
        segments: list[KBSegment] = []
        image_manifest: dict[str, str] = {}

        if image_manifest_path.exists():
            image_manifest = json.loads(image_manifest_path.read_text(encoding="utf-8"))

        for filename in KB_FILENAMES:
            path = kb_root / filename
            if not path.exists():
                continue
            raw_items = json.loads(path.read_text(encoding="utf-8"))
            for raw in raw_items:
                raw_content = raw.get("content", "")
                image_urls = _extract_image_urls(raw_content)
                clean_content = _clean_markdown(raw_content)
                if not clean_content:
                    continue
                first_line = clean_content.splitlines()[0].strip()
                title = _summarize_excerpt(first_line, limit=36) or filename
                segments.append(
                    KBSegment(
                        segment_id=str(raw.get("segment_id", "")),
                        dataset_name=str(raw.get("dataset_name", filename)),
                        position=int(raw.get("position", 0) or 0),
                        title=title,
                        clean_content=clean_content,
                        image_urls=image_urls,
                    )
                )

        llm_client = None
        llm_model = ""
        temperature = 0.0
        if settings and settings.llm_api_key:
            llm_client = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
            )
            llm_model = settings.llm_model
            temperature = settings.llm_temperature

        return cls(
            segments,
            settings=settings,
            llm_client=llm_client,
            llm_model=llm_model,
            temperature=temperature,
            image_manifest=image_manifest,
        )

    async def prepare_rag(self, *, force: bool = False) -> None:
        if force or self.settings.rag_warm_on_start:
            await self.rag.prepare()

    async def retrieve_references(self, query: str, *, limit: int = 4) -> list[ModuleReference]:
        if self.rag.enabled:
            try:
                results = await self.rag.retrieve(query, limit=limit)
                if results:
                    return [
                        ModuleReference(
                            segment_id=item["segment_id"],
                            source_label=item["source_label"],
                            title=item["title"],
                            excerpt=item["excerpt"],
                            score=item["score"],
                            image_urls=item["image_urls"],
                        )
                        for item in results
                    ]
            except Exception:
                pass
        return self.search(query, limit=limit)

    async def create_artifact(self, scene_key: str, query: str) -> ModuleArtifact:
        if scene_key == "safety":
            return await self.evaluate_feasibility(query)
        if scene_key == "learning":
            return await self.build_learning_path(query)
        return await self.answer_knowledge_query(query)

    async def answer_knowledge_query(self, query: str) -> ModuleArtifact:
        references = await self.retrieve_references(query, limit=4)
        if not references:
            artifact = ModuleArtifact(
                artifact_type="knowledge_brief",
                title="漆艺知识问答",
                summary="当前知识库里没有检索到足够相关的片段，建议把工艺名称、材料或异常现象说得更具体一些。",
                follow_up_questions=[
                    "你想查的是哪一道具体技法或材料？",
                    "当前对象是什么基底，例如木盒、托盘、胎体还是旧漆面？",
                    "你更关心原理、操作步骤，还是常见错误？",
                ],
            )
            artifact.markdown = self._artifact_markdown(artifact)
            return artifact

        artifact = ModuleArtifact(
            artifact_type="knowledge_brief",
            title="漆艺知识问答",
            summary=self._build_knowledge_summary(query, references),
            highlights=self._build_highlights(query, references, limit=3),
            recommendations=[
                "先把检索到的共识要点记成自己的工艺检查清单，再进入实际操作。",
                "如果准备马上动手，下一步直接切到“可执行工艺计划”模块补齐关键条件。",
                "如果已经出现表面异常，改用“工艺故障诊断”模块，不要只靠概念性解释继续操作。",
            ],
            safety_notes=self._build_safety_notes(query, references),
            follow_up_questions=[
                "你现在处在准备、涂装、固化还是打磨阶段？",
                "你打算用的大类漆体系是什么，例如生漆、水性漆或油性体系？",
                "你是想继续查原理，还是想让系统把它转成可执行步骤？",
            ],
            references=references,
        )

        artifact = await self._refine_with_llm(
            scene_key="knowledge",
            query=query,
            artifact=artifact,
        )
        artifact = self._normalize_artifact(artifact)
        artifact.markdown = self._artifact_markdown(artifact)
        return artifact

    async def evaluate_feasibility(self, query: str) -> ModuleArtifact:
        references = await self.retrieve_references(query, limit=5)
        if not references:
            artifact = ModuleArtifact(
                artifact_type="feasibility_verdict",
                title="安全护栏检查",
                summary="当前没有足够知识依据支持直接放行，建议先把步骤、材料、环境和已知前序条件说得更具体一些。",
                verdict="conditional",
                verdict_label="有条件可行",
                verdict_reason="系统没有检索到足够具体的知识片段，因此不能基于真实知识直接判断为可行。",
                required_conditions=[
                    "当前涉及的漆体系或材料类型",
                    "当前所处工艺阶段",
                    "环境温湿度或固化条件",
                ],
                blocking_factors=[
                    "描述过于泛，无法对应到具体工艺条件",
                ],
                recommendations=[
                    "把当前步骤说得更具体，例如重涂、固化、打磨或旧涂层覆盖。",
                    "补充对象、漆体系、环境和是否有旧涂层这类关键信息。",
                ],
                safety_notes=[
                    "在条件不明时，不要直接继续不可逆步骤。",
                ],
                follow_up_questions=[
                    "你现在准备做的具体动作是什么？",
                    "当前对象是什么基底，是否已有旧涂层？",
                    "当前环境温湿度和漆体系是否已知？",
                ],
            )
            artifact.markdown = self._artifact_markdown(artifact)
            return artifact

        artifact = ModuleArtifact(
            artifact_type="feasibility_verdict",
            title="安全护栏检查",
            summary="系统正在基于当前检索到的知识片段判断这个方案能不能继续推进。",
            verdict="conditional",
            verdict_label="有条件可行",
            verdict_reason="在正式判断前，系统先按保守策略视为需要补条件验证。",
            highlights=self._build_highlights(query, references, limit=3),
            recommendations=[
                "先补齐会直接影响不可逆步骤的条件，再决定是否继续。",
                "如果条件仍不完整，优先做样板验证，不要直接上正式件。",
            ],
            safety_notes=self._build_safety_notes(query, references),
            follow_up_questions=[
                "你要执行的下一步到底是什么？",
                "当前对象是否已有旧涂层或前序步骤历史不明？",
                "环境、固化方式和 PPE 是否已经确认？",
            ],
            required_conditions=[
                "漆体系或材料类型",
                "当前步骤和对象状态",
                "环境与固化条件",
            ],
            blocking_factors=[],
            references=references,
        )
        artifact = await self._generate_feasibility_with_llm(query=query, artifact=artifact)
        artifact = self._normalize_artifact(artifact)
        artifact.markdown = self._artifact_markdown(artifact)
        return artifact

    async def build_learning_path(self, query: str) -> ModuleArtifact:
        references = await self.retrieve_references(query, limit=4)
        profile = self._infer_learning_profile(query)
        practice_focus = self._infer_practice_focus(query, references)
        artifact = ModuleArtifact(
            artifact_type="learning_path",
            title="个性化学习路径",
            summary=self._build_learning_summary(query, references, profile, practice_focus),
            highlights=self._build_highlights(query, references, limit=3),
            recommendations=[
                "每次学习只追一个核心变量，不要同时改太多参数。",
                "先学会判断“现在该补什么信息”，再追求一次性做对全部步骤。",
                "把学习路径和真实项目连接起来，完成每个阶段后再进入下一种更复杂技法。",
            ],
            safety_notes=[
                "任何涉及重涂、固化、打磨或材料切换的环节，都先确认漆体系、环境和 PPE。",
                "没有做过样板验证时，不要直接把新参数用到正式作品上。",
            ],
            follow_up_questions=[
                "你现在更偏向学材料原理、基础涂装，还是某一种具体技法？",
                "你已有的练习对象是什么，是否能接受先做样板？",
                "你希望系统下一步帮你生成学习清单，还是直接生成项目计划？",
            ],
            phases=[
            LearningPhase(
                phase="阶段 1 / 建立术语地图",
                focus=f"先把 {practice_focus} 的核心概念、常见材料和基本工序说清楚，避免一开始就记碎片知识。",
                practice="用自己的话复述 3 个关键术语，并整理一页工艺流程卡。",
                completion_signal="你能说清楚材料、工序顺序和每一步大概目的。",
            ),
            LearningPhase(
                phase="阶段 2 / 材料与安全入门",
                focus="围绕漆体系、基底、环境温湿度和个人防护建立最低安全边界。",
                practice="完成一张“开工前检查表”，至少包含漆种、基底、湿度、固化方式和 PPE。",
                completion_signal="你知道哪些条件没确认时不能直接进入不可逆步骤。",
            ),
            LearningPhase(
                phase="阶段 3 / 小样板练习",
                focus=f"不要直接在成品上试，先围绕 {practice_focus} 做小样验证参数和手感。",
                practice="做 1 到 2 组小样，对比不同厚薄、工具或等待时间的差异。",
                completion_signal="你能说出哪组参数更稳，以及常见失败征兆是什么。",
            ),
            LearningPhase(
                phase="阶段 4 / 小项目实作",
                focus="把前面的概念和样板经验迁移到一个小体量作品上，开始形成完整流程。",
                practice="选择一个低风险对象，如木片、木板或小木盒，按步骤完成一次完整流程。",
                completion_signal="你能独立记录步骤、检查点和出问题后的回退动作。",
            ),
            LearningPhase(
                phase="阶段 5 / 复盘与升级",
                focus=f"针对 {profile} 学习者，把经验沉淀成下次还能复用的个人 playbook。",
                practice="复盘本次项目：列出 3 个有效做法、2 个风险点、1 个下次要先确认的条件。",
                completion_signal="你已经能把一次学习经历转成可复用的操作习惯。",
            ),
            ],
            references=references,
        )
        artifact = await self._refine_with_llm(
            scene_key="learning",
            query=query,
            artifact=artifact,
        )
        artifact = self._normalize_artifact(artifact)
        artifact.markdown = self._artifact_markdown(artifact)
        return artifact

    def search(self, query: str, *, limit: int = 4) -> list[ModuleReference]:
        keywords = _extract_keywords(query)
        if not keywords:
            return []

        scored: list[tuple[float, KBSegment]] = []
        query_lower = query.lower()

        for segment in self.segments:
            text = segment.clean_content.lower()
            score = 0.0
            matched_keywords: set[str] = set()

            for keyword in keywords:
                matched = False
                if keyword in segment.title.lower():
                    score += 4.0
                    matched = True
                if keyword in text:
                    score += 2.0 + min(text.count(keyword), 3)
                    matched = True
                if matched:
                    matched_keywords.add(keyword)

            if query_lower[:24] and query_lower[:24] in text:
                score += 2.5

            if "安全" in query and ("安全" in text or "防护" in text):
                score += 1.0
            if "打磨" in query and "打磨" in text:
                score += 1.0
            if "固化" in query and ("固化" in text or "干燥" in text):
                score += 1.0

            score += len(matched_keywords) * 2.5

            if score <= 0:
                continue

            scored.append((score, segment))

        scored.sort(key=lambda item: (-item[0], item[1].position, item[1].segment_id))
        references: list[ModuleReference] = []
        seen: set[tuple[str, str]] = set()

        for score, segment in scored:
            excerpt = self._best_excerpt(segment.clean_content, keywords)
            dedupe_key = (segment.title, excerpt)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            references.append(
                ModuleReference(
                    segment_id=segment.segment_id,
                    source_label=segment.dataset_name,
                    title=segment.title,
                    excerpt=excerpt,
                    score=round(score, 2),
                    image_urls=[
                        self.image_manifest.get(url, url)
                        for url in segment.image_urls[:4]
                    ],
                )
            )
            if len(references) >= limit:
                break

        return references

    def _best_excerpt(self, text: str, keywords: list[str]) -> str:
        sentences = _split_sentences(text)
        for keyword in keywords:
            for sentence in sentences:
                if keyword in sentence.lower():
                    return _summarize_excerpt(sentence, limit=120)
        return _summarize_excerpt(sentences[0] if sentences else text, limit=120)

    def _build_highlights(
        self,
        query: str,
        references: list[ModuleReference],
        *,
        limit: int,
    ) -> list[str]:
        highlights: list[str] = []
        seen: set[str] = set()
        for reference in references:
            line = reference.excerpt.strip()
            if not line or line in seen:
                continue
            seen.add(line)
            highlights.append(line)
            if len(highlights) >= limit:
                break

        if not highlights:
            highlights.append(f"当前问题与“{query[:24]}”相关，但还需要更具体的工艺关键词。")

        return highlights

    def _build_knowledge_summary(
        self,
        query: str,
        references: list[ModuleReference],
    ) -> str:
        lead = references[0].excerpt if references else "未检索到相关片段。"
        return (
            f"系统已从 5222 段漆艺知识内容中检索到与“{query[:28]}”最相关的片段。"
            f" 当前优先结论是：{lead}"
        )

    def _build_learning_summary(
        self,
        query: str,
        references: list[ModuleReference],
        profile: str,
        practice_focus: str,
    ) -> str:
        support = references[0].excerpt if references else "建议先从术语、材料和安全边界开始。"
        return (
            f"这条学习路径按“{profile} 学习者”设计，目标是围绕 {practice_focus} 形成从概念、样板到小项目的递进练习。"
            f" 路径依据的首条知识支撑是：{support}"
        )

    def _build_safety_notes(
        self,
        query: str,
        references: list[ModuleReference],
    ) -> list[str]:
        notes = [
            "如果当前要进入重涂、固化、打磨或材料切换，先确认漆体系、环境和个人防护。",
        ]
        if "湿度" in query or any("湿" in reference.excerpt for reference in references):
            notes.append("涉及湿度窗口时，不要在参数不明的情况下直接继续下一层。")
        if "旧涂层" in query or "重涂" in query:
            notes.append("旧涂层来源不明时，先做兼容性样板，不要直接在正式件上覆盖。")
        return notes

    def _infer_learning_profile(self, query: str) -> str:
        lowered = query.lower()
        if any(keyword in lowered for keyword in ("零基础", "入门", "初学", "新手", "第一次")):
            return "入门"
        if any(keyword in lowered for keyword in ("进阶", "提高", "优化", "升级")):
            return "进阶"
        return "基础到进阶过渡"

    def _infer_practice_focus(
        self,
        query: str,
        references: list[ModuleReference],
    ) -> str:
        candidates = (
            "描金",
            "髹饰",
            "打磨",
            "固化",
            "底胎",
            "黑漆",
            "犀皮",
            "螺钿",
            "雕填",
            "罩漆",
            "生漆",
            "水性漆",
        )
        for candidate in candidates:
            if candidate in query:
                return candidate
        for reference in references:
            for candidate in candidates:
                if candidate in reference.excerpt:
                    return candidate
        return "基础漆艺工艺"

    def _artifact_markdown(self, artifact: ModuleArtifact) -> str:
        lines = [f"# {artifact.title}", "", artifact.summary, ""]

        if artifact.verdict_label:
            lines.append("## 可行性结论")
            lines.append(f"- 结论: {artifact.verdict_label}")
            if artifact.verdict_reason:
                lines.append(f"- 依据: {artifact.verdict_reason}")
            lines.append("")

        if artifact.highlights:
            lines.append("## 关键要点")
            lines.extend(f"- {item}" for item in artifact.highlights)
            lines.append("")

        if artifact.required_conditions:
            lines.append("## 必须先确认的条件")
            lines.extend(f"- {item}" for item in artifact.required_conditions)
            lines.append("")

        if artifact.blocking_factors:
            lines.append("## 当前阻断因素")
            lines.extend(f"- {item}" for item in artifact.blocking_factors)
            lines.append("")

        if artifact.phases:
            lines.append("## 学习阶段")
            for phase in artifact.phases:
                lines.append(f"### {phase.phase}")
                lines.append(f"- 重点: {phase.focus}")
                lines.append(f"- 练习: {phase.practice}")
                lines.append(f"- 达标信号: {phase.completion_signal}")
                lines.append("")

        if artifact.recommendations:
            lines.append("## 建议动作")
            lines.extend(f"- {item}" for item in artifact.recommendations)
            lines.append("")

        if artifact.safety_notes:
            lines.append("## 安全提醒")
            lines.extend(f"- {item}" for item in artifact.safety_notes)
            lines.append("")

        if artifact.follow_up_questions:
            lines.append("## 建议继续追问")
            lines.extend(f"- {item}" for item in artifact.follow_up_questions)
            lines.append("")

        if artifact.references:
            lines.append("## 参考片段")
            for reference in artifact.references:
                lines.append(
                    f"- **{reference.title}** ({reference.source_label}, score={reference.score})"
                )
                lines.append(f"  - {reference.excerpt}")
                for image_url in reference.image_urls:
                    lines.append(f"  - 配图: {image_url}")
            lines.append("")

        return "\n".join(lines).strip()

    async def _refine_with_llm(
        self,
        *,
        scene_key: str,
        query: str,
        artifact: ModuleArtifact,
    ) -> ModuleArtifact:
        if self.llm_client is None or not self.llm_model:
            return artifact

        system_prompt = teaching_refiner_system_prompt()
        user_prompt = teaching_refiner_user_prompt(
            scene_key=MODULE_TITLES.get(scene_key, scene_key),
            query=query,
            artifact=artifact,
        )

        try:
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            payload = self._extract_json_payload(content)
            refined = ModuleArtifact.model_validate(payload)
            if not refined.artifact_type:
                refined.artifact_type = artifact.artifact_type
            if not refined.title:
                refined.title = artifact.title
            if not refined.references:
                refined.references = artifact.references
            return refined
        except Exception:
            return artifact

    async def _generate_feasibility_with_llm(
        self,
        *,
        query: str,
        artifact: ModuleArtifact,
    ) -> ModuleArtifact:
        if self.llm_client is None or not self.llm_model:
            return artifact

        try:
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": feasibility_system_prompt()},
                    {
                        "role": "user",
                        "content": feasibility_user_prompt(
                            query=query,
                            references=artifact.references,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            payload = self._extract_json_payload(content)
            merged = artifact.model_dump()
            merged.update(payload)
            refined = ModuleArtifact.model_validate(merged)
            if not refined.artifact_type:
                refined.artifact_type = "feasibility_verdict"
            if not refined.title:
                refined.title = "安全护栏检查"
            if not refined.references:
                refined.references = artifact.references
            return refined
        except Exception:
            return artifact

    def _normalize_artifact(self, artifact: ModuleArtifact) -> ModuleArtifact:
        if artifact.verdict:
            verdict_map = {
                "feasible": "可行",
                "conditional": "有条件可行",
                "not_feasible": "暂不可行",
            }
            artifact.verdict_label = verdict_map.get(
                artifact.verdict,
                artifact.verdict_label or "待判断",
            )

        if artifact.artifact_type == "feasibility_verdict":
            if artifact.verdict == "not_feasible" and not artifact.blocking_factors:
                artifact.blocking_factors = ["当前仍存在阻断继续执行的关键不确定项。"]
            if artifact.verdict in {"conditional", "not_feasible"} and not artifact.required_conditions:
                artifact.required_conditions = [
                    "当前步骤涉及的漆体系或材料类型",
                    "对象状态与前序步骤",
                    "环境温湿度或固化条件",
                ]
        return artifact

    @staticmethod
    def _extract_json_payload(content: str) -> dict[str, Any]:
        raw = content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
        return json.loads(raw)
