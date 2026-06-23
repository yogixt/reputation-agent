# Reputation Agent — Agent Notes

## Quick Start

```bash
# 1. Configure secrets
cp .env.example .env
python scripts/generate_keys.py   # paste output into .env
# Set DATABASE_URL, ADMIN_EMAIL, and a strong ADMIN_PASSWORD in .env

# 2. Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Run tests
python -m pytest

# 4. Start server locally (SQLite)
python main.py
```

## Critical Security Rules

- **Never commit `.env`**. It contains `SECRET_KEY`, `ENCRYPTION_KEY`, and `ADMIN_PASSWORD`.
- `ENCRYPTION_KEY` encrypts stored Gmail app passwords. Losing it means those credentials are unrecoverable.
- The app refuses to start with placeholder secrets (`change-me-*`, `admin123`, `admin@reputation.agent`, empty).
- CORS defaults to same-origin only. Set `CORS_ORIGINS` only if the SPA is hosted on a different origin.

## Project Layout

- `main.py` — FastAPI entry point, lifespan, middleware.
- `api/index.py` — Vercel serverless entry point.
- `config.py` — Pydantic settings; required env vars are enforced.
- `security.py` — bcrypt passwords + Fernet credential encryption.
- `db.py` — SQLAlchemy layer with inline schema migrations. PostgreSQL on Vercel; SQLite for local dev/tests.
- `routes/` — FastAPI routers.
- `api/cron.py` (mounted via `routes/cron.py`) — Vercel Cron Job endpoints.
- `services/` — Business logic.
- `providers/gmail.py` — IMAP/SMTP Gmail client.
- `templates/emails.py` — Sandboxed Jinja2 email rendering.
- `tests/` — pytest suite.

## Common Tasks

### Generate new keys
```bash
python scripts/generate_keys.py
```

### Deploy to Vercel
```bash
vercel --prod
vercel env add DATABASE_URL production --sensitive
vercel env add SECRET_KEY production --sensitive
vercel env add ENCRYPTION_KEY production --sensitive
vercel env add ADMIN_PASSWORD production --sensitive
vercel env add CRON_SECRET production --sensitive
```

### Add a database migration
Edit `db.py` and append a new string to `MIGRATIONS`. `init_db()` applies missing migrations automatically.

### Test against a fresh database
Tests use temporary SQLite databases automatically via `tests/conftest.py`.

## Architecture Decisions

- **PostgreSQL in production** (required for Vercel). SQLite remains supported for local development and tests only.
- **Vercel Cron Jobs** replace APScheduler because long-running background processes are not available on serverless platforms.
- **Session-based auth** for the SPA. CSRF protection relies on `SameSite=Lax` and HTTPS in production.
- **In-memory rate limiting** via slowapi. For multi-instance deployments, switch to Redis storage.
- **Queue processing** is triggered by the `/api/cron/queue` cron job.
- **Ramp weeks** advance automatically every Monday at 00:05 UTC via the cron job.

## Known Limitations

- Gmail is the only email provider.
- Single-user admin model; no RBAC.
- No built-in email delivery analytics beyond opens/moves/replies.
- Vercel Hobby limits cron jobs to once per day; upgrade to Pro for more frequent ticks.
- WebSocket real-time updates work locally but are unreliable across multiple Vercel serverless instances.
