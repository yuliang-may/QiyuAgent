"""Rule-based Contract Verifier — Module 4.

Deterministic verification of plan contracts against safety,
structural, and grounding requirements. No LLM calls.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
import structlog

from lacquertutor.models.contract import PlanContract
from lacquertutor.models.slots import HARD_GATE_SLOTS, SlotState
from lacquertutor.models.task import MER
from lacquertutor.modules.contract_quality import is_critical_action, recommended_gate_slots

logger = structlog.get_logger(__name__)

# Stage ordering for structural checks
STAGE_ORDER = {
    "preparation": 0,
    "coating": 1,
    "curing": 2,
    "polishing": 3,
    "finishing": 4,
}


class VerificationIssue(BaseModel):
    """A single issue found during contract verification."""

    category: str  # "safety", "structural", "grounding"
    severity: str  # "error", "warning"
    description: str
    affected_step: int | None = None
    suggested_action: str = ""  # "re_elicit", "re_retrieve", "conservative_replan"


class VerificationResult(BaseModel):
    """Result of contract verification."""

    passed: bool = True
    issues: list[VerificationIssue] = Field(default_factory=list)

    @property
    def errors(self) -> list[VerificationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[VerificationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def needs_re_elicit(self) -> bool:
        return any(i.suggested_action == "re_elicit" for i in self.errors)

    @property
    def needs_re_retrieve(self) -> bool:
        return any(i.suggested_action == "re_retrieve" for i in self.errors)

    @property
    def needs_replan(self) -> bool:
        return any(i.suggested_action == "conservative_replan" for i in self.errors)


class ContractVerifier:
    """Deterministic rule-based contract verifier."""

    def verify(
        self,
        contract: PlanContract,
        slot_state: SlotState,
        mer: MER | None = None,
    ) -> VerificationResult:
        """Run all verification checks on a contract.

        Checks three categories:
        1. Safety — gate compliance, checkpoint presence
        2. Structural — stage ordering
        3. Grounding — evidence refs on critical steps
        """
        result = VerificationResult()

        self._check_safety(contract, slot_state, result)
        self._check_structural(contract, result)
        self._check_grounding(contract, result)

        if mer:
            self._check_mer_compliance(contract, mer, result)

        result.passed = len(result.errors) == 0

        logger.info(
            "verification_complete",
            passed=result.passed,
            errors=len(result.errors),
            warnings=len(result.warnings),
        )
        return result

    def _check_safety(
        self,
        contract: PlanContract,
        slot_state: SlotState,
        result: VerificationResult,
    ) -> None:
        """Check gate compliance for irreversible steps."""
        checkpoint_ids = {cp.checkpoint_id for cp in contract.checkpoints}
        critical_but_unmarked = [
            step for step in contract.steps
            if is_critical_action(step.action) and not step.is_irreversible
        ]

        for step in critical_but_unmarked:
            result.issues.append(
                VerificationIssue(
                    category="safety",
                    severity="error",
                    description=(
                        f"步骤 {step.step_number} ({step.action}) 包含关键上漆/封闭动作，"
                        "但未标记为不可逆步骤"
                    ),
                    affected_step=step.step_number,
                    suggested_action="conservative_replan",
                )
            )

        for step in contract.steps:
            if not step.is_irreversible:
                continue

            # Check: irreversible step must have a checkpoint
            if not step.checkpoint_id or step.checkpoint_id not in checkpoint_ids:
                result.issues.append(
                    VerificationIssue(
                        category="safety",
                        severity="error",
                        description=(
                            f"步骤 {step.step_number} ({step.action}) 是不可逆操作，"
                            "但没有关联的检查点"
                        ),
                        affected_step=step.step_number,
                        suggested_action="conservative_replan",
                    )
                )

            # Check: irreversible step must have a high-risk warning
            has_warning = any(
                w.action == step.action or w.label.endswith(str(step.step_number))
                for w in contract.high_risk_warnings
            )
            if not has_warning:
                result.issues.append(
                    VerificationIssue(
                        category="safety",
                        severity="error",
                        description=(
                            f"步骤 {step.step_number} ({step.action}) 是不可逆操作，"
                            "但没有对应的高风险警告"
                        ),
                        affected_step=step.step_number,
                        suggested_action="conservative_replan",
                    )
                )

        # Check: unfilled hard-gate slots with irreversible steps
        if slot_state.unfilled_hard_gates:
            irreversible_steps = [s for s in contract.steps if s.is_irreversible]
            if irreversible_steps:
                # Verify the contract either stops before the gate or notes the assumption
                missing_in_assumptions = [
                    s
                    for s in slot_state.unfilled_hard_gates
                    if s not in contract.missing_critical_slots
                    and not any(
                        a.slot_name == s and not a.confirmed
                        for a in contract.assumptions
                    )
                ]
                if missing_in_assumptions:
                    result.issues.append(
                        VerificationIssue(
                            category="safety",
                            severity="error",
                            description=(
                                f"硬门控变量 {missing_in_assumptions} 未填充，"
                                "但计划包含不可逆步骤且未标注为假设或缺失"
                            ),
                            suggested_action="re_elicit",
                        )
                    )

        for assumption in contract.assumptions:
            if assumption.confirmed and assumption.value in (None, "", "None"):
                result.issues.append(
                    VerificationIssue(
                        category="safety",
                        severity="error",
                        description=(
                            f"假设 {assumption.slot_name} 被标记为已确认，但值为空。"
                        ),
                        suggested_action="conservative_replan",
                    )
                )

    def _check_structural(
        self,
        contract: PlanContract,
        result: VerificationResult,
    ) -> None:
        """Check stage ordering, step numbering, and structural completeness."""
        # Template compliance: must have at least one step
        if not contract.steps:
            result.issues.append(
                VerificationIssue(
                    category="structural",
                    severity="error",
                    description="合同不包含任何操作步骤",
                    suggested_action="conservative_replan",
                )
            )

        # Step numbering should be sequential
        for i, step in enumerate(contract.steps):
            if step.step_number != i + 1:
                result.issues.append(
                    VerificationIssue(
                        category="structural",
                        severity="warning",
                        description=f"步骤编号不连续: 期望 {i+1}, 实际 {step.step_number}",
                        affected_step=step.step_number,
                    )
                )

        # Irreversible steps should have corresponding contingencies
        irreversible_steps = [s for s in contract.steps if s.is_irreversible]
        if irreversible_steps and not contract.contingencies:
            result.issues.append(
                VerificationIssue(
                    category="structural",
                    severity="error",
                    description=(
                        f"合同包含 {len(irreversible_steps)} 个不可逆步骤，"
                        "但没有应急预案（contingencies）"
                    ),
                    suggested_action="conservative_replan",
                )
            )

        if irreversible_steps and not contract.checkpoints:
            result.issues.append(
                VerificationIssue(
                    category="structural",
                    severity="error",
                    description="合同包含不可逆步骤，但没有任何检查点",
                    suggested_action="conservative_replan",
                )
            )

        # Contingencies should reference valid checkpoint IDs
        checkpoint_ids = {cp.checkpoint_id for cp in contract.checkpoints}
        for ct in contract.contingencies:
            if ct.recheck_checkpoint and ct.recheck_checkpoint not in checkpoint_ids:
                result.issues.append(
                    VerificationIssue(
                        category="structural",
                        severity="warning",
                        description=(
                            f"应急预案引用了不存在的检查点: {ct.recheck_checkpoint}"
                        ),
                    )
                )

    def _check_grounding(
        self,
        contract: PlanContract,
        result: VerificationResult,
    ) -> None:
        """Check evidence grounding for critical steps."""
        for step in contract.steps:
            if step.is_irreversible and not step.evidence_refs:
                result.issues.append(
                    VerificationIssue(
                        category="grounding",
                        severity="error",
                        description=(
                            f"步骤 {step.step_number} ({step.action}) 是不可逆操作，"
                            "但没有证据引用"
                        ),
                        affected_step=step.step_number,
                        suggested_action="re_retrieve",
                    )
                )

        # Checkpoints should have evidence
        for cp in contract.checkpoints:
            if not cp.evidence_refs:
                result.issues.append(
                    VerificationIssue(
                        category="grounding",
                        severity="warning",
                        description=f"检查点 {cp.checkpoint_id} 没有证据引用",
                    )
                )

        for warning in contract.high_risk_warnings:
            if not warning.requires_slots:
                result.issues.append(
                    VerificationIssue(
                        category="grounding",
                        severity="warning",
                        description=(
                            f"高风险警告 {warning.label or warning.action} 没有声明所需关键条件，"
                            f"建议至少包含 {recommended_gate_slots(warning.action)}"
                        ),
                    )
                )

    def _check_mer_compliance(
        self,
        contract: PlanContract,
        mer: MER,
        result: VerificationResult,
    ) -> None:
        """Check contract against MER requirements (for evaluation only)."""
        # Check required checkpoints
        contract_cp_ids = {cp.checkpoint_id for cp in contract.checkpoints}
        for req_cp in mer.required_checkpoints:
            if req_cp.checkpoint_id not in contract_cp_ids:
                result.issues.append(
                    VerificationIssue(
                        category="grounding",
                        severity="warning",
                        description=(
                            f"MER 要求检查点 {req_cp.checkpoint_id}，"
                            "但合同中未包含"
                        ),
                    )
                )

        # Check required evidence refs
        contract_refs = set()
        for step in contract.steps:
            contract_refs.update(step.evidence_refs)
        for cp in contract.checkpoints:
            contract_refs.update(cp.evidence_refs)
        for ct in contract.contingencies:
            contract_refs.update(ct.evidence_refs)

        for ref in mer.required_evidence_refs:
            if ref not in contract_refs:
                result.issues.append(
                    VerificationIssue(
                        category="grounding",
                        severity="warning",
                        description=f"MER 要求证据引用 {ref}，但合同中未引用",
                    )
                )
