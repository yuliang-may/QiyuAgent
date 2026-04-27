# LacquerTutor 工程交付规格书

## 1. 文档目标

这份文档用于把 [PRODUCT_PRD_CN.md](D:/qiyupaper/lacquertutor/PRODUCT_PRD_CN.md) 转成可执行的工程交付标准。

适用对象：

- 产品经理
- 设计师
- 前端工程师
- 后端工程师
- Agent / LLM 工程师
- QA / 测试工程师
- 运维 / 发布负责人

交付目标：

1. 让团队可以直接拆任务开工。
2. 让设计、研发、测试使用同一套定义。
3. 让 V1 版本具备真正上线所需的边界、验收和稳定性标准。

---

## 2. V1 交付结论

### 2.1 V1 产品定义
V1 必须交付为一个**可持续使用的项目式 AI 工作台**，而不是一次性聊天 demo。

V1 的用户价值闭环：

1. 用户创建一个“制作项目”或“排障项目”。
2. 系统理解目标或问题，主动补问关键缺口。
3. 系统生成一个可执行方案，明确能做什么、不能做什么、先确认什么。
4. 用户按步骤执行，并可暂停、继续、记录。
5. 项目结束后形成可复用记录。

### 2.2 V1 必须满足的上线标准

- 有稳定的 Web UI，不是命令行。
- 有项目概念，不是单轮对话。
- 有结构化状态存储，不依赖上下文窗口记忆。
- 有规则化安全门控，不允许模型自由放行不可逆步骤。
- 有结构化输出，不靠后处理猜 JSON。
- 有日志、trace、评测、告警和回归测试。

---

## 3. 范围定义

### 3.1 V1 In Scope

- 首页
- 新建项目
- 项目工作台
- 执行清单页
- 知识卡详情页
- 项目列表与项目恢复
- Prompt 驱动的动态追问
- 基于知识库的证据检索
- 可执行方案生成
- 安全停步
- 项目级状态持久化
- 审计日志
- 基础管理后台

### 3.2 V1 Out of Scope

- 社区动态流
- 用户互相关注 / 私信
- 电商下单
- 全自动图像质检
- 复杂多角色审批流
- 实时多人协同编辑
- 多语言国际化

---

## 4. 产品模块拆解

### 4.1 前台模块

#### 模块 A：首页
目标：让用户 30 秒内知道产品能做什么，并进入项目创建。

关键组件：

- Hero 区域
- 两个主入口卡片：`开始制作`、`排查问题`
- 最近项目列表
- 常见问题快捷入口

#### 模块 B：新建项目
目标：收集创建项目的最小信息。

输入：

- 项目类型：`planning` / `troubleshooting`
- 自然语言描述
- 可选图片上传
- 项目名称

输出：

- `project_id`
- 初始项目状态
- 初始消息记录

#### 模块 C：项目工作台
目标：完成“理解 -> 追问 -> 检索 -> 生成方案”的核心闭环。

布局：

- 左栏：项目上下文 / 关键条件 / 当前门控
- 中栏：对话区 / 系统追问 / 用户回复
- 右栏：证据卡 / 方案卡 / 风险提示

#### 模块 D：执行清单页
目标：支持真正执行，而不是只看建议。

关键组件：

- 步骤列表
- 步骤状态：`pending / blocked / ready / done / failed`
- 检查点确认
- 备注和图片记录
- 暂停 / 继续

#### 模块 E：知识卡详情页
目标：建立用户信任。

关键内容：

- 卡片标题
- 摘要
- 适用阶段
- 适用条件
- 不适用边界
- 原始来源信息
- 与当前方案的关联步骤

### 4.2 后台模块

#### 模块 F：知识卡管理
- 新增知识卡
- 编辑知识卡
- 审核状态
- 标签管理
- 来源管理

#### 模块 G：项目查看
- 项目搜索
- 项目详情
- 失败案例筛选
- 风险拦截记录

---

## 5. 用户流

### 5.1 制作项目主流程

1. 用户进入首页
2. 点击 `开始制作`
3. 输入目标描述并创建项目
4. 系统抽取已知条件
5. 系统补问关键变量
6. 条件足够时生成方案
7. 用户进入执行清单
8. 用户确认检查点并推进步骤
9. 用户完成项目并归档

### 5.2 排障项目主流程

1. 用户进入首页
2. 点击 `排查问题`
3. 输入问题描述并上传图片
4. 系统识别故障模式与风险动作
5. 系统判断是否必须安全停步
6. 系统补问缺失信息
7. 系统生成修复方案或停步方案
8. 用户执行、反馈结果、归档

### 5.3 项目恢复流程

