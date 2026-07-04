# คำสั่งหลักตาม CLAUDE.md — บน Windows ที่ไม่มี make ให้รันคำสั่งด้านขวาโดยตรง
.PHONY: setup dev dev-down test lint format

setup:
	uv sync

dev:
	docker compose up -d

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
