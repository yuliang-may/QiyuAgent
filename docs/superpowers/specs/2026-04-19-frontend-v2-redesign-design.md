# LacquerTutor Frontend v2 — Design Spec

**Date:** 2026-04-19  
**Author:** Codex  
**Status:** Ready for implementation

---

## 1. 目标

把当前 FastAPI 直出的单文件前端重构为一个**聊天优先、抽屉承载结构化产物**的产品级前端，同时严格复用现有后端行为。

当前前端与接口真实基线：

- UI 入口：`src/lacquertutor/web/index.html`
- 前端逻辑：`src/lacquertutor/web/assets/app.js`
- 样式：`src/lacquertutor/web/assets/app.css`
- Web API：`src/lacquertutor/web/app.py`

这次重构要对齐 `PRODUCT_PRD_CN.md` 的五个核心机制：

1. 主动澄清
2. 不可逆门控
3. 证据卡驱动
4. 合同式输出
5. 项目记忆

### 明确边界

- **不改 Agent 能力与 API 语义**。前端只消费当前后端已经提供的认证、session、contract、artifact、execution、attachment 和 memory 数据。
- **不新增项目表**。用户看到的“项目”在技术上直接映射到当前 `session_id`。
- **不引入 SSE**。v2 不依赖 `/api/chat` 或流式协议，继续基于现有同步响应模型。
- **不做知识库自由检索页、模板库、后台管理、PWA、多语言、暗色主题**。
- **允许一处最小后端集成改动**：FastAPI 改为托管 Vite 构建产物，但不改业务接口。

---

## 2. 基于仓库现实的锁定决策

| 维度 | 决定 |
|---|---|
| 布局范式 | 聊天主区 + 右侧 Artifact 抽屉，默认关闭，可自动展开 |
| 技术栈 | React 18 + Vite + TypeScript + Zustand + React Router v6 |
| 术语策略 | 用户文案叫“项目”，前端路由、store、API 全部使用 `sessionId` |
| 路由模型 | `/login`、`/`、`/p/:sessionId`，抽屉标签用查询参数 `?tab=` 锁定 |
| 后端对齐 | 只复用现有 `/api/auth/*`、`/api/home`、`/api/sessions*` |
| 主实体 | `SessionSummary` + `WorkbenchState`，不再定义独立 `Project` 接口 |
| 交互模型 | 主输入框根据当前 session 状态在 4 种 composer 模式之间切换 |
| 视觉方向 | 中性暖白壳体 + 漆艺重音；赭红只用于门控、阻断和高风险提示 |
| 范围 | 保留聊天、planning、troubleshooting、knowledge、learning、safety 六类 session，但 UI 以“工作台动作”呈现，不再用旧的模块宫格作为主信息架构 |
| 迁移策略 | 先并行搭新前端，再切静态托管，最后删除旧 `index.html` / `app.js` / `app.css` |

---

## 3. 现有后端合同

本规格以 `src/lacquertutor/web/app.py` 为唯一后端真相。

### 3.1 已存在的接口

| 接口 | 用途 | v2 用法 |
|---|---|---|
| `POST /api/auth/register` | 注册 | 登录页注册表单 |
| `POST /api/auth/login` | 登录 | 登录页登录表单 |
| `POST /api/auth/logout` | 退出 | 侧栏账户菜单 |
| `GET /api/me` | 当前用户 | 应用启动时判定鉴权态 |
| `GET /api/home` | 账户级总览与记忆摘要 | `/` 欢迎页和侧栏记忆摘要 |
| `POST /api/sessions` | 创建新 session | 所有“新项目 / 新线程”动作 |
| `GET /api/sessions` | 最近 session 列表 | 侧栏最近项目 |
| `GET /api/sessions/{sessionId}` | 恢复完整工作台 | `/p/:sessionId` 刷新与直达恢复 |
| `POST /api/sessions/{sessionId}/messages` | 已有 chat session 继续聊天 | 仅 `scene_key === "chat"` 可用 |
| `POST /api/sessions/{sessionId}/answer` | 回答结构化补问 | 仅存在 `pending_question` 时可用 |
| `POST /api/sessions/{sessionId}/execution/steps/{stepNumber}` | 更新步骤状态 | 合同视图执行区 |
| `POST /api/sessions/{sessionId}/execution/checkpoints/{checkpointId}` | 更新检查点状态 | 合同视图执行区 |
| `POST /api/sessions/{sessionId}/attachments` | 上传图片记录 | 合同与执行跟踪 |
| `GET /api/sessions/{sessionId}/attachments` | 附件列表 | 合同抽屉 |
| `GET /api/sessions/{sessionId}/attachments/{attachmentId}` | 下载附件 | 合同抽屉 |
| `GET /api/sessions/{sessionId}/export/markdown` | 导出 Markdown | 顶部导出按钮 |

