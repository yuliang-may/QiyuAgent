FROM node:24-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json /frontend/package.json
COPY frontend/package-lock.json /frontend/package-lock.json
COPY frontend/tsconfig.json /frontend/tsconfig.json
COPY frontend/tsconfig.app.json /frontend/tsconfig.app.json
COPY frontend/tsconfig.node.json /frontend/tsconfig.node.json
COPY frontend/vite.config.ts /frontend/vite.config.ts
COPY frontend/index.html /frontend/index.html
COPY frontend/src /frontend/src

RUN npm ci --registry https://registry.npmmirror.com --no-audit --no-fund && npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
COPY kb /app/kb
COPY .env.example /app/.env.example
COPY --from=frontend-builder /src/lacquertutor/web/dist /app/src/lacquertutor/web/dist

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install -e . --no-build-isolation

EXPOSE 8000

CMD ["python", "-m", "lacquertutor", "serve", "--host", "0.0.0.0", "--port", "8000"]
