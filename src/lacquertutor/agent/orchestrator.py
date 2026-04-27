"""LacquerTutor orchestrator — multi-agent architecture.

Uses a Triage → Dialogue → Planning/Troubleshooting agent pipeline
with SDK-native handoffs. Each agent has focused instructions and tools.

The legacy single-agent mode is preserved for backward compatibility
with the evaluation harness (use LacquerTutorApp with multi_agent=False).
"""

from __future__ import annotations

import logging

from agents import (
    Agent,
    InputGuardrailTripwireTriggered,
    MaxTurnsExceeded,
    ModelSettings,
    Runner,
    handoff,
)

from lacquertutor.agent.agents.dialogue import create_dialogue_agent
from lacquertutor.agent.agents.planning import create_planning_agent
from lacquertutor.agent.agents.triage import create_triage_agent
from lacquertutor.agent.agents.troubleshooting import create_troubleshooting_agent
from lacquertutor.agent.context import LacquerTutorContext
from lacquertutor.agent.guardrails import (
    evidence_grounding_guardrail,
    hallucination_guardrail,
    off_topic_guardrail,
    safety_bypass_guardrail,
)
from lacquertutor.agent.resilience import CircuitBreaker, CircuitBreakerTripped
from lacquertutor.agent.tools import (
    ask_user_question,
    detect_intent,
    extract_slots,
    generate_plan,
    retrieve_evidence,
    score_unfilled_slots,
    verify_plan,
)
from lacquertutor.config import Settings
from lacquertutor.llm.client import configure_sdk
from lacquertutor.models.contract import PlanContract
from lacquertutor.models.evidence import EvidenceStore

logger = logging.getLogger(__name__)


# ── Single-agent instructions (kept for backward compat / eval) ──────

SINGLE_AGENT_INSTRUCTIONS = """\
你是 LacquerTutor —— 漆艺工艺智能助手。你帮助用户生成安全、可执行的漆艺工作流计划。最终请输出JSON格式的计划合同。

## 你的工作流程

1. **理解意图**: 使用 `detect_intent` 分析用户问题的类型和阶段
2. **提取已知信息**: 使用 `extract_slots` 从用户初始消息中提取变量
3. **评估缺失信息**: 使用 `score_unfilled_slots` 对未知变量进行 VoI 风险评分
4. **按优先级提问**: 如果有高优先级未知变量（分数 >= 2），使用 `ask_user_question` 提问
5. **重复步骤 3-4**: 直到停止条件满足（最多 6 个问题，或所有重要变量已知）
6. **检索证据**: 使用 `retrieve_evidence` 获取相关工艺知识
7. **生成计划**: 基于所有收集的信息，生成可执行计划合同
8. **验证计划**: 使用 `verify_plan` 检查合同（自动读取刚生成的合同），如有问题则修正后重新生成

## 安全规则

- 每个不可逆步骤必须有对应的检查点和证据引用
- 硬门控变量（lacquer_system, substrate_material, substrate_condition, environment_humidity_pct, environment_temperature_c, curing_method, time_since_last_coat_h, ppe_level）在不可逆步骤前必须确认
- 如果硬门控变量未确认，在该步骤前停止并标为假设
- 不要编造证据引用，只使用 retrieve_evidence 返回的证据卡 ID
- 优先保守：宁可多设检查点，不要跳过安全步骤

## 重要：你必须使用工具！

不使用工具就直接生成计划是不允许的。"""


