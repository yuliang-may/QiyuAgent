from __future__ import annotations

import pytest

from lacquertutor.agent.mem0_service import (
    _is_useful_memory_text,
    _collection_name_for_settings,
    _records_from_result,
)
from lacquertutor.agent.memory import SessionMemoryEngine
from lacquertutor.agent.state import ConversationState
from lacquertutor.config import Settings
from lacquertutor.models.contract import HighRiskWarning, PlanContract, PlanStep
from lacquertutor.models.memory import LearnedPlaybook, RecalledSession, RememberedPreference
from lacquertutor.storage.session_store import SessionStore


async def _seed_session(
    store: SessionStore,
    *,
    query: str,
    task_type: str = "planning",
    stage: str = "preparation",
    filled: dict[str, str] | None = None,
    contract: PlanContract | None = None,
) -> str:
    state = ConversationState(
        original_query=query,
        task_type=task_type,
        stage=stage,
        final_contract=contract,
    )
    for name, value in (filled or {}).items():
        state.slot_state.fill(name, value, source="user", confirmed=True)

    session_id = await store.create_session()
    await store.update_context(session_id, state.to_json())
    await store.update_status(session_id, "completed" if contract else "active")
    return session_id


@pytest.mark.asyncio
async def test_memory_engine_hydrates_profile_recall_and_playbooks():
    store = SessionStore(":memory:")
    await store.initialize()
    try:
        contract = PlanContract(
            steps=[
                PlanStep(step_number=1, action="先做样板测试"),
                PlanStep(step_number=2, action="薄涂第一层"),
            ],
            high_risk_warnings=[
                HighRiskWarning(label="湿度过高勿直接上漆", action="暂停涂装"),
            ],
        )

        await _seed_session(
            store,
            query="我准备开始一个新的漆艺制作项目。\n对象 / 基底: 木盘\n你想做成什么效果: 想做半光黑漆面",
            filled={
                "lacquer_system": "water_based",
                "target_finish": "semi_gloss",
                "curing_method": "air",
                "ppe_level": "respirator",
                "substrate_material": "wood",
            },
            contract=contract,
        )

        await _seed_session(
            store,
            query="我准备开始一个新的漆艺制作项目。\n对象 / 基底: 木盒\n你想做成什么效果: 想做半光黑漆面",
            filled={
                "lacquer_system": "water_based",
                "target_finish": "semi_gloss",
                "curing_method": "air",
                "ppe_level": "respirator",
                "substrate_material": "wood",
            },
        )

        current = ConversationState(
            original_query="我准备开始一个新的漆艺制作项目。\n对象 / 基底: 木托盘\n你想做成什么效果: 想做半光黑漆面",
            task_type="planning",
            stage="preparation",
        )
        current.slot_state.fill("substrate_material", "wood", source="user", confirmed=True)
        current.slot_state.fill("target_finish", "semi_gloss", source="user", confirmed=True)

        memory = SessionMemoryEngine(store)
        await memory.hydrate_state(current)

        assert any(item.slot_name == "lacquer_system" and item.value == "water_based" for item in current.remembered_preferences)
        assert current.recalled_sessions, "should recall similar past sessions"
        assert current.recalled_sessions[0].has_contract is True
        assert current.learned_playbooks, "completed sessions should become playbooks"
        assert current.learned_playbooks[0].key_steps[0] == "先做样板测试"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_memory_prompt_text_marks_history_as_reference_only():
    state = ConversationState(original_query="测试")
    assert SessionMemoryEngine.format_for_prompt(state) == "无"

    state.remembered_preferences = [
        RememberedPreference(
            slot_name="lacquer_system",
            value="water_based",
            source_sessions=2,
            confidence="medium",
        )
    ]
    state.recalled_sessions = [
        RecalledSession(
            session_id="S1",
            summary="木盘半光黑漆面",
            matched_reasons=["同类型任务", "共享条件: 基底材料"],
            leading_step="先做样板测试",
            has_contract=True,
        )
    ]
    state.learned_playbooks = [
        LearnedPlaybook(
            source_session_id="S1",
            title="木盘半光黑漆流程",
            when_to_use="木盘半光黑漆面",
            key_steps=["先做样板测试", "薄涂第一层"],
            warnings=["湿度过高勿直接上漆"],
        )
    ]

    prompt = SessionMemoryEngine.format_for_prompt(state)
    assert "工作室档案" in prompt
    assert "相似历史会话" in prompt
    assert "可借鉴流程" in prompt
    assert "仅供参考" in prompt


