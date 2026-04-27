"""Benchmark task definitions with MER (Minimum Executable Requirements).

Loads taskset_v0.json which contains 42 evaluation tasks (21 planning,
21 troubleshooting) with oracle ground truth values and MER checklists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class IrreversibleGate(BaseModel):
    """An irreversible transition that requires gating slots."""

    action: str
    requires_slots: list[str] = Field(default_factory=list)
    required_checkpoint: str = ""
    consequence: str = ""


class RequiredCheckpoint(BaseModel):
    """A checkpoint required by the MER."""

    checkpoint_id: str
    description: str = ""


class RequiredContingency(BaseModel):
    """A contingency required by the MER."""

    condition: str = ""  # "if" clause
    action: str = ""  # "then" clause
    recheck: str = ""  # checkpoint to recheck


class MER(BaseModel):
    """Minimum Executable Requirements for a benchmark task.

    Defines the safety bar — not a single correct recipe, but the
    minimum set of slots, gates, checkpoints, contingencies, and
    evidence that a safe contract must include.
    """

    required_slots: list[str] = Field(default_factory=list)
    irreversible_gates: list[IrreversibleGate] = Field(default_factory=list)
    required_checkpoints: list[RequiredCheckpoint] = Field(default_factory=list)
    required_contingencies: list[RequiredContingency] = Field(default_factory=list)
    required_evidence_refs: list[str] = Field(default_factory=list)


class BenchmarkTask(BaseModel):
    """A single evaluation task from the benchmark."""

    task_id: str
    task_type: str  # "planning" or "troubleshooting"
    stage: str
    failure_mode: str | None = None
    prompt_en: str = ""
    hidden_slot_values: dict[str, Any] = Field(default_factory=dict)
    mer: MER = Field(default_factory=MER)


class TaskSet:
    """Loads and indexes the full benchmark task set."""

    def __init__(
        self,
        tasks: list[BenchmarkTask],
        slot_schema: dict[str, Any] | None = None,
    ) -> None:
        self.tasks = tasks
        self.slot_schema_raw = slot_schema or {}
        self._by_id: dict[str, BenchmarkTask] = {t.task_id: t for t in tasks}

    def get(self, task_id: str) -> BenchmarkTask | None:
        return self._by_id.get(task_id)

    @property
    def planning_tasks(self) -> list[BenchmarkTask]:
        return [t for t in self.tasks if t.task_type == "planning"]

    @property
    def troubleshooting_tasks(self) -> list[BenchmarkTask]:
        return [t for t in self.tasks if t.task_type == "troubleshooting"]

    @classmethod
    def from_json(cls, path: str | Path) -> TaskSet:
        """Load task set from benchmark JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        tasks = [BenchmarkTask.model_validate(t) for t in data["tasks"]]
        return cls(tasks=tasks, slot_schema=data.get("slot_schema"))

    def __len__(self) -> int:
        return len(self.tasks)

    def __iter__(self):
        return iter(self.tasks)
