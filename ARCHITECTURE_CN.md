# LacquerTutor 技术架构文档

> 本文档面向开发者和论文审稿人，详细说明 LacquerTutor Agent 的技术架构、Multi-Agent 实现方式、核心技术选型及各模块间的协作关系。

---

## 1. 整体架构概览

LacquerTutor 是一个**合同驱动的混合主动对话 Agent**（Contract-Centered Mixed-Initiative Agent），采用 **Plan-and-Execute + Agentic RAG** 架构。系统不是一个简单的问答聊天机器人，而是一个能够主动提问、检索证据、生成结构化计划、验证安全性的自主智能体。

```
用户查询
  ↓
┌─────────────────────────────────────────────────────┐
│             TriageAgent（路由代理）                    │
│  "判断任务类型，转交给对应专家"                         │
│                                                      │
│  handoff →  DialogueAgent（对话代理）                  │
│             ├── detect_intent      意图检测            │
│             ├── extract_slots      变量提取            │
│             ├── score_unfilled     VoI 评分            │
│             └── ask_user_question  向用户提问           │
│                                                      │
│  handoff →  PlanningAgent（计划代理）                   │
│             ├── retrieve_evidence  检索证据            │
│             ├── generate_plan      生成合同            │
│             └── verify_plan        验证安全            │
│                                                      │
│  handoff →  TroubleshootingAgent（排查代理）            │
│             ├── retrieve_evidence  检索证据            │
│             ├── generate_plan      生成恢复计划        │
│             └── verify_plan        验证安全            │
└─────────────────────────────────────────────────────┘
  ↓
可执行计划合同（JSON，六部分 A-F）
```

---

## 2. 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **Agent 框架** | OpenAI Agents SDK v0.12+ (`openai-agents`) | Agent 编排、工具调用、Handoff、结构化输出 |
| **LLM** | 通义千问 Qwen-Plus（DashScope OpenAI 兼容 API） | 对话、推理、计划生成 |
| **嵌入模型** | Qwen text-embedding-v3（DashScope） | 知识库向量化，1024 维 |
| **重排序** | gte-rerank-v2（DashScope） | Cross-encoder 精排 |
| **向量数据库** | Qdrant（支持内存模式 + 服务器模式） | 稠密向量检索 + 元数据过滤 |
| **数据模型** | Pydantic v2 | 18 变量 Slot Schema、计划合同 Schema、验证规则 |
| **配置管理** | pydantic-settings | 环境变量 / `.env` 自动加载 |
| **持久化** | SQLite + aiosqlite | 会话存储（Session + Message） |
| **CLI** | Typer + Rich | 终端交互、面板渲染、进度显示 |
| **日志** | structlog | 结构化 JSON 审计日志 |
| **链路追踪** | 自定义 `StructlogTracingProcessor` | 替换 SDK 默认的 OpenAI Trace 导出器 |
| **容错** | tenacity | 指数退避重试（API 429/500） |
| **测试** | pytest + pytest-asyncio | 48 单元测试 + 2 集成测试 |
| **统计分析** | scipy | Wilcoxon 符号秩检验 + BH 校正 |

---

## 3. Multi-Agent 架构详解

### 3.1 为什么用 Multi-Agent？

论文描述了 5 个模块的管线架构。如果把所有 7 个工具放在一个 Agent 上，LLM 的工具选择准确率会下降（研究表明 ≤4 个工具时选择最准确）。拆分成专家 Agent 后：

- **每个 Agent 只看到 3-4 个工具**，选择更精准
- **职责单一**，Instructions 更聚焦，减少 LLM 混淆
- **可独立更新**，改一个 Agent 不影响其他
- **与论文架构一一对应**，便于验证和对比

### 3.2 为什么选 OpenAI Agents SDK 而不是 LangGraph / CrewAI？

| 方案 | 优点 | 缺点 | 选择原因 |
|------|------|------|---------|
| **OpenAI Agents SDK** | 原生 `handoffs=[]`，天然适合顺序路由；`RunContextWrapper` 共享状态；已在用 | 生态较新 | **选择** — 已有 7 个 `@function_tool`，无需重写 |
| LangGraph | 强大的 StateGraph，适合复杂 DAG | 需要重写全部工具和上下文；过度设计（我们是线性路由，不是 DAG） | 不选 |
| CrewAI | 适合多 Agent 自主协作 | 设计为 Agent 间自由对话；我们需要的是顺序路由 + 共享状态 | 不选 |

### 3.3 Handoff 机制实现

OpenAI Agents SDK 的 `handoff()` 本质是把目标 Agent 注册为一个特殊的 Tool。当 LLM 决定 "该交给下一个专家了"，它调用 `transfer_to_planning_agent` 这个工具，SDK 自动切换当前 Agent。

**核心代码（`orchestrator.py`）：**

