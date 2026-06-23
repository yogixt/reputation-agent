# Reputation Agent

A production-ready email reputation warm-up platform designed for serverless deployment on Vercel. Automatically sends emails from real Gmail accounts to your peer accounts, simulates organic engagement (opens, spam-to-inbox moves, replies), and tracks reputation scores over time.

## Features

- **Campaign Management** — Create warm-up campaigns per domain with ramp curves and schedules
- **Real Gmail Accounts** — Uses Gmail App Passwords for IMAP/SMTP (no fake accounts)
- **Email Templates** — Jinja2-powered templates with variables and live preview
- **Task Queue** — Built-in queue with retry logic and exponential backoff
- **Health Monitoring** — Automatic account health checks
- **Dashboard** — Stats, logs, and queue status UI
- **Authentication** — Session-based auth with bcrypt password hashing
- **Encrypted Credentials** — Gmail app passwords encrypted with Fernet
- **Analytics** — Per-campaign reputation score and inbox-rate charts

## Quick Start

### Local

```bash
# 1. Clone / enter the project
cd reputation-agent

# 2. Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment (required)
cp .env.example .env
python scripts/generate_keys.py   # paste keys into .env
# Set DATABASE_URL, ADMIN_EMAIL, and a strong ADMIN_PASSWORD in .env

# 4. Run tests
python -m pytest

# 5. Run locally (uses SQLite by default)
python main.py

# 6. Open http://localhost:8000
# Login with ADMIN_EMAIL / ADMIN_PASSWORD from .env
```

### Deploy on Vercel

1. **Provision a Postgres database**
   - Use Vercel Postgres, Neon, Supabase, or any hosted PostgreSQL.
   - Copy the connection string (must use `psycopg2`, e.g. `postgresql+psycopg2://...`).

2. **Deploy**
   ```bash
   vercel --prod
   ```

3. **Set environment variables**
   ```bash
   vercel env add DATABASE_URL production --sensitive
   vercel env add SECRET_KEY production --sensitive
   vercel env add ENCRYPTION_KEY production --sensitive
   vercel env add ADMIN_EMAIL production --sensitive
   vercel env add ADMIN_PASSWORD production --sensitive
   vercel env add CRON_SECRET production --sensitive
   ```

4. **Visit the production URL** and log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

## How It Works

1. **Add Gmail accounts** using App Passwords (enable 2FA, then generate at https://myaccount.google.com/apppasswords)
   - Add at least one **Sender** account
   - Add two or more **Peer** accounts
2. **Create email templates** for warm-up content
3. **Create a campaign** linking a domain, sender, peers, template, and schedule
4. **Cron jobs queue and send emails** during active hours (see `vercel.json`)
5. **Watch reputation grow** on the dashboard and analytics pages

## Architecture

```
reputation-agent/
├── main.py              # FastAPI app entry point
├── api/index.py         # Vercel serverless entry point
├── config.py            # Settings / env vars (required secrets enforced)
├── auth.py              # Session authentication
├── security.py          # Password hashing + Fernet encryption
├── limiter.py           # Rate limiter
├── db.py                # SQLAlchemy layer (PostgreSQL on Vercel, SQLite locally)
├── models.py            # Pydantic models
├── providers/gmail.py   # Gmail IMAP/SMTP client
├── routes/              # FastAPI routers
├── templates/emails.py  # Sandboxed Jinja2 email rendering
├── services/            # Business logic
├── static/              # Frontend SPA
├── tests/               # pytest suite
├── scripts/             # Helper scripts (key generation)
└── vercel.json          # Vercel routes and Cron Jobs
```

## Database Schema

- `users` — admin users
- `accounts` — Gmail accounts (sender/peer) with encrypted passwords
- `templates` — email templates
- `campaigns` — warm-up campaigns
- `campaign_peers` — many-to-many campaign ↔ peer
- `email_queue` — pending/running/sent/failed jobs
- `engagements` — opens, moves, replies
- `reputation` — daily reputation snapshots per campaign
- `agent_logs` — system and agent logs
- `settings` — runtime configuration

## Security Notes

- `SECRET_KEY`, `ENCRYPTION_KEY`, `ADMIN_PASSWORD`, `ADMIN_EMAIL`, `CRON_SECRET`, and `DATABASE_URL` are required; the app refuses to start with placeholder values
- Never commit `.env` to version control
- Gmail passwords are encrypted at rest using Fernet symmetric encryption
- Session cookies are HTTP-only and Secure in production
- CORS defaults to same-origin only; configure `CORS_ORIGINS` explicitly if needed
- Login is rate-limited (default 5/minute)
- Email templates render in a sandboxed Jinja2 environment
- Cron endpoints require the `CRON_SECRET` token in the `Authorization` header

## Cron Jobs

Vercel Cron Jobs are defined in `vercel.json`:

| Path | Default schedule | Purpose |
|------|------------------|---------|
| `/api/cron/queue` | `0 9 * * *` | Queue emails and process pending jobs |
| `/api/cron/health` | `0 10 * * *` | Check account health |
| `/api/cron/reputation` | `0 11 * * *` | Calculate reputation scores |
| `/api/cron/advance-weeks` | `5 0 * * 1` | Advance campaign ramp weeks |
| `/api/cron/log-cleanup` | `0 2 * * *` | Clean old logs |

On Vercel Hobby, cron jobs are limited to once per day. Upgrade to Pro for more frequent schedules.

## Troubleshooting

- **Invalid credentials**: Make sure you're using Gmail App Passwords, not your normal Gmail password
- **Spam folder not found**: The provider auto-detects `[Gmail]/Spam`, `Spam`, `Junk`, and `INBOX.Spam`
- **Queue not processing**: Cron jobs handle queue processing on Vercel; locally run `python main.py`
- **Account health low**: Check the account password and that IMAP is enabled in Gmail settings
- **Deployment error**: Ensure `DATABASE_URL` is set to a reachable PostgreSQL server
