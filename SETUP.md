# Local Setup Guide

Three ways to get a Postgres+PostGIS database for Mendyr: **Supabase** (managed, zero local
install), **Docker Compose** (simplest self-hosted option, identical on every OS), or a **native
setup** installing Postgres+PostGIS/Redis directly. Instructions below cover macOS and Windows
for the self-hosted paths.

**If you don't want to manage a local database at all, use Supabase** — see the very next
section. Otherwise, Docker Compose is the next-easiest and sidesteps two genuinely annoying
Windows problems: Postgres+PostGIS has no official Windows installer bundle, and Redis has no
official Windows build at all.

---

## Option 0 — Supabase Postgres (managed, no local Postgres needed)

Supabase gives you a hosted Postgres with PostGIS available as a one-click extension — you still
need Redis locally (Supabase doesn't provide that), but the database itself needs no local
install at all. This is the fastest way to get running, and works identically on macOS/Windows
since it's just a connection string.

### 1. Create the project and enable PostGIS

1. Create a project at [supabase.com](https://supabase.com) (or use an existing one).
2. In the dashboard: **Database → Extensions**, search `postgis`, and enable it. (Equivalent SQL,
   run in the **SQL Editor** if you prefer: `create extension if not exists postgis;`)

### 2. Get your connection string — pick the right one

Go to **Project Settings → Database → Connection string**. Supabase offers three modes; **use
the Session pooler** unless you have a specific reason not to:

| Mode | Port | Use for Mendyr? |
|---|---|---|
| Direct connection | 5432 | Works, but is **IPv6-only** unless you've paid for Supabase's IPv4 add-on — many home/office networks and some CI runners can't reach it. |
| **Session pooler** (recommended) | 5432 (pooler host) | ✅ IPv4-compatible, keeps a dedicated backend connection per client (so prepared statements work normally) — no extra config needed beyond the connection details. |
| Transaction pooler | 6543 | Also IPv4-compatible, but PgBouncer hands each query to a different backend connection, which breaks asyncpg's prepared-statement cache. Only use this if you specifically need its higher connection-multiplexing (e.g. serverless functions each opening their own connection) — see the flag below. |

### 3. Configure `.env`

Copy the host/port/user/password from the connection string Supabase shows you into the
existing `POSTGRES_*` variables — don't paste the whole URI, the app builds it from these parts:

```
POSTGRES_HOST=aws-0-<region>.pooler.supabase.com   # from your Session pooler connection string
POSTGRES_PORT=5432
POSTGRES_USER=postgres.<your-project-ref>           # pooler usernames include the project ref
POSTGRES_PASSWORD=<your DB password>
POSTGRES_DB=postgres
POSTGRES_SSL_REQUIRED=true
DB_DISABLE_PREPARED_STATEMENT_CACHE=false
```

If you use the **Transaction pooler** (port 6543) instead, set:

```
POSTGRES_PORT=6543
DB_DISABLE_PREPARED_STATEMENT_CACHE=true
```

`POSTGRES_SSL_REQUIRED=true` makes both the app's asyncpg connection and the migration
runner's psycopg connection negotiate TLS — Supabase rejects plaintext connections, so this
must be `true`.

### 4. Run migrations and seed, same as any other Postgres

```bash
make migrate     # uv run python scripts/run_migrations.py
make seed        # uv run python -m scripts.seed
```

Redis is used for OTP resend-cooldown and rate limiting — install it via Homebrew (macOS) or run
it under WSL2/Docker (Windows), as shown in the options below, point `REDIS_URL` at a managed
Redis (Upstash, etc.), **or just skip it entirely**: set `REDIS_ENABLED=false` in `.env` and the
app runs with no Redis at all (rate limiting falls back to an in-process store, OTP resend
cooldown is skipped). This is the simplest choice on native Windows, where Redis has no official
build.

**Joining an existing project?** If you're adding a teammate to a project that already has a
Supabase database set up, skip steps 1–2 and step 4 (schema + reference data already exist) —
just get the Session pooler host/user/password from whoever set it up (or the team's shared
`.env`) and go straight to step 3, then the "Run the app" step below.

Then continue from **step 8 ("Run the app")** in the Common steps section below.

---

## Option A — Docker Compose (recommended, both OS)

**Prerequisite:** Docker Desktop, installed and running.
- macOS: `brew install --cask docker`, then open it once from Applications.
- Windows: install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
  with the **WSL2 backend** (the installer defaults to this — accept it). Requires WSL2, which
  the installer will set up for you if it's missing.

Confirm Docker is actually running before continuing:

```bash
docker info
```

If that errors, start Docker Desktop and wait for its whale icon to show "running" before
retrying.

### macOS / Linux (bash/zsh)

```bash
cp .env.example .env
# edit .env: set SECRET_KEY, and any provider keys you have (Razorpay/MSG91/FCM) — safe to
# leave the rest as defaults for local dev.

make up
```

### Windows

`make` isn't available in a plain Windows `cmd`/PowerShell prompt. Either run the setup from
**WSL2** (where `make` works exactly like Linux — just open an Ubuntu terminal and follow the
macOS/Linux commands above), or run the equivalent `docker compose` commands directly from
PowerShell:

```powershell
copy .env.example .env
# edit .env in Notepad/VS Code: set SECRET_KEY, and any provider keys you have.

docker compose up --build
```

(`make up`/`make down`/`make logs` in the Makefile are just short aliases for `docker compose
up --build` / `docker compose down -v` / `docker compose logs -f api worker beat` — use whichever
side you're comfortable with.)

### Both platforms, once containers are up

This starts `postgres` (PostGIS baked in), `redis`, `api`, `worker`, and `beat` together. The
`api` container runs `make migrate` (`scripts/run_migrations.py`) automatically before serving
traffic. Then seed
reference data from your host machine (needs the Python venv from step 5 of Option B, or run it
inside the container):

```bash
docker compose exec api uv run python -m scripts.seed
```

Check it's alive: `curl http://localhost:8000/api/v1/healthz`. Docs at
`http://localhost:8000/docs`.

Stop everything (and wipe the DB volume): `make down` (or `docker compose down -v` on Windows).

---

## Option B — Native setup

Only do this if you specifically want to run Postgres/Redis/Python directly on your machine
without Docker (e.g. for faster edit-reload cycles). Pick your OS below.

### macOS (Homebrew)

**1. Check what you already have**

```bash
brew services list | grep -E "postgresql|redis"
```

If you already run Postgres for other projects (e.g. `postgresql@16` on port 5432), **don't
repurpose it** — Mendyr needs the **PostGIS** extension, which that instance may not have, and
you don't want to touch another project's database. Run a second, dedicated Postgres instance
on its own port instead (steps below use port **5433**).

**2. Install PostGIS-capable Postgres + Redis**

```bash
brew install postgresql@17 postgis redis
brew services start redis          # if not already running
```

**3. Create a dedicated data directory and start Postgres on port 5433**

Do **not** use `brew services start postgresql@17` if `postgresql@16` (or anything else) is
already on port 5432 — the default config for both formulas listens on 5432 and they'll
conflict. Instead, initialize a separate cluster for this project:

```bash
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"

# macOS gotcha: initdb/pg_ctl can fail with
#   FATAL: postmaster became multithreaded during startup
#   HINT:  Set the LC_ALL environment variable to a valid locale.
# Setting LANG/LC_ALL to C avoids it — do this in every shell you run these commands from.
export LANG=C LC_ALL=C

initdb -D .pgdata -U mendyr --auth=trust -E UTF8 --locale=C
pg_ctl -D .pgdata -o "-p 5433" -l .pgdata/server.log start
```

Create the database and enable PostGIS:

```bash
createdb -h 127.0.0.1 -p 5433 -U mendyr mendyr
psql -h 127.0.0.1 -p 5433 -U mendyr -d mendyr -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

To stop it later: `pg_ctl -D .pgdata stop`. `.pgdata/` is already covered by `.gitignore` — it's
local-only state, never commit it.

Continue at **"Common steps"** below, using `POSTGRES_HOST=127.0.0.1` / `POSTGRES_PORT=5433`.

### Windows

Native Postgres+PostGIS on Windows means installing the EnterpriseDB Postgres installer, then
running **Stack Builder** separately to add PostGIS, and Redis has no official Windows port at
all (Microsoft's old port is unmaintained). The realistic path that mirrors the macOS/Linux
instructions almost exactly is **WSL2** — a real Ubuntu userspace running under Windows.

**1. Install WSL2** (skip if already set up)

In an elevated PowerShell:

```powershell
wsl --install -d Ubuntu
```

Reboot if prompted, then open the "Ubuntu" app from the Start menu and finish the one-time
Linux user setup.

**2. Inside the Ubuntu/WSL2 terminal, install Postgres + PostGIS + Redis**

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib postgis postgresql-16-postgis-3 redis-server python3-venv python3-pip make git
sudo service redis-server start
```

(Package name suffixes like `postgresql-16-postgis-3` track the Ubuntu release's default
Postgres version — if `apt install` complains the package doesn't exist, run
`apt search postgis` to find the version-matched package name.)

**3. Start Postgres and create the database**

```bash
sudo service postgresql start
sudo -u postgres createuser -s mendyr
sudo -u postgres psql -c "ALTER USER mendyr WITH PASSWORD 'mendyr';"
sudo -u postgres createdb -O mendyr mendyr
psql -h 127.0.0.1 -U mendyr -d mendyr -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

This runs on the default port 5432 inside WSL2 — that's fine, it's an isolated Linux
environment, not your Windows host's port 5432 (if anything is even using that on Windows).

**4. Get the project into WSL2**

Either `git clone` it directly inside the Ubuntu filesystem (fastest disk I/O), or work from
your Windows checkout via the `/mnt/c/...` path if you'd rather edit from a Windows editor —
both work, but native `~/mendyr-backend` is noticeably faster for installs/test runs.

Continue at **"Common steps"** below, run entirely inside the Ubuntu/WSL2 terminal, using
`POSTGRES_HOST=127.0.0.1` / `POSTGRES_PORT=5432`.

> **Prefer to stay fully native on Windows (no WSL2)?** It's possible but not covered
> step-by-step here: install Postgres via the [EDB installer](https://www.postgresql.org/download/windows/),
> run **Stack Builder** (bundled with it) to add the PostGIS extension, and run Redis via
> [Memurai](https://www.memurai.com/) (a Redis-compatible Windows service) or inside Docker
> just for that one dependency. Given the extra moving parts, Option A (Docker Compose) or WSL2
> will save you time.

---

### Common steps (after Postgres/Redis are running, either OS)

**4. Configure `.env`**

```bash
cp .env.example .env   # Windows native/PowerShell: copy .env.example .env
```

Edit `POSTGRES_HOST`/`POSTGRES_PORT` to match what you set up above, e.g. for the macOS
instructions:

```
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5433
POSTGRES_USER=mendyr
POSTGRES_PASSWORD=
POSTGRES_DB=mendyr
```

or for WSL2 (default port, password set):

```
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=mendyr
POSTGRES_PASSWORD=mendyr
POSTGRES_DB=mendyr
```

Also set `SECRET_KEY` to any random string (`openssl rand -hex 32`, available in WSL2/macOS; on
native Windows PowerShell use `python -c "import secrets; print(secrets.token_hex(32))"`).
Everything else has a working local default — see `.env.example` for the full list (OTP/JWT/
marketplace rules, provider keys, etc.).

**5. Python environment**

Dependencies are pinned in `uv.lock` — everyone who runs `uv sync` gets the exact same package
versions, not just whatever `>=` floor `pip` happens to resolve that day. Install
[uv](https://docs.astral.sh/uv/getting-started/installation/) once:

```bash
# macOS/Linux/WSL2:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Native Windows (PowerShell):
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

then:

```bash
uv sync --extra dev      # creates .venv and installs the exact locked versions
```

Prefer plain `pip`? It still works (`pip install -e ".[dev]"`), but won't guarantee identical
versions across teammates' machines — use `uv sync` if reproducibility matters, e.g. onboarding
someone new or debugging a "works on my machine" issue.

From here on, run project commands with `uv run <command>` (e.g. `uv run python
scripts/run_migrations.py`) instead of activating a venv manually — every `make` target
already does this for you.

**6. Run migrations**

```bash
make migrate      # uv run python scripts/run_migrations.py
```

This creates all 30 tables. Confirm with `psql -h 127.0.0.1 -p <port> -U mendyr -d mendyr -c "\dt"`.

**7. Seed reference data**

```bash
make seed        # uv run python -m scripts.seed
```

Idempotent — populates service categories (Nursing Care, Physiotherapy, Elder Care, ...),
services, and specializations. Safe to re-run any time.

**8. Run the app**

```bash
make dev
# equivalent to: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In separate terminals, if you want background jobs running (offer-expiry sweep, payout
generation, visit reminders):

```bash
make worker   # celery -A app.workers.celery_app worker --loglevel=info
make beat     # celery -A app.workers.celery_app beat --loglevel=info
```

(No `make` on native Windows without WSL2 — run the `uvicorn`/`celery` commands shown above
directly.)

**9. Verify it's working**

```bash
curl http://localhost:8000/api/v1/healthz          # {"status": "ok"}
curl http://localhost:8000/api/v1/readyz           # {"status": "ready"}  — confirms DB connectivity
curl http://localhost:8000/api/v1/services/categories
```

Interactive docs: http://localhost:8000/docs

Try the OTP login flow end-to-end:

```bash
curl -X POST http://localhost:8000/api/v1/auth/otp/request \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+919876500000","purpose":"login"}'
# the OTP code is printed in the server console (ConsoleSMSProvider) since SMS_PROVIDER=console

curl -X POST http://localhost:8000/api/v1/auth/otp/verify \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"+919876500000","purpose":"login","code":"<code from console>","full_name":"Test Patient","role":"patient"}'
# returns { "access_token": "...", "refresh_token": "..." }
```

(On native Windows PowerShell, `curl` is aliased to `Invoke-WebRequest` with different flags —
either use `curl.exe` explicitly to get the real curl binary, or run these from WSL2/Git Bash.)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `initdb`/`pg_ctl` fails with "postmaster became multithreaded during startup" (macOS) | Set `export LANG=C LC_ALL=C` before running Postgres commands (macOS-specific Homebrew/Postgres 17 issue). |
| `createdb`/`psql` connection refused | Confirm the right port — `pg_isready -h 127.0.0.1 -p <port>`. If you have another Postgres already running, don't mix them up. |
| `CREATE EXTENSION postgis` fails: "could not open extension control file" | PostGIS isn't installed for this Postgres version. macOS: `brew install postgis` must match the running `postgresql@*` formula version. WSL2/Ubuntu: install the version-suffixed package, e.g. `postgresql-16-postgis-3`. |
| `make migrate` fails with `relation "..." does not exist` mid-way | `make migrate` applies `migrations/001_extensions.sql` first, which runs `CREATE EXTENSION IF NOT EXISTS postgis` for you — no manual `CREATE EXTENSION` step needed. If it still fails here, the connecting Postgres user lacks `CREATE EXTENSION` rights (common on some managed/shared hosts); grant that privilege (or ask whoever administers the DB to run migration 001's `CREATE EXTENSION` statements once as a superuser), then re-run `make migrate`. |
| `docker info` errors / `docker compose up` hangs | Docker Desktop isn't running — start it, wait for it to report healthy, then retry. On Windows, confirm WSL2 integration is enabled in Docker Desktop's settings. |
| `make` not found (Windows) | You're in native PowerShell/cmd, not WSL2 — either run commands from a WSL2 Ubuntu terminal, or use the raw `uvicorn`/`celery`/`docker compose` commands shown inline above. |
| Tests wipe your dev data | `tests/conftest.py` runs `Base.metadata.create_all`/`drop_all` against whatever DB your `.env` points at. Point `POSTGRES_*` at a **separate** disposable test database before running `make test`, or re-run `make migrate && make seed` afterward to restore your dev DB. |
| Redis connection errors | macOS: `brew services list | grep redis`, start with `brew services start redis`. WSL2: `sudo service redis-server status`, start with `sudo service redis-server start`. |

See `ARCHITECTURE.md` for the folder structure, domain model, and what each service does.
