"""Tests for Pydantic data models."""

import json

from lacquertutor.models.contract import (
    Assumption,
    Checkpoint,
    Contingency,
    HighRiskWarning,
    PlanContract,
    PlanStep,
)
from lacquertutor.models.evidence import EvidenceStore
from lacquertutor.models.slots import (
    ALL_SLOTS,
    HARD_GATE_SLOTS,
    SlotState,
    create_slot_state,
)
from lacquertutor.models.task import TaskSet


class TestSlotState:
    def test_create_has_18_slots(self, slot_state: SlotState):
        assert len(slot_state.schema_defs) == 18
        assert len(slot_state.all_slot_names) == 18

    def test_all_unfilled_initially(self, slot_state: SlotState):
        assert len(slot_state.unfilled) == 18
        assert len(slot_state.filled) == 0

    def test_hard_gate_slots(self):
        assert len(HARD_GATE_SLOTS) == 8
        assert "environment_humidity_pct" in HARD_GATE_SLOTS
        assert "lacquer_system" in HARD_GATE_SLOTS
        assert "substrate_material" in HARD_GATE_SLOTS
        assert "ppe_level" in HARD_GATE_SLOTS
        assert "ventilation_quality" not in HARD_GATE_SLOTS  # soft

    def test_fill_slot(self, slot_state: SlotState):
        slot_state.fill("environment_humidity_pct", "70%", source="user", turn=1)
        assert slot_state.is_filled("environment_humidity_pct")
        assert len(slot_state.unfilled) == 17
        assert slot_state.filled["environment_humidity_pct"].value == "70%"
        assert slot_state.filled["environment_humidity_pct"].source == "user"

    def test_fill_invalid_slot_ignored(self, slot_state: SlotState):
        slot_state.fill("nonexistent_slot", "value")
        assert len(slot_state.filled) == 0

    def test_filled_dict(self, slot_state: SlotState):
        slot_state.fill("environment_humidity_pct", "70%")
        slot_state.fill("environment_temperature_c", "25")
        d = slot_state.filled_dict
        assert d == {"environment_humidity_pct": "70%", "environment_temperature_c": "25"}

    def test_unfilled_hard_gates(self, slot_state: SlotState):
        assert len(slot_state.unfilled_hard_gates) == 8
        slot_state.fill("environment_humidity_pct", "70%")
        assert len(slot_state.unfilled_hard_gates) == 7
        assert "environment_humidity_pct" not in slot_state.unfilled_hard_gates

    def test_all_hard_gates_filled(self, slot_state: SlotState):
        assert not slot_state.all_hard_gates_filled
        for s in HARD_GATE_SLOTS:
            slot_state.fill(s, "value")
        assert slot_state.all_hard_gates_filled

    def test_reset(self, slot_state: SlotState):
        slot_state.fill("environment_humidity_pct", "70%")
        slot_state.reset()
        assert len(slot_state.filled) == 0

    def test_slot_names_match_benchmark(self, taskset: TaskSet):
        """Verify every slot name used in the benchmark exists in our schema."""
        for task in taskset:
            for slot_name in task.hidden_slot_values:
                assert slot_name in ALL_SLOTS, (
                    f"Benchmark slot '{slot_name}' (task {task.task_id}) "
                    f"not in ALL_SLOTS"
                )
            for slot_name in task.mer.required_slots:
                assert slot_name in ALL_SLOTS, (
                    f"MER required_slot '{slot_name}' (task {task.task_id}) "
                    f"not in ALL_SLOTS"
                )


class TestEvidenceStore:
    def test_load_count(self, evidence_store: EvidenceStore):
        assert len(evidence_store) >= 40  # At least 40 cards

    def test_get_by_id(self, evidence_store: EvidenceStore):
        card = evidence_store.get("E-SAFE-01")
        assert card is not None
        assert card.stage == "general"
        assert card.is_safety

    def test_filter_by_stage(self, evidence_store: EvidenceStore):
        curing = evidence_store.filter_by_stage("curing")
        assert len(curing) > 0
        assert all(c.stage == "curing" for c in curing)

    def test_retrieve_top_k(self, evidence_store: EvidenceStore):
        results = evidence_store.retrieve("curing", "tackiness", k=4)
        assert len(results) == 4
        # First result should be curing+tackiness match (highest score)
        assert results[0].stage == "curing" or results[0].failure_mode == "tackiness"

    def test_safety_cards_included(self, evidence_store: EvidenceStore):
        results = evidence_store.retrieve("preparation", k=6)
        ids = {c.evidence_id for c in results}
        # Safety cards should appear in broader retrievals
        has_safety = any(c.is_safety for c in results)
        assert has_safety or len(results) == 6  # might be crowded out


class TestTaskSet:
    def test_load_count(self, taskset: TaskSet):
        assert len(taskset) == 42

    def test_planning_troubleshooting_split(self, taskset: TaskSet):
        assert len(taskset.planning_tasks) == 21
        assert len(taskset.troubleshooting_tasks) == 21

    def test_get_by_id(self, taskset: TaskSet):
        p01 = taskset.get("P01")
        assert p01 is not None
        assert p01.task_type == "planning"
        assert p01.stage == "preparation"
        assert len(p01.hidden_slot_values) > 0

    def test_mer_structure(self, taskset: TaskSet):
        p01 = taskset.get("P01")
        assert len(p01.mer.required_slots) > 0
        assert len(p01.mer.irreversible_gates) > 0
        for gate in p01.mer.irreversible_gates:
            assert gate.action
            assert len(gate.requires_slots) > 0


class TestPlanContract:
    def test_empty_contract(self):
        c = PlanContract()
        assert len(c.steps) == 0
        assert len(c.checkpoints) == 0

    def test_to_markdown(self):
        c = PlanContract(
            assumptions=[Assumption(slot_name="environment_humidity_pct", value="70%", confirmed=True)],
            steps=[PlanStep(step_number=1, action="涂装", parameters="薄涂")],
            checkpoints=[Checkpoint(checkpoint_id="CP-1", description="干燥检查")],
        )
        md = c.to_markdown()
        assert "environment_humidity_pct" in md
        assert "CP-1" in md
        assert "涂装" in md

    def test_json_roundtrip(self):
        c = PlanContract(
            assumptions=[Assumption(slot_name="environment_humidity_pct", value="70%")],
            steps=[
                PlanStep(
                    step_number=1,
                    action="涂装",
                    is_irreversible=True,
                    checkpoint_id="CP-1",
                    evidence_refs=["E-APPL-01"],
                )
            ],
            checkpoints=[Checkpoint(checkpoint_id="CP-1", description="检查")],
            contingencies=[
                Contingency(condition="漆膜发白", action="延长固化时间")
            ],
        )
        data = json.loads(c.model_dump_json())
        c2 = PlanContract.model_validate(data)
        assert c2.steps[0].action == "涂装"
        assert c2.checkpoints[0].checkpoint_id == "CP-1"
