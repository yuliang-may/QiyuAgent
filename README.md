# LacquerTutor 漆艺教学智能助手

LacquerTutor 是一个面向漆艺学习、工艺计划和故障排查的智能助手。它不是简单的通用聊天机器人，而是围绕“先追问关键条件、再生成可执行方案、在不可逆步骤前做安全门控”的工作流设计。

项目包含：

- 后端：FastAPI + Typer CLI + SQLite 会话存储
- 前端：React + Vite
- Agent：基于 OpenAI 兼容接口，可接入 DashScope/Qwen 等模型
- 知识库：`kb/` 下的漆艺知识片段与图片镜像
- 基准数据：`benchmark/` 下的任务集与证据卡
- 部署：Dockerfile + docker-compose 单机部署

## 主要功能

- 注册、登录和个人会话管理
- 通用漆艺问答
- 工艺计划生成
- 故障排查与安全停步判断
- 知识问答、学习路径、安全评估等场景入口
- 基于知识库的参考资料与图片引用
- 可执行方案中的步骤、检查点和应急预案
- 执行过程状态记录与现场图片上传
- 会话 Markdown 导出

## 目录结构

```text
.
├── benchmark/                 # 评测任务与证据卡
├── docs/                      # 项目文档
├── frontend/                  # React/Vite 前端
├── kb/                        # 漆艺知识库与图片镜像
├── src/lacquertutor/          # Python 后端、Agent、Web API
├── tests/                     # pytest 测试
├── .env.example               # 环境变量示例
├── DEPLOYMENT.md              # 现有部署说明
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## 环境要求

本地开发建议使用：

- Python 3.11 或更高版本
- Node.js 20.19+ 或 22.12+ 或更高版本
- npm
- Docker 与 Docker Compose，用于容器部署

如果只使用 Docker 部署，本机不需要单独安装 Python 和 Node 运行环境。

## 配置环境变量

复制环境变量示例：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

至少需要配置：

```env
LACQUERTUTOR_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LACQUERTUTOR_LLM_API_KEY=sk-your-key-here
LACQUERTUTOR_LLM_MODEL=qwen-plus
LACQUERTUTOR_AUTH_SECRET_KEY=replace-with-a-long-random-secret
```

部署时建议同时使用持久化路径：

```env
LACQUERTUTOR_SESSION_DB_PATH=/app/data/lacquertutor_web.db
LACQUERTUTOR_MEM0_DATA_DIR=/app/data/mem0
```

注意：`.env` 里包含 API Key 和登录签名密钥，不能上传到 GitHub。

## Docker 部署

这是推荐的单机部署方式。它会在镜像构建阶段编译前端，并用 FastAPI 同时提供前端页面和后端 API。

1. 准备 `.env`

```bash
cp .env.example .env
```

编辑 `.env`，填入真实 API Key 和随机生成的 `LACQUERTUTOR_AUTH_SECRET_KEY`。

2. 构建并启动

```bash
docker compose up --build -d
```

3. 打开服务

```text
http://localhost:8000
```

4. 查看健康检查

```bash
curl http://localhost:8000/health
```

正常返回：

```json
{"status":"ok"}
```

5. 停止服务

```bash
docker compose down
```

6. 更新部署

```bash
docker compose down
docker compose up --build -d
```

`docker-compose.yml` 会把会话数据库和本地记忆数据保存到 Docker named volume `lacquertutor_data` 中。

## 本地开发运行

后端与前端分开启动，便于开发调试。

1. 安装 Python 依赖

```bash
python -m pip install -e ".[dev,retrieval]"
```

如果只运行基础 Web 产品，也可以使用：

```bash
python -m pip install -e .
```

2. 安装前端依赖

```bash
cd frontend
npm install
```

3. 启动后端开发服务

前端开发代理默认转发到 `127.0.0.1:8001`，所以开发时建议后端使用 8001 端口：

```bash
python -m lacquertutor serve --host 127.0.0.1 --port 8001
```

4. 启动前端开发服务

```bash
cd frontend
npm run dev
```

打开 Vite 输出的本地地址，通常是：

```text
http://localhost:5173
```

## 本地生产方式运行

如果不使用 Docker，也可以先构建前端，再由 Python 后端直接托管静态页面。

```bash
cd frontend
npm install
npm run build
cd ..
python -m pip install -e .
python -m lacquertutor serve --host 0.0.0.0 --port 8000
```

然后访问：

```text
http://localhost:8000
```

## CLI 使用

安装项目后可使用 `python -m lacquertutor` 或 `lacquertutor` 命令。

交互对话：

```bash
python -m lacquertutor chat --mode agent
```

启动 Web 服务：

```bash
python -m lacquertutor serve --host 127.0.0.1 --port 8000
```

运行单个评测任务：

```bash
python -m lacquertutor run --task P01 --condition S2 --output output
```

查看任务信息：

```bash
python -m lacquertutor info --task P01
```

构建知识库索引：

```bash
python -m lacquertutor index
```

## 测试

运行后端测试：

```bash
pytest
```

运行前端构建检查：

```bash
cd frontend
npm run build
```

## 上传到 GitHub

首次上传时可以按以下流程操作。

1. 确认不要上传密钥、数据库和依赖目录

```bash
git status
```

不要提交：

- `.env`
- `.venv/`
- `frontend/node_modules/`
- `.data/`
- `lacquertutor_web.db`
- `.pytest_cache/`
- `.tmp/`
- 其他本地输出目录

2. 初始化 Git 仓库

```bash
git init
git add .
git commit -m "Document LacquerTutor deployment and usage"
```

3. 关联 GitHub 远程仓库

```bash
git branch -M main
git remote add origin https://github.com/<your-name>/<your-repo>.git
git push -u origin main
```

如果已经是 Git 仓库，只需要：

```bash
git add README.md docs/USER_MANUAL_CN.tex .gitignore
git commit -m "Add Chinese README and user manual"
git push
```

## 公开部署建议

当前 `docker-compose.yml` 适合本地演示、单机内网部署和教学团队试用。若要面向公网使用，建议补充：

- 反向代理和 HTTPS，例如 Nginx、Caddy 或云厂商负载均衡
- 更严格的密钥管理，不在服务器上明文散落 `.env`
- 数据库和上传文件备份
- 访问日志、错误日志和运行监控
- 服务器防火墙和最小开放端口

生产环境中不要使用默认的 `LACQUERTUTOR_AUTH_SECRET_KEY`。

## 常见问题

### 页面能打开，但模型没有回复

检查 `.env` 中的 `LACQUERTUTOR_LLM_API_KEY`、`LACQUERTUTOR_LLM_BASE_URL` 和 `LACQUERTUTOR_LLM_MODEL` 是否正确。

### 前端开发服务请求接口失败

开发环境中 Vite 会把 `/api` 转发到 `http://127.0.0.1:8001`。请确认后端以 8001 端口启动：

```bash
python -m lacquertutor serve --host 127.0.0.1 --port 8001
```

### Docker 启动后数据在哪里

Compose 会把数据写入 named volume `lacquertutor_data`。如果执行 `docker compose down`，数据仍会保留；只有删除 volume 时才会清空。

### 可以把 `.env` 上传到 GitHub 吗

不可以。`.env` 包含 API Key 和认证密钥。请只上传 `.env.example`。