### 3.2 不允许在 v2 中假设存在的接口

- `/api/projects`
- `/api/projects/:id/state`
- `/api/chat`
- `/api/kb/search`
- 独立模板接口
- 独立 evidence 详情接口

以上接口都**不纳入实现计划**。如果未来需要，必须另开后端规格。

---

## 4. 信息架构

### 4.1 路由

```
/login                    登录 / 注册页
/                         已登录欢迎页，无当前 session
/p/:sessionId             主工作台，恢复并展示指定 session
/p/:sessionId?tab=contract  锁定抽屉到合同
/p/:sessionId?tab=evidence  锁定抽屉到证据
/p/:sessionId?tab=gate      锁定抽屉到门控
/p/:sessionId?tab=reference 锁定抽屉到参考 / 资料
```

约束：

- 不做 `/kb`、`/templates`、`/home` 独立页面。
- `/` 只承担欢迎态、最近项目、账户记忆摘要和新建动作。
- 一旦进入具体 session，主 URL 固定为 `/p/:sessionId`，所有面板状态都通过本地 store 和 `?tab=` 管理。

### 4.2 用户看到的“项目”与技术实体映射

| 用户文案 | 技术实体 |
|---|---|
| 项目 | session |
| 项目 ID | sessionId |
| 新建项目 | `POST /api/sessions` |
| 继续项目 | `GET /api/sessions/{sessionId}` |
| 项目状态 | `status` + `state` |

前端组件、router 参数、store 字段、adapter 类型全部使用 `sessionId`，只在 UI 文案中展示“项目”。

### 4.3 主工作台布局

```
┌──────────────┬────────────────────────────┬──────────────────────┐
│ Sidebar      │ ChatPane                   │ ArtifactDrawer       │
│ 260px        │ flex 1, max 840px          │ 480px                │
│              │                            │ overlay / push       │
│ Brand        │ GateChip                   │ Tabs                 │
│ Quick Actions│ Conversation Thread        │ contract             │
│ Recent       │                            │ evidence             │
│ Memory       │ Composer                   │ gate                 │
│ Account      │                            │ reference            │
└──────────────┴────────────────────────────┴──────────────────────┘
```

规则：

- 主区永远以聊天线程为中心，不切成“表单页 / 合同页 / 知识页”。
- 右侧抽屉是结构化产物容器，不与聊天区抢主叙事。
- 抽屉关闭后，GateChip 仍需持续显示当前门控状态。

### 4.4 Sidebar 结构

1. 品牌区
2. Quick Actions
3. 最近项目列表
4. 账户记忆摘要
5. 账号动作

#### Quick Actions

Quick Actions 不再暴露“六模块卡片”，而是统一为 6 个动作：

- 继续聊天
- 开始制作
- 排查问题
- 安全检查
- 查资料
- 学习路径

每个动作都只负责设置默认 `scene_key` 与启动文案模板，最终仍通过 `POST /api/sessions` 创建 session。

### 4.5 Artifact 抽屉的 4 个标签

