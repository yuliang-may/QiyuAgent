"""Batch evaluation runner for benchmark experiments.

Runs all tasks × all conditions with oracle simulation,
computes metrics, and saves results.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import structlog
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from lacquertutor.agent.pipeline import LacquerTutorAgent
from lacquertutor.config import Settings
from lacquertutor.eval.conditions import CONDITIONS, get_condition
from lacquertutor.eval.metrics import TaskMetrics, compute_metrics
from lacquertutor.eval.oracle import OracleSimulator
from lacquertutor.models.evidence import EvidenceStore
from lacquertutor.models.task import BenchmarkTask, TaskSet

logger = structlog.get_logger(__name__)
console = Console()


class EvaluationRunner:
    """Runs the full evaluation benchmark."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.taskset = TaskSet.from_json(settings.taskset_path)
        self.evidence_store = EvidenceStore.from_json(settings.evidence_cards_path)

    async def run_all(
        self,
        conditions: list[str] | None = None,
        task_ids: list[str] | None = None,
        output_dir: str = "results",
        concurrency: int = 3,
    ) -> list[TaskMetrics]:
        """Run all task × condition combinations and save results."""
        cond_names = conditions or list(CONDITIONS.keys())
        tasks = (
            [self.taskset.get(tid) for tid in task_ids if self.taskset.get(tid)]
            if task_ids
            else list(self.taskset)
        )

        total = len(tasks) * len(cond_names)
        console.print(
            f"\n[bold]评估开始[/bold]: {len(tasks)} 任务 × {len(cond_names)} 条件 = {total} 组合"
        )

        all_results: list[TaskMetrics] = []
        sem = asyncio.Semaphore(concurrency)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            pbar = progress.add_task("运行中...", total=total)

            async def run_one(task: BenchmarkTask, cond_name: str) -> TaskMetrics:
                async with sem:
                    result = await self._run_single(task, cond_name)
                    progress.advance(pbar)
                    return result

            coros = [
                run_one(task, cond_name)
                for cond_name in cond_names
                for task in tasks
            ]
            all_results = await asyncio.gather(*coros, return_exceptions=True)

        # Filter out exceptions
        results: list[TaskMetrics] = []
        errors = 0
        for r in all_results:
            if isinstance(r, Exception):
                errors += 1
                logger.error("eval_task_failed", error=str(r))
            else:
                results.append(r)

        # Save results
        out_path = Path(output_dir)
        out_path.mkdir(exist_ok=True, parents=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = out_path / f"eval_{timestamp}.json"

        result_data = {
            "timestamp": timestamp,
            "conditions": cond_names,
            "task_count": len(tasks),
            "total_runs": len(results),
            "errors": errors,
            "results": [r.model_dump() for r in results],
        }
        result_file.write_text(
            json.dumps(result_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        console.print(f"\n[green]✓ 评估完成[/green]: {len(results)} 成功, {errors} 失败")
        console.print(f"[dim]结果保存到: {result_file}[/dim]")

        # Print summary table
        self._print_summary(results, cond_names)

        return results

    async def _run_single(
        self, task: BenchmarkTask, cond_name: str
    ) -> TaskMetrics:
        """Run a single task under a single condition."""
        cond = get_condition(cond_name)
        agent = LacquerTutorAgent(self.settings, self.evidence_store)
        oracle = OracleSimulator(task.hidden_slot_values)

        try:
            contract, state = await agent.run(
                query=task.prompt_en,
                answer_fn=oracle.answer_question,
                enable_dialogue=cond.enable_dialogue,
                enable_verifier=cond.enable_verifier,
                slot_selection=cond.slot_selection,
                enable_retrieval=cond.enable_retrieval,
            )

            metrics = compute_metrics(task, contract, state)
            metrics.condition = cond_name
            return metrics

        finally:
            await agent.close()

    @staticmethod
    def _print_summary(results: list[TaskMetrics], conditions: list[str]) -> None:
        """Print a summary table of metrics by condition."""
        from rich.table import Table

        table = Table(
            title="评估结果摘要", show_header=True, header_style="bold"
        )
        table.add_column("条件", style="bold")
        table.add_column("M1 门控↑", justify="right")
        table.add_column("M2 缺失↓", justify="right")
        table.add_column("M3a CP↑", justify="right")
        table.add_column("M3b CT↑", justify="right")
        table.add_column("M4a 证据↑", justify="right")
        table.add_column("M6 问题数", justify="right")
        table.add_column("M7 合规", justify="right")

        for cond in conditions:
            cond_results = [r for r in results if r.condition == cond]
            if not cond_results:
                continue

            n = len(cond_results)
            m1 = sum(r.m1_gate_compliance for r in cond_results) / n
            m2 = sum(r.m2_missing_slot_errors for r in cond_results) / n
            m3a = sum(r.m3a_checkpoint_coverage for r in cond_results) / n
            m3b = sum(r.m3b_contingency_coverage for r in cond_results) / n
            m4a = sum(r.m4a_evidence_coverage for r in cond_results) / n
            m6 = sum(r.m6_questions_asked for r in cond_results) / n
            m7 = sum(1 for r in cond_results if r.m7_template_compliance) / n

            table.add_row(
                cond,
                f"{m1:.2f}",
                f"{m2:.1f}",
                f"{m3a:.2f}",
                f"{m3b:.2f}",
                f"{m4a:.2f}",
                f"{m6:.1f}",
                f"{m7:.0%}",
            )

        console.print(table)
