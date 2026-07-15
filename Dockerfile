# ชิมลาง — production image (P4-M5, มติผู้ใช้: self-hosted docker)
# stage 1: build React UI
FROM node:22-alpine AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

# stage 2: Python app (API + worker ใช้ image เดียวกัน)
FROM python:3.12-slim
WORKDIR /srv/chimlang
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev --no-install-project

COPY core/ core/
COPY api/ api/
COPY simulation/ simulation/
COPY graphlayer/ graphlayer/
COPY trust/ trust/
COPY governance/ governance/
COPY scripts/ scripts/
COPY config/ config/
COPY assets/ assets/
COPY data/samples/ data/samples/
COPY docs/reports/ docs/reports/
RUN uv sync --frozen --no-dev
COPY --from=webbuild /web/dist web/dist

EXPOSE 8000
# api (default) — worker override command ใน compose
CMD ["uv", "run", "--no-sync", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
