"""Agent definitions using the OpenAI Agents SDK.

Each pipeline step is an Agent with typed output via output_type.
The SDK handles JSON schema enforcement and structured output parsing.

NOTE: Qwen requires the word "json" in prompts when using response_format.
All output_type agents include "请输出JSON" in their instructions.
"""

from __future__ import annotations

from agents import Agent, AgentOutputSchema, ModelSettings

from lacquertutor.llm.outputs import ExtractedSlots, IntentResult, VoIScores
from lacquertutor.models.contract import PlanContract


def _model_settings(temperature: float = 0.0) -> ModelSettings:
    return ModelSettings(temperature=temperature)


def create_intent_agent(model: str = "qwen3.5-plus") -> Agent:
    """Agent that detects task type, stage, and failure mode."""
    return Agent(
        name="IntentDetector",
        model=model,
        model_settings=_model_settings(),
        instructions="""\
你是漆艺工艺专家。分析用户的问题，判断任务类型和所处阶段。请输出JSON格式。

任务类型：
- planning: 用户想制定一个工艺流程计划
- troubleshooting: 用户遇到了工艺问题需要排查

工作阶段：
- preparation: 准备（打磨、除油、封底）
- coating: 涂装（刷漆、喷漆）
- curing: 固化（阴干、湿房）
- polishing: 打磨抛光
- finishing: 最终完成

故障模式（仅 troubleshooting）：
tackiness, wrinkling, haze, contamination, bubbles, runs, uneven_gloss,
dust, orange_peel, pinholes, fish_eye, adhesion_failure, cracking,
sand_through, polish_through, surface_unevenness, curing_anomaly""",
        output_type=IntentResult,
    )


def create_slot_extractor_agent(model: str = "qwen3.5-plus") -> Agent:
    """Agent that extracts slot values from user messages."""
    return Agent(
        name="SlotExtractor",
        model=model,
        model_settings=_model_settings(),
        instructions="""\
你是漆艺工艺信息提取专家。从用户消息中提取与漆艺相关的变量值。请输出JSON格式。

变量列表（18个）：
- lacquer_system: 漆种/体系 (urushi/synthetic_solvent/synthetic_two_part/water_based)
- substrate_material: 基底材料 (wood/metal/ceramic/plastic/composite)
- substrate_condition: 基底状态 (raw/previously_finished)
- dilution_ratio_pct: 稀释比例 (%)
- environment_temperature_c: 环境温度 (°C)
- environment_humidity_pct: 环境湿度 (RH%)
- ventilation_quality: 通风条件 (poor/limited/good)
- dust_control_level: 防尘等级 (low/medium/high)
- curing_method: 固化方式 (air/humidity_box/cabinet)
- time_since_last_coat_h: 距上次涂装时间 (小时)
- available_time_days: 可用时间 (天)
- coat_thickness: 涂层厚度 (thin/medium/thick)
- application_tool: 涂装工具 (brush/pad/spray)
- layer_count_target: 目标层数 (整数)
- sanding_grit_last: 上次砂纸目数 (整数)
- prior_steps_known: 前序步骤是否已知 (true/false)
- target_finish: 目标光泽度 (matte/semi_gloss/gloss)
- ppe_level: 个人防护 (basic_gloves/respirator)

规则：
1. 只提取用户消息中明确提到的信息
2. 不要猜测或推断未提及的变量
3. 值为空或无法确定时不要包含该变量""",
        output_type=AgentOutputSchema(ExtractedSlots, strict_json_schema=False),
    )


def create_voi_scorer_agent(model: str = "qwen3.5-plus") -> Agent:
    """Agent that scores unfilled slots for VoI priority."""
    return Agent(
        name="VoIScorer",
        model=model,
        model_settings=_model_settings(),
        instructions="""\
你是漆艺工艺安全评估专家。评估每个未知变量对"安全执行下一步"的信息价值。请输出JSON格式。

评分标准：

【3分 - 安全门控变量】
  该变量直接决定下一个不可逆操作是否安全。
  不知道就执行 → 可能导致不可逆损失。
  例：重涂前不知道湿度 → 可能发白/起皱。

【2分 - 计划影响变量】
  影响参数选择但不直接阻止安全执行。

【1分 - 补充信息变量】
  对安全决策影响很小。

【0分 - 当前不相关】
  与当前任务/阶段无关。

重要规则：
- 结合用户任务意图和工作流阶段判断
- 不可逆操作相关的 gate 变量必须是 3 分
- 故障排除时，与诊断最相关的缺失变量得高分
- 同时指出下一个不可逆操作是什么""",
        output_type=AgentOutputSchema(VoIScores, strict_json_schema=False),
    )


def create_question_agent(model: str = "qwen3.5-plus") -> Agent:
    """Agent that generates targeted questions for unfilled slots."""
    return Agent(
        name="QuestionGenerator",
        model=model,
        model_settings=_model_settings(temperature=0.3),
        instructions="""\
你是漆艺辅助系统的对话模块。针对一个特定的缺失变量，向用户提出一个简洁、有针对性的问题。

规则：
1. 每次只问一个问题，针对指定的变量
2. 用简单易懂的语言，新手能理解
3. 如果可能，给出常见选项帮助用户回答
4. 简要说明为什么需要这个信息（一句话，关联到安全/可行性）
5. 不要问用户已经告诉你的信息
6. 如果提示里提供了历史偏好，只能把它当作待确认经验，不能当作本次已知事实
7. 若历史偏好与当前变量强相关，优先用确认式问法，例如“这次还是水性木器漆吗？”""",
    )


def create_planner_agent(model: str = "qwen3.5-plus") -> Agent:
    """Agent that generates executable plan contracts (sections A-F)."""
    return Agent(
        name="ContractPlanner",
        model=model,
        model_settings=_model_settings(),
        instructions="""\
你是 LacquerTutor 的计划生成模块。根据用户需求和已知条件，生成可执行的漆艺工作流计划合同。请输出JSON格式。

计划合同包含六个部分（A-F），全部必须包含：

A. assumptions — 已知条件与假设
   列出所有已确认和未确认的变量值。未确认标 confirmed: false

B. missing_critical_slots — 缺失的关键变量列表

C. steps — 操作步骤（有序）
   每步: step_number, action, parameters, timing_window, checkpoint_id, evidence_refs, is_irreversible
   不可逆步骤必须标 is_irreversible: true 且关联检查点

D. high_risk_warnings — 高风险警告
   每个不可逆步骤: label, action, requires_slots, required_checkpoint, consequence

E. checkpoints — 检查点
   每个不可逆步骤前: checkpoint_id, description, evidence_refs

F. contingencies — 应急预案
   if-then 恢复分支: condition, action, recheck_checkpoint, evidence_refs

安全规则：
- 硬门控变量未确认 → 在不可逆步骤前停止并标为假设
- 不要编造证据引用，只用提供的证据卡 ID
- 优先保守：宁可多设检查点""",
        output_type=AgentOutputSchema(PlanContract, strict_json_schema=False),
    )
