"""Presentation helpers for user-facing web responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lacquertutor.models.contract import PlanContract
from lacquertutor.models.slots import SLOT_SCHEMA

SLOT_VALUE_LABELS: dict[str, dict[str, str]] = {
    "substrate_material": {
        "wood": "木材",
        "metal": "金属",
        "ceramic": "陶瓷",
        "plastic": "塑料",
        "composite": "复合材料",
    },
    "substrate_condition": {
        "raw": "素底 / 未上涂层",
        "previously_finished": "已有旧涂层",
    },
    "ventilation_quality": {
        "poor": "通风差",
        "limited": "通风一般",
        "good": "通风良好",
    },
    "dust_control_level": {
        "low": "防尘较弱",
        "medium": "防尘一般",
        "high": "防尘较好",
    },
    "curing_method": {
        "air": "自然干燥",
        "humidity_box": "湿润固化箱",
        "cabinet": "固化柜",
    },
    "coat_thickness": {
        "thin": "薄涂",
        "medium": "中等厚度",
        "thick": "厚涂",
    },
    "application_tool": {
        "brush": "刷涂",
        "pad": "擦涂 / 棉垫",
        "spray": "喷涂",
    },
    "target_finish": {
        "matte": "哑光",
        "semi_gloss": "半光",
        "gloss": "高光",
    },
    "ppe_level": {
        "basic_gloves": "基础手套防护",
        "respirator": "含呼吸防护",
    },
    "prior_steps_known": {
        "true": "已知前序步骤",
        "false": "前序步骤不明确",
    },
    "lacquer_system": {
        "urushi": "大漆 / 生漆",
        "raw_lacquer": "生漆",
        "waterborne": "水性木器漆",
        "water_based": "水性木器漆",
        "solvent_based": "油性 / 溶剂型漆",
        "polyurethane": "聚氨酯漆",
        "nitrocellulose": "硝基漆",
    },
}

UNIT_SUFFIXES: dict[str, str] = {
    "environment_humidity_pct": "%",
    "dilution_ratio_pct": "%",
    "environment_temperature_c": "°C",
    "time_since_last_coat_h": " 小时",
    "available_time_days": " 天",
    "layer_count_target": " 层",
    "sanding_grit_last": " 目",
}

SCENE_LABELS: dict[str, str] = {
    "chat": "通用漆艺助手",
    "planning": "可执行工艺计划",
    "troubleshooting": "工艺故障诊断",
    "knowledge": "漆艺知识问答",
    "learning": "个性化学习路径",
    "safety": "安全护栏检查",
}

SCENE_SUMMARY_PATTERNS: dict[str, tuple[str, ...]] = {
    "planning": ("我想生成一份可执行工艺计划", "可执行工艺计划"),
    "troubleshooting": ("我正在处理一个漆艺故障", "工艺故障诊断"),
    "knowledge": ("我想快速查一个漆艺知识点", "漆艺知识问答"),
    "learning": ("我想获得一条个性化学习路径", "个性化学习路径"),
    "safety": (
        "我想先确认关键步骤是否安全",
        "我想先判断当前方案到底可不可行",
        "安全护栏检查",
        "到底可不可行",
        "能不能继续",
    ),
}

OBJECT_LABELS: tuple[str, ...] = (
    "对象 / 基底",
    "对象 / 当前阶段",
    "主题 / 当前对象",
    "当前水平 / 学习目标",
    "关键步骤 / 当前方案",
)
GOAL_LABELS: tuple[str, ...] = (
    "你想做成什么效果",
    "你遇到了什么现象",
    "你想知道什么",
    "你现在最想补哪一块",
    "你最想先确认什么",
)


def slot_label(slot_name: str) -> str:
    slot_def = SLOT_SCHEMA.get(slot_name)
    return slot_def.label_zh if slot_def else slot_name


def infer_scene_key(original_query: str) -> str:
    """Infer the product scene from the initial user query."""
    query = str(original_query or "").strip()
    first_line = query.splitlines()[0].strip() if query else ""
    for scene_key, patterns in SCENE_SUMMARY_PATTERNS.items():
        if any(pattern in first_line for pattern in patterns):
            return scene_key
    return "planning"


def scene_label(scene_key: str) -> str:
    return SCENE_LABELS.get(scene_key, "当前项目")


def extract_labeled_value(text: str, labels: tuple[str, ...]) -> str:
    """Extract the first labeled value from a multi-line query."""
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        for label in labels:
            for separator in (":", "："):
                prefix = f"{label}{separator}"
                if line.startswith(prefix):
                    return line[len(prefix) :].strip()
    return ""


def humanize_slot_value(slot_name: str, value: Any) -> str:
    """Convert internal slot values into user-facing labels."""
    if value is None:
        return ""

    if isinstance(value, bool):
        normalized = "true" if value else "false"
        return SLOT_VALUE_LABELS.get(slot_name, {}).get(normalized, "是" if value else "否")

    raw = str(value).strip()
    if not raw:
        return raw

    lowered = raw.lower()
    mapped = SLOT_VALUE_LABELS.get(slot_name, {}).get(lowered)
    if mapped:
        return mapped

    suffix = UNIT_SUFFIXES.get(slot_name)
    if suffix and not raw.endswith(suffix.strip()):
        return f"{raw}{suffix}"

    return raw


def display_slot_items(values: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return user-facing slot display items."""
    return [
        {
            "name": name,
            "label": slot_label(name),
            "value": humanize_slot_value(name, value),
        }
        for name, value in values.items()
    ]


