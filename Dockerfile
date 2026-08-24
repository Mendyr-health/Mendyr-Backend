# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Pinned to the same uv version used to generate uv.lock — keeps container builds
# byte-identical to what `uv sync` installs on a developer's machine.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/srv/.venv/bin:$PATH"

WORKDIR /srv

# libpq-dev: psycopg build; the rest are geo/runtime libs pulled in transitively.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached separately from app code) straight from the lock file —
# `--frozen` fails the build if uv.lock is stale instead of silently re-resolving.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

RUN addgroup --system mendyr && adduser --system --ingroup mendyr mendyr
USER mendyr

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/healthz || exit 1

CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", \
     "-b", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