```python
from agents import Agent, handoff, Runner

# 1. 创建各专家 Agent（注意循环依赖的解法）
planning_agent = create_planning_agent(model, dialogue_agent_ref)
troubleshooting_agent = create_troubleshooting_agent(model, dialogue_agent_ref)
dialogue_agent = create_dialogue_agent(model, planning_agent, troubleshooting_agent)

# 2. 补上反向 Handoff（验证失败 → 回到对话补充提问）
back_handoff = handoff(
    dialogue_agent,
    tool_description_override="移交回对话代理以收集更多信息。"
)
planning_agent.handoffs = [back_handoff]
troubleshooting_agent.handoffs = [back_handoff]

# 3. Triage 是入口
triage_agent = create_triage_agent(model, dialogue_agent)

# 4. 运行
await Runner.run(
    starting_agent=triage_agent,
    input=user_query,
    context=lacquertutor_context,  # RunContextWrapper，所有 Agent 共享
    max_turns=80,
)
```

### 3.4 条件 Handoff（`is_enabled` 谓词）

不是任何时候都能移交——DialogueAgent 只有在检测到意图后才能移交给 PlanningAgent：

```python
def can_handoff_to_planning(ctx: RunContextWrapper[LacquerTutorContext], agent: Agent) -> bool:
    return ctx.context.task_type == "planning"

handoff(
    planning_agent,
    is_enabled=can_handoff_to_planning,  # 返回 False 时，LLM 完全看不到这个选项
    tool_description_override="当信息收集完成后，移交给计划生成代理。"
)
```

当 `is_enabled` 返回 `False`，这个 Handoff 工具**完全从 LLM 的工具列表中消失**，LLM 无法调用也无法看到它。

### 3.5 共享状态（`RunContextWrapper`）

所有 Agent 共享同一个 `LacquerTutorContext` 对象，通过 `RunContextWrapper` 传递。这个对象不会发送给 LLM——它是本地内存中的状态容器。

```python
@dataclass
class LacquerTutorContext:
    evidence_store: EvidenceStore      # 注入的证据库
    answer_fn: AnswerFn | None         # 用户交互回调
    slot_state: SlotState              # 18 个变量的当前状态
    task_type: str                     # planning / troubleshooting
    stage: str                         # preparation / coating / ...
    questions_asked: int               # 已问问题数
    retrieved_evidence: list           # 检索到的证据卡
    voi_logs: list[VoIScoringRecord]   # VoI 评分审计日志
    # ... 更多字段
```

DialogueAgent 的 `extract_slots` 工具写入 `ctx.context.slot_state`，PlanningAgent 的 `generate_plan` 工具读取同一个 `slot_state`——状态自动在 Agent 之间传递，无需消息传递或序列化。

---

## 4. 7 个 Agent 工具（@function_tool）

每个工具是一个 `@function_tool` 装饰的 async 函数，内部调用 Sub-Agent（LLM）或确定性逻辑：

| 工具 | 所属 Agent | 内部实现 | 输出 |
|------|-----------|---------|------|
| `detect_intent` | Dialogue | Sub-Agent → `IntentResult` (Pydantic) | 任务类型 + 阶段 + 故障模式 |
| `extract_slots` | Dialogue | Sub-Agent → `ExtractedSlots` (Pydantic) | 从文本中提取的变量键值对 |
| `score_unfilled_slots` | Dialogue | Sub-Agent → `VoIScores` + **确定性调整** | 优先级排序 + 是否继续提问 |
| `ask_user_question` | Dialogue | 回调函数 `answer_fn` + 自动提取 | 用户回答 + 更新 slot_state |
| `retrieve_evidence` | Planning / Troubleshooting | `EvidenceStore.retrieve()` | Top-k 证据卡 |
| `generate_plan` | Planning / Troubleshooting | Sub-Agent → `PlanContract` + **重试逻辑** | 六部分计划合同 JSON |
| `verify_plan` | Planning / Troubleshooting | `ContractVerifier`（纯规则，无 LLM） | 通过/失败 + 问题列表 |

**关键设计：Sub-Agent 模式**

工具内部不是直接调用 LLM API，而是创建一个 Sub-Agent（有自己的 Instructions 和 `output_type`），让 SDK 处理 JSON Schema 强制和结构化输出解析：

```python
@function_tool
async def detect_intent(ctx: RunContextWrapper[LacquerTutorContext], user_query: str) -> str:
    agent = Agent(
        name="IntentDetector",
        model="qwen-plus",
        instructions="你是漆艺工艺专家。分析用户问题...",
        output_type=AgentOutputSchema(IntentResult, strict_json_schema=False),
    )
    result = await Runner.run(agent, user_query)
    intent: IntentResult = result.final_output
    ctx.context.task_type = intent.task_type  # 写入共享状态
    return f"任务类型: {intent.task_type}"
```

