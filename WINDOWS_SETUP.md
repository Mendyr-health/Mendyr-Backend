# Windows Setup Guide

Everything a Windows user needs to clone this repo and start developing — no WSL2, Docker, or
local Postgres install required. The project's database lives on Supabase (managed Postgres),
so a native Windows setup is just: install a couple of tools, fill in `.env`, run the app.

If you'd rather work inside a full Linux environment (matching `make` commands, Docker Compose,
etc. exactly as documented in `SETUP.md`), skip to **"Alternative: WSL2"** at the bottom instead.

---

## 1. Install prerequisites

- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/). During install,
  check **"Add python.exe to PATH"**.
- **Git for Windows** — [git-scm.com/download/win](https://git-scm.com/download/win). This also
  installs **Git Bash**, a good alternative terminal if PowerShell's quirks below annoy you.
- **uv** (Python dependency manager), in PowerShell:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
  Close and reopen your terminal afterward so `uv` is on `PATH`.

Confirm both installed correctly:
```powershell
python --version
uv --version
```

---

## 2. Clone the repo

```powershell
git clone <repo-url>
cd Mendly-Backend
```

Ask whoever's onboarding you which URL to use — this project currently has two remotes in play
(`kartikrana05/Mendly-Backend` and the `Mendyr-health/Mendyr-Backend` org repo). Either works
the same way from here on.

---

## 3. Configure `.env`

```powershell
copy .env.example .env
```

Open `.env` in any editor and fill in:

```
SECRET_KEY=<any random string for local dev>
```

Then the database section — **two scenarios**:

### Scenario A: joining an existing project (most common)

Someone already has a Supabase project set up for this app. Ask them for the Session pooler
connection details (or check the team's shared secrets/password manager), and fill in:

```
POSTGRES_HOST=aws-0-<region>.pooler.supabase.com
POSTGRES_PORT=5432
POSTGRES_USER=postgres.<project-ref>
POSTGRES_PASSWORD=<the shared DB password>
POSTGRES_DB=postgres
POSTGRES_SSL_REQUIRED=true
```

The schema and reference data already exist — skip straight to step 5 (no migration/seed
needed).

### Scenario B: starting a brand-new Supabase project

1. Create a project at [supabase.com](https://supabase.com).
2. In the dashboard: **Database → Extensions**, search `postgis`, enable it.
3. Click the green **Connect** button near the top of any dashboard page → **Session pooler**
   tab → copy the host/user shown there into `.env` as above.
4. Continue to step 4 below (you'll need to run migrations + seed since the DB is empty).

### Redis

Redis has no official Windows build, so the simplest choice is to skip it entirely — add this
to `.env`:

```
REDIS_ENABLED=false
```

This disables OTP resend-cooldown enforcement and falls back rate limiting to an in-process
store — both fine for local development. (If you specifically need real Redis behavior, see
"Alternative: WSL2" below instead.)

---

## 4. Install dependencies

```powershell
uv sync --extra dev
```

This creates a `.venv` and installs the exact versions pinned in `uv.lock` — no separate
`pip install` step, and no need to manually activate the venv; `uv run` (used below) finds it
automatically.

---

## 5. Run migrations + seed (skip if joining an existing project)

```powershell
uv run python scripts/run_migrations.py
uv run python -m scripts.seed
```

The first creates all 30 tables; the second populates service categories/services/
specializations. Both are safe to re-run — `scripts/run_migrations.py` tracks applied
filenames in a `schema_migrations` table, so re-running it after everything is applied just
no-ops, and the seed script is idempotent.

---

## 6. Run the app

```powershell
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 7. Verify it's working

Open in a browser or use `curl.exe` (see the note below about PowerShell's built-in `curl`):

- **http://localhost:8000/docs** — interactive API docs
- **http://localhost:8000/api/v1/healthz** — should return `{"status":"ok"}`
- **http://localhost:8000/api/v1/readyz** — should return `{"status":"ready"}` (confirms it can
  reach Supabase)

---

## Windows-specific gotchas

| Issue | Fix |
|---|---|
| `uv : File cannot be loaded because running scripts is disabled on this system` | PowerShell's execution policy is blocking the installer. Run PowerShell **as Administrator** once and execute `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`, then retry the `irm ... \| iex` install command. |
| `curl` in PowerShell doesn't behave like real curl (different flags, no `-X`, etc.) | PowerShell aliases `curl` to `Invoke-WebRequest`. Use `curl.exe` explicitly to get the real curl binary bundled with Windows, or just open the URLs in a browser for GET requests, or use Git Bash (installed with Git for Windows) which has real `curl`. |
| `make` is not recognized | The `Makefile` targets (`make dev`, `make migrate`, etc.) require `make`, which plain PowerShell/cmd don't have. Use the `uv run ...` commands directly as shown in this guide instead — they're exactly what each `make` target runs under the hood. |
| `python` not found / wrong version | Reinstall Python and make sure "Add python.exe to PATH" was checked, or use the Python launcher: `py -3.11 -m venv .venv`. |
| Line-ending warnings from Git (`LF will be replaced by CRLF`) | Harmless — Git is normalizing line endings on checkout. Don't disable this unless you know why. |

---

## Alternative: WSL2 (if you want the full Linux experience)

If you'd rather use `make`, Docker Compose, or match the macOS/Linux instructions in `SETUP.md`
exactly:

```powershell
wsl --install -d Ubuntu
```

Reboot if prompted, open the "Ubuntu" app from the Start menu, finish the one-time Linux user
setup, then follow `SETUP.md` from inside that Ubuntu terminal exactly as written for
macOS/Linux — `uv`, `make`, `git`, everything behaves identically to a real Linux box from
there. Clone the repo *inside* the Ubuntu filesystem (e.g. `~/Mendly-Backend`) rather than
under `/mnt/c/...` for noticeably faster installs and test runs.
