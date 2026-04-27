"""Triage Agent — routes incoming queries to the right specialist.

The triage agent is the starting_agent for the multi-agent architecture.
It examines the user's query and hands off to DialogueAgent, which then
routes to PlanningAgent or TroubleshootingAgent after elicitation.
"""

from __future__ import annotations

from agents import Agent, ModelSettings

from lacquertutor.agent.context import LacquerTutorContext
from lacquertutor.agent.guardrails import off_topic_guardrail, safety_bypass_guardrail

TRIAGE_INSTRUCTIONS = """\
你是 LacquerTutor 的路由代理。你的唯一职责是将用户的问题转交给合适的专家代理。

## 路由规则

收到用户消息后，立即移交给 Dialogue Agent（对话代理）。对话代理会负责：
- 分析用户意图（planning/troubleshooting）
- 收集必要信息
- 然后移交给相应的专家

## 重要

- 不要自己回答用户的问题
- 不要自己分析或处理
- 直接移交给 Dialogue Agent"""


def create_triage_agent(
    model,
    dialogue_agent: Agent,
) -> Agent[LacquerTutorContext]:
    """Create the Triage Agent that routes to DialogueAgent."""
    return Agent[LacquerTutorContext](
        name="TriageAgent",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
        instructions=TRIAGE_INSTRUCTIONS,
        handoffs=[dialogue_agent],
        input_guardrails=[safety_bypass_guardrail, off_topic_guardrail],
    )