---

## 5. VoI 评分系统

### 5.1 三阶段管线

论文的核心创新之一。对每个未填变量评估 "现在问这个问题的信息价值"：

```
阶段 1: LLM 风险评分
  每个未填变量 → r(s) ∈ {0, 1, 2, 3}
  3 = 安全门控（不知道就可能导致不可逆损失）
  2 = 计划影响（影响参数但不阻止安全执行）
  1 = 补充信息
  0 = 不相关

阶段 2: 确定性硬门控调整
  r̃(s) = max(r(s), 2·g(s))
  其中 g(s) = 1 当该变量是硬门控变量
  → 硬门控变量永远不会低于 2 分

阶段 3: 排序 + 停止判断
  按 r̃(s) 降序排列（同分时硬门控优先）
  停止条件：已问 6 题 / 最高分 ≤ 1 / 全部填充
```

### 5.2 18 变量 Slot Schema

与论文 Table 1 的分类对齐，名称与 benchmark `taskset_v0.json` 完全一致：

| 类别 | 变量名 | 门控级别 |
|------|--------|---------|
| **材料** | `lacquer_system` | 硬门控 |
| | `substrate_material` | 硬门控 |
| | `substrate_condition` | 硬门控 |
| | `dilution_ratio_pct` | 软 |
| **环境** | `environment_temperature_c` | 硬门控 |
| | `environment_humidity_pct` | 硬门控 |
| | `ventilation_quality` | 软 |
| | `dust_control_level` | 软 |
| **时间/固化** | `curing_method` | 硬门控 |
| | `time_since_last_coat_h` | 硬门控 |
| | `available_time_days` | 软 |
| **工艺** | `coat_thickness` | 软 |
| | `application_tool` | 软 |
| | `layer_count_target` | 软 |
| | `sanding_grit_last` | 软 |
| | `prior_steps_known` | 软 |
| | `target_finish` | 软 |
| **安全** | `ppe_level` | 硬门控 |

**8 个硬门控 + 10 个软变量 = 18 个**

---

## 6. 检索管线（Agentic RAG）

### 6.1 架构

```
用户查询 + Slot 上下文
  ↓
[Qwen text-embedding-v3] → 1024 维稠密向量
  ↓
[Qdrant 向量检索] + 元数据过滤（stage, failure_mode）→ Top-20
  ↓
[gte-rerank-v2 Cross-Encoder] → Top-4
  ↓
[相关性评估 Agent] → 是否足够相关？
  ├── 是 → 返回 Top-4 证据卡
  └── 否 → [查询改写 Agent] → 重新检索（最多 2 次）
```

### 6.2 知识库

从 Dify 的 PostgreSQL 数据库直接导出：

| 知识库 | 分段方式 | 段落数 | 内容 |
|--------|---------|--------|------|
| fuzi-kb | 父子分段 | 2,246 | 漆艺教材、工艺手册 |
| tongyong-kb | 通用分段 | 2,976 | 通用漆艺百科、历史、材料学 |
| **合计** | | **5,222** | |

### 6.3 回退机制

当 Qdrant 不可用时（未安装 `qdrant-client` 或未运行服务），自动回退到基于元数据的内存检索（`EvidenceStore.retrieve()`），使用 stage/failure_mode 匹配 + 得分排序。

---

## 7. 计划合同 Schema（A-F 六部分）

输出的核心制品是一个 Pydantic 验证的 JSON 结构：

```json
{
  "assumptions": [
    {"slot_name": "lacquer_system", "value": "urushi", "confirmed": true, "note": "用户确认"}
  ],
  "missing_critical_slots": ["ppe_level"],
  "steps": [
    {
      "step_number": 1,
      "action": "基底打磨",
      "parameters": "320目砂纸，顺纹方向",
      "timing_window": "无特殊要求",
      "checkpoint_id": "CP-01",
      "evidence_refs": ["E-PREP-01"],
      "is_irreversible": false
    }
  ],
  "high_risk_warnings": [
    {
      "label": "首涂不可逆",
      "action": "涂布底漆",
      "requires_slots": ["lacquer_system", "substrate_condition"],
      "required_checkpoint": "CP-02",
      "consequence": "底漆封闭后无法修改基底处理"
    }
  ],
  "checkpoints": [
    {"checkpoint_id": "CP-01", "description": "表面均匀无油渍", "evidence_refs": ["E-PREP-01"]}
  ],
  "contingencies": [
    {
      "condition": "底漆出现气泡",
      "action": "停止涂布，刮除气泡后重新薄涂",
      "recheck_checkpoint": "CP-02",
      "evidence_refs": ["E-APPL-01"]
    }
  ]
}
```

### 验证器（纯规则，无 LLM）

`ContractVerifier` 执行三类检查：

