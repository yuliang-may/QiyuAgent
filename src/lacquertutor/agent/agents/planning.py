"""Planning Agent — generates and verifies executable plan contracts.

Responsible for:
- Retrieving procedural evidence from the knowledge base
- Generating structured plan contracts (sections A-F)
- Verifying plans against safety/structural/grounding rules
- Handing back to DialogueAgent if verifier says re-elicit
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

PLANNING_INSTRUCTIONS = """\
你是 LacquerTutor 的计划生成代理，负责生成安全、可执行的漆艺工作流计划。

## 你的职责

1. **检索证据**: 使用 `retrieve_evidence` 获取相关工艺知识
2. **生成计划**: 使用 `generate_plan` 基于所有收集的信息生成计划合同
3. **验证计划**: 使用 `verify_plan` 检查安全性、结构完整性和证据引用（直接验证刚生成的合同，无需传参）

## 计划合同格式 (JSON)

必须包含六部分：
A. assumptions — 已知条件与假设
B. missing_critical_slots — 缺失关键变量
C. steps — 有序操作步骤
D. high_risk_warnings — 高风险警告
E. checkpoints — 检查点
F. contingencies — 应急预案

## 安全规则

- 每个不可逆步骤必须有检查点和证据引用
- 硬门控变量未确认时，在不可逆步骤前停止并标为假设
- 不编造证据引用，只使用 retrieve_evidence 返回的证据卡 ID
- 优先保守：宁可多设检查点

## 验证失败处理

如果 verify_plan 发现问题：
- 证据不足 → 重新 retrieve_evidence
- 缺少关键变量 → 移交回 Dialogue Agent 补充提问
- 结构问题 → 重新 generate_plan 修正"""


def create_planning_agent(
    model,
    dialogue_agent_ref: list,
) -> Agent[LacquerTutorContext]:
    """Create the Planning Agent.

    dialogue_agent_ref is a mutable list that will be populated after
    the dialogue agent is created (to break circular dependency).
    """

    def can_handoff_to_dialogue(
        ctx: RunContextWrapper[LacquerTutorContext], agent: Agent
    ) -> bool:
        """Allow handoff back to dialogue when re-elicitation is needed."""
        return ctx.context.revision_count < ctx.context.max_revisions

    agent = Agent[LacquerTutorContext](
        name="PlanningAgent",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        instructions=PLANNING_INSTRUCTIONS,
        tools=[
            retrieve_evidence,
            generate_plan,
            verify_plan,
        ],
        output_guardrails=[evidence_grounding_guardrail, hallucination_guardrail],
        handoffs=[],  # populated after dialogue agent is created
    )

    # Store ref so we can add handoff after dialogue agent is created
    agent._dialogue_agent_ref = dialogue_agent_ref
    return agent