class LacquerTutorApp:
    """Application wrapper for running the LacquerTutor agent.

    Supports two modes:
    - multi_agent=True (default): Triage → Dialogue → Planning/Troubleshooting
    - multi_agent=False: Single agent with all 7 tools (legacy, for eval)
    """

    def __init__(
        self,
        settings: Settings,
        evidence_store: EvidenceStore,
        multi_agent: bool = True,
        vector_store=None,
        session_store=None,
    ) -> None:
        self.settings = settings
        self.evidence_store = evidence_store
        self.multi_agent = multi_agent
        self._vector_store = vector_store
        self._session_store = session_store

        # Configure SDK and get model
        self._client, self._model = configure_sdk(settings)

        if multi_agent:
            self._build_multi_agent()
        else:
            self._build_single_agent()

    def _build_single_agent(self) -> None:
        """Build the legacy single-agent with all 7 tools."""
        self.agent = Agent[LacquerTutorContext](
            name="LacquerTutor",
            model=self._model,
            model_settings=ModelSettings(temperature=0.0),
            instructions=SINGLE_AGENT_INSTRUCTIONS,
            tools=[
                detect_intent,
                extract_slots,
                score_unfilled_slots,
                ask_user_question,
                retrieve_evidence,
                generate_plan,
                verify_plan,
            ],
            input_guardrails=[safety_bypass_guardrail, off_topic_guardrail],
            output_guardrails=[evidence_grounding_guardrail, hallucination_guardrail],
        )

    def _build_multi_agent(self) -> None:
        """Build the multi-agent pipeline with handoffs."""
        # Break circular dependency: create planning/troubleshooting first,
        # then dialogue (which references them), then triage (which references dialogue).
        # dialogue_agent_ref is a mutable list used to add handoff back later.
        dialogue_agent_ref: list[Agent] = []

        self.planning_agent = create_planning_agent(
            self._model, dialogue_agent_ref
        )
        self.troubleshooting_agent = create_troubleshooting_agent(
            self._model, dialogue_agent_ref
        )
        self.dialogue_agent = create_dialogue_agent(
            self._model,
            planning_agent=self.planning_agent,
            troubleshooting_agent=self.troubleshooting_agent,
        )

        # Now wire the back-handoff from planning/troubleshooting → dialogue
        back_handoff = handoff(
            self.dialogue_agent,
            tool_description_override=(
                "移交回对话代理以收集更多信息。当验证发现缺少关键变量时调用。"
            ),
        )
        self.planning_agent.handoffs = [back_handoff]
        self.troubleshooting_agent.handoffs = [back_handoff]

        # Triage is the entry point
        self.triage_agent = create_triage_agent(
            self._model, self.dialogue_agent
        )
        self.agent = self.triage_agent

    async def run(
        self,
        query: str,
        answer_fn=None,
        session_id: str | None = None,
    ) -> tuple[PlanContract, LacquerTutorContext]:
        """Run the agent on a user query.

        Args:
            query: User's lacquer craft question
            answer_fn: Async callback (question, slot_name) -> answer
            session_id: Resume an existing session (or create new if None)

        Returns:
            (PlanContract, LacquerTutorContext)

        Raises:
            InputGuardrailTripwireTriggered: When input is blocked by safety/off-topic guardrails
            CircuitBreakerTripped: When turn or cost limits are exceeded
        """
        # Session management: create or resume
        if self._session_store and not session_id:
            session_id = await self._session_store.create_session()
        if self._session_store and session_id:
            await self._session_store.add_message(session_id, "user", content=query)

        context = LacquerTutorContext(
            evidence_store=self.evidence_store,
            answer_fn=answer_fn,
            vector_store=self._vector_store,
            max_questions=self.settings.max_questions,
            evidence_top_k=self.settings.evidence_top_k,
            max_revisions=self.settings.max_revisions,
            original_query=query,
        )

        breaker = CircuitBreaker(
            max_turns=self.settings.max_turns,
            max_cost_usd=self.settings.max_cost_usd,
        )

        try:
            await Runner.run(
                starting_agent=self.agent,
                input=query,
                context=context,
                max_turns=breaker.max_turns,
            )
        except InputGuardrailTripwireTriggered as e:
            logger.warning("Input guardrail triggered: %s", e)
            raise
        except MaxTurnsExceeded:
            logger.warning("Max turns exceeded (%d)", breaker.max_turns)
            context.stop_reason = "max_turns_exceeded"
        except Exception as e:
            logger.error("Agent run failed: %s", e)
            context.stop_reason = f"error: {type(e).__name__}"

        contract = getattr(context, '_generated_contract', None)
        if contract is None:
            contract = PlanContract(stop_reason=getattr(context, 'stop_reason', 'no_contract'))

        # Session management: persist result
        if self._session_store and session_id:
            await self._session_store.update_context(session_id, context.to_json())
            status = "completed" if contract.steps else "abandoned"
            await self._session_store.update_status(session_id, status)
            await self._session_store.add_message(
                session_id, "assistant",
                content=contract.model_dump_json(indent=2),
                tool_name="generate_plan",
            )

        return contract, context

    async def close(self) -> None:
        """Clean up."""
        pass