def display_missing_slot_items(slot_names: list[str]) -> list[dict[str, str]]:
    """Return user-facing labels for missing slots."""
    return [{"name": slot_name, "label": slot_label(slot_name)} for slot_name in slot_names]


def derive_project_title(
    original_query: str,
    *,
    scene_key: str | None = None,
    fallback: str = "当前项目",
) -> str:
    """Generate a stable, user-facing title for a session."""
    resolved_scene = scene_key or infer_scene_key(original_query)
    scene_title = scene_label(resolved_scene)
    object_value = extract_labeled_value(original_query, OBJECT_LABELS)
    if object_value:
        return f"{scene_title} · {object_value[:32]}"
    if resolved_scene == "chat":
        first_line = next(
            (line.strip() for line in str(original_query or "").splitlines() if line.strip()),
            "",
        )
        if first_line:
            return f"{scene_title} · {first_line[:28]}"
    return scene_title or fallback


def derive_project_summary(
    original_query: str,
    *,
    scene_key: str | None = None,
    fallback: str = "",
) -> str:
    """Generate a short summary for landing cards and workspace headers."""
    goal_value = extract_labeled_value(original_query, GOAL_LABELS)
    if goal_value:
        return goal_value[:120]

    first_line = next(
        (line.strip() for line in str(original_query or "").splitlines() if line.strip()),
        "",
    )
    if (scene_key or "").strip() == "chat" and first_line:
        return first_line[:120]
    return first_line[:120] if first_line else fallback


def serialize_contract_display(contract: PlanContract | None) -> dict[str, Any] | None:
    """Return a user-facing view of the generated contract."""
    if contract is None:
        return None

    return {
        "assumptions": [
            {
                "slot_name": item.slot_name,
                "label": slot_label(item.slot_name),
                "value": humanize_slot_value(item.slot_name, item.value),
                "confirmed": item.confirmed,
                "note": item.note,
            }
            for item in contract.assumptions
        ],
        "missing_critical_slots": display_missing_slot_items(contract.missing_critical_slots),
        "steps": [
            {
                "step_number": step.step_number,
                "action": step.action,
                "parameters": step.parameters or "未指定",
                "timing_window": step.timing_window or "未指定",
                "checkpoint_id": step.checkpoint_id or "",
                "evidence_refs": step.evidence_refs,
                "is_irreversible": step.is_irreversible,
            }
            for step in contract.steps
        ],
        "high_risk_warnings": [
            {
                "label": warning.label or "高风险步骤",
                "action": warning.action or "未说明",
                "requires_slots": display_missing_slot_items(warning.requires_slots),
                "required_checkpoint": warning.required_checkpoint or "未指定",
                "consequence": warning.consequence or "未说明",
            }
            for warning in contract.high_risk_warnings
        ],
        "checkpoints": [
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "description": checkpoint.description,
                "evidence_refs": checkpoint.evidence_refs,
            }
            for checkpoint in contract.checkpoints
        ],
        "contingencies": [
            {
                "condition": contingency.condition,
                "action": contingency.action,
                "recheck_checkpoint": contingency.recheck_checkpoint or "",
                "evidence_refs": contingency.evidence_refs,
            }
            for contingency in contract.contingencies
        ],
        "summary": {
            "step_count": len(contract.steps),
            "warning_count": len(contract.high_risk_warnings),
            "checkpoint_count": len(contract.checkpoints),
            "contingency_count": len(contract.contingencies),
            "stop_reason": contract.stop_reason,
        },
    }
