.PHONY: install dev run worker beat migrate revision seed repair-migrations repair-migrations-apply lint format test up down logs lock

# Every target runs through `uv run`, which uses the exact versions pinned in uv.lock —
# no manual venv activation needed, and every teammate gets identical dependency versions.

install:
	uv sync --extra dev

lock:
	uv lock

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run:
	uv run gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000

worker:
	uv run celery -A app.workers.celery_app worker --loglevel=info

beat:
	uv run celery -A app.workers.celery_app beat --loglevel=info

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(m)"

seed:
	uv run python -m scripts.seed

repair-migrations:
	uv run python -m scripts.repair_migrations

repair-migrations-apply:
	uv run python -m scripts.repair_migrations --apply

lint:
	uv run ruff check app/
	uv run mypy app/

format:
	uv run ruff format app/
	uv run ruff check --fix app/

test:
	uv run pytest --cov=app --cov-report=term-missing

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api worker beat