1. 用户进入最近项目
2. 打开未完成项目
3. 系统恢复项目状态
4. 默认展示当前阶段、阻塞条件和下一步
5. 用户继续回复或直接进入执行

---

## 6. 状态机设计

### 6.1 项目状态机

项目状态：

- `draft`
- `intake_in_progress`
- `waiting_user_input`
- `retrieving_evidence`
- `plan_ready`
- `safe_stop`
- `execution_in_progress`
- `completed`
- `archived`
- `failed`

状态迁移：

1. `draft -> intake_in_progress`
2. `intake_in_progress -> waiting_user_input`
3. `waiting_user_input -> intake_in_progress`
4. `intake_in_progress -> retrieving_evidence`
5. `retrieving_evidence -> plan_ready`
6. `retrieving_evidence -> safe_stop`
7. `plan_ready -> execution_in_progress`
8. `execution_in_progress -> completed`
9. 任意状态 -> `failed`

### 6.2 步骤状态机

步骤状态：

- `pending`
- `blocked`
- `ready`
- `done`
- `skipped`
- `failed`

规则：

- 被门控变量阻塞的步骤必须为 `blocked`
- 通过检查点后才允许 `blocked -> ready`
- 用户确认执行后才允许 `ready -> done`

---

## 7. 系统架构

### 7.1 推荐架构

#### Frontend
- Next.js / React
- Tailwind 或等价设计系统
- Server actions 或 REST/JSON API

#### Backend API
- Python FastAPI
- 项目服务
- 会话服务
- 知识库服务
- Agent orchestration service

#### Agent Runtime
- Responses API / Agents SDK
- Structured outputs
- Prompt playbooks
- Rule engine

#### Storage
- PostgreSQL
- Object storage
- Vector DB
- Redis

#### Observability
- Structured logs
- Traces
- Metrics
- Alerting

### 7.2 服务边界

#### Service 1：Project Service
职责：

- 项目 CRUD
- 项目状态流转
- 步骤记录
- 检查点记录

#### Service 2：Conversation Service
职责：

- 消息写入
- 会话恢复
- prompt 输入组装
- trace 关联

#### Service 3：Knowledge Service
职责：

- 知识卡管理
- 检索接口
- 标签和来源管理

#### Service 4：Agent Service
职责：

- 任务理解
- 追问决策
- 方案生成
- 安全审查

#### Service 5：Policy Service
职责：

- 不可逆门控规则
- 违禁建议拦截
- 发布策略控制

---

## 8. AI 架构标准

### 8.1 V1 不强制多 Agent
V1 不以多 agent 数量为目标。

V1 推荐采用：

- 一个 orchestrator
- 四套 prompt workflow
- 一个 rule engine
- 一个结构化状态机

### 8.2 四个核心 prompt workflow

#### Workflow A：任务理解
输入：

- 用户最近消息
- 项目上下文
- 已知槽位

输出：

- `task_type`
- `stage`
- `failure_mode`
- `confidence`
- `extracted_slots`

#### Workflow B：缺口追问
输入：

- 当前目标
- 已知槽位
- 当前阶段
- 风险动作

输出：

- `should_ask_more`
- `question_text`
- `target_slot`
- `reason_for_user`
- `priority`

#### Workflow C：方案生成
输入：

- 项目上下文
- 已知条件
- 检索证据
- 当前安全状态

输出：

- `assumptions`
- `missing_critical_info`
- `steps`
- `warnings`
- `checkpoints`
- `contingencies`
- `safe_to_proceed`

#### Workflow D：安全审查
输入：

- 方案草稿
- 当前槽位
- 规则集

输出：

- `passed`
- `blocking_issues`
- `warnings`
- `required_user_confirmation`

### 8.3 AI 输出要求

- 所有关键输出必须是严格 schema
- 所有步骤必须带 `step_id`
- 所有检查点必须带 `checkpoint_id`
- 所有关键建议必须带 `evidence_refs`
- 任何不可逆步骤必须带 `blocking_requirements`

---

## 9. 数据模型

### 9.1 Project

字段：

- `id`
- `user_id`
- `title`
- `project_type`
- `status`
- `current_stage`
- `failure_mode`
- `current_blockers`
- `created_at`
- `updated_at`

### 9.2 Message

字段：

- `id`
- `project_id`
- `role`
- `content`
- `message_type`
- `trace_id`
- `created_at`

### 9.3 SlotState

字段：

- `project_id`
- `slot_name`
- `slot_value`
- `confidence`
- `source`
- `confirmed`
- `updated_at`

### 9.4 EvidenceCard

字段：

- `id`
- `title`
- `summary`
- `stage`
- `failure_mode`
- `applicable_conditions`
- `not_applicable_conditions`
- `source_type`
- `source_ref`
- `tags`
- `status`

