"""Executable Plan Contract — the core output artifact.

A contract contains six sections (A–F):
  A. Known context & assumptions
  B. Missing critical slots
  C. Ordered steps with parameters, timing, checkpoints, evidence
  D. High-risk warnings (irreversible transitions)
  E. Checkpoints (verifiable conditions)
  F. Contingencies (if-then recovery branches)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Assumption(BaseModel):
    """Section A: A context variable the plan conditions on."""

    slot_name: str
    value: Any = None
    confirmed: bool = True
    note: str = ""


class PlanStep(BaseModel):
    """Section C: A single ordered step in the workflow."""

    step_number: int
    action: str
    parameters: str = ""
    timing_window: str = ""
    checkpoint_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    is_irreversible: bool = False


class HighRiskWarning(BaseModel):
    """Section D: Warning for an irreversible transition."""

    label: str
    action: str
    requires_slots: list[str] = Field(default_factory=list)
    required_checkpoint: str = ""
    consequence: str = ""


class Checkpoint(BaseModel):
    """Section E: A verifiable condition before a critical transition."""

    checkpoint_id: str
    description: str
    evidence_refs: list[str] = Field(default_factory=list)


class Contingency(BaseModel):
    """Section F: An if-then recovery branch."""

    condition: str  # "IF ..."
    action: str  # "THEN ..."
    recheck_checkpoint: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class PlanContract(BaseModel):
    """The complete executable plan contract (sections A–F)."""

    # Section A: Known context & assumptions
    assumptions: list[Assumption] = Field(default_factory=list)

    # Section B: Missing critical slots
    missing_critical_slots: list[str] = Field(default_factory=list)

    # Section C: Ordered steps
    steps: list[PlanStep] = Field(default_factory=list)

    # Section D: High-risk warnings
    high_risk_warnings: list[HighRiskWarning] = Field(default_factory=list)

    # Section E: Checkpoints
    checkpoints: list[Checkpoint] = Field(default_factory=list)

    # Section F: Contingencies
    contingencies: list[Contingency] = Field(default_factory=list)

    # Metadata
    task_type: str = ""
    stage: str = ""
    stop_reason: str = ""

    def to_markdown(self) -> str:
        """Render the contract as a Markdown document."""
        lines: list[str] = []

        # Section A
        lines.append("## A. 已知条件与假设")
        if self.assumptions:
            for a in self.assumptions:
                status = "✓ 已确认" if a.confirmed else "▲ 未确认"
                note = f" — {a.note}" if a.note else ""
                lines.append(f"- **{a.slot_name}**: {a.value} [{status}]{note}")
        else:
            lines.append("- （无）")
        lines.append("")

        # Section B
        lines.append("## B. 缺失的关键变量")
        if self.missing_critical_slots:
            for slot in self.missing_critical_slots:
                lines.append(f"- ⚠ {slot}")
        else:
            lines.append("- （所有关键变量已确认）")
        lines.append("")

        # Section C
        lines.append("## C. 操作步骤")
        lines.append("")
        lines.append(
            "| # | 操作 | 参数 | 时间窗口 | 检查点 | 证据 | 不可逆 |"
        )
        lines.append("|---|------|------|----------|--------|------|--------|")
        for step in self.steps:
            irrev = "⚠ 是" if step.is_irreversible else "—"
            cp = step.checkpoint_id or "—"
            refs = ", ".join(step.evidence_refs) if step.evidence_refs else "—"
            lines.append(
                f"| {step.step_number} | {step.action} | {step.parameters} "
                f"| {step.timing_window} | {cp} | {refs} | {irrev} |"
            )
        lines.append("")

        # Section D
        lines.append("## D. 高风险警告")
        if self.high_risk_warnings:
            for w in self.high_risk_warnings:
                lines.append(f"### {w.label}")
                lines.append(f"- **操作**: {w.action}")
                lines.append(f"- **所需变量**: {', '.join(w.requires_slots)}")
                lines.append(f"- **前置检查点**: {w.required_checkpoint}")
                lines.append(f"- **失败后果**: {w.consequence}")
                lines.append("")
        else:
            lines.append("- （无高风险步骤）")
            lines.append("")

        # Section E
        lines.append("## E. 检查点")
        if self.checkpoints:
            for cp in self.checkpoints:
                refs = ", ".join(cp.evidence_refs) if cp.evidence_refs else "—"
                lines.append(f"- **{cp.checkpoint_id}**: {cp.description} [{refs}]")
        else:
            lines.append("- （无）")
        lines.append("")

        # Section F
        lines.append("## F. 应急预案")
        if self.contingencies:
            for c in self.contingencies:
                refs = ", ".join(c.evidence_refs) if c.evidence_refs else ""
                recheck = f" → 重新检查 {c.recheck_checkpoint}" if c.recheck_checkpoint else ""
                lines.append(f"- **如果** {c.condition} **→** {c.action}{recheck}")
                if refs:
                    lines.append(f"  - 证据: {refs}")
        else:
            lines.append("- （无）")
        lines.append("")

        # Metadata
        if self.stop_reason:
            lines.append(f"---\n*对话停止原因: {self.stop_reason}*")

        return "\n".join(lines)