- **安全检查**：不可逆步骤有检查点？未确认的硬门控变量阻止了不可逆操作？
- **结构检查**：步骤编号连续？阶段顺序合理？
- **证据检查**：不可逆步骤有证据引用？检查点有证据支撑？

验证失败 → 触发修订循环（最多 2 次），修订动作包括：重新提问、补充检索、保守重写。

---

## 8. 生产特性

### 8.1 会话持久化

```
SessionStore (SQLite)
  ├── sessions 表：session_id, user_id, status, context_json
  └── messages 表：message_id, session_id, role, content, tool_name
```

`LacquerTutorContext` 支持 `to_json()` / `from_json()` 序列化，可存入 `context_json` 字段，实现跨会话恢复。

### 8.2 安全护栏（Guardrails）

| 护栏 | 类型 | 触发条件 |
|------|------|---------|
| `safety_bypass_guardrail` | 输入 | 用户试图跳过安全步骤（"跳过检查"、"skip safety"） |
| `off_topic_guardrail` | 输入 | 用户问题与漆艺无关 |
| `evidence_grounding_guardrail` | 输出 | 不可逆步骤缺少证据引用 |
| `hallucination_guardrail` | 输出 | 引用了不存在的证据 ID |

使用 SDK 原生 `@input_guardrail` / `@output_guardrail` 装饰器，触发时抛出 `GuardrailTripwireTriggered`。

### 8.3 链路追踪

自定义 `StructlogTracingProcessor` 替换 SDK 默认的 OpenAI 导出器（DashScope 不支持 OpenAI Trace API）。每个 Span 记录：Agent 名称、工具调用（输入/输出/耗时）、LLM 调用、Handoff 事件。

### 8.4 容错

- **指数退避重试**：`tenacity` 库，处理 DashScope 429/500/502/503
- **熔断器**：`CircuitBreaker`，最大 80 轮 + 每会话 $5 成本上限
- **优雅降级**：计划生成失败 3 次后，返回最小合同（标注 `stop_reason=planner_failure`）

---

## 9. 评估体系

### 5 个实验条件

| 条件 | 对话 | 变量选择策略 | 验证器 |
|------|------|------------|--------|
| B1 | 无 | — | 无 |
| B2-random | 有 | 随机选择 | 无 |
| B2-prompt | 有 | LLM 内部推理（原始分数） | 无 |
| B2-VoI | 有 | VoI 三阶段评分 | 无 |
| **S2** | **有** | **VoI 三阶段评分** | **有** |

### 7 个评估指标（M1-M7）

| 指标 | 含义 | 方向 |
|------|------|------|
| M1 | 不可逆门控合规率 | ↑ |
| M2 | 关键缺失变量数 | ↓ |
| M3a | 检查点覆盖率 | ↑ |
| M3b | 应急预案覆盖率 | ↑ |
| M4a | 证据覆盖率 | ↑ |
| M4b | 无证据关键决策数 | ↓ |
| M5 | 内部一致性问题数 | ↓ |
| M6 | 提问效率 | — |
| M7 | 模板合规（能否解析为合同） | ↑ |

### Oracle 模拟器

用 `hidden_slot_values`（每个任务的地面真值）自动回答 Agent 的提问，无需人工参与即可批量评估。

---

## 10. 目录结构一览

```
src/lacquertutor/
├── agent/
│   ├── agents/          ← Multi-Agent 专家定义
│   │   ├── triage.py        路由代理
│   │   ├── dialogue.py      对话代理（4 工具）
│   │   ├── planning.py      计划代理（3 工具）
│   │   └── troubleshooting.py 排查代理（3 工具）
│   ├── orchestrator.py  ← 统一入口（单 Agent / Multi-Agent 两种模式）
│   ├── tools.py         ← 7 个 @function_tool
│   ├── context.py       ← 共享状态 RunContextWrapper
│   ├── guardrails.py    ← 4 个安全护栏
│   └── resilience.py    ← 重试 + 熔断器
├── models/              ← Pydantic 领域模型
│   ├── slots.py             18 变量 Schema
│   ├── contract.py          计划合同 A-F
│   └── evidence.py          证据卡 + 内存检索
├── retrieval/           ← Qdrant 检索管线
│   ├── embedder.py          向量嵌入
│   ├── indexer.py           索引构建
│   ├── hybrid_search.py     混合检索
│   ├── reranker.py          交叉编码器重排
│   ├── agentic_rag.py       自修正检索循环
│   └── store.py             VectorEvidenceStore
├── storage/             ← SQLite 会话持久化
├── observability/       ← 链路追踪 + 成本跟踪
├── eval/                ← 评估框架（Oracle + M1-M7 + 统计）
├── llm/                 ← LLM 客户端 + Prompt 模板
└── cli/                 ← Typer 命令行（chat/run/eval/index）
```