### 9.5 PlanContract

字段：

- `id`
- `project_id`
- `version`
- `is_active`
- `safe_to_proceed`
- `stop_reason`
- `created_at`

### 9.6 PlanStep

字段：

- `id`
- `contract_id`
- `step_order`
- `title`
- `instruction`
- `parameters`
- `timing_window`
- `is_irreversible`
- `blocking_requirements`
- `status`

### 9.7 Checkpoint

字段：

- `id`
- `contract_id`
- `step_id`
- `title`
- `description`
- `confirmation_type`
- `status`

### 9.8 ExecutionLog

字段：

- `id`
- `project_id`
- `step_id`
- `event_type`
- `payload`
- `created_at`

---

## 10. API 设计

### 10.1 项目接口

#### `POST /api/projects`
用途：创建项目

请求体：

```json
{
  "title": "木胎亮光黑漆底",
  "project_type": "planning",
  "initial_message": "我想在木胎上做亮光黑漆底"
}
```

#### `GET /api/projects/{projectId}`
用途：获取项目详情

#### `GET /api/projects`
用途：获取项目列表

#### `POST /api/projects/{projectId}/resume`
用途：恢复项目

### 10.2 对话接口

#### `POST /api/projects/{projectId}/messages`
用途：发送用户消息并触发下一轮 workflow

响应：

```json
{
  "project_status": "waiting_user_input",
  "assistant_message": {
    "type": "question",
    "text": "请问固化时环境湿度大概是多少？"
  },
  "current_blockers": ["environment_humidity_pct"],
  "trace_id": "tr_123"
}
```

### 10.3 合同接口

#### `GET /api/projects/{projectId}/contract`
用途：获取当前激活方案

#### `POST /api/projects/{projectId}/contract/regenerate`
用途：重新生成方案

### 10.4 执行接口

#### `POST /api/projects/{projectId}/steps/{stepId}/complete`
用途：完成步骤

#### `POST /api/projects/{projectId}/checkpoints/{checkpointId}/confirm`
用途：确认检查点

#### `POST /api/projects/{projectId}/steps/{stepId}/block`
用途：手动阻塞步骤

### 10.5 知识库接口

#### `GET /api/evidence/{evidenceId}`
用途：获取证据详情

#### `POST /api/admin/evidence`
用途：创建知识卡

---

## 11. Prompt Playbook

### 11.1 Prompt 设计原则

- 不在 prompt 中暴露学术术语
- 用用户可理解的行动语言
- 明确禁止越过安全边界
- 先判断是否能做，再输出怎么做
- 每个 prompt 只负责一个决策

### 11.2 任务理解 Prompt 模板

目标：

- 识别任务类型
- 提取当前阶段
- 提取明确已知条件

约束：

- 不猜未出现信息
- 故障模式必须从白名单中选择
- 输出必须是 schema

### 11.3 追问 Prompt 模板

目标：

- 判断还缺哪些信息
- 只问当前最关键的一项

约束：

- 问题必须短
- 问题必须直接可答
- 必须说明“为什么现在需要这个信息”
- 不得一次并列多个问题

### 11.4 方案 Prompt 模板

目标：

- 生成一步步可执行方案

约束：

- 每步必须可执行
- 不可逆步骤必须显式标注
- 必须告诉用户现在不该做什么
- 不能用“视情况而定”作为空泛答案

### 11.5 安全审查 Prompt 模板

目标：

- 找出应该阻塞的地方

约束：

- 以保守优先
- 如果证据不足，则返回阻塞
- 如果缺少关键变量，则返回补问

---

## 12. 规则引擎

### 12.1 规则类型

- 硬门控规则
- 软提醒规则
- 证据覆盖规则
- 用户确认规则

### 12.2 典型硬门控规则

- 未知漆种时，不允许生成跨层修复建议
- 未知固化状态时，不允许建议打磨重涂
- 未知环境湿度时，不允许放行与固化直接相关的关键步骤
- 未知防护条件时，不允许给出高暴露风险操作建议

### 12.3 规则执行时机

- 任务理解后
- 追问前
- 方案生成后
- 步骤推进前

---

## 13. 前端交付标准

### 13.1 页面标准

- 支持桌面端优先
- 宽屏三栏布局
- 主要信息不超过两次点击
- 所有阻塞状态必须有明显视觉反馈

### 13.2 组件标准

必须有以下核心组件：

- 项目卡片
- 状态标签
- 关键条件卡
- 系统追问卡
- 证据卡
- 方案步骤卡
- 检查点卡
- 风险提示卡

### 13.3 空状态和异常状态

必须覆盖：

- 无项目
- 无证据
- 检索失败
- 方案生成失败
- 项目恢复失败
- 网络异常

