"""Typer CLI application with commands for interactive, single-run, and eval modes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from lacquertutor.config import Settings

app = typer.Typer(
    name="lacquertutor",
    help="LacquerTutor — 漆艺工艺智能助手",
    no_args_is_help=True,
)

console = Console()


@app.command()
def chat(
    mode: str = typer.Option(
        "agent",
        "--mode",
        help="会话模式: workflow=保守工作流, agent=智能体补问",
    ),
) -> None:
    """交互对话模式 — 与 LacquerTutor 进行漆艺咨询。"""
    from lacquertutor.cli.interactive import run_interactive

    settings = Settings()

    if not settings.llm_api_key:
        console.print(
            "[red]错误: 未设置 LACQUERTUTOR_LLM_API_KEY[/red]\n"
            "请复制 .env.example 为 .env 并填入 API Key"
        )
        raise typer.Exit(1)

    asyncio.run(run_interactive(settings, mode=mode))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(8000, "--port", help="监听端口"),
) -> None:
    """启动最小 Web 产品工作台。"""
    import uvicorn

    from lacquertutor.web.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


@app.command()
def run(
    task: str = typer.Option(..., "--task", "-t", help="任务 ID (如 P01, T01)"),
    condition: str = typer.Option(
        "S2", "--condition", "-c", help="实验条件 (B1/B2-random/B2-prompt/B2-VoI/S2)"
    ),
    output_dir: str = typer.Option("output", "--output", "-o", help="输出目录"),
) -> None:
    """单任务运行 — 用 oracle 模拟运行指定任务。"""
    settings = Settings()

    if not settings.llm_api_key:
        console.print("[red]错误: 未设置 LACQUERTUTOR_LLM_API_KEY[/red]")
        raise typer.Exit(1)

    asyncio.run(_run_single(settings, task, condition, output_dir))


async def _run_single(
    settings: Settings, task_id: str, condition: str, output_dir: str
) -> None:
    from lacquertutor.agent.pipeline import LacquerTutorAgent
    from lacquertutor.cli.display import render_contract, render_slot_panel
    from lacquertutor.eval.conditions import get_condition
    from lacquertutor.eval.oracle import OracleSimulator
    from lacquertutor.models.evidence import EvidenceStore
    from lacquertutor.models.task import TaskSet

    taskset = TaskSet.from_json(settings.taskset_path)
    task = taskset.get(task_id)
    if not task:
        console.print(f"[red]任务 {task_id} 不存在[/red]")
        return

    cond = get_condition(condition)
    evidence_store = EvidenceStore.from_json(settings.evidence_cards_path)
    agent = LacquerTutorAgent(settings, evidence_store)
    oracle = OracleSimulator(task.hidden_slot_values)

    try:
        contract, state = await agent.run(
            query=task.prompt_en,
            answer_fn=oracle.answer_question,
            enable_dialogue=cond.enable_dialogue,
            enable_verifier=cond.enable_verifier,
            slot_selection=cond.slot_selection,
            mer=task.mer,
        )

        console.print(render_slot_panel(state.slot_state))
        console.print(render_contract(contract))

        # Save
        out = Path(output_dir)
        out.mkdir(exist_ok=True, parents=True)
        fname = f"{task_id}_{condition}"

        (out / f"{fname}_contract.json").write_text(
            contract.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out / f"{fname}_state.json").write_text(
            json.dumps(state.to_audit_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        console.print(f"\n[green]✓ 输出已保存到 {out}/{fname}_*[/green]")

    finally:
        await agent.close()


@app.command(name="eval")
def run_eval(
    conditions: str = typer.Option(
        "B1,B2-random,B2-VoI,S2",
        "--conditions",
        help="逗号分隔的实验条件列表",
    ),
    tasks: Optional[str] = typer.Option(
        None, "--tasks", help="逗号分隔的任务 ID (默认全部)"
    ),
    all_tasks: bool = typer.Option(False, "--all", help="运行全部 42 个任务"),
    output_dir: str = typer.Option("results", "--output", "-o", help="输出目录"),
    concurrency: int = typer.Option(3, "--concurrency", help="并发数"),
) -> None:
    """批量评估 — 运行基准测试实验。"""
    settings = Settings()

    if not settings.llm_api_key:
        console.print("[red]错误: 未设置 LACQUERTUTOR_LLM_API_KEY[/red]")
        raise typer.Exit(1)

    cond_list = [c.strip() for c in conditions.split(",")]
    task_list = [t.strip() for t in tasks.split(",")] if tasks else None

    asyncio.run(
        _run_eval(settings, cond_list, task_list, all_tasks, output_dir, concurrency)
    )


async def _run_eval(
    settings: Settings,
    conditions: list[str],
    task_ids: list[str] | None,
    all_tasks: bool,
    output_dir: str,
    concurrency: int,
) -> None:
    from lacquertutor.eval.runner import EvaluationRunner

    runner = EvaluationRunner(settings)
    await runner.run_all(
        conditions=conditions,
        task_ids=task_ids,
        output_dir=output_dir,
        concurrency=concurrency,
    )


@app.command()
def info(
    task: str = typer.Option(..., "--task", "-t", help="任务 ID"),
) -> None:
    """查看任务详情 — 显示任务描述和 MER 要求。"""
    from rich.table import Table

    settings = Settings()
    from lacquertutor.models.task import TaskSet

    taskset = TaskSet.from_json(settings.taskset_path)
    t = taskset.get(task)
    if not t:
        console.print(f"[red]任务 {task} 不存在[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]{t.task_id}[/bold] — {t.task_type} / {t.stage}")
    if t.failure_mode:
        console.print(f"故障模式: {t.failure_mode}")
    console.print(f"\n[cyan]提示:[/cyan] {t.prompt_en}\n")

    console.print("[bold]MER 要求:[/bold]")
    console.print(f"  必需变量: {t.mer.required_slots}")
    console.print(f"  不可逆门控: {len(t.mer.irreversible_gates)}")
    for gate in t.mer.irreversible_gates:
        console.print(f"    - {gate.action} (需要: {gate.requires_slots})")
    console.print(f"  必需检查点: {len(t.mer.required_checkpoints)}")
    console.print(f"  必需应急预案: {len(t.mer.required_contingencies)}")
    console.print(f"  必需证据引用: {t.mer.required_evidence_refs}")
    console.print(f"\n  隐藏变量数: {len(t.hidden_slot_values)}")


@app.command()
def index() -> None:
    """构建知识库索引 — 将证据卡嵌入到 Qdrant 向量数据库。"""
    settings = Settings()

    if not settings.llm_api_key:
        console.print("[red]错误: 未设置 LACQUERTUTOR_LLM_API_KEY[/red]")
        raise typer.Exit(1)

    asyncio.run(_run_index(settings))


async def _run_index(settings: Settings) -> None:
    from pathlib import Path

    from openai import AsyncOpenAI

    from lacquertutor.models.evidence import EvidenceStore
    from lacquertutor.retrieval.embedder import Embedder
    from lacquertutor.retrieval.indexer import QdrantIndexer
    from lacquertutor.web.teaching import TeachingAssistantService

    evidence_store = EvidenceStore.from_json(settings.evidence_cards_path)
    console.print(f"加载了 {len(evidence_store)} 张证据卡")

    # Check for KB segments
    kb_dir = Path(__file__).resolve().parent.parent.parent.parent / "kb"
    if kb_dir.exists():
        kb_files = list(kb_dir.glob("*_segments.json"))
        console.print(f"找到 {len(kb_files)} 个知识库文件: {[f.name for f in kb_files]}")
    else:
        kb_dir = None
        console.print("[yellow]未找到 kb/ 目录，仅索引证据卡[/yellow]")

    # Create embedding client
    client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
    embedder = Embedder(client, model=settings.embedding_model)

    # Create Qdrant client
    try:
        from qdrant_client import QdrantClient

        if settings.qdrant_url:
            qdrant = QdrantClient(url=settings.qdrant_url)
            console.print(f"连接到 Qdrant: {settings.qdrant_url}")
        else:
            qdrant = QdrantClient(":memory:")
            console.print("[yellow]使用内存模式 Qdrant（数据不持久化）[/yellow]")
    except ImportError:
        console.print(
            "[red]错误: 需要安装 qdrant-client[/red]\n"
            "运行: pip install lacquertutor[retrieval]"
        )
        raise typer.Exit(1)

    indexer = QdrantIndexer(embedder, qdrant, settings.qdrant_collection)

    with console.status("正在嵌入和索引..."):
        counts = await indexer.index_full(evidence_store, kb_dir)
        teaching_service = TeachingAssistantService.from_repo(settings)
        await teaching_service.prepare_rag(force=True)

    for source, count in counts.items():
        console.print(f"  {source}: {count} 条")
    total = sum(counts.values())
    console.print(f"[green]✓ 总计索引 {total} 条到 '{settings.qdrant_collection}'[/green]")
    console.print(f"[green]✓ 已准备通用聊天 RAG 索引 '{settings.rag_collection}'[/green]")
