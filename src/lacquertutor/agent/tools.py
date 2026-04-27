"""Function tools for the LacquerTutor agent.

Each tool is a capability the agent can invoke. The agent
decides WHEN and HOW to use each tool based on its reasoning.
Adding a new capability = adding a new @function_tool here.
"""

from __future__ import annotations

import logging
import os

from agents import (
    Agent,
    ModelSettings,
    OpenAIChatCompletionsModel,
    Runner,
    RunContextWrapper,
    function_tool,
)

from lacquertutor.agent.context import LacquerTutorContext
from lacquertutor.llm.outputs import ExtractedSlots, IntentResult, VoIScores
from lacquertutor.models.contract import PlanContract
from lacquertutor.models.slots import HARD_GATE_SLOTS, SLOT_SCHEMA
from lacquertutor.modules.retrieval import EvidenceRetriever
from lacquertutor.modules.verifier import ContractVerifier
from lacquertutor.modules.voi_scorer import VoIScoringRecord


def _sub_agent(name: str, instructions: str, output_type=None) -> Agent:
    """Create a sub-agent reusing the global OpenAI client.

    Sub-agents use the same model/client configured via set_default_openai_client.
    They inherit the global chat completions mode.
    Uses qwen-plus by default (NOT qwen3.5-plus which is a thinking model
    that doesn't support structured output properly).
    """
    from agents import AgentOutputSchema

    model_name = os.environ.get("LACQUERTUTOR_LLM_MODEL", "qwen-plus")
    kwargs = dict(
        name=name,
        model=model_name,
        model_settings=ModelSettings(temperature=0.0),
        instructions=instructions,
    )
    if output_type:
        # Use non-strict schema for dict-based outputs (Qwen compatibility)
        kwargs["output_type"] = AgentOutputSchema(output_type, strict_json_schema=False)
    return Agent(**kwargs)


# ── Tool: Detect Intent ──────────────────────────────────────────

@function_tool
async def detect_intent(
    ctx: RunContextWrapper[LacquerTutorContext],
    user_query: str,
) -> str:
    """分析用户的漆艺问题，判断任务类型(planning/troubleshooting)、工作阶段和故障模式。
    将用户的感性描述（如"发白""发粘"）规范化为工艺术语标签，用于检索和计划生成。
    在对话开始时调用一次。

    Args:
        user_query: 用户的原始问题
    """
    agent = _sub_agent(
        "IntentDetector",
        instructions=(
            "你是漆艺工艺专家。分析用户问题，完成以下任务：\n\n"
            "1. **判断任务类型**: planning(制定计划) 或 troubleshooting(故障排查)\n"
            "2. **识别工作阶段**: preparation / coating / curing / polishing / finishing\n"
            "3. **故障模式规范化**: 将用户的感性描述规范化为以下标准标签之一：\n"
            "   - haze_whitening（发白/发雾/发灰/cloudy/milky）\n"
            "   - wrinkling（起皱/wrinkle/shrink）\n"
            "   - uneven_gloss（光泽不均/mottled/patchy）\n"
            "   - persistent_tackiness（发粘/不干/sticky/tacky after expected time）\n"
            "   - surface_contamination（污染/颗粒/dust/particles/fish eyes）\n"
            "   - bubbles（气泡/起泡/bubbling/pinholes）\n"
            "   - adhesion_failure（脱落/起皮/peeling/flaking）\n"
            "   - curing_anomaly（固化异常/异味/discoloration during cure）\n"
            "   - final_unevenness（最终不平整/orange peel/waviness）\n"
            "   planning 任务 failure_mode 为 null\n\n"
            "4. **感性→术语映射说明**: 简短说明用户的原始描述如何映射到标准标签\n\n"
            "请输出JSON格式：\n"
            '{"task_type": "...", "stage": "...", "failure_mode": "...", '
            '"normalization_note": "用户描述X→标准标签Y，因为..."}'
        ),
        output_type=IntentResult,
    )
    result = await Runner.run(agent, user_query)
    intent: IntentResult = result.final_output

    ctx.context.task_type = intent.task_type
    ctx.context.stage = intent.stage
    ctx.context.failure_mode = intent.failure_mode

    normalization = getattr(intent, 'normalization_note', '') or ''
    norm_line = f"规范化: {normalization}" if normalization else ""

    return (
        f"任务类型: {intent.task_type}, 阶段: {intent.stage}, "
        f"故障模式: {intent.failure_mode or '无'}"
        + (f"\n{norm_line}" if norm_line else "")
    )


