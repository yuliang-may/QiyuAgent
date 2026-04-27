"""Post-processing and heuristics for contract quality.

Normalizes planner output into a safer, more consistent contract:
- rebuilds assumptions from slot state
- infers irreversible steps from action text
- ensures critical steps have checkpoints, warnings, contingencies, and evidence
"""

from __future__ import annotations

import re
from typing import Iterable

from lacquertutor.models.contract import (
    Assumption,
    Checkpoint,
    Contingency,
    HighRiskWarning,
    PlanContract,
    PlanStep,
)
from lacquertutor.models.evidence import EvidenceCard
from lacquertutor.models.slots import HARD_GATE_SLOTS, SlotState
from lacquertutor.models.task import MER

CRITICAL_ACTION_PATTERNS = [
    r"\bapply\b",
    r"\bcoat\b",
    r"\brecoat\b",
    r"\bseal(?:ing)?\b",
    r"\bprime(?:r|ing)?\b",
    r"\bbuild coat\b",
    r"\bfinish(?:ing)? coat\b",
    r"\btop coat\b",
    r"涂",
    r"刷漆",
    r"上漆",
    r"重涂",
    r"封底",
    r"底漆",
    r"罩面",
]


def _clean_text(value: str | None, fallback: str = "") -> str:
    text = (value or "").strip()
    return text if text else fallback


