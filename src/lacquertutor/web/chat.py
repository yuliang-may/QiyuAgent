"""Generic RAG+LLM chat service for the product shell."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from lacquertutor.agent.memory import PROFILE_SLOT_CANDIDATES, SessionMemoryEngine
from lacquertutor.agent.slot_normalizer import extract_slot_values_from_text
from lacquertutor.config import Settings
from lacquertutor.web.prompts import (
    chat_assistant_system_prompt,
    chat_assistant_user_prompt,
)

if TYPE_CHECKING:
    from lacquertutor.agent.mem0_service import Mem0MemoryService
    from lacquertutor.agent.state import ConversationState
    from lacquertutor.web.teaching import ModuleReference, TeachingAssistantService

class AssistantChatService:
    """LLM-backed generic chat for the authenticated default workspace."""

    def __init__(
        self,
        *,
        teaching_service: "TeachingAssistantService",
        llm_client: AsyncOpenAI | None = None,
        llm_model: str = "",
        temperature: float = 0.0,
        memory_engine: SessionMemoryEngine | None = None,
        mem0_service: "Mem0MemoryService | None" = None,
    ) -> None:
        self.teaching_service = teaching_service
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.temperature = temperature
        self.memory_engine = memory_engine
        self.mem0_service = mem0_service

    @classmethod
    def from_services(
        cls,
        *,
        settings: Settings,
        teaching_service: "TeachingAssistantService",
        memory_engine: SessionMemoryEngine | None = None,
        mem0_service: "Mem0MemoryService | None" = None,
    ) -> "AssistantChatService":
        llm_client = getattr(teaching_service, "llm_client", None)
        llm_model = getattr(teaching_service, "llm_model", "")
        temperature = getattr(teaching_service, "temperature", 0.0)
        if llm_client is None and settings.llm_api_key:
            llm_client = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
            )
            llm_model = settings.llm_model
            temperature = settings.llm_temperature

        return cls(
            teaching_service=teaching_service,
            llm_client=llm_client,
            llm_model=llm_model,
            temperature=temperature,
            memory_engine=memory_engine,
            mem0_service=mem0_service,
        )

    async def reply(self, state: "ConversationState", message: str) -> dict[str, Any]:
        state.scene_key = "chat"
        state.stage = "conversation"
        state.task_type = ""
        state.failure_mode = None
        state.pending_slot_name = None
        state.pending_question = ""
        state.pending_question_reason = ""
        self._apply_profile_slots_from_message(state, message)

        if not state.original_query.strip():
            state.original_query = message.strip()

        if self.memory_engine is not None and state.user_id:
            await self.memory_engine.hydrate_state(state)

        if self.mem0_service is not None and state.user_id:
            state.agent_memories = [
                item.model_dump()
                for item in await self.mem0_service.search(
                    query=message,
                    user_id=state.user_id,
                )
            ]

        references = await self.teaching_service.retrieve_references(message, limit=4)
        reference_payload = [item.model_dump() for item in references]
        state.chat_references = reference_payload
        state.chat_suggested_scene_keys = []

        reply_text = await self._generate_reply(
            state=state,
            message=message,
            references=references,
        )
        state.add_assistant_turn(reply_text)
        return {
            "type": "message",
            "text": reply_text,
            "suggested_scene_keys": [],
            "references": reference_payload,
        }

    def _apply_profile_slots_from_message(self, state: "ConversationState", message: str) -> None:
        extracted = extract_slot_values_from_text(
            message,
            slot_names=PROFILE_SLOT_CANDIDATES,
        )
        for slot_name, value in extracted.items():
            state.slot_state.fill(
                name=slot_name,
                value=str(value),
                source="user",
                confirmed=True,
                turn=state.questions_asked,
            )

    async def _generate_reply(
        self,
        *,
        state: "ConversationState",
        message: str,
        references: list["ModuleReference"],
    ) -> str:
        if self.llm_client is None or not self.llm_model:
            return self._fallback_reply(message=message, references=references)

        history_lines = [
            f"{'用户' if turn.role == 'user' else '助手'}: {turn.content}"
            for turn in state.dialogue_history[-8:]
            if turn.content.strip()
        ]
        memory_context = SessionMemoryEngine.format_for_prompt(state)
        user_prompt = chat_assistant_user_prompt(
            message=message,
            history_lines=history_lines,
            memory_context=memory_context,
            references=references,
        )
        try:
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                temperature=max(self.temperature, 0.2),
                messages=[
                    {"role": "system", "content": chat_assistant_system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            return text or self._fallback_reply(
                message=message,
                references=references,
            )
        except Exception:
            return self._fallback_reply(
                message=message,
                references=references,
            )

    def _fallback_reply(
        self,
        *,
        message: str,
        references: list["ModuleReference"],
    ) -> str:
        if references:
            lead = references[0].excerpt.strip()
            return (
                f"我先按通用漆艺聊天助手来回答。结合当前知识片段，最值得先抓住的点是：{lead}。"
                "如果你接下来要动手做，建议把对象、漆体系和环境条件再说具体一点。"
            ).strip()

        return (
            f"我已经收到你的问题：“{message.strip() or '当前问题'}”。"
            " 现在还缺少足够具体的工艺上下文，所以我先不编造结论。"
            " 如果你愿意，把当前对象、材料、环境或异常现象说得更具体一点，我就能给出更稳的建议。"
        ).strip()