---

## 14. 后端交付标准

### 14.1 基础要求

- 所有接口有 schema 校验
- 所有关键写操作具备幂等策略
- 所有错误返回统一错误码
- 所有状态变更有审计日志

### 14.2 性能目标

- 创建项目 P95 < 500ms
- 普通读取接口 P95 < 300ms
- 单轮 agent 响应首字节时间 < 3s
- 方案生成完整响应 < 15s

### 14.3 稳定性要求

- 失败重试策略
- 外部依赖降级策略
- Agent 超时保护
- 检索失败 fallback

---

## 15. 数据与存储标准

### 15.1 PostgreSQL
存储：

- 用户
- 项目
- 消息
- 槽位
- 合同
- 步骤
- 检查点
- 执行日志

### 15.2 Object Storage
存储：

- 用户上传图片
- 导出文件
- 知识卡附件

### 15.3 Vector Store
存储：

- 知识卡 embedding
- 案例 embedding
- 检索索引

### 15.4 Redis
用途：

- 短期缓存
- 限流
- 后台任务状态

---

## 16. 可观测性与运维

### 16.1 必须记录的日志

- 项目创建日志
- 消息发送日志
- prompt 调用日志
- 检索日志
- 规则命中日志
- 合同生成日志
- 步骤推进日志

### 16.2 必须记录的 trace

- 每轮 workflow trace
- prompt 输入输出 trace
- 工具调用 trace
- 状态迁移 trace

### 16.3 关键监控指标

- 方案生成成功率
- 安全停步占比
- prompt 失败率
- 检索空结果率
- 项目恢复成功率
- 步骤完成率

### 16.4 告警规则

- 连续 5 分钟方案生成失败率 > 20%
- 检索服务不可用
- API 错误率 > 5%
- 数据库连接异常

---

## 17. Evals 与测试

### 17.1 测试分层

#### 单元测试
- schema 校验
- 规则引擎
- 状态机
- API handler

#### 集成测试
- 项目创建到方案生成
- 方案生成到执行推进
- 项目恢复流程

#### Agent 回归测试
- 任务理解准确率
- 追问合理率
- 方案结构完整率
- 安全拦截准确率

#### E2E 测试
- 用户从首页完成一次制作项目
- 用户完成一次排障项目

### 17.2 必须有的评测集

- 制作任务集
- 排障任务集
- 高风险任务集
- 证据稀缺任务集
- 用户表达模糊任务集

### 17.3 核心验收指标

- 方案结构合法率 >= 99%
- 不可逆步骤误放行率 <= 1%
- 高风险案例拦截率 >= 95%
- 项目恢复成功率 >= 99%
- E2E 关键路径通过率 >= 95%

---

## 18. 安全与治理

### 18.1 安全底线

- 不输出明显跳过安全步骤的建议
- 不在关键变量缺失时放行不可逆动作
- 不伪造证据
- 不假装知道用户未提供的条件

### 18.2 权限与审计

- 管理后台操作必须记录审计日志
- 知识卡变更必须记录版本
- 合同版本必须可追溯

### 18.3 用户提示原则

- 告诉用户为什么拦截
- 告诉用户下一步该补什么信息
- 告诉用户当前安全可做的动作

---

## 19. 里程碑

### M1：产品骨架

- 首页
- 新建项目
- 项目列表
- 项目状态持久化

### M2：AI 核心闭环

- 任务理解
- 追问
- 检索
- 方案生成
- 安全审查

### M3：执行闭环

- 执行清单
- 检查点确认
- 项目恢复
- 导出

### M4：上线准备

- 回归评测
- 监控告警
- 压测
- 发布清单

---

## 20. 发布清单

上线前必须逐项通过：

- 前端设计验收通过
- 后端接口联调通过
- prompt 版本冻结
- 规则集冻结
- 回归评测通过
- 监控告警生效
- 日志和 trace 可用
- 数据备份策略验证
- 灰度发布方案确认
- 回滚方案确认

---

## 21. 工程验收 Definition of Done

某个需求只有在以下条件全部满足时才算完成：

1. PRD 已明确。
2. 设计稿已确认。
3. 前端已实现并联调。
4. 后端接口已完成并有 schema 校验。
5. Agent / prompt 输出已通过结构化验收。
6. 单元测试与集成测试通过。
7. 日志、trace、监控已接入。
8. QA 验收通过。
9. 文档已更新。

---

## 22. 一句话交付标准

LacquerTutor 的 V1 工程交付，不是“能跑一次 demo”，而是：

**一个有明确页面、有稳定状态机、有结构化 AI 输出、有安全门控、有项目恢复能力、有评测和上线标准的可上线产品。**
