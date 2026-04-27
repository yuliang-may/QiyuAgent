"""Execution-state models for contract follow-through in the web product."""

from __future__ import annotations

from pydantic import BaseModel, Field


STEP_STATUSES: tuple[str, ...] = ("pending", "in_progress", "done", "blocked")
CHECKPOINT_STATUSES: tuple[str, ...] = ("pending", "confirmed", "failed")


class ExecutionStepState(BaseModel):
    step_number: int
    status: str = "pending"
    note: str = ""
    updated_at: str = ""


class ExecutionCheckpointState(BaseModel):
    checkpoint_id: str
    status: str = "pending"
    note: str = ""
    updated_at: str = ""


class ExecutionRecord(BaseModel):
    record_type: str  # step / checkpoint / system
    target_id: str
    status: str
    note: str = ""
    updated_at: str = ""