| Tab | 数据来源 | 内容 | 自动打开时机 |
|---|---|---|---|
| `contract` | `state.contract_display` + `state.execution` + `state.attachments` | 6 段合同、执行摘要、步骤状态、检查点、附件、导出 | `response.type === "contract"` |
| `evidence` | `state.retrieved_evidence` 或 `state.chat_references` | 证据卡 / 知识片段 | 结构化 session 生成合同后；chat 命中参考资料时 |
| `gate` | `pending_question`、`missing_hard_gates_display`、`execution.summary.has_blocker`、`module_artifact.verdict` | 当前需补条件、阻塞原因、下一步建议 | `response.type === "question"`；安全结果为非可行；执行出现阻塞 |
| `reference` | `state.module_artifact`、`remembered_preferences`、`learned_playbooks`、`agent_memories` | 教学结果、资料摘要、个人记忆与参考信息 | `response.type === "artifact"`；用户手动切入 |

---

## 5. 响应类型与工作台行为

后端返回体以 `response.type` 为核心分支，前端不得自行发明第五类。

### 5.1 `response.type === "message"`

适用于通用聊天：

- 线程追加 assistant 消息
- 主 composer 维持自由输入
- `evidence` tab 展示 `chat_references`
- 若存在 `chat_suggested_scene_keys`，以轻量建议 chip 展示，不自动切 scene
- GateChip 默认隐藏

### 5.2 `response.type === "question"`

适用于 planning / troubleshooting 等结构化流程中的补问：

- 线程追加用户消息与系统问题
- composer 切到 `pending-answer` 模式
- `gate` tab 自动展开
- GateChip 显示“需补充条件”
- 顶部状态文案明确当前只需要回答一个问题

### 5.3 `response.type === "contract"`

适用于 planning / troubleshooting 流程完成后：

- `contract` tab 自动展开
- `evidence` tab 展示 `retrieved_evidence`
- composer 回到“继续补充 / 继续记录”状态
- 若 `execution.summary.has_blocker === true`，GateChip 显示阻塞

### 5.4 `response.type === "artifact"`

适用于 knowledge / learning / safety：

- 默认打开 `reference` tab
- 若 `module_artifact.verdict === "conditional"` 或 `"not_feasible"`，改为自动打开 `gate` tab
- 资料类内容显示在 `reference` tab
- 若 artifact 带 `references`、`required_conditions`、`blocking_factors`，同步映射进 evidence / gate 适配层

---

## 6. 前端状态模型

### 6.1 适配层原则

React 组件不直接消费后端原始 payload。所有接口结果先进入 adapter，归一化为以下前端类型。

### 6.2 TypeScript 接口

```ts
export type DrawerTab = "contract" | "evidence" | "gate" | "reference";

export type ComposerMode =
  | "new-chat"
  | "chat-message"
  | "new-scene-session"
  | "pending-answer";

export interface SessionSummary {
  sessionId: string;
  status: string;
  sceneKey: "chat" | "planning" | "troubleshooting" | "knowledge" | "learning" | "safety";
  sceneLabel: string;
  projectTitle: string;
  projectSummary: string;
  pendingSlotLabel: string;
  hasContract: boolean;
  hasArtifact: boolean;
}

export interface WorkbenchState {
  sessionId: string;
  sceneKey: SessionSummary["sceneKey"];
  sessionMode: "agent" | "workflow";
  status: string;
  projectTitle: string;
  projectSummary: string;
  pendingQuestion: string;
  pendingQuestionReason: string;
  filledSlots: Array<{ label: string; value: string }>;
  missingHardGates: Array<{ label: string }>;
  contractDisplay: ContractDisplay | null;
  execution: ExecutionDisplay | null;
  retrievedEvidence: EvidenceCardDisplay[];
  chatReferences: ReferenceCardDisplay[];
  moduleArtifact: ModuleArtifactDisplay | null;
  rememberedPreferences: PreferenceChip[];
  learnedPlaybooks: PlaybookCard[];
  agentMemories: MemoryCard[];
  attachments: AttachmentDisplay[];
}

export interface ArtifactModel {
  contract: ContractPanelModel | null;
  evidence: EvidencePanelModel;
  gate: GatePanelModel;
  reference: ReferencePanelModel;
}
```

### 6.3 GatePanelModel 的组装规则

`gate` 面板统一来自以下来源：

