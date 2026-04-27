# LacquerTutor 可运行产品流程示例

这份文档不是设计稿，而是一份**能直接照着跑起来**的产品运行手册。

目标：

1. 启动当前产品
2. 预热标准 RAG
3. 跑通通用聊天、工艺计划、安全检查三条典型路径
4. 给出可直接复制的 PowerShell 示例

适用目录：

- 项目根目录：`D:\CCNU\lacquertutor`

---

## 1. 当前产品是什么

当前版本是一个**产品工作台**，不是纯 demo。

保留的能力：

- 登录 / 注册
- 最近项目
- 通用聊天助手
- 工艺计划
- 安全检查
- 学习路径
- 抽屉式 Artifact 展示
- 执行步骤更新

其中通用聊天已经升级为**标准 RAG 主链**：

- 预分段知识库 chunk
- dense retrieval
- lexical retrieval
- RRF 融合
- cross-encoder rerank
- top-k 参考片段注入 LLM

相关实现：

- 聊天入口：[chat.py](D:/CCNU/lacquertutor/src/lacquertutor/web/chat.py)
- 知识服务：[teaching.py](D:/CCNU/lacquertutor/src/lacquertutor/web/teaching.py)
- 标准 RAG：[rag.py](D:/CCNU/lacquertutor/src/lacquertutor/web/rag.py)
- Web 服务：[app.py](D:/CCNU/lacquertutor/src/lacquertutor/web/app.py)

---

## 2. 运行前准备

### 2.1 环境变量

至少需要配置：

- `LACQUERTUTOR_LLM_API_KEY`

当前默认模型配置来源：

- [config.py](D:/CCNU/lacquertutor/src/lacquertutor/config.py)

默认值：

- `llm_base_url=https://dashscope.aliyuncs.com/compatible-mode/v1`
- `llm_model=qwen-plus`
- `embedding_model=text-embedding-v3`
- `rerank_model=gte-rerank-v2`

建议做法：

1. 复制 `.env.example` 为 `.env`
2. 填入 `LACQUERTUTOR_LLM_API_KEY`

### 2.2 前端依赖

如果你第一次在本机运行：

```powershell
cd D:\CCNU\lacquertutor\frontend
npm install --registry https://registry.npmmirror.com --no-audit --no-fund
```

---

## 3. 本地运行

### 3.1 构建前端

```powershell
cd D:\CCNU\lacquertutor\frontend
npm run build
```

构建产物会输出到：

- [dist/index.html](D:/CCNU/lacquertutor/src/lacquertutor/web/dist/index.html)
- [dist/assets/app.js](D:/CCNU/lacquertutor/src/lacquertutor/web/dist/assets/app.js)
- [dist/assets/app.css](D:/CCNU/lacquertutor/src/lacquertutor/web/dist/assets/app.css)

### 3.2 预热标准 RAG 索引

建议首次运行前先执行：

```powershell
cd D:\CCNU\lacquertutor
python -m lacquertutor index
```

这一步会：

- 检查 `kb/*_segments.json`
- 建 evidence 索引
- 建通用聊天 RAG 索引

### 3.3 启动服务

```powershell
cd D:\CCNU\lacquertutor
python -m lacquertutor serve --host 127.0.0.1 --port 8000
```

打开：

- `http://127.0.0.1:8000/`

健康检查：

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing
```

期望返回：

```json
{"status":"ok"}
```

---

## 4. Docker 运行

### 4.1 构建镜像

```powershell
cd D:\CCNU\lacquertutor
docker build -t lacquertutor:frontend-v2 .
```

### 4.2 启动容器

```powershell
docker run -d -P --name lacquertutor-app lacquertutor:frontend-v2
docker port lacquertutor-app 8000/tcp
```

拿到映射端口后，访问：

```text
http://127.0.0.1:<映射端口>/
```

健康检查：

```powershell
$port = (docker port lacquertutor-app 8000/tcp).Split(':')[-1]
Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing
```

停止容器：

```powershell
docker rm -f lacquertutor-app
```

---

## 5. PowerShell 可运行 API 示例

以下示例默认服务跑在：

- `http://127.0.0.1:8000`

先定义基础变量：

```powershell
$base = "http://127.0.0.1:8000"
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
```

### 5.1 注册

```powershell
$registerBody = @{
  display_name = "李老师"
  username = "teacher_li_demo"
  password = "secret123"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "$base/api/auth/register" `
  -Method Post `
  -WebSession $session `
  -ContentType "application/json" `
  -Body $registerBody
```

### 5.2 登录