def test_mem0_default_collection_name_is_dimension_scoped():
    settings = Settings(mem0_collection="lacquertutor_memories")

    assert _collection_name_for_settings(settings, 1024) == "lacquertutor_memories_1024d"
    assert _collection_name_for_settings(settings, 1536) == "lacquertutor_memories_1536d"


def test_mem0_records_are_deduplicated_by_memory_text_and_sorted_by_score():
    records = _records_from_result(
        {
            "results": [
                {
                    "id": "1",
                    "memory": "User prefers semi-gloss finish",
                    "score": 0.6,
                    "metadata": {"created_at": "2026-04-20T10:00:00+00:00"},
                },
                {
                    "id": "2",
                    "memory": "user prefers semi-gloss finish",
                    "score": 0.9,
                    "metadata": {"created_at": "2026-04-20T11:00:00+00:00"},
                },
                {
                    "id": "3",
                    "memory": "User uses water-based systems",
                    "score": 0.7,
                    "metadata": {"created_at": "2026-04-20T09:00:00+00:00"},
                },
                {
                    "id": "4",
                    "memory": "User has not yet specified the substrate material.",
                    "score": 0.99,
                    "metadata": {"created_at": "2026-04-20T12:00:00+00:00"},
                },
            ]
        },
        sort_by="score",
    )

    assert [item.memory_id for item in records] == ["2", "3"]


def test_mem0_filters_low_value_missing_info_memories():
    assert _is_useful_memory_text("User prefers semi-gloss finish") is True
    assert _is_useful_memory_text("User has not yet specified the substrate material.") is False


def test_chat_profile_extraction_uses_shared_slot_normalizer():
    from lacquertutor.agent.slot_normalizer import extract_slot_values_from_text

    extracted = extract_slot_values_from_text(
        "我更喜欢半光效果，平时刷涂，而且会戴呼吸防护面罩。",
        slot_names=("target_finish", "application_tool", "ppe_level"),
    )

    assert extracted == {
        "target_finish": "semi_gloss",
        "application_tool": "brush",
        "ppe_level": "respirator",
    }


@pytest.mark.asyncio
async def test_memory_engine_profile_ignores_low_signal_sessions():
    store = SessionStore(":memory:")
    await store.initialize()
    try:
        weak_state = ConversationState(
            original_query="我想开始一个项目",
            task_type="planning",
            stage="preparation",
        )
        weak_state.slot_state.fill("lacquer_system", "water_based", source="user", confirmed=True)
        weak_session_id = await store.create_session()
        await store.update_context(weak_session_id, weak_state.to_json())
        await store.update_status(weak_session_id, "active")

        strong_state = ConversationState(
            original_query="我想给木盘做半光漆面",
            task_type="planning",
            stage="preparation",
        )
        for name, value in {
            "lacquer_system": "water_based",
            "target_finish": "semi_gloss",
            "application_tool": "brush",
        }.items():
            strong_state.slot_state.fill(name, value, source="user", confirmed=True)
        strong_state.add_user_turn("补充：我一般刷涂")
        strong_state.add_assistant_turn("好的")
        strong_session_id = await store.create_session()
        await store.update_context(strong_session_id, strong_state.to_json())
        await store.update_status(strong_session_id, "active")

        engine = SessionMemoryEngine(store)
        profile = engine._build_profile(
            engine._filter_memory_source_sessions(
                await engine._load_past_sessions(ConversationState, "")
            )
        )

        assert any(item.slot_name == "lacquer_system" for item in profile) is False
    finally:
        await store.close()