1. `pendingQuestion` 与 `pendingQuestionReason`
2. `missingHardGates`
3. `execution.summary.has_blocker`
4. `contractDisplay.high_risk_warnings`
5. `module_artifact.verdict`
6. `module_artifact.required_conditions`
7. `module_artifact.blocking_factors`

不要在组件内写分散分支，全部在 adapter 中完成。

### 6.4 Composer 模式判定

| 模式 | 触发条件 | 提交动作 |
|---|---|---|
| `new-chat` | 当前在 `/` 或当前 scene 为 chat 且尚无 session | `POST /api/sessions`，`scene_key="chat"` |
| `chat-message` | 当前 session 为 chat | `POST /api/sessions/{sessionId}/messages` |
| `new-scene-session` | 当前选中结构化动作但尚无 session，或当前结构化 session 已结束且用户要新开 | `POST /api/sessions` |
| `pending-answer` | `pendingQuestion` 存在 | `POST /api/sessions/{sessionId}/answer` |

---

## 7. 组件与目录结构

新前端源码固定放在仓库根目录 `frontend/`，构建结果输出到 `src/lacquertutor/web/dist/`。

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── main.tsx
    ├── app/
    │   ├── App.tsx
    │   ├── router.tsx
    │   └── providers.tsx
    ├── pages/
    │   ├── LoginPage.tsx
    │   ├── HomePage.tsx
    │   └── WorkbenchPage.tsx
    ├── features/
    │   ├── auth/
    │   │   ├── api.ts
    │   │   ├── store.ts
    │   │   └── components/LoginCard.tsx
    │   ├── sessions/
    │   │   ├── api.ts
    │   │   ├── adapters.ts
    │   │   ├── store.ts
    │   │   ├── components/Sidebar.tsx
    │   │   ├── components/QuickActions.tsx
    │   │   ├── components/RecentSessionList.tsx
    │   │   └── components/MemorySummary.tsx
    │   ├── chat/
    │   │   ├── store.ts
    │   │   ├── components/GateChip.tsx
    │   │   ├── components/ConversationPane.tsx
    │   │   ├── components/MessageBubble.tsx
    │   │   └── components/Composer.tsx
    │   ├── artifact/
    │   │   ├── store.ts
    │   │   ├── components/ArtifactDrawer.tsx
    │   │   ├── components/ContractTab.tsx
    │   │   ├── components/EvidenceTab.tsx
    │   │   ├── components/GateTab.tsx
    │   │   └── components/ReferenceTab.tsx
    │   └── execution/
    │       ├── api.ts
    │       └── components/ExecutionControls.tsx
    ├── shared/
    │   ├── api/client.ts
    │   ├── ui/
    │   ├── theme/tokens.ts
    │   └── utils/
    └── types/
        ├── api.ts
        └── domain.ts
