"""Troubleshooting Agent — diagnoses failures and generates recovery plans.

Responsible for:
- Retrieving evidence relevant to the failure mode
- Generating diagnosis-to-recovery plan contracts
- Verifying recovery plans
- Handing back to DialogueAgent if more info needed
"""

from __future__ import annotations

from agents import Agent, ModelSettings, handoff, RunContextWrapper

from lacquertutor.agent.context import LacquerTutorContext
from lacquertutor.agent.guardrails import (
    evidence_grounding_guardrail,
    hallucination_guardrail,
)
from lacquertutor.agent.tools import (
    retrieve_evidence,
    generate_plan,
    verify_plan,
)

TROUBLESHOOTING_INSTRUCTIONS = """\
你是 LacquerTutor 的故障排查代理，负责诊断漆艺工艺问题并生成恢复计划。

## 你的职责

1. **检索证据**: 使用 `retrieve_evidence` 获取与故障模式相关的工艺知识
2. **生成恢复计划**: 使用 `generate_plan` 生成诊断到恢复的计划合同
3. **验证计划**: 使用 `verify_plan` 检查计划的安全性和完整性（直接验证刚生成的合同，无需传参）

## 故障排查特点

与 planning 不同，troubleshooting 需要：
- 诊断根本原因（如：发白可能是湿度过低或涂层过厚）
- 评估当前损伤是否可逆
- 如果不可逆，建议最小化损失的恢复步骤
- 提供 if-then 分支（contingencies），因为同一症状可能有多种原因

## 安全规则

- 优先确认当前漆层状态再建议任何操作
- 恢复操作中的不可逆步骤（如磨掉漆层）必须有检查点
- 不编造证据引用
- 如果信息不足以确定根因，标明需要哪些额外信息"""


def create_troubleshooting_agent(
    model,
    dialogue_agent_ref: list,
) -> Agent[LacquerTutorContext]:
    """Create the Troubleshooting Agent."""
    agent = Agent[LacquerTutorContext](
        name="TroubleshootingAgent",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        instructions=TROUBLESHOOTING_INSTRUCTIONS,
        tools=[
            retrieve_evidence,
            generate_plan,
            verify_plan,
        ],
        output_guardrails=[evidence_grounding_guardrail, hallucination_guardrail],
        handoffs=[],  # populated after dialogue agent is created
    )
    agent._dialogue_agent_ref = dialogue_agent_ref
    return agent
