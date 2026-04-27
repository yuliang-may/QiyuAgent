"""Tests for M1-M7 metric computation."""

from lacquertutor.agent.state import ConversationState
from lacquertutor.eval.metrics import compute_metrics
from lacquertutor.models.contract import (
    Assumption,
    Checkpoint,
    Contingency,
    PlanContract,
    PlanStep,
)
from lacquertutor.models.task import (
    BenchmarkTask,
    IrreversibleGate,
    MER,
    RequiredCheckpoint,
    RequiredContingency,
)


def _make_task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="TEST",
        task_type="planning",
        stage="coating",
        prompt_en="Test task",
        hidden_slot_values={
            "environment_humidity_pct": "70%",
            "lacquer_system": "urushi",
        },
        mer=MER(
            required_slots=["environment_humidity_pct", "lacquer_system"],
            irreversible_gates=[
                IrreversibleGate(
                    action="涂装",
                    requires_slots=["environment_humidity_pct", "lacquer_system"],
                    required_checkpoint="CP-1",
                    consequence="返工",
                )
            ],
            required_checkpoints=[
                RequiredCheckpoint(checkpoint_id="CP-1", description="干燥")
            ],
            required_contingencies=[
                RequiredContingency(condition="发白", action="延长干燥")
            ],
            required_evidence_refs=["E-APPL-01", "E-CURE-01"],
        ),
    )


class TestGateCompliance:
    def test_m1_all_slots_filled(self):
        """M1 should be 1.0 when all required slots are filled."""
        task = _make_task()
        state = ConversationState()
        state.slot_state.fill("environment_humidity_pct", "70%")
        state.slot_state.fill("lacquer_system", "urushi")

        contract = PlanContract(
            assumptions=[
                Assumption(slot_name="environment_humidity_pct", value="70%", confirmed=True),
                Assumption(slot_name="lacquer_system", value="urushi", confirmed=True),
            ],
            steps=[PlanStep(step_number=1, action="涂装")],
        )

        metrics = compute_metrics(task, contract, state)
        assert metrics.m1_gate_compliance == 1.0

    def test_m1_missing_slots(self):
        """M1 should be 0.0 when required slots are not handled."""
        task = _make_task()
        state = ConversationState()
        contract = PlanContract(
            assumptions=[],
            steps=[PlanStep(step_number=1, action="涂装")],
        )

        metrics = compute_metrics(task, contract, state)
        assert metrics.m1_gate_compliance == 0.0

    def test_m1_declared_missing(self):
        """M1 should count slots declared as missing (safe stop)."""
        task = _make_task()
        state = ConversationState()
        contract = PlanContract(
            assumptions=[],
            missing_critical_slots=["environment_humidity_pct", "lacquer_system"],
            steps=[PlanStep(step_number=1, action="涂装")],
        )

        metrics = compute_metrics(task, contract, state)
        assert metrics.m1_gate_compliance == 1.0


class TestMissingSlotErrors:
    def test_m2_zero_when_all_handled(self):
        task = _make_task()
        state = ConversationState()
        state.slot_state.fill("environment_humidity_pct", "70%")
        state.slot_state.fill("lacquer_system", "urushi")

        contract = PlanContract(
            assumptions=[Assumption(slot_name="environment_humidity_pct", value="70%")],
            steps=[PlanStep(step_number=1, action="涂装")],
        )

        metrics = compute_metrics(task, contract, state)
        assert metrics.m2_missing_slot_errors == 0

    def test_m2_counts_unhandled(self):
        task = _make_task()
        state = ConversationState()
        contract = PlanContract(
            steps=[PlanStep(step_number=1, action="涂装")],
        )

        metrics = compute_metrics(task, contract, state)
        assert metrics.m2_missing_slot_errors == 2  # environment_humidity_pct + lacquer_system


class TestEvidenceCoverage:
    def test_m4a_full_coverage(self):
        task = _make_task()
        state = ConversationState()
        contract = PlanContract(
            assumptions=[Assumption(slot_name="environment_humidity_pct", value="70%")],
            steps=[
                PlanStep(
                    step_number=1,
                    action="涂装",
                    evidence_refs=["E-APPL-01", "E-CURE-01"],
                )
            ],
        )

        metrics = compute_metrics(task, contract, state)
        assert metrics.m4a_evidence_coverage == 1.0

    def test_m4a_partial_coverage(self):
        task = _make_task()
        state = ConversationState()
        contract = PlanContract(
            assumptions=[Assumption(slot_name="environment_humidity_pct", value="70%")],
            steps=[
                PlanStep(
                    step_number=1, action="涂装", evidence_refs=["E-APPL-01"]
                )
            ],
        )

        metrics = compute_metrics(task, contract, state)
        assert metrics.m4a_evidence_coverage == 0.5


class TestTemplateCompliance:
    def test_m7_valid_contract(self):
        task = _make_task()
        state = ConversationState()
        contract = PlanContract(
            assumptions=[Assumption(slot_name="environment_humidity_pct", value="70%")],
            steps=[PlanStep(step_number=1, action="涂装")],
        )

        metrics = compute_metrics(task, contract, state)
        assert metrics.m7_template_compliance is True

    def test_m7_no_steps_fails(self):
        task = _make_task()
        state = ConversationState()
        contract = PlanContract(
            assumptions=[Assumption(slot_name="environment_humidity_pct", value="70%")],
        )

        metrics = compute_metrics(task, contract, state)
        assert metrics.m7_template_compliance is False
