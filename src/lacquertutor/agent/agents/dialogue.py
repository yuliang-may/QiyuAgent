"""Dialogue Agent — proactive slot elicitation with VoI scoring.

Responsible for:
- Detecting user intent (planning vs troubleshooting)
- Extracting slot values from user messages
- VoI-scoring unfilled slots to prioritize questions
- Asking targeted questions one at a time
- Handing off to PlanningAgent or TroubleshootingAgent when done
"""

from __future__ import annotations

from agents import Agent, ModelSettings, handoff, RunContextWrapper

from lacquertutor.agent.context import LacquerTutorContext
from lacquertutor.agent.tools import (
    detect_intent,
    extract_slots,
    score_unfilled_slots,
    ask_user_question,
)

DIALOGUE_INSTRUCTIONS = """\
你是 LacquerTutor 的对话代理，负责收集用户的漆艺任务关键信息。

## 你的职责

1. **理解意图**: 使用 `detect_intent` 分析用户问题
2. **提取变量**: 使用 `extract_slots` 从用户消息中提取已知信息
3. **VoI评分**: 使用 `score_unfilled_slots` 评估缺失变量的优先级
4. **按优先级提问**: 使用 `ask_user_question` 向用户提问
5. **循环**: 重复步骤 3-4，直到停止条件满足

## 停止条件

当以下任一条件满足时，停止提问并移交给计划/排查代理：
- 已问 6 个问题
- VoI评分显示剩余变量优先级低（最高分 ≤ 1）
- 所有关键变量已填充

## 移交规则

- **planning 任务** → 移交给 Planning Agent
- **troubleshooting 任务** → 移交给 Troubleshooting Agent
- 移交前确保已完成意图检测和基本变量提取

## 提问规则

- 每次只问一个问题
- 用简单语言，新手能理解
- 给出常见选项帮助回答
- 简要说明为什么需要这个信息"""


def create_dialogue_agent(
    model,
    planning_agent: Agent,
    troubleshooting_agent: Agent,
) -> Agent[LacquerTutorContext]:
    """Create the Dialogue Agent with handoffs to specialist agents."""

    def can_handoff_to_planning(
        ctx: RunContextWrapper[LacquerTutorContext], agent: Agent
    ) -> bool:
        """Allow handoff to planning when intent is detected as planning."""
        return ctx.context.task_type == "planning"

    def can_handoff_to_troubleshooting(
        ctx: RunContextWrapper[LacquerTutorContext], agent: Agent
    ) -> bool:
        """Allow handoff to troubleshooting when intent is detected."""
        return ctx.context.task_type == "troubleshooting"

    return Agent[LacquerTutorContext](
        name="DialogueAgent",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        instructions=DIALOGUE_INSTRUCTIONS,
        tools=[
            detect_intent,
            extract_slots,
            score_unfilled_slots,
            ask_user_question,
        ],
        handoffs=[
            handoff(
                planning_agent,
                tool_description_override=(
                    "将对话移交给计划生成代理。当任务类型为planning且信息收集"
                    "基本完成（VoI评分建议停止或已达问题上限）时调用。"
                ),
                is_enabled=can_handoff_to_planning,
            ),
            handoff(
                troubleshooting_agent,
                tool_description_override=(
                    "将对话移交给故障排查代理。当任务类型为troubleshooting且"
                    "信息收集基本完成时调用。"
                ),
                is_enabled=can_handoff_to_troubleshooting,
            ),
        ],
    )
