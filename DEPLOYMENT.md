# LacquerTutor Deployment

## Local Docker Deployment

This repo now ships with a single-node deployment path for the web product.

### 1. Prepare environment

Copy `.env.example` to `.env`, then fill in at least:

- `LACQUERTUTOR_LLM_API_KEY`
- `LACQUERTUTOR_LLM_BASE_URL`
- `LACQUERTUTOR_LLM_MODEL`
- `LACQUERTUTOR_AUTH_SECRET_KEY`

For the current DashScope/Qwen setup, `.env` can keep:

```env
LACQUERTUTOR_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LACQUERTUTOR_LLM_MODEL=qwen-plus
```

Add these deployment settings as well:

```env
LACQUERTUTOR_AUTH_SECRET_KEY=replace-with-a-long-random-secret
LACQUERTUTOR_SESSION_DB_PATH=/app/data/lacquertutor_web.db
LACQUERTUTOR_MEM0_DATA_DIR=/app/data/mem0
```

### 2. Build and start

```bash
docker compose up --build -d
```

The product will be available at:

```text
http://localhost:8000
```

### 3. Persistent data

The compose setup persists the following inside the named Docker volume:

- account/session SQLite database
- Mem0 local Qdrant store
- Mem0 history database

### 4. Update the service

```bash
docker compose down
docker compose up --build -d
```

## Direct Python Run

If you want to run without Docker:

```bash
python -m pip install -e .
python -m lacquertutor serve --host 0.0.0.0 --port 8000
```

## Current Deployment Scope

This deployment target is suitable for:

- local demo server
- single-machine internal deployment
- pilot rollout inside one teaching team

For public internet deployment, add:

- reverse proxy and HTTPS
- managed database backups
- log aggregation
- secret management outside `.env`
