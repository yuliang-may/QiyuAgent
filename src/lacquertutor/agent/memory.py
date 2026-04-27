"""Hermes-inspired persistent memory and cross-session recall."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any

from lacquertutor.models.memory import LearnedPlaybook, RecalledSession, RememberedPreference
from lacquertutor.models.slots import SLOT_SCHEMA

if TYPE_CHECKING:
    from lacquertutor.agent.state import ConversationState
    from lacquertutor.agent.mem0_service import Mem0MemoryService
    from lacquertutor.storage.session_store import SessionStore


PROFILE_SLOT_CANDIDATES: tuple[str, ...] = (
    "lacquer_system",
    "curing_method",
    "ppe_level",
    "application_tool",
    "target_finish",
    "dust_control_level",
    "ventilation_quality",
    "coat_thickness",
)

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")


def _slot_label(slot_name: str) -> str:
    slot_def = SLOT_SCHEMA.get(slot_name)
    return slot_def.label_zh if slot_def else slot_name


def _query_excerpt(text: str, limit: int = 96) -> str:
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if line:
            return line[:limit]
    return ""


def _tokenize(text: str) -> set[str]:
    tokens = {token.lower() for token in TOKEN_RE.findall(str(text or ""))}
    return {token for token in tokens if len(token) >= 2}


class SessionMemoryEngine:
    """Build profile memory, session recall, and procedural playbooks."""

    def __init__(
        self,
        session_store: SessionStore,
        *,
        mem0_service: Mem0MemoryService | None = None,
        session_window: int = 24,
        profile_limit: int = 4,
        recall_limit: int = 3,
        playbook_limit: int = 2,
    ) -> None:
        self.session_store = session_store
        self.mem0_service = mem0_service
        self.session_window = session_window
        self.profile_limit = profile_limit
        self.recall_limit = recall_limit
        self.playbook_limit = playbook_limit

    async def hydrate_state(self, state: ConversationState) -> None:
        """Attach memory-derived context to the current state."""
        past_sessions = await self._load_past_sessions(state.__class__, state.user_id)
        memory_sessions = self._filter_memory_source_sessions(past_sessions)

        state.remembered_preferences = self._build_profile(memory_sessions)
        state.recalled_sessions = self._recall_sessions(memory_sessions, state)
        state.learned_playbooks = self._build_playbooks(memory_sessions, state.recalled_sessions)
        if self.mem0_service is not None:
            state.agent_memories = [
                item.model_dump()
                for item in await self.mem0_service.search(
                    query=state.original_query,
                    user_id=state.user_id,
                )
            ]

    async def build_snapshot(self, *, user_id: str) -> dict[str, Any]:
        """Return homepage-friendly memory data for a specific user."""
        from lacquertutor.agent.state import ConversationState

        past_sessions = await self._load_past_sessions(ConversationState, user_id)
        memory_sessions = self._filter_memory_source_sessions(past_sessions)
        completed_sessions = sum(
            1 for _, past_state in past_sessions if past_state.final_contract or past_state.module_artifact
        )
        recent_topics = [
            _query_excerpt(past_state.original_query, limit=56)
            for _, past_state in past_sessions[:5]
            if past_state.original_query.strip()
        ]
        return {
            "remembered_preferences": [item.model_dump() for item in self._build_profile(memory_sessions)],
            "learned_playbooks": [item.model_dump() for item in self._build_playbooks(memory_sessions, [])],
            "completed_sessions": completed_sessions,
            "recent_topics": recent_topics,
            "agent_memories": [
                item.model_dump()
                for item in (
                    await self.mem0_service.get_all(
                        user_id=user_id,
                        limit=self.mem0_service.top_k,
                    )
                    if self.mem0_service is not None
                    else []
                )
            ],
        }

    @staticmethod
    def format_for_prompt(state: ConversationState) -> str:
        """Render memory context for prompt injection."""
        lines: list[str] = []

        if state.remembered_preferences:
            lines.append("工作室档案（仅供参考，不能视为本次已确认事实）:")
            for item in state.remembered_preferences:
                lines.append(
                    f"- 最近常见 {_slot_label(item.slot_name)} = {item.value} "
                    f"({item.source_sessions} 次会话, {item.confidence} 置信)"
                )

        if state.recalled_sessions:
            lines.append("相似历史会话:")
            for item in state.recalled_sessions:
                reason_text = "；".join(item.matched_reasons) or "语义相近"
                leading = f"；关键动作: {item.leading_step}" if item.leading_step else ""
                lines.append(
                    f"- {item.summary} | 匹配原因: {reason_text}{leading}"
                )

        if state.learned_playbooks:
            lines.append("可借鉴流程:")
            for item in state.learned_playbooks:
                steps = " -> ".join(item.key_steps[:3]) or "无"
                warnings = "；".join(item.warnings[:2]) or "无额外高风险警告"
                lines.append(
                    f"- {item.title}: 适用场景 {item.when_to_use} | 步骤参考 {steps} | 风险提示 {warnings}"
                )

        if state.agent_memories:
            lines.append("长期记忆（Mem0，按当前账户召回）:")
            for item in state.agent_memories[:4]:
                memory_text = str(item.get("memory", "")).strip()
                if memory_text:
                    lines.append(f"- {memory_text}")

        return "\n".join(lines) if lines else "无"

    def _build_profile(
        self,
        past_sessions: list[tuple[dict[str, Any], ConversationState]],
    ) -> list[RememberedPreference]:
        values_by_slot: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for row, past_state in past_sessions:
            filled = past_state.slot_state.filled_dict
            for slot_name in PROFILE_SLOT_CANDIDATES:
                value = filled.get(slot_name)
                if value is None or not str(value).strip():
                    continue
                values_by_slot[slot_name].append((str(value).strip(), row.get("updated_at", "")))

        remembered: list[RememberedPreference] = []
        for slot_name in PROFILE_SLOT_CANDIDATES:
            observations = values_by_slot.get(slot_name, [])
            if len(observations) < 2:
                continue

            counts = Counter(value for value, _ in observations)
            top_value, top_count = counts.most_common(1)[0]
            total = len(observations)
            ratio = top_count / max(total, 1)
            confidence = "high" if top_count >= 3 and ratio >= 0.75 else "medium"
            last_seen_at = max(
                (updated_at for value, updated_at in observations if value == top_value),
                default="",
            )
            remembered.append(
                RememberedPreference(
                    slot_name=slot_name,
                    value=top_value,
                    source_sessions=top_count,
                    confidence=confidence,
                    last_seen_at=last_seen_at,
                    note=f"在最近 {total} 次相关会话中有 {top_count} 次使用该设置",
                )
            )

        remembered.sort(key=lambda item: (-item.source_sessions, item.slot_name))
        return remembered[: self.profile_limit]

    async def _load_past_sessions(
        self,
        state_cls: type["ConversationState"],
        user_id: str,
    ) -> list[tuple[dict[str, Any], "ConversationState"]]:
        rows = await self.session_store.list_sessions(
            user_id=user_id or None,
            limit=self.session_window,
        )
        past_sessions: list[tuple[dict[str, Any], "ConversationState"]] = []
        for row in rows:
            context_json = row.get("context_json") or ""
            if not context_json.strip():
                continue
            try:
                past_state = state_cls.from_json(context_json)
            except Exception:
                continue
            if not past_state.original_query.strip():
                continue
            past_sessions.append((row, past_state))
        return past_sessions

    @staticmethod
    def _filter_memory_source_sessions(
        past_sessions: list[tuple[dict[str, Any], "ConversationState"]],
    ) -> list[tuple[dict[str, Any], "ConversationState"]]:
        return [
            (row, past_state)
            for row, past_state in past_sessions
            if SessionMemoryEngine._is_memory_source_session(past_state)
        ]

    @staticmethod
    def _is_memory_source_session(past_state: "ConversationState") -> bool:
        if past_state.final_contract is not None or past_state.module_artifact:
            return True
        if len(past_state.slot_state.filled_dict) >= 3:
            return True
        return len(past_state.dialogue_history) >= 4

    def _recall_sessions(
        self,
        past_sessions: list[tuple[dict[str, Any], ConversationState]],
        current_state: ConversationState,
    ) -> list[RecalledSession]:
        current_tokens = _tokenize(current_state.original_query)
        current_filled = current_state.slot_state.filled_dict
        recalled: list[RecalledSession] = []

        for row, past_state in past_sessions:
            score = 0.0
            reasons: list[str] = []

            if past_state.task_type == current_state.task_type and current_state.task_type:
                score += 2.0
                reasons.append("同类型任务")
            if past_state.stage == current_state.stage and current_state.stage:
                score += 1.5
                reasons.append("同工作阶段")
            if current_state.failure_mode and past_state.failure_mode == current_state.failure_mode:
                score += 2.0
                reasons.append("同故障模式")

            shared_slots: list[str] = []
            for slot_name, slot_value in current_filled.items():
                if past_state.slot_state.filled_dict.get(slot_name) == slot_value:
                    score += 1.8
                    shared_slots.append(_slot_label(slot_name))

            if shared_slots:
                reasons.append(f"共享条件: {', '.join(shared_slots[:3])}")

            overlap_tokens = current_tokens & _tokenize(past_state.original_query)
            if overlap_tokens:
                score += min(len(overlap_tokens), 4) * 0.3
                reasons.append("问题表述相近")

            if past_state.final_contract is not None:
                score += 0.5

            if score < 3.0:
                continue

            leading_step = (
                past_state.final_contract.steps[0].action
                if past_state.final_contract and past_state.final_contract.steps
                else ""
            )
            recalled.append(
                RecalledSession(
                    session_id=row["session_id"],
                    task_type=past_state.task_type,
                    stage=past_state.stage,
                    failure_mode=past_state.failure_mode,
                    overlap_score=round(score, 2),
                    matched_reasons=reasons[:3],
                    summary=_query_excerpt(past_state.original_query),
                    leading_step=leading_step,
                    has_contract=past_state.final_contract is not None,
                )
            )

        recalled.sort(key=lambda item: (-item.overlap_score, item.session_id))
        return recalled[: self.recall_limit]

    def _build_playbooks(
        self,
        past_sessions: list[tuple[dict[str, Any], ConversationState]],
        recalled_sessions: list[RecalledSession],
    ) -> list[LearnedPlaybook]:
        recalled_map = {item.session_id: item for item in recalled_sessions}
        playbooks: list[LearnedPlaybook] = []

        for row, past_state in past_sessions:
            recalled = recalled_map.get(row["session_id"])
            contract = past_state.final_contract
            if recalled is None or contract is None or not contract.steps:
                continue

            playbooks.append(
                LearnedPlaybook(
                    source_session_id=row["session_id"],
                    title=_query_excerpt(past_state.original_query, limit=48) or "历史流程",
                    when_to_use=recalled.summary,
                    key_steps=[step.action for step in contract.steps[:3]],
                    warnings=[
                        warning.label or warning.action
                        for warning in contract.high_risk_warnings[:2]
                    ],
                )
            )

        return playbooks[: self.playbook_limit]
