"""Slot schema and state tracking for the 18-variable proactive dialogue system.

The 18 slots are derived from the paper's trace-analysis taxonomy (Table 1)
and the benchmark's slot_schema in taskset_v0.json. Slot names match the
benchmark exactly so that evaluation metrics (M1-M7) compute correctly.

Hard-gate slots (8) directly gate irreversible steps and MUST be confirmed
before crossing irreversible transitions. The VoI formula r̃(s) = max(r(s), 2·g(s))
ensures they never drop below score 2 near irreversible boundaries.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GateLevel(str, Enum):
    """Whether a slot gates an irreversible step."""

    HARD = "hard"
    SOFT = "soft"


class SlotDefinition(BaseModel):
    """Schema definition for a single slot."""

    name: str
    label_zh: str
    label_en: str
    gate_level: GateLevel
    category: str = ""

    @property
    def is_hard_gate(self) -> bool:
        return self.gate_level == GateLevel.HARD


class SlotValue(BaseModel):
    """A filled slot value with provenance."""

    slot_name: str
    value: Any
    source: str = "user"  # "user", "oracle", "assumption"
    confirmed: bool = False
    turn_filled: int = 0


class SlotState(BaseModel):
    """Tracks the current state of all 18 slots across dialogue turns."""

    schema_defs: dict[str, SlotDefinition] = Field(default_factory=dict)
    filled: dict[str, SlotValue] = Field(default_factory=dict)

    @property
    def all_slot_names(self) -> list[str]:
        return list(self.schema_defs.keys())

    @property
    def unfilled(self) -> list[str]:
        return [s for s in self.schema_defs if s not in self.filled]

    @property
    def unfilled_hard_gates(self) -> list[str]:
        return [
            s
            for s in self.schema_defs
            if s not in self.filled and self.schema_defs[s].is_hard_gate
        ]

    @property
    def all_hard_gates_filled(self) -> bool:
        return len(self.unfilled_hard_gates) == 0

    @property
    def filled_dict(self) -> dict[str, Any]:
        """Slot name → value mapping for filled slots."""
        return {k: v.value for k, v in self.filled.items()}

    def fill(
        self,
        name: str,
        value: Any,
        source: str = "user",
        confirmed: bool = True,
        turn: int = 0,
    ) -> None:
        if name in self.schema_defs and value is not None:
            self.filled[name] = SlotValue(
                slot_name=name,
                value=value,
                source=source,
                confirmed=confirmed,
                turn_filled=turn,
            )

    def is_filled(self, name: str) -> bool:
        return name in self.filled

    def reset(self) -> None:
        self.filled.clear()


# ── Canonical 18-slot schema (matches benchmark/taskset_v0.json) ─────

SLOT_DEFINITIONS: list[SlotDefinition] = [
    # ── Materials ──
    SlotDefinition(
        name="lacquer_system",
        label_zh="漆种/体系",
        label_en="Lacquer system/type (drives curing, compatibility, safety)",
        gate_level=GateLevel.HARD,
        category="materials",
    ),
    SlotDefinition(
        name="substrate_material",
        label_zh="基底材料",
        label_en="Primary substrate material (wood/metal/ceramic/plastic/composite)",
        gate_level=GateLevel.HARD,
        category="materials",
    ),
    SlotDefinition(
        name="substrate_condition",
        label_zh="基底状态",
        label_en="Substrate condition (raw/previously_finished)",
        gate_level=GateLevel.HARD,
        category="materials",
    ),
    SlotDefinition(
        name="dilution_ratio_pct",
        label_zh="稀释比例",
        label_en="Approximate thinner/dilution percentage (%)",
        gate_level=GateLevel.SOFT,
        category="materials",
    ),
    # ── Environment ──
    SlotDefinition(
        name="environment_temperature_c",
        label_zh="环境温度",
        label_en="Ambient temperature (°C)",
        gate_level=GateLevel.HARD,
        category="environment",
    ),
    SlotDefinition(
        name="environment_humidity_pct",
        label_zh="环境湿度",
        label_en="Relative humidity (%RH)",
        gate_level=GateLevel.HARD,
        category="environment",
    ),
    SlotDefinition(
        name="ventilation_quality",
        label_zh="通风条件",
        label_en="Ventilation quality (poor/limited/good)",
        gate_level=GateLevel.SOFT,
        category="environment",
    ),
    SlotDefinition(
        name="dust_control_level",
        label_zh="防尘等级",
        label_en="Dust control level (low/medium/high)",
        gate_level=GateLevel.SOFT,
        category="environment",
    ),
    # ── Timing / Curing ──
    SlotDefinition(
        name="curing_method",
        label_zh="固化方式",
        label_en="Curing method (air/humidity_box/cabinet)",
        gate_level=GateLevel.HARD,
        category="timing",
    ),
    SlotDefinition(
        name="time_since_last_coat_h",
        label_zh="距上次涂装时间",
        label_en="Hours since the last coat was applied",
        gate_level=GateLevel.HARD,
        category="timing",
    ),
    SlotDefinition(
        name="available_time_days",
        label_zh="可用时间",
        label_en="Time budget for the whole workflow (days)",
        gate_level=GateLevel.SOFT,
        category="timing",
    ),
    # ── Process / Application ──
    SlotDefinition(
        name="coat_thickness",
        label_zh="涂层厚度",
        label_en="Qualitative coat thickness (thin/medium/thick)",
        gate_level=GateLevel.SOFT,
        category="process",
    ),
    SlotDefinition(
        name="application_tool",
        label_zh="涂装工具",
        label_en="Primary application tool (brush/pad/spray)",
        gate_level=GateLevel.SOFT,
        category="process",
    ),
    SlotDefinition(
        name="layer_count_target",
        label_zh="目标层数",
        label_en="Target number of coats/layers",
        gate_level=GateLevel.SOFT,
        category="process",
    ),
    SlotDefinition(
        name="sanding_grit_last",
        label_zh="上次砂纸目数",
        label_en="Last sanding grit used (integer)",
        gate_level=GateLevel.SOFT,
        category="process",
    ),
    SlotDefinition(
        name="prior_steps_known",
        label_zh="前序步骤已知",
        label_en="Whether user can describe prior steps reliably (boolean)",
        gate_level=GateLevel.SOFT,
        category="process",
    ),
    SlotDefinition(
        name="target_finish",
        label_zh="目标光泽度",
        label_en="Desired finish sheen (matte/semi_gloss/gloss)",
        gate_level=GateLevel.SOFT,
        category="process",
    ),
    # ── Safety ──
    SlotDefinition(
        name="ppe_level",
        label_zh="个人防护装备",
        label_en="PPE readiness (basic_gloves/respirator)",
        gate_level=GateLevel.HARD,
        category="safety",
    ),
]

ALL_SLOTS: list[str] = [s.name for s in SLOT_DEFINITIONS]

HARD_GATE_SLOTS: list[str] = [s.name for s in SLOT_DEFINITIONS if s.is_hard_gate]

SLOT_SCHEMA: dict[str, SlotDefinition] = {s.name: s for s in SLOT_DEFINITIONS}


def create_slot_state() -> SlotState:
    """Create a fresh SlotState with the canonical 18-slot schema."""
    return SlotState(schema_defs=SLOT_SCHEMA)