def _unique(seq: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def is_critical_action(action: str) -> bool:
    text = action.lower().strip()
    return any(re.search(pattern, text) for pattern in CRITICAL_ACTION_PATTERNS)


def recommended_gate_slots(action: str) -> list[str]:
    text = action.lower()
    if any(k in text for k in ["seal", "prime", "封底", "底漆"]):
        return ["substrate_condition", "substrate_material", "lacquer_system"]
    if any(k in text for k in ["recoat", "next coat", "重涂", "build coat", "second coat"]):
        return ["time_since_last_coat_h", "coat_thickness", "environment_humidity_pct"]
    if any(k in text for k in ["apply", "coat", "涂", "上漆", "罩面"]):
        return [
            "lacquer_system",
            "environment_temperature_c",
            "environment_humidity_pct",
            "curing_method",
            "ppe_level",
        ]
    return ["lacquer_system", "environment_humidity_pct", "ppe_level"]


class ContractEnricher:
    """Repairs under-specified planner output into a stricter contract."""

    def enrich(
        self,
        contract: PlanContract,
        slot_state: SlotState,
        evidence_cards: list[EvidenceCard],
        *,
        task_type: str = "",
        stage: str = "",
        failure_mode: str | None = None,
        stop_reason: str = "",
        mer: MER | None = None,
    ) -> PlanContract:
        evidence_pool = [card.evidence_id for card in evidence_cards]
        missing_critical_slots = self._build_missing_critical_slots(contract, slot_state, mer)
        assumptions = self._build_assumptions(contract, slot_state, missing_critical_slots)
        steps = self._build_steps(contract, evidence_pool)
        checkpoints = self._build_checkpoints(contract, steps, evidence_pool)
        warnings = self._build_warnings(contract, steps, checkpoints)
        contingencies = self._build_contingencies(
            contract, steps, checkpoints, evidence_pool, failure_mode
        )

        return PlanContract(
            assumptions=assumptions,
            missing_critical_slots=missing_critical_slots,
            steps=steps,
            high_risk_warnings=warnings,
            checkpoints=checkpoints,
            contingencies=contingencies,
            task_type=task_type or contract.task_type,
            stage=stage or contract.stage,
            stop_reason=stop_reason or contract.stop_reason,
        )

    def _build_missing_critical_slots(
        self,
        contract: PlanContract,
        slot_state: SlotState,
        mer: MER | None,
    ) -> list[str]:
        mer_required = mer.required_slots if mer else []
        still_missing = [
            slot for slot in mer_required
            if slot not in slot_state.filled_dict and slot in HARD_GATE_SLOTS
        ]
        return sorted(
            _unique(contract.missing_critical_slots + slot_state.unfilled_hard_gates + still_missing)
        )

    def _build_assumptions(
        self,
        contract: PlanContract,
        slot_state: SlotState,
        missing_critical_slots: list[str],
    ) -> list[Assumption]:
        existing_notes = {a.slot_name: a.note for a in contract.assumptions if a.note}
        assumptions: list[Assumption] = []

        for slot_name, slot_value in slot_state.filled.items():
            assumptions.append(
                Assumption(
                    slot_name=slot_name,
                    value=slot_value.value,
                    confirmed=True,
                    note=existing_notes.get(slot_name, "用户已提供该条件"),
                )
            )

        for slot_name in missing_critical_slots:
            assumptions.append(
                Assumption(
                    slot_name=slot_name,
                    value=None,
                    confirmed=False,
                    note=existing_notes.get(slot_name, "关键条件缺失，需在进入不可逆步骤前确认"),
                )
            )

        for assumption in contract.assumptions:
            if assumption.slot_name in {a.slot_name for a in assumptions}:
                continue
            if assumption.confirmed and assumption.value in (None, "", "None"):
                continue
            assumptions.append(assumption)

        return assumptions

    def _build_steps(
        self,
        contract: PlanContract,
        evidence_pool: list[str],
    ) -> list[PlanStep]:
        steps: list[PlanStep] = []
        next_cp = 1
        used_cp_ids: set[str] = set()

        for idx, step in enumerate(contract.steps, start=1):
            action = _clean_text(step.action, f"步骤 {idx}")
            parameters = _clean_text(step.parameters, "按当前材料条件执行，必要时先做小样")
            timing = _clean_text(step.timing_window, "遵循当前阶段要求，进入下一步前确认检查点")
            critical = bool(step.is_irreversible or is_critical_action(action))

            evidence_refs = [ref for ref in step.evidence_refs if ref in evidence_pool]
            if not evidence_refs and evidence_pool:
                evidence_refs = evidence_pool[: min(2, len(evidence_pool))]

            checkpoint_id = step.checkpoint_id.strip() if step.checkpoint_id else None
            if critical and not checkpoint_id:
                while f"CP-{next_cp:02d}" in used_cp_ids:
                    next_cp += 1
                checkpoint_id = f"CP-{next_cp:02d}"
                used_cp_ids.add(checkpoint_id)
                next_cp += 1
            elif checkpoint_id:
                used_cp_ids.add(checkpoint_id)

            steps.append(
                PlanStep(
                    step_number=idx,
                    action=action,
                    parameters=parameters,
                    timing_window=timing,
                    checkpoint_id=checkpoint_id,
                    evidence_refs=evidence_refs,
                    is_irreversible=critical,
                )
            )

        return steps

    def _build_checkpoints(
        self,
        contract: PlanContract,
        steps: list[PlanStep],
        evidence_pool: list[str],
    ) -> list[Checkpoint]:
        existing = {cp.checkpoint_id: cp for cp in contract.checkpoints}
        checkpoints: list[Checkpoint] = []

        for step in steps:
            if not step.checkpoint_id:
                continue
            existing_cp = existing.get(step.checkpoint_id)
            description = (
                _clean_text(existing_cp.description)
                if existing_cp
                else f"进入“{step.action}”前，确认材料、环境和表面状态满足要求。"
            )
            refs = existing_cp.evidence_refs if existing_cp else []
            refs = [ref for ref in refs if ref in evidence_pool] or step.evidence_refs[:]
            if not refs and evidence_pool:
                refs = evidence_pool[:1]

            checkpoints.append(
                Checkpoint(
                    checkpoint_id=step.checkpoint_id,
                    description=description,
                    evidence_refs=refs,
                )
            )

        for cp in contract.checkpoints:
            if cp.checkpoint_id not in {item.checkpoint_id for item in checkpoints}:
                refs = [ref for ref in cp.evidence_refs if ref in evidence_pool]
                checkpoints.append(
                    Checkpoint(
                        checkpoint_id=cp.checkpoint_id,
                        description=_clean_text(cp.description, "补充检查点"),
                        evidence_refs=refs or evidence_pool[:1],
                    )
                )

        return checkpoints

    def _build_warnings(
        self,
        contract: PlanContract,
        steps: list[PlanStep],
        checkpoints: list[Checkpoint],
    ) -> list[HighRiskWarning]:
        existing = {warning.action: warning for warning in contract.high_risk_warnings}
        checkpoint_ids = {cp.checkpoint_id for cp in checkpoints}
        warnings: list[HighRiskWarning] = []

        for step in steps:
            if not step.is_irreversible:
                continue
            existing_warning = existing.get(step.action)
            required_checkpoint = step.checkpoint_id if step.checkpoint_id in checkpoint_ids else ""
            warnings.append(
                HighRiskWarning(
                    label=_clean_text(
                        existing_warning.label if existing_warning else "",
                        f"步骤 {step.step_number} 高风险",
                    ),
                    action=step.action,
                    requires_slots=(
                        existing_warning.requires_slots
                        if existing_warning and existing_warning.requires_slots
                        else recommended_gate_slots(step.action)
                    ),
                    required_checkpoint=required_checkpoint,
                    consequence=_clean_text(
                        existing_warning.consequence if existing_warning else "",
                        "若在条件未确认时执行，可能造成返工、附着失败或不可逆表面缺陷。",
                    ),
                )
            )

        return warnings

    def _build_contingencies(
        self,
        contract: PlanContract,
        steps: list[PlanStep],
        checkpoints: list[Checkpoint],
        evidence_pool: list[str],
        failure_mode: str | None,
    ) -> list[Contingency]:
        contingencies: list[Contingency] = []
        checkpoint_ids = {cp.checkpoint_id for cp in checkpoints}

        for contingency in contract.contingencies:
            refs = [ref for ref in contingency.evidence_refs if ref in evidence_pool]
            contingencies.append(
                Contingency(
                    condition=_clean_text(contingency.condition, "出现异常"),
                    action=_clean_text(contingency.action, "停止进入下一步并重新检查当前状态"),
                    recheck_checkpoint=(
                        contingency.recheck_checkpoint
                        if contingency.recheck_checkpoint in checkpoint_ids
                        else ""
                    ),
                    evidence_refs=refs or evidence_pool[:1],
                )
            )

        if contingencies:
            return contingencies

        generic_condition = (
            f"出现与 {failure_mode} 相关的表面异常"
            if failure_mode else
            "出现发白、起皱、流挂、持续发黏或附着异常"
        )

        for step in steps:
            if not step.is_irreversible:
                continue
            contingencies.append(
                Contingency(
                    condition=f"{generic_condition}（发生在“{step.action}”后）",
                    action="停止进入下一步，保持当前层状态，检查环境与固化条件，必要时做小范围修正后再继续。",
                    recheck_checkpoint=step.checkpoint_id or "",
                    evidence_refs=step.evidence_refs[:1] or evidence_pool[:1],
                )
            )

        return contingencies