# ── Tool: Extract Slots ──────────────────────────────────────────

@function_tool
async def extract_slots(
    ctx: RunContextWrapper[LacquerTutorContext],
    text: str,
) -> str:
    """从用户消息中提取漆艺相关变量值（如湿度、漆种、基底状态等）。每次用户回复后调用，更新已知变量状态。

    Args:
        text: 用户的消息文本
    """
    agent = _sub_agent(
        "SlotExtractor",
        instructions=(
            "你是漆艺信息提取专家。从用户消息中提取以下18个变量的值，请输出JSON格式：\n"
            "lacquer_system, substrate_material, substrate_condition, dilution_ratio_pct, "
            "environment_temperature_c, environment_humidity_pct, ventilation_quality, "
            "dust_control_level, curing_method, time_since_last_coat_h, available_time_days, "
            "coat_thickness, application_tool, layer_count_target, sanding_grit_last, "
            "prior_steps_known, target_finish, ppe_level\n\n"
            "规则：只提取明确提到的，不猜测。未提及的变量不要包含。"
        ),
        output_type=ExtractedSlots,
    )
    result = await Runner.run(agent, f"用户消息: {text}")
    extracted: ExtractedSlots = result.final_output

    count = 0
    for name, value in extracted.slots.items():
        if name in SLOT_SCHEMA and value and str(value).strip():
            ctx.context.slot_state.fill(
                name=name, value=str(value).strip(), source="user",
                confirmed=True, turn=ctx.context.questions_asked,
            )
            count += 1

    return (
        f"提取了 {count} 个变量。"
        f"已知: {ctx.context.filled_slots_json}。"
        f"未知: {ctx.context.unfilled_list}"
    )


# ── Tool: VoI Score Slots ────────────────────────────────────────

@function_tool
async def score_unfilled_slots(
    ctx: RunContextWrapper[LacquerTutorContext],
) -> str:
    """对所有未填变量进行VoI风险评分，确定下一个应该询问的变量。返回排序后的优先级列表和是否应继续提问的决策。"""
    c = ctx.context
    unfilled = c.slot_state.unfilled

    if not unfilled:
        return "所有变量已填充。建议直接 retrieve_evidence 然后生成计划。"

    if c.questions_asked >= c.max_questions:
        return f"已达最大问题数 ({c.max_questions})。停止提问，建议 retrieve_evidence 然后生成计划。"

    agent = _sub_agent(
        "VoIScorer",
        instructions=(
            "你是漆艺安全评估专家。对每个未知变量打分(0-3)，请输出JSON格式：\n"
            "3=安全门控（不知道就可能导致不可逆损失）\n"
            "2=计划影响（影响参数但不阻止安全执行）\n"
            "1=补充信息（影响很小）\n"
            "0=不相关\n"
            "同时说明下一个不可逆操作是什么。"
        ),
        output_type=VoIScores,
    )

    failure_line = f"故障模式: {c.failure_mode}" if c.failure_mode else "故障模式: 无"
    prompt = (
        f"用户任务: {c.original_query}\n"
        f"任务类型: {c.task_type}, 阶段: {c.stage}, {failure_line}\n"
        f"已知: {c.filled_slots_json}\n"
        f"未知变量: {', '.join(unfilled)}"
    )

    result = await Runner.run(agent, prompt)
    voi: VoIScores = result.final_output

    raw_scores = {s: max(0, min(3, voi.scores.get(s, 1))) for s in unfilled}
    adjusted = {s: max(sc, 2 * (1 if s in HARD_GATE_SLOTS else 0)) for s, sc in raw_scores.items()}

    hard_set = set(HARD_GATE_SLOTS)
    ranked = sorted(adjusted.items(), key=lambda x: (-x[1], -(1 if x[0] in hard_set else 0), x[0]))

    record = VoIScoringRecord(
        turn=c.questions_asked, raw_scores=raw_scores,
        adjusted_scores=adjusted, reasons=voi.reasons, ranked_list=ranked,
    )

    top_slot, top_score = ranked[0] if ranked else (None, 0)

    if top_score <= 1:
        record.decision = "stop"
        record.stop_reason = "low_priority"
        c.voi_logs.append(record)
        return f"所有剩余变量优先级低(最高分={top_score})。停止提问，建议 retrieve_evidence 然后生成计划。"

    record.selected_slot = top_slot
    record.decision = "ask"
    record.stop_reason = "continue"
    c.voi_logs.append(record)

    ranking_text = ", ".join(f"{s}={sc}" for s, sc in ranked[:5])
    gate_type = "硬门控" if top_slot in hard_set else "软门控"
    return (
        f"VoI评分完成。优先级: {ranking_text}。\n"
        f"建议下一个询问: {top_slot} (分数={top_score}, {gate_type})。\n"
        f"请用 ask_user_question 向用户询问 {top_slot}。"
    )