```

### 7.1 边界约束

- `features/sessions/adapters.ts` 是唯一允许读取原始后端 schema 的位置。
- `chat` 不直接解析 `module_artifact` 或 `contract_display`。
- `artifact` 只消费 `ArtifactModel`。
- `execution` 只负责步骤、检查点、附件相关写操作。
- 不引入 UI 组件库，自建最小 `Button`、`Tabs`、`Drawer`、`Dialog`、`Tooltip` 原语。

---

## 8. 页面与交互细节

### 8.1 `/login`

目标：只完成注册、登录与鉴权跳转。

规则：

- 未登录访问任何其他路由都重定向到 `/login`
- 登录成功后跳转 `/`
- 不显示最近项目、不显示工作台侧栏

### 8.2 `/`

目标：作为已登录欢迎态，不绑定当前 session。

内容：

- 账户欢迎文案
- Quick Actions
- 最近项目列表
- 记忆摘要
- 一条简短产品说明

来源：

- `GET /api/home`
- `GET /api/sessions?limit=20`

规则：

- 点击最近项目进入 `/p/:sessionId`
- 点击 Quick Action 不立即跳页面，先进入对应空白 composer，再在第一次提交时创建 session

### 8.3 `/p/:sessionId`

目标：恢复并承载完整工作台。

初始化：

1. `GET /api/sessions/{sessionId}`
2. 通过 adapter 转成 `WorkbenchState`
3. 根据 `response` 不存在这一事实，直接按 state 决定初始 tab

默认 tab 规则：

- 有 `pendingQuestion`：`gate`
- 有 `contractDisplay`：`contract`
- 有 `moduleArtifact`：`reference`
- 仅 chat 且有 `chatReferences`：`evidence`
- 否则保持 URL 查询参数指定值

### 8.4 GateChip

GateChip 只在非 chat session 中显示。

状态判定：

| 状态 | 条件 | 文案 |
|---|---|---|
| `needs-input` | `pendingQuestion` 存在 | `需补充 1 项关键条件` |
| `blocked` | `missingHardGates.length > 0` 或 `execution.summary.has_blocker === true` 或 `moduleArtifact.verdict === "not_feasible"` | `当前不可继续` |
| `review` | `moduleArtifact.verdict === "conditional"` | `有条件可行` |
| `safe` | 已有合同或 artifact 且不满足以上条件 | `可继续查看方案` |

点击 GateChip 永远打开 `gate` tab。

### 8.5 抽屉自动展开规则

- 用户第一次进入 `/p/:sessionId` 时，如果存在合同、补问、artifact 或 evidence，抽屉默认展开
- 用户手动关闭后，当同一 session 再次收到新的 `question`、`contract` 或阻塞更新时重新自动展开
- 仅 chat 场景收到普通 `message` 时不强制展开抽屉

### 8.6 证据展示规则

- chat 场景：展示 `chat_references`
- contract 场景：展示 `retrieved_evidence`
- artifact 场景：若 `module_artifact.references` 存在，也进入统一 evidence 列表
- 不做独立 evidence 详情页；卡片展开即是最大信息密度

### 8.7 执行与附件

只要 `contractDisplay` 存在，就保留以下能力：

- 步骤状态更新
- 检查点确认
- 附件上传
- 附件列表与下载
- 导出 Markdown

这部分是现有产品能力，v2 不能删除。

---

## 9. 视觉系统

```ts
export const color = {
  bg: "#faf7f2",
  surface: "#fffdf9",
  surfaceRaised: "#f4eee6",
  border: "#e7ddd0",
  text: "#211712",
  textMuted: "#6b5b53",
  accent: "#b77942",
  accentSoft: "#efe0d0",
  danger: "#8f2117",
  dangerSoft: "#f4dfda",
  warn: "#8b5a1f",
  ok: "#2b5b49",
  okSoft: "#ddebe4",
  bubbleUser: "#efe8df",
  bubbleAssistant: "#fffdf9",
};

