"""Rich-based display renderers for the CLI.

Provides formatted panels for slot state, evidence cards,
VoI scoring logs, and plan contracts.
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.markdown import Markdown

# Force UTF-8 on Windows to avoid GBK encoding errors with Rich
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from rich.panel import Panel
from rich.table import Table

from lacquertutor.models.contract import PlanContract
from lacquertutor.models.evidence import EvidenceCard
from lacquertutor.models.slots import HARD_GATE_SLOTS, SlotState
from lacquertutor.modules.verifier import VerificationResult
from lacquertutor.modules.voi_scorer import VoIScoringRecord

console = Console()


def render_slot_panel(slot_state: SlotState) -> Panel:
    """Render the current slot state as a rich panel."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("变量", style="bold")
    table.add_column("值")
    table.add_column("状态")
    table.add_column("门控")

    for name, slot_def in slot_state.schema_defs.items():
        is_hard = name in HARD_GATE_SLOTS
        gate = "[red]硬门控[/red]" if is_hard else "[dim]软[/dim]"

        if name in slot_state.filled:
            sv = slot_state.filled[name]
            status = "[green]✓ 已确认[/green]" if sv.confirmed else "[yellow]▲ 假设[/yellow]"
            value = str(sv.value)
        else:
            status = "[red]✗ 未填[/red]"
            value = "—"

        table.add_row(slot_def.label_zh, value, status, gate)

    filled = len(slot_state.filled)
    total = len(slot_state.schema_defs)
    title = f"变量状态 ({filled}/{total})"

    return Panel(table, title=title, border_style="cyan")


def render_evidence_panel(evidence: list[EvidenceCard]) -> Panel:
    """Render retrieved evidence cards."""
    table = Table(show_header=True, header_style="bold green", expand=True)
    table.add_column("ID", style="bold", width=12)
    table.add_column("阶段", width=10)
    table.add_column("摘要")

    for card in evidence:
        fm = f"/{card.failure_mode}" if card.failure_mode else ""
        table.add_row(
            card.evidence_id,
            f"{card.stage}{fm}",
            card.summary_en[:80] + "..." if len(card.summary_en) > 80 else card.summary_en,
        )

    return Panel(table, title=f"证据卡 ({len(evidence)})", border_style="green")


def render_contract(contract: PlanContract) -> Panel:
    """Render a plan contract as a rich Markdown panel."""
    md = Markdown(contract.to_markdown())
    return Panel(md, title="可执行计划合同", border_style="blue", padding=(1, 2))


def render_voi_log(record: VoIScoringRecord) -> Panel:
    """Render a VoI scoring record."""
    table = Table(show_header=True, header_style="bold yellow", expand=True)
    table.add_column("变量", style="bold")
    table.add_column("原始分", justify="center")
    table.add_column("调整分", justify="center")

    for slot, adj_score in record.ranked_list[:6]:  # Show top 6
        raw = record.raw_scores.get(slot, "?")
        adj_style = "bold red" if adj_score >= 3 else "yellow" if adj_score >= 2 else "dim"
        table.add_row(slot, str(raw), f"[{adj_style}]{adj_score}[/{adj_style}]")

    decision = "🔍 继续提问" if record.decision == "ask" else "✅ 开始生成计划"
    selected = f"选中: {record.selected_slot}" if record.selected_slot else ""

    return Panel(
        table,
        title=f"VoI 评分 (第{record.turn + 1}轮) — {decision} {selected}",
        border_style="yellow",
    )


def render_verification(result: VerificationResult) -> Panel:
    """Render verification results."""
    if result.passed:
        content = "[green]✓ 合同验证通过[/green]"
    else:
        lines = ["[red]✗ 合同验证未通过[/red]\n"]
        for issue in result.issues:
            icon = "❌" if issue.severity == "error" else "⚠️"
            lines.append(f"{icon} [{issue.category}] {issue.description}")
        content = "\n".join(lines)

    return Panel(content, title="验证结果", border_style="red" if not result.passed else "green")


def print_welcome() -> None:
    """Print the welcome banner."""
    console.print()
    console.print(
        Panel(
            "[bold]LacquerTutor[/bold] — 漆艺工艺智能助手\n"
            "输入您的漆艺问题，系统将通过对话收集必要信息，\n"
            "生成包含安全检查点和应急预案的可执行计划合同。\n\n"
            "[dim]输入 quit 或 exit 退出[/dim]",
            border_style="bright_blue",
            title="🎨 LacquerTutor v0.1",
        )
    )
    console.print()
