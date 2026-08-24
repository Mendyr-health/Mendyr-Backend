# Deploying to FastAPI Cloud

FastAPI Cloud is the managed hosting platform built by the FastAPI team, driven by the
`fastapi` CLI's `deploy`/`cloud` subcommands (from the `fastapi-cloud-cli` package, installed
automatically with `fastapi[standard]`). This guide was written against `fastapi-cloud-cli`
0.22.2 by actually installing it and inspecting `--help` output — not from memory — so the
commands below are real.

## What it does and doesn't do — read this first

**FastAPI Cloud deploys your ASGI app only.** It has no visible mechanism for running a
separate long-lived worker process. That matters a lot for Mendyr specifically:

- ✅ The FastAPI app (`app/main.py:app`) — all 36 HTTP endpoints — deploys fine as-is.
- ❌ **Celery `worker` and `beat` do not run on FastAPI Cloud.** That means the offer-expiry
  sweep (`sweep_expired_offers`, every 15s — this is how a `SEARCHING` booking escalates to a
  wider radius or fails over), weekly payout generation, and visit reminders **will not fire**
  unless you run them somewhere else. See "Running Celery separately" below — don't skip it,
  the booking dispatch flow silently stalls without it.
- FastAPI Cloud doesn't provide Postgres or Redis. You need external Postgres+PostGIS
  (**Supabase** — see `SETUP.md`'s "Option 0", already set up for this project) and an external
  Redis (e.g. [Upstash](https://upstash.com/), which has a free tier and works over TLS the same
  way Supabase does for Postgres).
- It builds from `pyproject.toml`/`uv.lock` in the target directory — **not** from our
  `Dockerfile`. The Dockerfile stays relevant for the Docker Compose path and for wherever you
  run the Celery worker/beat, just not for the FastAPI Cloud deploy itself.
- Migrations are **not** run automatically. Run `make migrate` (or the direct
  `uv run python scripts/run_migrations.py` form) against the production database yourself (from
  your machine, since Supabase is reachable the same way it is for local dev) before/after each
  deploy that changes the schema.

## 1. Install the CLI and log in

```bash
pip install "fastapi[standard]"   # bundles fastapi-cloud-cli — do this in a throwaway env or
                                   # pipx, not inside this project's uv-managed .venv
fastapi login
```

Opens a browser to authorize the CLI against your FastAPI Cloud account.

## 2. Set environment variables

FastAPI Cloud has no concept of a committed `.env` file — variables are pushed via the CLI (or
its dashboard) and injected into the running app. `app/core/config.py` reads them from the
process environment the same way either way, so no code changes are needed.

From the project root:

```bash
fastapi cloud env set SECRET_KEY "$(openssl rand -hex 32)" --secret
fastapi cloud env set ENVIRONMENT production
fastapi cloud env set DEBUG false
fastapi cloud env set LOG_JSON true
fastapi cloud env set CORS_ORIGINS '["https://your-app-domain.com"]'
fastapi cloud env set ALLOWED_HOSTS '["your-app-domain.com"]'

# Database — Supabase Session pooler details (see SETUP.md "Option 0")
fastapi cloud env set POSTGRES_HOST aws-0-<region>.pooler.supabase.com
fastapi cloud env set POSTGRES_PORT 5432
fastapi cloud env set POSTGRES_USER "postgres.<your-project-ref>"
fastapi cloud env set POSTGRES_PASSWORD "<your DB password>" --secret
fastapi cloud env set POSTGRES_DB postgres
fastapi cloud env set POSTGRES_SSL_REQUIRED true

# Redis (Upstash or similar — needs to be reachable from both FastAPI Cloud and wherever
# you run the Celery worker/beat, since they share the same queue)
fastapi cloud env set REDIS_URL "rediss://<upstash-connection-string>"
fastapi cloud env set CELERY_BROKER_URL "rediss://<upstash-connection-string>/1"
fastapi cloud env set CELERY_RESULT_BACKEND "rediss://<upstash-connection-string>/2"

# Provider keys — whichever you're actually using in production
fastapi cloud env set RAZORPAY_KEY_ID "rzp_live_..." --secret
fastapi cloud env set RAZORPAY_KEY_SECRET "..." --secret
fastapi cloud env set RAZORPAY_WEBHOOK_SECRET "..." --secret
fastapi cloud env set SMS_PROVIDER msg91
fastapi cloud env set MSG91_AUTH_KEY "..." --secret
```

`--secret` marks a variable as write-only/masked in the dashboard — use it for anything
resembling a password, API key, or signing secret. `fastapi cloud env list` shows what's set;
`fastapi cloud env get NAME` / `env delete NAME` manage individual values.

## 3. Run migrations against the production database

```bash
POSTGRES_HOST=aws-0-<region>.pooler.supabase.com \
POSTGRES_PORT=5432 \
POSTGRES_USER="postgres.<your-project-ref>" \
POSTGRES_PASSWORD="<your DB password>" \
POSTGRES_DB=postgres \
POSTGRES_SSL_REQUIRED=true \
uv run python scripts/run_migrations.py
```

(Or duplicate `.env` as `.env.production` locally with these values and load it — either way,
this runs from your machine against the same Supabase instance the deployed app will use, since
`scripts/run_migrations.py` connects directly via `psycopg` using the same `POSTGRES_*` settings
locally or in CI — no ORM or app import graph involved.)

## 4. Deploy

```bash
fastapi deploy
```

Reads `pyproject.toml`/`uv.lock` from the current directory, auto-detects `app/main.py`'s `app`
object (matches Mendyr's layout exactly — no `--entrypoint` flag needed), builds, and deploys.
First run creates a `.fastapicloud/cloud.json` linking this directory to the new app (`fastapi
cloud apps list` / `fastapi cloud unlink` manage that link).

## 5. Verify

```bash
fastapi cloud logs                                    # tail the running app's logs
curl https://<your-app>.fastapicloud.app/api/v1/healthz
curl https://<your-app>.fastapicloud.app/api/v1/readyz   # confirms it can reach Supabase
```

## 6. Auto-deploy on push (optional)

```bash
fastapi cloud setup-ci --branch main
```

Provisions a deploy token, adds it as a GitHub Actions secret, and writes a workflow that runs
`fastapi deploy` on every push to `main`. Use `--dry-run` first to see exactly what it would do
before it touches your repo/secrets.

## Running Celery worker + beat separately

Since FastAPI Cloud only runs the web process, deploy `worker` and `beat` (the same two
services `docker-compose.yml` already defines) to any host that can run our existing
`Dockerfile` and reach the same Supabase database + Redis instance the API uses — a small
Railway/Render/Fly.io service, or a cheap always-on VM, all work. Point them at the identical
`POSTGRES_*`, `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` values you set on
FastAPI Cloud, since the worker needs to read/write the same booking rows and the same Redis
queue the API enqueues work onto.

If you'd rather not run an always-on worker at all, the periodic jobs
(`sweep_expired_offers`/reminders/payouts — see `app/workers/tasks/`) could be converted into
protected HTTP endpoints triggered by an external scheduler (GitHub Actions cron, cron-job.org,
Supabase's `pg_cron`) instead of Celery beat — that's a real code change, not just config, so
it's not done here; ask if you want that built out.