export const radius = { sm: 8, md: 12, lg: 16, xl: 20 };
export const font = {
  ui: '"PingFang SC", "Microsoft YaHei", sans-serif',
  heading: '"Noto Serif SC", "Source Han Serif SC", serif',
  mono: '"JetBrains Mono", monospace',
};
```

### 视觉约束

- 红色总面积控制在 5% 以内
- 大段正文不用纯白背景堆叠卡片，优先用层次化留白和细边框
- 气泡采用纸感浅底，不做 ChatGPT 式强灰块
- 标题区允许少量漆艺金棕装饰，不做拟物纹理
- 抽屉打开时主聊天列最大宽度收窄到 720px

---

## 10. 构建与集成

### 10.1 Vite 约定

```ts
// frontend/vite.config.ts
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/kb-images": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
```

### 10.2 构建产物位置

- 源码目录：`frontend/`
- 本地构建目录：`frontend/dist/`
- 发布目录：`src/lacquertutor/web/dist/`

### 10.3 FastAPI 集成

需要一处静态托管切换：

- `/assets` 改为指向 `src/lacquertutor/web/dist/assets`
- 根路径与 SPA fallback 返回 `src/lacquertutor/web/dist/index.html`
- `kb-images` 继续保持现状

### 10.4 旧文件删除条件

以下条件全部满足后，删除旧前端：

1. 新前端登录、创建 session、恢复 session、执行更新、附件上传、导出全部跑通
2. FastAPI 已托管新 `dist`
3. `/` 与 `/p/:sessionId` 刷新无 404

待删除文件：

- `src/lacquertutor/web/index.html`
- `src/lacquertutor/web/assets/app.js`
- `src/lacquertutor/web/assets/app.css`

---

## 11. 迁移实施顺序

### Phase 1：脚手架与基础设施

- 新建 `frontend/` Vite 工程
- 搭建路由、鉴权守卫、API client、Zustand store
- 实现 `sessions/adapters.ts`

### Phase 2：登录与欢迎态

- 实现 `/login`
- 实现 `/`
- 对接 `/api/me`、`/api/home`、`/api/sessions`

### Phase 3：Workbench 主体验

- 实现 `/p/:sessionId`
- 实现 Sidebar、ConversationPane、Composer、GateChip
- 接入 chat、question、contract、artifact 四类结果分支

### Phase 4：Artifact 与执行闭环

- 接入 contract / evidence / gate / reference 四个 tab
- 接入执行状态更新、检查点、附件与导出
- 验证刷新恢复与最近项目切换

### Phase 5：切换静态托管

- 在 FastAPI 中挂载 Vite 产物
- 通过完整回归后删除旧前端文件

---

## 12. 不做的事

- 不新增后端 session 结构字段
- 不做 SSE / EventSource
- 不做独立项目实体
- 不做模板库页面和模板复用接口
- 不做知识库自由搜索输入框
- 不做独立 evidence 详情页
- 不做多标签协同状态同步
- 不做 UI 组件库引入
- 不做暗色主题和多语言

---

## 13. 验收标准

1. 未登录只能访问 `/login`，登录成功后进入 `/`。
2. `/` 能正确展示最近项目、Quick Actions 和账户记忆摘要。
3. 点击最近项目能进入 `/p/:sessionId`，并通过 `GET /api/sessions/{sessionId}` 完整恢复线程与抽屉状态。
4. chat session 首次发送消息走 `POST /api/sessions`，后续消息走 `POST /api/sessions/{sessionId}/messages`。
5. 结构化 session 在 `pendingQuestion` 存在时只走 `POST /api/sessions/{sessionId}/answer`。
6. 合同生成后 `contract` tab 自动展开，6 段内容、证据卡、步骤状态和检查点全部可见。
7. safety / knowledge / learning 的 artifact 结果能正确落入 `reference` 或 `gate` tab，不误渲染为合同。
8. `retrieved_evidence` 与 `chat_references` 不混用，证据展示来源正确。
9. 步骤更新、检查点确认、附件上传与下载在新前端中继续可用。
10. 关闭抽屉、刷新页面、重新进入时能恢复到正确 session 和可推导的 tab。
11. 新前端接管后，旧 `index.html` / `app.js` / `app.css` 已删除，FastAPI 只服务 `dist/`。
12. 桌面端 Lighthouse Performance ≥ 80。

---

## 14. 风险与处理

| 风险 | 处理 |
|---|---|
| 当前后端返回的 `module_artifact` 结构在不同 scene 间差异较大 | 统一在 `adapters.ts` 中归一化，组件层只读 `ArtifactModel` |
| chat 与结构化 session 的提交路径不同，容易在 composer 中写乱 | 用显式 `ComposerMode` 状态机封装，禁止组件直接拼 URL |
| “项目”与 `session` 双重命名造成实现混淆 | 技术层统一使用 `sessionId`，只在 UI copy 上保留“项目” |
| 静态托管切换时刷新路由可能 404 | 在 FastAPI 添加 SPA fallback 后再删除旧页面 |
| 执行更新与附件能力在重构中被遗漏 | 把 `execution` 与 `attachments` 列为硬性保留范围，并纳入验收项 |

---

## 15. 一句话结论

Frontend v2 不是为一个新后端协议重做 UI，而是**在保持当前 session-based FastAPI 合同不变的前提下，把单文件脚本页面升级为一个以聊天为主轴、以抽屉承载结构化产物、可恢复、可执行、可维护的 React 工作台。**
