.PHONY: install dev run worker beat migrate revision lint format test up down logs

install:
	pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run:
	gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000

worker:
	celery -A app.workers.celery_app worker --loglevel=info

beat:
	celery -A app.workers.celery_app beat --loglevel=info

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

lint:
	ruff check app/
	mypy app/

format:
	ruff format app/
	ruff check --fix app/

test:
	pytest --cov=app --cov-report=term-missing

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api worker beat
