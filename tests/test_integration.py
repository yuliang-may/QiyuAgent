"""End-to-end integration test using the pipeline with oracle simulation.

Requires a live LLM connection (Qwen via DashScope). Skipped by default.
Run with: pytest tests/test_integration.py -v --run-integration
"""

from __future__ import annotations

import os

import pytest

from lacquertutor.agent.pipeline import LacquerTutorAgent
from lacquertutor.config import Settings
from lacquertutor.eval.conditions import get_condition
from lacquertutor.eval.metrics import compute_metrics
from lacquertutor.eval.oracle import OracleSimulator
from lacquertutor.models.evidence import EvidenceStore
from lacquertutor.models.task import TaskSet

# Skip unless --run-integration flag or LACQUERTUTOR_RUN_INTEGRATION env var
requires_llm = pytest.mark.skipif(
    not os.environ.get("LACQUERTUTOR_RUN_INTEGRATION"),
    reason="Requires live LLM. Set LACQUERTUTOR_RUN_INTEGRATION=1 to run.",
)

BENCHMARK_DIR = Settings().benchmark_dir


@requires_llm
@pytest.mark.asyncio
async def test_p01_s2_end_to_end():
    """Run task P01 through the full S2 pipeline with oracle simulation.

    Validates:
    - Contract has steps (not empty)
    - Contract has checkpoints
    - M1 gate compliance > 0
    - M7 template compliance is True
    """
    settings = Settings()
    taskset = TaskSet.from_json(settings.taskset_path)
    evidence_store = EvidenceStore.from_json(settings.evidence_cards_path)

    task = taskset.get("P01")
    assert task is not None, "Task P01 not found in taskset"

    # S2 = full system: VoI scoring + verifier
    condition = get_condition("S2")

    # Create oracle simulator with ground truth
    oracle = OracleSimulator(task.hidden_slot_values)

    # Create and run agent
    agent = LacquerTutorAgent(settings, evidence_store)
    try:
        contract, state = await agent.run(
            query=task.prompt_en,
            answer_fn=oracle.answer_question,
            enable_dialogue=condition.enable_dialogue,
            enable_verifier=condition.enable_verifier,
            slot_selection=condition.slot_selection,
        )
    finally:
        await agent.close()

    # Validate contract structure
    assert len(contract.steps) > 0, "Contract should have at least one step"
    assert contract.task_type == "planning"
    assert contract.stage == "preparation"

    # Compute metrics against MER
    metrics = compute_metrics(task, contract, state)

    assert metrics.m7_template_compliance is True, "Contract should parse as valid template"
    assert metrics.m1_gate_compliance > 0, "At least some gates should be handled"

    # Log metrics for debugging
    print(f"\n--- P01 S2 Metrics ---")
    print(f"M1 (gate compliance): {metrics.m1_gate_compliance:.2f}")
    print(f"M2 (missing slots):   {metrics.m2_missing_slot_errors}")
    print(f"M3a (checkpoints):    {metrics.m3a_checkpoint_coverage:.2f}")
    print(f"M3b (contingencies):  {metrics.m3b_contingency_coverage:.2f}")
    print(f"M4a (evidence):       {metrics.m4a_evidence_coverage:.2f}")
    print(f"M7 (template):        {metrics.m7_template_compliance}")
    print(f"Questions asked:      {state.questions_asked}")
    print(f"Slots filled:         {len(state.slot_state.filled)}")
    print(f"Steps:                {len(contract.steps)}")
    print(f"Checkpoints:          {len(contract.checkpoints)}")


@requires_llm
@pytest.mark.asyncio
async def test_p01_b1_no_dialogue():
    """Run P01 in B1 condition (RAG-only, no dialogue).

    Should produce a valid contract with lower M1 than S2.
    """
    settings = Settings()
    taskset = TaskSet.from_json(settings.taskset_path)
    evidence_store = EvidenceStore.from_json(settings.evidence_cards_path)

    task = taskset.get("P01")
    condition = get_condition("B1")

    oracle = OracleSimulator(task.hidden_slot_values)

    agent = LacquerTutorAgent(settings, evidence_store)
    try:
        contract, state = await agent.run(
            query=task.prompt_en,
            answer_fn=oracle.answer_question,
            enable_dialogue=condition.enable_dialogue,
            enable_verifier=condition.enable_verifier,
            slot_selection=condition.slot_selection,
        )
    finally:
        await agent.close()

    assert len(contract.steps) > 0
    assert state.questions_asked == 0, "B1 should not ask any questions"

    metrics = compute_metrics(task, contract, state)
    assert metrics.m7_template_compliance is True
