# คำสั่งหลักตาม CLAUDE.md — บน Windows ที่ไม่มี make ให้รันคำสั่งด้านขวาโดยตรง
.PHONY: setup dev dev-down api worker readiness test lint format

setup:
	uv sync

dev:
	docker compose up -d --build --wait
	uv run python scripts/wait_for_readiness.py

api:
	uv run uvicorn api.app:app --reload --port 8000

worker:
	uv run celery -A core.tasks.celery_app worker --pool=solo -l info -Q fabric,debate,maintenance

readiness:
	uv run python scripts/wait_for_readiness.py

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
