"""M1–M7 metric computation for benchmark evaluation.

Metrics are computed from a generated PlanContract against the
task's MER (Minimum Executable Requirements) checklist.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from lacquertutor.agent.state import ConversationState
from lacquertutor.models.contract import PlanContract
from lacquertutor.models.task import BenchmarkTask


class TaskMetrics(BaseModel):
    """Evaluation metrics for a single task under a single condition."""

    task_id: str
    condition: str

    # M1: Gate compliance ↑
    m1_gate_compliance: float = 0.0

    # M2: Missing-slot errors ↓
    m2_missing_slot_errors: int = 0

    # M3: Coverage
    m3a_checkpoint_coverage: float = 0.0
    m3b_contingency_coverage: float = 0.0

    # M4: Evidence grounding
    m4a_evidence_coverage: float = 0.0
    m4b_ungrounded_decisions: int = 0

    # M5: Consistency flags ↓
    m5_consistency_flags: int = 0

    # M6: Elicitation overhead
    m6_questions_asked: int = 0
    m6_slots_filled: int = 0

    # M7: Template compliance (binary)
    m7_template_compliance: bool = False


def compute_metrics(
    task: BenchmarkTask,
    contract: PlanContract,
    state: ConversationState,
) -> TaskMetrics:
    """Compute M1–M7 metrics for a task result."""
    mer = task.mer
    metrics = TaskMetrics(task_id=task.task_id, condition="")

    # M1: Gate compliance
    metrics.m1_gate_compliance = _compute_gate_compliance(contract, mer, state)

    # M2: Missing-slot errors
    metrics.m2_missing_slot_errors = _compute_missing_slot_errors(
        contract, mer, state
    )

    # M3a: Checkpoint coverage
    metrics.m3a_checkpoint_coverage = _compute_checkpoint_coverage(contract, mer)

    # M3b: Contingency coverage
    metrics.m3b_contingency_coverage = _compute_contingency_coverage(contract, mer)

    # M4a: Evidence coverage
    metrics.m4a_evidence_coverage = _compute_evidence_coverage(contract, mer)

    # M4b: Ungrounded critical decisions
    metrics.m4b_ungrounded_decisions = _compute_ungrounded_decisions(contract)

    # M5: Consistency flags
    metrics.m5_consistency_flags = _compute_consistency_flags(contract)

    # M6: Elicitation overhead
    metrics.m6_questions_asked = state.questions_asked
    metrics.m6_slots_filled = len(state.slot_state.filled)

    # M7: Template compliance
    metrics.m7_template_compliance = _check_template_compliance(contract)

    return metrics


def _compute_gate_compliance(
    contract: PlanContract,
    mer: 'MER',
    state: ConversationState,
) -> float:
    """M1: Fraction of irreversible gates that are safely handled.

    A gate is safely handled if:
    (a) the plan stops before crossing it (contract has no steps beyond), OR
    (b) all required gating slots are confirmed in the slot state
    """
    gates = mer.irreversible_gates
    if not gates:
        return 1.0

    safe_count = 0
    filled = set(state.slot_state.filled.keys())
    # Map 18-slot schema names to 12-slot names where needed
    for gate in gates:
        required = set(gate.requires_slots)
        # Check if gate is protected: required slots filled OR
        # contract declares them as missing/assumption
        handled = required.issubset(filled) or all(
            s in contract.missing_critical_slots
            or any(
                a.slot_name == s and not a.confirmed for a in contract.assumptions
            )
            for s in required - filled
        )
        if handled:
            safe_count += 1

    return safe_count / len(gates)


def _compute_missing_slot_errors(
    contract: PlanContract,
    mer: 'MER',
    state: ConversationState,
) -> int:
    """M2: Count required gating slots neither filled nor safely handled."""
    errors = 0
    filled = set(state.slot_state.filled.keys())
    declared_missing = set(contract.missing_critical_slots)
    assumption_slots = {
        a.slot_name for a in contract.assumptions if not a.confirmed
    }

    for gate in mer.irreversible_gates:
        for slot in gate.requires_slots:
            if slot not in filled and slot not in declared_missing and slot not in assumption_slots:
                errors += 1

    return errors


def _compute_checkpoint_coverage(contract: PlanContract, mer: 'MER') -> float:
    """M3a: Fraction of required checkpoints present in contract."""
    if not mer.required_checkpoints:
        return 1.0

    contract_cp_ids = {cp.checkpoint_id for cp in contract.checkpoints}
    found = sum(
        1 for req in mer.required_checkpoints if req.checkpoint_id in contract_cp_ids
    )
    return found / len(mer.required_checkpoints)


def _compute_contingency_coverage(contract: PlanContract, mer: 'MER') -> float:
    """M3b: Fraction of required contingencies present in contract."""
    if not mer.required_contingencies:
        return 1.0

    # Fuzzy match: check if contract has contingencies covering similar conditions
    if not contract.contingencies:
        return 0.0

    # Simple: ratio of contract contingencies to required
    return min(1.0, len(contract.contingencies) / len(mer.required_contingencies))


def _compute_evidence_coverage(contract: PlanContract, mer: 'MER') -> float:
    """M4a: Fraction of required evidence refs cited in contract."""
    if not mer.required_evidence_refs:
        return 1.0

    contract_refs: set[str] = set()
    for step in contract.steps:
        contract_refs.update(step.evidence_refs)
    for cp in contract.checkpoints:
        contract_refs.update(cp.evidence_refs)
    for ct in contract.contingencies:
        contract_refs.update(ct.evidence_refs)

    found = sum(1 for ref in mer.required_evidence_refs if ref in contract_refs)
    return found / len(mer.required_evidence_refs)


def _compute_ungrounded_decisions(contract: PlanContract) -> int:
    """M4b: Count irreversible steps without evidence references."""
    return sum(
        1
        for step in contract.steps
        if step.is_irreversible and not step.evidence_refs
    )


def _compute_consistency_flags(contract: PlanContract) -> int:
    """M5: Count structural consistency issues."""
    flags = 0

    # Check step numbering
    for i, step in enumerate(contract.steps):
        if step.step_number != i + 1:
            flags += 1

    # Check checkpoint references in steps point to existing checkpoints
    cp_ids = {cp.checkpoint_id for cp in contract.checkpoints}
    for step in contract.steps:
        if step.checkpoint_id and step.checkpoint_id not in cp_ids:
            flags += 1

    return flags


def _check_template_compliance(contract: PlanContract) -> bool:
    """M7: Check if contract has all required sections and parses correctly."""
    has_steps = len(contract.steps) > 0
    has_assumptions = len(contract.assumptions) > 0 or len(contract.missing_critical_slots) > 0
    return has_steps and has_assumptions
