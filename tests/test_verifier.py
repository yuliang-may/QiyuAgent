"""Tests for the rule-based contract verifier."""

from lacquertutor.models.contract import (
    Assumption,
    Checkpoint,
    Contingency,
    HighRiskWarning,
    PlanContract,
    PlanStep,
)
from lacquertutor.models.slots import SlotState, create_slot_state
from lacquertutor.modules.verifier import ContractVerifier


class TestSafetyChecks:
    def setup_method(self):
        self.verifier = ContractVerifier()

    def test_empty_contract_fails(self):
        """Empty contract should fail structural check (no steps)."""
        result = self.verifier.verify(PlanContract(), create_slot_state())
        assert not result.passed
        assert any(i.category == "structural" for i in result.issues)

    def test_irreversible_without_checkpoint_fails(self):
        """Irreversible step without checkpoint should fail."""
        contract = PlanContract(
            steps=[
                PlanStep(step_number=1, action="涂装", is_irreversible=True)
            ],
            assumptions=[Assumption(slot_name="humidity", value="70%")],
        )
        result = self.verifier.verify(contract, create_slot_state())
        assert not result.passed
        safety_errors = [i for i in result.issues if i.category == "safety"]
        assert len(safety_errors) > 0

    def test_critical_action_without_irreversible_flag_fails(self):
        """Applying lacquer without irreversible marker should fail."""
        contract = PlanContract(
            steps=[
                PlanStep(step_number=1, action="Apply first lacquer coat", is_irreversible=False)
            ],
        )
        result = self.verifier.verify(contract, create_slot_state())
        assert not result.passed
        assert any("未标记为不可逆步骤" in issue.description for issue in result.issues)

    def test_confirmed_assumption_with_empty_value_fails(self):
        """Confirmed assumptions cannot have nullish values."""
        contract = PlanContract(
            assumptions=[Assumption(slot_name="lacquer_system", value=None, confirmed=True)],
            steps=[PlanStep(step_number=1, action="准备")],
        )
        result = self.verifier.verify(contract, create_slot_state())
        assert not result.passed
        assert any("值为空" in issue.description for issue in result.issues)

    def test_proper_contract_passes(self):
        """Contract with proper checkpoints and evidence should pass."""
        state = create_slot_state()
        # Fill all hard gates
        for slot in state.unfilled_hard_gates[:]:
            state.fill(slot, "value")

        contract = PlanContract(
            assumptions=[
                Assumption(slot_name=s, value="value", confirmed=True)
                for s in state.filled_dict
            ],
            steps=[
                PlanStep(
                    step_number=1,
                    action="准备",
                    parameters="400-800目",
                    is_irreversible=False,
                ),
                PlanStep(
                    step_number=2,
                    action="涂装",
                    is_irreversible=True,
                    checkpoint_id="CP-1",
                    evidence_refs=["E-APPL-01"],
                ),
            ],
            high_risk_warnings=[
                HighRiskWarning(
                    label="W1",
                    action="涂装",
                    requires_slots=["humidity"],
                    required_checkpoint="CP-1",
                    consequence="需要返工",
                )
            ],
            checkpoints=[
                Checkpoint(
                    checkpoint_id="CP-1",
                    description="漆膜干燥",
                    evidence_refs=["E-CURE-01"],
                )
            ],
            contingencies=[
                Contingency(condition="发白", action="延长干燥时间")
            ],
        )
        result = self.verifier.verify(contract, state)
        assert result.passed, f"Issues: {[i.description for i in result.issues]}"


class TestGroundingChecks:
    def setup_method(self):
        self.verifier = ContractVerifier()

    def test_irreversible_without_evidence_fails(self):
        """Irreversible step without evidence refs should fail grounding."""
        contract = PlanContract(
            assumptions=[Assumption(slot_name="humidity", value="70%")],
            steps=[
                PlanStep(
                    step_number=1,
                    action="涂装",
                    is_irreversible=True,
                    checkpoint_id="CP-1",
                    evidence_refs=[],  # No evidence!
                )
            ],
            checkpoints=[
                Checkpoint(checkpoint_id="CP-1", description="检查")
            ],
            missing_critical_slots=["humidity", "lacquer_system",
                                     "substrate_condition", "time_since_coat",
                                     "curing_duration", "layer_thickness"],
        )
        state = create_slot_state()
        result = self.verifier.verify(contract, state)
        grounding_errors = [
            i for i in result.issues if i.category == "grounding" and i.severity == "error"
        ]
        assert len(grounding_errors) > 0


class TestStructuralChecks:
    def setup_method(self):
        self.verifier = ContractVerifier()

    def test_misnumbered_steps_warned(self):
        """Non-sequential step numbering should produce a warning."""
        contract = PlanContract(
            assumptions=[Assumption(slot_name="humidity", value="70%")],
            steps=[
                PlanStep(step_number=1, action="准备"),
                PlanStep(step_number=3, action="涂装"),  # Should be 2
            ],
        )
        result = self.verifier.verify(contract, create_slot_state())
        structural_warnings = [
            i for i in result.issues
            if i.category == "structural" and i.severity == "warning"
        ]
        assert len(structural_warnings) > 0
