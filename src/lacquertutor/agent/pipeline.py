"""LacquerTutor agent pipeline — built on OpenAI Agents SDK.

Uses Agent primitives with typed structured outputs:
- IntentAgent → IntentResult
- SlotExtractorAgent → ExtractedSlots
- VoIScorerAgent → VoIScores (+ deterministic adjustment)
- QuestionAgent → free-text question
- PlannerAgent → PlanContract (with output_guardrail for verification)

The pipeline orchestrates multi-turn dialogue with VoI scoring,
while the SDK handles JSON schema enforcement and tool calling.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import structlog
from agents import Runner

from lacquertutor.agent.memory import SessionMemoryEngine
from lacquertutor.agent.mem0_service import Mem0MemoryService
from lacquertutor.agent.slot_normalizer import normalize_slot_answer
from lacquertutor.agent.state import ConversationState
from lacquertutor.config import Settings
from lacquertutor.llm.agents import (
    create_intent_agent,
    create_planner_agent,
    create_question_agent,
    create_slot_extractor_agent,
    create_voi_scorer_agent,
)
from lacquertutor.llm.client import configure_sdk
from lacquertutor.llm.outputs import ExtractedSlots, IntentResult, VoIScores
from lacquertutor.models.contract import (
    Checkpoint,
    Contingency,
    HighRiskWarning,
    PlanContract,
    PlanStep,
)
from lacquertutor.models.evidence import EvidenceStore
from lacquertutor.models.slots import HARD_GATE_SLOTS, SLOT_SCHEMA
from lacquertutor.models.task import MER
from lacquertutor.modules.contract_quality import ContractEnricher
from lacquertutor.modules.retrieval import EvidenceRetriever
from lacquertutor.modules.verifier import ContractVerifier
from lacquertutor.modules.voi_scorer import VoIScoringRecord
from lacquertutor.storage.session_store import SessionStore

logger = structlog.get_logger(__name__)

AnswerFn = Callable[[str, str], Awaitable[str]]


class LacquerTutorAgent:
    """Main agent pipeline using OpenAI Agents SDK."""

    def __init__(self, settings: Settings, evidence_store: EvidenceStore) -> None:
        self.settings = settings
        self.evidence_store = evidence_store
        self.retriever = EvidenceRetriever(evidence_store)
        self.verifier = ContractVerifier()
        self.enricher = ContractEnricher()
        self.session_store: SessionStore | None = None
        self.memory_engine: SessionMemoryEngine | None = None
        self.mem0_service: Mem0MemoryService | None = None
        if settings.llm_api_key:
            try:
                self.mem0_service = Mem0MemoryService.from_settings(settings)
            except Exception as exc:
                logger.warning("mem0_unavailable_fallback", error=str(exc))
                self.mem0_service = None

        # Configure SDK for Qwen
        self._client, self._model = configure_sdk(settings)

        # Create typed agents
        model = settings.llm_model
        self.intent_agent = create_intent_agent(model)
        self.extractor_agent = create_slot_extractor_agent(model)
        self.voi_agent = create_voi_scorer_agent(model)
        self.question_agent = create_question_agent(model)
        self.planner_agent = create_planner_agent(model)

    def bind_session_store(self, session_store: SessionStore) -> None:
        """Attach persistent session storage for cross-session memory."""
        self.session_store = session_store
        self.memory_engine = SessionMemoryEngine(
            session_store,
            mem0_service=self.mem0_service,
            session_window=self.settings.memory_session_window,
            profile_limit=self.settings.memory_profile_limit,
            recall_limit=self.settings.memory_recall_limit,
            playbook_limit=self.settings.memory_playbook_limit,
        )

    async def run(
        self,
        query: str,
        answer_fn: AnswerFn,
        enable_dialogue: bool = True,
        enable_verifier: bool = True,
        slot_selection: str = "voi",
        enable_retrieval: bool = True,
        mer: MER | None = None,
    ) -> tuple[PlanContract, ConversationState]:
        """Run the full pipeline with a user answer callback."""
        state = await self.start_session(query)

        # ── Step 3: Elicitation loop ──
        if enable_dialogue and slot_selection != "none":
            await self._elicitation_loop(state, answer_fn, slot_selection)

        # ── Step 4: Evidence retrieval (skipped for B0) ──
        if enable_retrieval:
            state.retrieved_evidence = self.retriever.retrieve(
                stage=state.stage,
                failure_mode=state.failure_mode,
                slot_state=state.slot_state.filled_dict,
                k=self.settings.evidence_top_k,
            )
        else:
            state.retrieved_evidence = []

        # ── Step 5: Plan generation (structured output → PlanContract) ──
        contract = await self._generate_contract(state, mer=mer)

        # ── Step 6: Verification + revision ──
        if enable_verifier:
            contract = await self._verify_and_revise(state, contract, mer=mer)

        state.final_contract = contract
        contract.task_type = state.task_type
        contract.stage = state.stage
        contract.stop_reason = state.stop_reason

        logger.info(
            "pipeline_complete",
            questions=state.questions_asked,
            steps=len(contract.steps),
            revisions=state.revision_count,
        )

        return contract, state

    async def start_session(self, query: str, *, user_id: str = "") -> ConversationState:
        """Bootstrap a conversation state from the initial user query."""
        state = ConversationState(original_query=query)
        state.user_id = user_id
        state.add_user_turn(query)

        intent: IntentResult = await self._run_agent(
            self.intent_agent, f"用户问题: {query}"
        )
        state.task_type = intent.task_type
        state.stage = intent.stage
        state.failure_mode = intent.failure_mode

        logger.info(
            "intent_detected",
            task_type=intent.task_type,
            stage=intent.stage,
            failure_mode=intent.failure_mode,
        )

        extracted: ExtractedSlots = await self._run_agent(
            self.extractor_agent, f"用户消息: {query}"
        )
        self._apply_extracted_slots(state, extracted)
        if self.memory_engine is not None:
            await self.memory_engine.hydrate_state(state)
        return state

    async def advance(
        self,
        state: ConversationState,
        *,
        enable_dialogue: bool = True,
        enable_verifier: bool = True,
        slot_selection: str = "voi",
        enable_retrieval: bool = True,
        mer: MER | None = None,
    ) -> dict[str, Any]:
        """Advance a session by either asking the next question or generating a contract."""
        if state.pending_slot_name:
            return {
                "type": "question",
                "slot_name": state.pending_slot_name,
                "text": state.pending_question,
                "reason": state.pending_question_reason,
            }

        next_question = None
        if enable_dialogue and slot_selection != "none":
            next_question = await self._next_question(state, slot_selection)

        if next_question is not None:
            state.pending_slot_name = next_question["slot_name"]
            state.pending_question = next_question["text"]
            state.pending_question_reason = next_question.get("reason", "")
            state.questions_asked += 1
            state.add_system_turn(next_question["text"], slot_name=next_question["slot_name"])
            return next_question

        if enable_retrieval:
            state.retrieved_evidence = self.retriever.retrieve(
                stage=state.stage,
                failure_mode=state.failure_mode,
                slot_state=state.slot_state.filled_dict,
                k=self.settings.evidence_top_k,
            )
        else:
            state.retrieved_evidence = []

        contract = await self._generate_contract(state, mer=mer)
        if enable_verifier:
            contract = await self._verify_and_revise(state, contract, mer=mer)

        state.final_contract = contract
        contract.task_type = state.task_type
        contract.stage = state.stage
        contract.stop_reason = state.stop_reason
        return {"type": "contract", "contract": contract}

    async def submit_answer(
        self,
        state: ConversationState,
        answer: str,
    ) -> None:
        """Apply a user answer to the currently pending question."""
        if not state.pending_slot_name:
            raise ValueError("No pending question to answer.")

        state.add_user_turn(answer)
        extracted: ExtractedSlots = await self._run_agent(
            self.extractor_agent, f"用户消息: {answer}"
        )
        self._apply_extracted_slots(state, extracted)
        self._apply_pending_slot_fallback(state, answer)
        state.pending_slot_name = None
        state.pending_question = ""
        state.pending_question_reason = ""

    async def _elicitation_loop(
        self,
        state: ConversationState,
        answer_fn: AnswerFn,
        slot_selection: str,
    ) -> None:
        """VoI-scored ask/stop loop using SDK agents."""
        while state.questions_asked < self.settings.max_questions:
            next_question = await self._next_question(state, slot_selection)
            if next_question is None:
                return

            selected_slot = next_question["slot_name"]
            question = next_question["text"]
            state.add_system_turn(question, slot_name=selected_slot)
            state.questions_asked += 1
            state.pending_question_reason = next_question.get("reason", "")

            # Get user answer and extract slots
            answer = await answer_fn(question, selected_slot)
            state.add_user_turn(answer)

            extracted: ExtractedSlots = await self._run_agent(
                self.extractor_agent, f"用户消息: {answer}"
            )
            self._apply_extracted_slots(state, extracted)
            self._apply_pending_slot_fallback(state, answer)
            state.pending_question_reason = ""

        state.stop_reason = "max_questions"

    async def _next_question(
        self,
        state: ConversationState,
        slot_selection: str,
    ) -> dict[str, Any] | None:
        """Return the next system question payload, or None when planning should proceed."""
        unfilled = state.slot_state.unfilled
        if not unfilled:
            state.stop_reason = "all_filled"
            return None

        if slot_selection == "voi":
            record = await self._voi_score(state)
            state.voi_logs.append(record)

            if record.decision == "stop":
                state.stop_reason = record.stop_reason
                return None

            selected_slot = record.selected_slot
            score = record.adjusted_scores.get(selected_slot, 2)
            reason = record.reasons.get(selected_slot, "")

        elif slot_selection == "random":
            import random
            selected_slot = random.choice(unfilled)
            score = 2
            reason = "随机选择"

        elif slot_selection == "prompt":
            record = await self._voi_score(state)
            state.voi_logs.append(record)
            if record.decision == "stop":
                state.stop_reason = record.stop_reason
                return None

            raw_ranked = sorted(record.raw_scores.items(), key=lambda x: -x[1])
            if not raw_ranked or raw_ranked[0][1] <= 1:
                state.stop_reason = "low_priority"
                return None
            selected_slot = raw_ranked[0][0]
            score = raw_ranked[0][1]
            reason = record.reasons.get(selected_slot, "")
        else:
            state.stop_reason = "dialogue_disabled"
            return None

        slot_def = SLOT_SCHEMA.get(selected_slot)
        slot_label = slot_def.label_zh if slot_def else selected_slot

        question_prompt = (
            f"用户的原始问题: {state.original_query}\n"
            f"已知信息: {json.dumps(state.slot_state.filled_dict, ensure_ascii=False)}\n\n"
            f"现在需要询问的变量: {selected_slot}（{slot_label}）\n"
            f"该变量的安全重要性: {score}/3\n"
            f"重要原因: {reason or '该变量对当前任务的安全执行有重要影响'}\n\n"
            f"历史经验（仅供参考，不能视为本次已确认事实）:\n"
            f"{SessionMemoryEngine.format_for_prompt(state)}\n\n"
            "如果历史经验里出现了与当前变量相关的常见偏好，请优先用“这次还是...吗”这类确认式问法。"
        )

        question = await self._run_agent_text(self.question_agent, question_prompt)
        return {
            "type": "question",
            "slot_name": selected_slot,
            "text": question,
            "reason": reason,
            "priority": score,
        }

    async def _voi_score(self, state: ConversationState) -> VoIScoringRecord:
        """Run VoI scoring using the SDK agent + deterministic adjustment."""
        failure_line = f"故障模式: {state.failure_mode}" if state.failure_mode else "故障模式: 无"

        scoring_prompt = (
            f"用户任务: {state.original_query}\n"
            f"任务类型: {state.task_type}\n"
            f"当前阶段: {state.stage}\n"
            f"{failure_line}\n\n"
            f"已知信息:\n{json.dumps(state.slot_state.filled_dict, ensure_ascii=False)}\n\n"
            f"未知变量: {', '.join(state.slot_state.unfilled)}"
        )

        # Stage 1: LLM scoring via SDK agent (structured output)
        voi_result: VoIScores = await self._run_agent(self.voi_agent, scoring_prompt)

        raw_scores = {
            s: max(0, min(3, voi_result.scores.get(s, 1)))
            for s in state.slot_state.unfilled
        }

        # Stage 2: Deterministic hard-gate floor adjustment
        adjusted = {
            s: max(score, 2 * (1 if s in HARD_GATE_SLOTS else 0))
            for s, score in raw_scores.items()
        }

        # Stage 3: Rank and decide
        hard_set = set(HARD_GATE_SLOTS)
        ranked = sorted(
            adjusted.items(),
            key=lambda x: (-x[1], -(1 if x[0] in hard_set else 0), x[0]),
        )

        record = VoIScoringRecord(
            turn=state.questions_asked,
            raw_scores=raw_scores,
            adjusted_scores=adjusted,
            reasons=voi_result.reasons,
            ranked_list=ranked,
        )

        if not ranked:
            record.decision = "stop"
            record.stop_reason = "all_filled"
        elif state.questions_asked >= self.settings.max_questions:
            record.decision = "stop"
            record.stop_reason = "max_questions"
        elif ranked[0][1] <= 1:
            record.decision = "stop"
            record.stop_reason = "low_priority"
        else:
            record.selected_slot = ranked[0][0]
            record.decision = "ask"
            record.stop_reason = "continue"

        return record

    async def _generate_contract(
        self,
        state: ConversationState,
        mer: MER | None = None,
    ) -> PlanContract:
        """Generate plan contract via SDK agent with structured output."""
        evidence_text = EvidenceRetriever.format_evidence_summaries(
            state.retrieved_evidence
        )
        failure_line = f"故障模式: {state.failure_mode}" if state.failure_mode else "故障模式: 无"
        mer_text = self._format_mer(mer)

        plan_prompt = (
            f"用户问题: {state.original_query}\n"
            f"任务类型: {state.task_type}\n"
            f"工作阶段: {state.stage}\n"
            f"{failure_line}\n"
            f"对话停止原因: {state.stop_reason}\n\n"
            f"已确认的变量:\n{json.dumps(state.slot_state.filled_dict, ensure_ascii=False, indent=2)}\n\n"
            f"未填充的变量: {', '.join(state.slot_state.unfilled) or '无'}\n"
            f"未填充的硬门控变量: {', '.join(state.slot_state.unfilled_hard_gates) or '无'}\n\n"
            f"历史经验（仅供参考，绝不能替代本次已确认事实）:\n"
            f"{SessionMemoryEngine.format_for_prompt(state)}\n\n"
            f"可用证据卡:\n{evidence_text}\n\n"
            f"{mer_text}"
        )

        try:
            raw_contract: PlanContract = await self._run_agent(self.planner_agent, plan_prompt)
        except Exception as exc:
            logger.warning("planner_structured_output_failed", error=str(exc))
            raw_contract = self._build_fallback_contract(state)
        contract = self.enricher.enrich(
            raw_contract,
            state.slot_state,
            state.retrieved_evidence,
            task_type=state.task_type,
            stage=state.stage,
            failure_mode=state.failure_mode,
            stop_reason=state.stop_reason,
            mer=mer,
        )

        if not contract.steps:
            logger.warning(
                "planner_empty_contract_fallback",
                task_type=state.task_type,
                stage=state.stage,
                stop_reason=state.stop_reason,
                missing_hard_gates=state.slot_state.unfilled_hard_gates,
            )
            contract = self.enricher.enrich(
                self._build_fallback_contract(state),
                state.slot_state,
                state.retrieved_evidence,
                task_type=state.task_type,
                stage=state.stage,
                failure_mode=state.failure_mode,
                stop_reason=state.stop_reason,
                mer=mer,
            )

        logger.info(
            "plan_generated",
            steps=len(contract.steps),
            checkpoints=len(contract.checkpoints),
            contingencies=len(contract.contingencies),
        )
        return contract

    async def _verify_and_revise(
        self,
        state: ConversationState,
        contract: PlanContract,
        mer: MER | None = None,
    ) -> PlanContract:
        """Verify contract and revise if needed."""
        for _ in range(self.settings.max_revisions):
            result = self.verifier.verify(contract, state.slot_state, mer=mer)
            state.verification_result = result

            if result.passed:
                return contract

            state.revision_count += 1
            logger.info("contract_revision", revision=state.revision_count)

            if result.needs_re_retrieve:
                state.retrieved_evidence = self.retriever.retrieve(
                    stage=state.stage,
                    failure_mode=state.failure_mode,
                    slot_state=state.slot_state.filled_dict,
                    k=self.settings.evidence_top_k + 2,
                )

            revision_notes = "\n".join(
                f"- {issue.description}" for issue in result.errors
            )
            state_backup = state.original_query
            state.original_query = (
                f"{state_backup}\n\n"
                f"[修订说明 - 请修正以下问题：\n{revision_notes}]"
            )
            contract = await self._generate_contract(state, mer=mer)
            state.original_query = state_backup

        state.verification_result = self.verifier.verify(contract, state.slot_state, mer=mer)
        return contract

    async def _run_agent(self, agent, prompt: str) -> Any:
        """Run an SDK agent and return its typed output."""
        result = await Runner.run(agent, input=prompt)
        return result.final_output

    async def _run_agent_text(self, agent, prompt: str) -> str:
        """Run an SDK agent and return its text output."""
        result = await Runner.run(agent, input=prompt)
        output = result.final_output
        return str(output) if output else ""

    @staticmethod
    def _apply_extracted_slots(
        state: ConversationState, extracted: ExtractedSlots
    ) -> None:
        """Apply extracted slots to conversation state."""
        for name, value in extracted.slots.items():
            if name in SLOT_SCHEMA and value and str(value).strip():
                state.slot_state.fill(
                    name=name,
                    value=str(value).strip(),
                    source="user",
                    confirmed=True,
                    turn=state.questions_asked,
                )

    @staticmethod
    def _apply_pending_slot_fallback(state: ConversationState, answer: str) -> None:
        pending_slot = state.pending_slot_name
        if not pending_slot or state.slot_state.is_filled(pending_slot):
            return

        normalized = LacquerTutorAgent._normalize_slot_answer(pending_slot, answer)
        if normalized is None:
            return

        state.slot_state.fill(
            name=pending_slot,
            value=normalized,
            source="user",
            confirmed=True,
            turn=state.questions_asked,
        )

    @staticmethod
    def _normalize_slot_answer(slot_name: str, answer: str) -> Any:
        return normalize_slot_answer(slot_name, answer)

    @staticmethod
    def _build_fallback_contract(state: ConversationState) -> PlanContract:
        missing = state.slot_state.unfilled_hard_gates
        filled = state.slot_state.filled_dict
        lacquer_system = str(filled.get("lacquer_system", "当前漆体系")).strip() or "当前漆体系"
        substrate = str(filled.get("substrate_material", "当前基底")).strip() or "当前基底"

        if state.task_type == "troubleshooting":
            steps = [
                PlanStep(
                    step_number=1,
                    action="立即暂停当前操作，并记录故障现象与最后一步动作。",
                    parameters="拍照、记录环境和当前层状态",
                    timing_window="发现异常后立即",
                    checkpoint_id="CP-01",
                    is_irreversible=False,
                ),
                PlanStep(
                    step_number=2,
                    action="确认漆体系、环境条件和前序步骤，再决定是否继续处理。",
                    parameters="优先确认湿度、温度、漆体系、上一层时间",
                    timing_window="继续任何修复动作前",
                    checkpoint_id="CP-02",
                    is_irreversible=False,
                ),
                PlanStep(
                    step_number=3,
                    action="先做小面积样板验证，再执行正式修复。",
                    parameters="仅在同体系、相近位置做局部测试",
                    timing_window="确认条件后",
                    checkpoint_id="CP-03",
                    is_irreversible=True,
                ),
            ]
        else:
            steps = [
                PlanStep(
                    step_number=1,
                    action=f"确认 {substrate} 的表面状态，并完成清洁、除尘与样板准备。",
                    parameters="表面无油污、无粉尘，先准备小样板",
                    timing_window="正式上漆前",
                    checkpoint_id="CP-01",
                    is_irreversible=False,
                ),
                PlanStep(
                    step_number=2,
                    action="确认环境温湿度、固化方式和个人防护后，再进入正式施工。",
                    parameters="湿度、温度、固化方式、PPE 必须明确",
                    timing_window="任何不可逆步骤前",
                    checkpoint_id="CP-02",
                    is_irreversible=False,
                ),
                PlanStep(
                    step_number=3,
                    action=f"先以 {lacquer_system} 做小样验证，再决定是否进入第一道正式涂装。",
                    parameters="薄涂、观察干燥与附着力",
                    timing_window="条件确认后立即",
                    checkpoint_id="CP-03",
                    is_irreversible=True,
                ),
                PlanStep(
                    step_number=4,
                    action="样板验证通过后，进行第一道正式涂装。",
                    parameters="保持薄涂，避免一次成膜过厚",
                    timing_window="样板通过后",
                    checkpoint_id="CP-04",
                    is_irreversible=True,
                ),
                PlanStep(
                    step_number=5,
                    action="按固化要求等待并复检表面状态，再决定后续层次或收尾。",
                    parameters="检查干燥、附着力、表面均匀性",
                    timing_window="每层施工后",
                    checkpoint_id="CP-05",
                    is_irreversible=False,
                ),
            ]

        warnings = [
            HighRiskWarning(
                label="关键条件未完全确认",
                action="不要直接进入正式不可逆步骤",
                requires_slots=missing,
                required_checkpoint="CP-02" if state.task_type != "troubleshooting" else "CP-02",
                consequence="条件不明会导致返工、附着力失败或表面缺陷",
            )
        ] if missing else []

        checkpoints = [
            Checkpoint(checkpoint_id="CP-01", description="表面状态和样板准备已确认"),
            Checkpoint(checkpoint_id="CP-02", description="环境、漆体系与个人防护已确认"),
            Checkpoint(checkpoint_id="CP-03", description="小样结果可接受，未出现明显缺陷"),
        ]
        if state.task_type != "troubleshooting":
            checkpoints.extend(
                [
                    Checkpoint(checkpoint_id="CP-04", description="正式第一道涂装前条件再次确认"),
                    Checkpoint(checkpoint_id="CP-05", description="固化后表面状态复检通过"),
                ]
            )

        contingencies = [
            Contingency(
                condition="小样或正式表面出现明显发白、起泡、发黏或附着力异常",
                action="立即停止后续施工，回到条件确认与样板验证步骤",
                recheck_checkpoint="CP-02",
            )
        ]

        return PlanContract(
            missing_critical_slots=missing,
            steps=steps,
            high_risk_warnings=warnings,
            checkpoints=checkpoints,
            contingencies=contingencies,
            task_type=state.task_type,
            stage=state.stage,
            stop_reason=state.stop_reason or "fallback_contract",
        )

    async def close(self) -> None:
        """Clean up resources."""
        if self._client and not self._client.is_closed:
            await self._client.close()
        if self.mem0_service is not None:
            await self.mem0_service.close()

    @staticmethod
    def _format_mer(mer: MER | None) -> str:
        if mer is None:
            return (
                "最小可执行要求: 请至少为所有不可逆步骤提供检查点、风险警告、应急预案和证据引用。"
            )

        gates_text = "\n".join(
            f"- {gate.action}: 需要 {', '.join(gate.requires_slots)}"
            for gate in mer.irreversible_gates
        ) or "- 无"
        checkpoints_text = "\n".join(
            f"- {cp.checkpoint_id}: {cp.description}"
            for cp in mer.required_checkpoints
        ) or "- 无"
        contingencies_text = "\n".join(
            f"- {item.condition} -> {item.action}"
            for item in mer.required_contingencies
        ) or "- 无"
        evidence_text = ", ".join(mer.required_evidence_refs) or "无"

        return (
            "最小可执行要求（必须尽量覆盖）:\n"
            f"必需变量: {', '.join(mer.required_slots) or '无'}\n"
            f"不可逆门控:\n{gates_text}\n"
            f"必需检查点:\n{checkpoints_text}\n"
            f"必需应急预案:\n{contingencies_text}\n"
            f"必需证据引用: {evidence_text}"
        )
