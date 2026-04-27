# QiyuAgent / LacquerTutor

漆艺教学智能助手。系统面向漆艺学习、工艺计划、故障排查和安全评估，通过对话补齐关键条件，再生成可执行方案、检查点和应急预案。

## 功能

- 漆艺知识问答
- 工艺计划生成
- 故障排查
- 安全评估
- 学习路径建议
- 会话记录、方案导出和现场图片上传

## 技术栈

- 后端：Python、FastAPI、Typer、SQLite
- 前端：React、Vite、TypeScript
- Agent：OpenAI 兼容接口，可接入 DashScope/Qwen 等模型
- 部署：Docker、Docker Compose

## 环境变量

复制配置模板：

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

不要把 `.env` 上传到 GitHub。

## Docker 部署

```bash
docker compose up --build -d
```

访问：

```text
http://localhost:8000
```

健康检查：

```bash
curl http://localhost:8000/health
```

停止服务：

```bash
docker compose down
```

## 本地开发

安装后端依赖：

```bash
python -m pip install -e ".[dev,retrieval]"
```

启动后端：

```bash
python -m lacquertutor serve --host 127.0.0.1 --port 8001
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

开发地址通常是：

```text
http://localhost:5173
```

## 生产方式本地运行

```bash
cd frontend
npm install
npm run build
cd ..
python -m pip install -e .
python -m lacquertutor serve --host 0.0.0.0 --port 8000
```

## 测试

```bash
pytest
```

```bash
cd frontend
npm run build
```

## 使用手册

中文使用手册：

- `docs/USER_MANUAL_CN.tex`
- `docs/USER_MANUAL_CN.pdf`

## 上传说明

当前仓库暂不上传：

- `benchmark/`
- `kb/`
- `.env`
- 本地数据库
- 虚拟环境和依赖缓存

这些内容已在 `.gitignore` 中排除。