```powershell
$loginBody = @{
  username = "teacher_li_demo"
  password = "secret123"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "$base/api/auth/login" `
  -Method Post `
  -WebSession $session `
  -ContentType "application/json" `
  -Body $loginBody
```

### 5.3 查看首页数据

```powershell
Invoke-RestMethod -Uri "$base/api/home" -WebSession $session
```

---

## 6. 可运行流程示例

### 6.1 流程 A：通用聊天

创建聊天 session：

```powershell
$chatCreateBody = @{
  query = "木胎如何处理"
  mode = "agent"
  scene_key = "chat"
} | ConvertTo-Json

$chat = Invoke-RestMethod `
  -Uri "$base/api/sessions" `
  -Method Post `
  -WebSession $session `
  -ContentType "application/json" `
  -Body $chatCreateBody

$chat
```

你应该看到：

- `response.type = "message"`
- `state.scene_key = "chat"`
- `state.chat_references` 有命中的参考片段

继续聊天：

```powershell
$chatMessageBody = @{
  message = "木胎底处理最容易出什么问题"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "$base/api/sessions/$($chat.session_id)/messages" `
  -Method Post `
  -WebSession $session `
  -ContentType "application/json" `
  -Body $chatMessageBody
```

### 6.2 流程 B：工艺计划

创建 planning session：

```powershell
$planningCreateBody = @{
  query = "我想生成一份可执行工艺计划。`n对象 / 基底: 木托盘`n你想做成什么效果: 半光黑漆面"
  mode = "workflow"
  scene_key = "planning"
} | ConvertTo-Json

$planning = Invoke-RestMethod `
  -Uri "$base/api/sessions" `
  -Method Post `
  -WebSession $session `
  -ContentType "application/json" `
  -Body $planningCreateBody

$planning
```

期望：

- `response.type = "question"`

回答当前补问：

```powershell
$planningAnswerBody = @{
  answer = "生漆体系"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "$base/api/sessions/$($planning.session_id)/answer" `
  -Method Post `
  -WebSession $session `
  -ContentType "application/json" `
  -Body $planningAnswerBody
```

期望：

- `response.type = "contract"`

### 6.3 流程 C：安全检查

```powershell
$safetyCreateBody = @{
  query = "我想先判断当前方案到底可不可行。`n关键步骤 / 当前方案: 已有旧涂层的木盒重涂`n你最想先确认什么: 现在能不能直接继续重涂"
  mode = "agent"
  scene_key = "safety"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "$base/api/sessions" `
  -Method Post `
  -WebSession $session `
  -ContentType "application/json" `
  -Body $safetyCreateBody
```

期望：

- `response.type = "artifact"`
- `response.artifact.verdict = "conditional"` 或 `not_feasible`

### 6.4 流程 D：执行步骤更新

假设你已经拿到 planning session 的 `session_id`：

```powershell
$stepUpdateBody = @{
  status = "done"
  note = "已完成第一步"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "$base/api/sessions/$($planning.session_id)/execution/steps/1" `
  -Method Post `
  -WebSession $session `
  -ContentType "application/json" `
  -Body $stepUpdateBody
```

期望：

- `state.execution.steps[0].status = "done"`

---

## 7. 常见问题

### 7.1 登录 / 注册报错显示 `[object Object]`

已经修复。  
如果你还看到这个：

1. 强刷浏览器缓存
2. 确认 `frontend` 重新 build 过
3. 确认服务加载的是最新 `dist`

### 7.2 通用聊天回复太保守

先确认两件事：

1. 有没有配置 `LACQUERTUTOR_LLM_API_KEY`
2. 有没有先执行 `python -m lacquertutor index`

如果没有 key，系统会退回轻量 fallback，不是完整标准 RAG。

### 7.3 Docker build 偶发拉基础镜像失败

这是网络问题，不是代码问题。  
通常重试 `docker build` 即可。

---

## 8. 当前推荐验证顺序

如果你要做完整联调，建议按这个顺序：

1. `npm run build`
2. `python -m lacquertutor index`
3. `python -m lacquertutor serve --host 127.0.0.1 --port 8000`
4. 注册 / 登录
5. 跑流程 A：通用聊天
6. 跑流程 B：工艺计划
7. 跑流程 C：安全检查
8. 跑流程 D：执行更新
9. 再验证 Docker 构建和启动

---

## 9. 一句话结论

这套产品现在已经不是“只有一个网页能打开”的状态，而是：

**可以本地启动、可以 Docker 部署、可以跑通标准 RAG 聊天、也能保留 planning / safety / execution 等原有产品功能的一套可运行产品。**
