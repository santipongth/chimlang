# คำสั่งหลักตาม CLAUDE.md — บน Windows ที่ไม่มี make ให้รันคำสั่งด้านขวาโดยตรง
.PHONY: setup dev dev-down api test lint format

setup:
	uv sync

dev:
	docker compose up -d

api:
	uv run uvicorn api.app:app --reload --port 8000

dev-down:
	docker compose down

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .
