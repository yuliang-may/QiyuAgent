from __future__ import annotations

import pytest

from lacquertutor.agent.pipeline import LacquerTutorAgent
from lacquertutor.agent.state import ConversationState
from lacquertutor.config import Settings
from lacquertutor.models.contract import PlanContract
from lacquertutor.models.evidence import EvidenceStore


def test_pending_slot_fallback_fills_humidity_from_percent_answer():
    state = ConversationState(original_query="test")
    state.pending_slot_name = "environment_humidity_pct"

    LacquerTutorAgent._apply_pending_slot_fallback(state, "55%")

    assert state.slot_state.filled_dict["environment_humidity_pct"] == "55"


def test_pending_slot_fallback_fills_dilution_ratio_from_number_answer():
    state = ConversationState(original_query="test")
    state.pending_slot_name = "dilution_ratio_pct"

    LacquerTutorAgent._apply_pending_slot_fallback(state, "12")

    assert state.slot_state.filled_dict["dilution_ratio_pct"] == "12"


def test_pending_slot_fallback_fills_ventilation_quality_from_text_answer():
    state = ConversationState(original_query="test")
    state.pending_slot_name = "ventilation_quality"

    LacquerTutorAgent._apply_pending_slot_fallback(state, "good")

    assert state.slot_state.filled_dict["ventilation_quality"] == "good"


def test_pending_slot_fallback_fills_application_tool_from_text_answer():
    state = ConversationState(original_query="test")
    state.pending_slot_name = "application_tool"

    LacquerTutorAgent._apply_pending_slot_fallback(state, "brush")

    assert state.slot_state.filled_dict["application_tool"] == "brush"


def test_fallback_contract_is_generated_without_planner_output():
    state = ConversationState(original_query="我想做一个木托盘")
    state.task_type = "planning"
    state.stage = "preparation"
    state.stop_reason = "max_questions"
    state.slot_state.fill("substrate_material", "wood", source="user", confirmed=True)
    state.slot_state.fill("lacquer_system", "water_based", source="user", confirmed=True)

    contract = LacquerTutorAgent._build_fallback_contract(state)

    assert isinstance(contract, PlanContract)
    assert contract.steps
    assert contract.checkpoints
    assert contract.stop_reason == "max_questions"


@pytest.mark.asyncio
async def test_generate_contract_falls_back_when_planner_returns_empty_contract(monkeypatch):
    agent = LacquerTutorAgent(Settings(), EvidenceStore([]))
    state = ConversationState(original_query="我想给木胎做一道生漆底")
    state.task_type = "planning"
    state.stage = "preparation"
    state.stop_reason = "max_questions"
    state.slot_state.fill("lacquer_system", "urushi", source="user", confirmed=True)
    state.slot_state.fill("environment_humidity_pct", "55", source="user", confirmed=True)
    state.slot_state.fill("environment_temperature_c", "25", source="user", confirmed=True)

    async def fake_run_agent(target, prompt: str):
        assert target is agent.planner_agent
        assert "对话停止原因: max_questions" in prompt
        return PlanContract()

    monkeypatch.setattr(agent, "_run_agent", fake_run_agent)

    try:
        contract = await agent._generate_contract(state)
    finally:
        await agent.close()

    assert contract.steps
    assert contract.checkpoints
    assert contract.high_risk_warnings
    assert contract.contingencies
    assert contract.stop_reason == "max_questions"
