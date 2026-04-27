"""Shared test fixtures."""

from pathlib import Path

import pytest

from lacquertutor.models.evidence import EvidenceStore
from lacquertutor.models.slots import SlotState, create_slot_state
from lacquertutor.models.task import TaskSet


def _benchmark_dir() -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent / "benchmark",
        Path(__file__).resolve().parent.parent.parent / "benchmark",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


BENCHMARK_DIR = _benchmark_dir()


@pytest.fixture
def slot_state() -> SlotState:
    return create_slot_state()


@pytest.fixture
def evidence_store() -> EvidenceStore:
    return EvidenceStore.from_json(BENCHMARK_DIR / "evidence_cards_v0.json")


@pytest.fixture
def taskset() -> TaskSet:
    return TaskSet.from_json(BENCHMARK_DIR / "taskset_v0.json")
