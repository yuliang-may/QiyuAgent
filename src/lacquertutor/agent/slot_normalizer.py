"""Deterministic slot normalization helpers shared across chat and workflow paths."""

from __future__ import annotations

import re
from typing import Any, Iterable

NUMBER_RE = re.compile(r"(-?\d+(?:\.\d+)?)")


def normalize_slot_answer(slot_name: str, answer: str) -> Any:
    text = str(answer or "").strip()
    lowered = text.lower()
    number_match = NUMBER_RE.search(lowered)

    if slot_name == "dilution_ratio_pct":
        if "%" in text or "稀释" in text or "兑" in text or number_match:
            return number_match.group(1) if number_match else None

    if slot_name == "environment_humidity_pct":
        if "%" in text or "湿度" in text or number_match:
            return number_match.group(1) if number_match else None

    if slot_name == "environment_temperature_c":
        if any(token in text for token in ("°", "℃", "度", "c", "C")) or number_match:
            return number_match.group(1) if number_match else None

    if slot_name == "time_since_last_coat_h":
        if any(token in text for token in ("还没开始", "没有上一层", "未上漆", "还没上")):
            return "0"
        if number_match:
            hours = float(number_match.group(1))
            if "天" in text:
                hours *= 24
            return str(int(hours) if hours.is_integer() else round(hours, 2))

    if slot_name == "lacquer_system":
        if any(token in text for token in ("水性", "water")):
            return "water_based"
        if any(token in text for token in ("生漆", "大漆", "urushi")):
            return "urushi"
        if any(token in text for token in ("双组分", "2k", "双组份")):
            return "synthetic_two_part"
        if any(token in text for token in ("油性", "溶剂", "腰果")):
            return "synthetic_solvent"

    if slot_name == "substrate_condition":
        if any(token in text for token in ("原木", "素底", "未上", "没有旧", "无旧")):
            return "raw"
        if any(token in text for token in ("旧涂层", "翻新", "已有涂层", "重涂")):
            return "previously_finished"

    if slot_name == "substrate_material":
        if any(token in text for token in ("木", "wood")):
            return "wood"
        if any(token in text for token in ("金属", "metal", "铁", "铜", "铝")):
            return "metal"
        if any(token in text for token in ("陶", "瓷", "ceramic")):
            return "ceramic"
        if any(token in text for token in ("塑料", "plastic")):
            return "plastic"
        if any(token in text for token in ("复合", "composite")):
            return "composite"

    if slot_name == "curing_method":
        if any(token in text for token in ("自然", "晾干", "风干", "空气")):
            return "air"
        if any(token in text for token in ("湿房", "湿润", "湿箱", "湿盒")):
            return "humidity_box"
        if any(token in text for token in ("固化柜", "烘箱", "烘干", "热风", "加热")):
            return "cabinet"

    if slot_name == "ventilation_quality":
        if any(token in lowered for token in ("good", "strong", "exhaust")) or any(
            token in text for token in ("良好", "很好", "强通风", "排风", "通风柜", "通风好")
        ):
            return "good"
        if any(token in lowered for token in ("limited", "normal", "medium")) or any(
            token in text for token in ("一般", "有限", "普通")
        ):
            return "limited"
        if any(token in lowered for token in ("poor", "bad", "closed")) or any(
            token in text for token in ("较差", "很差", "密闭", "闷", "无通风", "通风差")
        ):
            return "poor"

    if slot_name == "dust_control_level":
        if any(token in lowered for token in ("high",)) or any(
            token in text for token in ("高", "很好", "严格")
        ):
            return "high"
        if any(token in lowered for token in ("medium", "mid")) or any(
            token in text for token in ("中", "一般", "普通")
        ):
            return "medium"
        if any(token in lowered for token in ("low",)) or any(
            token in text for token in ("低", "较差", "很差")
        ):
            return "low"

    if slot_name == "ppe_level":
        if any(token in text for token in ("口罩", "呼吸", "防毒", "面罩")):
            return "respirator"
        if any(token in text for token in ("手套", "基础防护")):
            return "basic_gloves"

    if slot_name == "available_time_days":
        if "一周" in text:
            return "7"
        if "两周" in text:
            return "14"
        if number_match:
            days = float(number_match.group(1))
            if any(token in text for token in ("小时", "h", "H")):
                days /= 24
            return str(int(days) if days.is_integer() else round(days, 2))

    if slot_name == "coat_thickness":
        if any(token in lowered for token in ("thin",)) or any(token in text for token in ("薄", "偏薄")):
            return "thin"
        if any(token in lowered for token in ("medium",)) or any(token in text for token in ("中", "适中")):
            return "medium"
        if any(token in lowered for token in ("thick",)) or any(token in text for token in ("厚", "偏厚")):
            return "thick"

    if slot_name == "application_tool":
        if any(token in lowered for token in ("brush",)) or any(token in text for token in ("刷", "毛刷")):
            return "brush"
        if any(token in lowered for token in ("pad", "cloth")) or any(token in text for token in ("擦", "棉", "布")):
            return "pad"
        if any(token in lowered for token in ("spray",)) or any(token in text for token in ("喷", "喷枪")):
            return "spray"

    if slot_name == "layer_count_target":
        if number_match:
            count = float(number_match.group(1))
            return str(int(count))

    if slot_name == "sanding_grit_last":
        if number_match:
            grit = float(number_match.group(1))
            return str(int(grit))

    if slot_name == "prior_steps_known":
        if any(token in text for token in ("不知道", "不清楚", "不明确", "还没开始")):
            return "false"
        if any(token in text for token in ("知道", "清楚", "明确")):
            return "true"

    if slot_name == "target_finish":
        if any(token in lowered for token in ("matte",)) or any(token in text for token in ("哑光", "消光")):
            return "matte"
        if any(token in lowered for token in ("semi", "semi_gloss", "satin")) or any(
            token in text for token in ("半光", "丝光")
        ):
            return "semi_gloss"
        if any(token in lowered for token in ("gloss", "glossy")) or any(token in text for token in ("高光", "亮光")):
            return "gloss"

    return None


def extract_slot_values_from_text(
    text: str,
    *,
    slot_names: Iterable[str],
) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    for slot_name in slot_names:
        normalized = normalize_slot_answer(slot_name, text)
        if normalized is not None:
            extracted[slot_name] = normalized
    return extracted