# ── Tool: Ask User Question ─────────────────────────────────────

@function_tool
async def ask_user_question(
    ctx: RunContextWrapper[LacquerTutorContext],
    question: str,
    slot_name: str,
) -> str:
    """向用户提出一个关于特定变量的针对性问题，并等待回答。用户回答后自动提取变量值。

    Args:
        question: 要向用户提出的问题文本
        slot_name: 这个问题针对的变量名
    """
    c = ctx.context

    if c.answer_fn is None:
        return "无法提问：没有用户交互回调。"

    c.questions_asked += 1
    answer = await c.answer_fn(question, slot_name)

    # Auto-extract slots
    agent = _sub_agent(
        "SlotExtractor",
        instructions=(
            "从用户消息中提取漆艺变量值，请输出JSON格式。18个变量：\n"
            "lacquer_system, substrate_material, substrate_condition, dilution_ratio_pct, "
            "environment_temperature_c, environment_humidity_pct, ventilation_quality, "
            "dust_control_level, curing_method, time_since_last_coat_h, available_time_days, "
            "coat_thickness, application_tool, layer_count_target, sanding_grit_last, "
            "prior_steps_known, target_finish, ppe_level\n"
            "只提取明确提到的。"
        ),
        output_type=ExtractedSlots,
    )
    result = await Runner.run(agent, f"用户消息: {answer}")
    extracted: ExtractedSlots = result.final_output

    for name, value in extracted.slots.items():
        if name in SLOT_SCHEMA and value and str(value).strip():
            c.slot_state.fill(name=name, value=str(value).strip(), source="user",
                              confirmed=True, turn=c.questions_asked)

    return (
        f"用户回答: {answer}\n"
        f"已知: {c.filled_slots_json}\n"
        f"未知: {c.unfilled_list}\n"
        f"已问 {c.questions_asked}/{c.max_questions} 个问题"
    )


# ── Tool: Retrieve Evidence ──────────────────────────────────────

@function_tool
async def retrieve_evidence(
    ctx: RunContextWrapper[LacquerTutorContext],
) -> str:
    """根据当前任务上下文检索相关的证据卡（工艺知识）。在准备生成计划之前调用。"""
    c = ctx.context

    # Prefer vector store (Qdrant + agentic RAG) when available
    if c.vector_store is not None:
        try:
            c.retrieved_evidence = await c.vector_store.retrieve(
                stage=c.stage,
                failure_mode=c.failure_mode,
                slot_state=c.slot_state.filled_dict,
                k=c.evidence_top_k,
            )
            return EvidenceRetriever.format_evidence_summaries(c.retrieved_evidence)
        except Exception as e:
            logging.getLogger("lacquertutor.tools").warning(
                "Vector retrieval failed (%s), falling back to metadata", e
            )

    # Fallback: metadata-based retrieval
    retriever = EvidenceRetriever(c.evidence_store)
    c.retrieved_evidence = retriever.retrieve(
        stage=c.stage, failure_mode=c.failure_mode,
        slot_state=c.slot_state.filled_dict, k=c.evidence_top_k,
    )

    return EvidenceRetriever.format_evidence_summaries(c.retrieved_evidence)


# ── Tool: Generate Plan ──────────────────────────────────────────

