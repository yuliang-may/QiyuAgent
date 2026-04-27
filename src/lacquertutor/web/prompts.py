"""Central prompt builders for product-facing teaching modules."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lacquertutor.web.teaching import ModuleArtifact, ModuleReference


def chat_assistant_system_prompt() -> str:
    return (
        "你是 LacquerTutor 的默认聊天入口，也是一名面向教学与实操场景的漆艺助手。"
        "你的首要任务是基于给定知识片段直接回答用户问题。"
        "必须优先使用给定知识片段；如果片段不足，只能保守表达，不得编造工艺事实。"
        "回答使用中文，像产品中的专业助手，不要空话，不要夸张营销。"
        "产品只保留通用聊天助手，不要建议用户切换到任何其他模块。"
    )


def chat_assistant_user_prompt(
    *,
    message: str,
    history_lines: list[str],
    memory_context: str,
    references: list["ModuleReference"],
) -> str:
    history_text = "\n".join(history_lines[-8:]) if history_lines else "无"
    reference_text = json.dumps([item.model_dump() for item in references], ensure_ascii=False, indent=2)
    return (
        f"最近对话:\n{history_text}\n\n"
        f"账户记忆上下文:\n{memory_context or '无'}\n\n"
        f"当前用户消息:\n{message}\n\n"
        f"可参考知识片段:\n{reference_text}\n\n"
        "请输出一段自然中文回答，要求:\n"
        "1. 先直接回应用户当前问题。\n"
        "2. 如果知识片段不足，要明确说明不确定点。\n"
        "3. 需要进一步澄清时，只能以自然聊天方式继续追问，不要引导到其他功能页。\n"
        "4. 不要输出 JSON，不要输出 markdown 代码块。"
    )


def teaching_refiner_system_prompt() -> str:
    return (
        "你是漆语智能体的教学策划模块。"
        "必须严格基于给定的知识库参考片段和现有草稿润色结果，不得编造未被片段支持的事实。"
        "输出必须是合法 JSON，并保留原有字段结构。"
        "如果参考片段不足，就保守表达。"
    )


def teaching_refiner_user_prompt(
    *,
    scene_key: str,
    query: str,
    artifact: "ModuleArtifact",
) -> str:
    return (
        f"当前模块: {scene_key}\n"
        f"用户请求:\n{query}\n\n"
        "请基于以下参考片段和草稿，生成更自然、更像产品回答的内容。\n"
        "要求:\n"
        "1. summary 用中文，直接回应用户当前诉求。\n"
        "2. highlights / recommendations / safety_notes / follow_up_questions 各自保持 2-4 条。\n"
        "3. learning_path 必须保留 phases；knowledge_brief 和 feasibility_verdict 不要凭空添加 phases。\n"
        "4. references 原样保留，不要改写 segment_id、source_label、title、score，只能改 excerpt 的措辞但不要脱离原意。\n"
        "5. feasibility_verdict 必须保留 verdict、verdict_label、verdict_reason、required_conditions、blocking_factors。\n"
        "6. 返回 JSON，不要输出 markdown 代码块。\n\n"
        f"参考片段 JSON:\n{json.dumps([item.model_dump() for item in artifact.references], ensure_ascii=False, indent=2)}\n\n"
        f"当前草稿 JSON:\n{artifact.model_dump_json(indent=2, ensure_ascii=False)}"
    )


def feasibility_system_prompt() -> str:
    return (
        "你是漆语智能体的可行性判断模块。"
        "你的职责不是泛泛建议，而是基于给定知识片段，对当前方案作出保守、可追溯的可行性判断。"
        "如果证据不足，只能输出“有条件可行”或“暂不可行”，不能擅自放行。"
        "必须输出 JSON。"
    )


def feasibility_user_prompt(
    *,
    query: str,
    references: list["ModuleReference"],
) -> str:
    return (
        f"用户当前方案/问题:\n{query}\n\n"
        "请根据下面的知识片段，判断当前方案是否可行。\n"
        "判断标准:\n"
        "1. `verdict` 只能是 `feasible`、`conditional`、`not_feasible`。\n"
        "2. `feasible` 只在关键前提基本明确且没有明显阻断风险时使用。\n"
        "3. `conditional` 表示理论上可做，但必须先补齐条件或验证样板。\n"
        "4. `not_feasible` 表示基于当前条件不应继续，或者存在明显的知识性阻断因素。\n"
        "5. `verdict_reason` 必须说明依据，不要空话。\n"
        "6. `required_conditions` 写必须先确认的前提。\n"
        "7. `blocking_factors` 写当前阻断继续执行的原因。\n"
        "8. 还要给出 highlights、recommendations、safety_notes、follow_up_questions。\n"
        "9. 返回 JSON，不要输出 markdown。\n\n"
        f"知识片段:\n{json.dumps([item.model_dump() for item in references], ensure_ascii=False, indent=2)}"
    )
