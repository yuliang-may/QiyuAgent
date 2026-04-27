"""Interactive CLI conversation loop for the session-based agent pipeline."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from lacquertutor.agent.pipeline import LacquerTutorAgent
from lacquertutor.agent.session_modes import (
    get_session_mode_options,
    normalize_session_mode,
)
from lacquertutor.cli.display import (
    print_welcome,
    render_contract,
    render_evidence_panel,
    render_slot_panel,
    render_voi_log,
)
from lacquertutor.config import Settings
from lacquertutor.models.evidence import EvidenceStore

_console = Console()


async def _interactive_answer(question: str, slot_name: str) -> str:
    """Prompt the user for an answer to a question."""
    answer = Prompt.ask("[bold]您的回答[/bold]")
    return answer


async def run_interactive(settings: Settings, mode: str = "agent") -> None:
    """Run an interactive conversation session."""
    print_welcome()
    session_mode = normalize_session_mode(mode)
    _console.print(f"[dim]当前会话模式: {session_mode}[/dim]")
    _console.print()

    evidence_store = EvidenceStore.from_json(settings.evidence_cards_path)
    agent = LacquerTutorAgent(settings, evidence_store)

    try:
        query = Prompt.ask("[bold]请描述您的漆艺问题或需求[/bold]")

        if query.lower() in ("quit", "exit", "q"):
            _console.print("[dim]再见！[/dim]")
            return

        _console.print()
        _console.print("[dim]Agent 正在思考...[/dim]")

        ctx = await agent.start_session(query)
        ctx.session_mode = session_mode

        while True:
            result = await agent.advance(ctx, **get_session_mode_options(ctx.session_mode))

            if result["type"] == "contract":
                contract = result["contract"]
                break

            _console.print()
            _console.print(f"[bold cyan]LacquerTutor:[/bold cyan] {result['text']}")
            if result.get("priority"):
                _console.print(
                    f"[dim]模式: {ctx.session_mode} | 变量: {result['slot_name']} | 优先级: {result['priority']}[/dim]"
                )

            answer = await _interactive_answer(result["text"], result["slot_name"])
            if answer.lower() in ("quit", "exit", "q"):
                _console.print("[dim]会话已中止。[/dim]")
                return

            await agent.submit_answer(ctx, answer)

        # Display results
        _console.print()
        _console.print(render_slot_panel(ctx.slot_state))
        _console.print()

        if ctx.retrieved_evidence:
            _console.print(render_evidence_panel(ctx.retrieved_evidence))
            _console.print()

        for record in ctx.voi_logs:
            _console.print(render_voi_log(record))

        _console.print()
        _console.print(render_contract(contract))

        # Save outputs
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        json_path = output_dir / "contract.json"
        json_path.write_text(
            contract.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _console.print(f"\n[dim]合同 JSON 已保存到: {json_path}[/dim]")

        md_path = output_dir / "contract.md"
        md_path.write_text(contract.to_markdown(), encoding="utf-8")
        _console.print(f"[dim]合同 Markdown 已保存到: {md_path}[/dim]")

        audit_path = output_dir / "audit_log.json"
        audit_path.write_text(
            ctx.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _console.print(f"[dim]审计日志已保存到: {audit_path}[/dim]")

    finally:
        await agent.close()