@function_tool
async def generate_plan(
    ctx: RunContextWrapper[LacquerTutorContext],
) -> str:
    """基于已收集的变量和证据，生成可执行的漆艺计划合同。必须在 retrieve_evidence 之后调用。"""
    c = ctx.context
    log = logging.getLogger("lacquertutor.tools.generate_plan")

    evidence_text = EvidenceRetriever.format_evidence_summaries(c.retrieved_evidence)
    failure_line = f"故障模式: {c.failure_mode}" if c.failure_mode else "故障模式: 无"

    prompt = (
        f"用户问题: {c.original_query}\n"
        f"任务类型: {c.task_type}, 阶段: {c.stage}, {failure_line}\n\n"
        f"已确认变量:\n{c.filled_slots_json}\n\n"
        f"未填充变量: {c.unfilled_list}\n"
        f"未填充硬门控: {c.unfilled_hard_gates_list}\n\n"
        f"可用证据卡:\n{evidence_text}"
    )

    planner = _sub_agent(
        "ContractPlanner",
        instructions=(
            "你是漆艺计划生成器。请输出JSON格式的可执行计划合同，包含六部分：\n"
            "A. assumptions — 已知条件列表 (slot_name, value, confirmed, note)\n"
            "B. missing_critical_slots — 缺失的关键变量名列表\n"
            "C. steps — 有序操作步骤列表 (step_number, action, parameters, timing_window, checkpoint_id, evidence_refs, is_irreversible)\n"
            "D. high_risk_warnings — 高风险警告列表 (label, action, requires_slots, required_checkpoint, consequence)\n"
            "E. checkpoints — 检查点列表 (checkpoint_id, description, evidence_refs)\n"
            "F. contingencies — 应急预案列表 (condition, action, recheck_checkpoint, evidence_refs)\n\n"
            "## 安全规则\n"
            "- 不可逆步骤(is_irreversible=true)必须有checkpoint_id和evidence_refs\n"
            "- 只使用提供的证据卡ID，不编造\n"
            "- 每个不可逆步骤应在high_risk_warnings中有对应条目\n"
            "- 至少为主要操作步骤设置检查点\n"
            "- 至少为可能失败的步骤设置应急预案\n\n"
            "## 完整示例\n"
            '{"assumptions": [\n'
            '  {"slot_name": "lacquer_system", "value": "urushi", "confirmed": true, "note": "用户确认使用大漆"},\n'
            '  {"slot_name": "substrate_material", "value": "wood", "confirmed": true, "note": "木质基底"},\n'
            '  {"slot_name": "environment_humidity_pct", "value": "75", "confirmed": true, "note": "湿度适宜"}\n'
            '],\n'
            '"missing_critical_slots": ["ppe_level"],\n'
            '"steps": [\n'
            '  {"step_number": 1, "action": "基底打磨", "parameters": "320目砂纸，顺纹方向打磨至光滑", '
            '"timing_window": "无特殊要求", "checkpoint_id": "CP-01", "evidence_refs": ["E-PREP-01"], "is_irreversible": false},\n'
            '  {"step_number": 2, "action": "除尘清洁", "parameters": "用湿布擦拭，待完全干燥", '
            '"timing_window": "打磨后15分钟内", "checkpoint_id": null, "evidence_refs": ["E-PREP-01"], "is_irreversible": false},\n'
            '  {"step_number": 3, "action": "涂布底漆", "parameters": "薄涂大漆，刷子均匀涂布", '
            '"timing_window": "清洁后1小时内", "checkpoint_id": "CP-02", "evidence_refs": ["E-APPL-01"], "is_irreversible": true},\n'
            '  {"step_number": 4, "action": "湿室固化", "parameters": "温度20-25°C，湿度70-80%RH", '
            '"timing_window": "涂布后立即", "checkpoint_id": "CP-03", "evidence_refs": ["E-CURE-01"], "is_irreversible": false}\n'
            '],\n'
            '"high_risk_warnings": [\n'
            '  {"label": "底漆不可逆", "action": "涂布底漆", "requires_slots": ["lacquer_system", "substrate_condition"], '
            '"required_checkpoint": "CP-02", "consequence": "底漆封闭后无法修改基底处理，需打磨重做"}\n'
            '],\n'
            '"checkpoints": [\n'
            '  {"checkpoint_id": "CP-01", "description": "表面均匀无油渍、无粉尘残留", "evidence_refs": ["E-PREP-01"]},\n'
            '  {"checkpoint_id": "CP-02", "description": "漆膜均匀无气泡、无流挂、厚度适中", "evidence_refs": ["E-APPL-01"]},\n'
            '  {"checkpoint_id": "CP-03", "description": "漆膜触干、指压无痕", "evidence_refs": ["E-CURE-01"]}\n'
            '],\n'
            '"contingencies": [\n'
            '  {"condition": "底漆出现气泡", "action": "停止涂布，用刮刀轻刮气泡，待干后补涂", '
            '"recheck_checkpoint": "CP-02", "evidence_refs": ["E-APPL-01"]},\n'
            '  {"condition": "固化后漆面发白", "action": "检查湿度是否偏低，必要时增加湿度重新固化", '
            '"recheck_checkpoint": "CP-03", "evidence_refs": ["E-CURE-01"]}\n'
            ']}'
        ),
        output_type=PlanContract,
    )

    # Retry with feedback on validation failures (max 2 retries)
    max_retries = 2
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if attempt == 0:
                result = await Runner.run(planner, prompt)
            else:
                # Feed error back for correction
                retry_prompt = (
                    f"{prompt}\n\n"
                    f"上次生成失败，错误: {last_error}\n"
                    f"请修正JSON格式后重新输出完整的计划合同。"
                )
                result = await Runner.run(planner, retry_prompt)

            contract: PlanContract = result.final_output
            contract.task_type = c.task_type
            contract.stage = c.stage
            c._generated_contract = contract

            summary = (
                f"计划生成完成！\n"
                f"- 步骤数: {len(contract.steps)}\n"
                f"- 检查点: {len(contract.checkpoints)}\n"
                f"- 应急预案: {len(contract.contingencies)}\n"
                f"- 高风险警告: {len(contract.high_risk_warnings)}\n"
                f"- 假设: {len(contract.assumptions)}\n"
                f"- 缺失关键变量: {contract.missing_critical_slots}"
            )
            return summary

        except Exception as e:
            last_error = str(e)
            log.warning(f"Plan generation attempt {attempt + 1} failed: {last_error}")
            if attempt == max_retries:
                # Fallback: minimal contract with unconfirmed assumptions
                log.error(f"All {max_retries + 1} attempts failed. Producing minimal contract.")
                from lacquertutor.models.contract import Assumption, PlanStep

                contract = PlanContract(
                    task_type=c.task_type,
                    stage=c.stage,
                    stop_reason="planner_failure",
                    assumptions=[
                        Assumption(
                            slot_name=name,
                            value=val.value,
                            confirmed=val.confirmed,
                            note="自动生成（计划器失败后回退）",
                        )
                        for name, val in c.slot_state.filled.items()
                    ],
                    missing_critical_slots=c.slot_state.unfilled_hard_gates,
                    steps=[
                        PlanStep(
                            step_number=1,
                            action="计划生成失败，请检查输入并重试",
                            parameters="N/A",
                        )
                    ],
                )
                c._generated_contract = contract
                return f"计划生成失败（{max_retries + 1}次尝试）。已生成最小回退合同。错误: {last_error}"


# ── Tool: Verify Plan ────────────────────────────────────────────

@function_tool
async def verify_plan(
    ctx: RunContextWrapper[LacquerTutorContext],
) -> str:
    """验证已生成的计划合同是否满足安全、结构和证据要求。必须在 generate_plan 之后调用。如果验证失败，返回具体问题和修改建议。"""
    contract = getattr(ctx.context, '_generated_contract', None)
    if contract is None:
        return "尚未生成计划合同。请先调用 generate_plan。"

    verifier = ContractVerifier()
    result = verifier.verify(contract, ctx.context.slot_state)

    if result.passed:
        return "验证通过。所有安全、结构和证据检查均满足。"

    issues = []
    for issue in result.issues:
        icon = "ERROR" if issue.severity == "error" else "WARN"
        issues.append(f"[{icon}/{issue.category}] {issue.description}")

    ctx.context.revision_count += 1

    return (
        f"验证未通过（修订轮次 {ctx.context.revision_count}/{ctx.context.max_revisions}）:\n"
        + "\n".join(issues)
        + "\n\n建议：请根据上述问题重新调用 generate_plan 修正计划。"
    )
