"""Pydantic output types for Agent structured outputs.

These models are used as `output_type` on Agents, enabling the SDK
to enforce JSON schema at the API level — no manual parsing needed.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    """Output of the intent detection agent."""

    task_type: str = Field(description="planning 或 troubleshooting")
    stage: str = Field(description="preparation/coating/curing/polishing/finishing")
    failure_mode: str | None = Field(default=None, description="故障模式标准标签，如 haze_whitening/wrinkling/persistent_tackiness，planning 任务为 null")
    normalization_note: str = Field(default="", description="感性描述→术语标签的映射说明")


class ExtractedSlots(BaseModel):
    """Output of the slot extraction agent."""

    slots: dict[str, str] = Field(
        default_factory=dict,
        description="提取到的变量名和值的映射",
    )


class VoIScores(BaseModel):
    """Output of the VoI scoring agent."""

    scores: dict[str, int] = Field(
        default_factory=dict,
        description="每个未填变量的风险分数 (0-3)",
    )
    reasons: dict[str, str] = Field(
        default_factory=dict,
        description="每个评分 >= 2 的变量的理由",
    )
    next_irreversible_action: str = Field(
        default="",
        description="下一个不可逆操作是什么",
    )
