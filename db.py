"""
Database layer with SQLAlchemy backend and inline migrations.

Production (Vercel) uses PostgreSQL or Turso (libSQL). SQLite is still
supported for local development and tests because sqlite3 is part of the
Python standard library.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool, StaticPool

from config import settings


def _is_turso(url: str) -> bool:
    return url.startswith("libsql://") or url.startswith("sqlite+libsql://")


_IS_SQLITE = settings.database_url.startswith("sqlite") or _is_turso(settings.database_url)
_IS_TURSO = _is_turso(settings.database_url)

if _IS_TURSO:
    # Turso uses the libSQL SQLAlchemy dialect. Convert a plain libsql:// URL
    # to the sqlite+libsql:// dialect URL and supply the auth token.
    raw_url = settings.database_url
    if raw_url.startswith("libsql://"):
        raw_url = "sqlite+libsql://" + raw_url[len("libsql://"):]
    parsed = urlparse(raw_url)
    query = parsed.query
    if "secure" not in query:
        sep = "&" if query else "?"
        raw_url += f"{sep}secure=true"
    connect_args = {}
    if settings.turso_auth_token:
        connect_args["auth_token"] = settings.turso_auth_token
    # Use a static pool for Turso so repeated serverless requests reuse the same
    # remote connection instead of paying the TLS/handshake cost on every call.
    _engine = create_engine(
        raw_url,
        poolclass=StaticPool,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
elif _IS_SQLITE:
    _DB_PATH = settings.database_url.replace("sqlite:///", "").replace("sqlite://", "")
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    _local = threading.local()

    _engine = create_engine(
        settings.database_url,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
else:
    _engine = create_engine(settings.database_url, poolclass=NullPool)


class _RowProxy:
    """Expose SQLAlchemy/SQLite rows as dict-like objects."""

    def __init__(self, row):
        self._mapping = row._mapping
        self._keys = list(row._mapping.keys())

    def __getitem__(self, key: str):
        return self._mapping[key]

    def __contains__(self, key: str):
        return key in self._mapping

    def keys(self):
        return list(self._mapping.keys())

    def get(self, key: str, default=None):
        return self._mapping.get(key, default)


class _CursorResult:
    """Compatibility wrapper matching sqlite3 cursor API."""

    def __init__(self, result, lastrowid=None):
        self._result = result
        self.lastrowid = lastrowid

    def fetchone(self):
        row = self._result.fetchone()
        return _RowProxy(row) if row else None

    def fetchall(self) -> List[_RowProxy]:
        return [_RowProxy(row) for row in self._result.fetchall()]

    def scalar(self):
        row = self._result.fetchone()
        return row[0] if row else None


def _convert_placeholders(sql: str) -> str:
    """Convert positional ? placeholders to named :pN placeholders for PostgreSQL."""
    # Only convert standalone ? outside of string literals
    result = []
    in_string = False
    string_char = None
    param_index = [0]

    def repl(ch):
        if not in_string and ch == "?":
            param_index[0] += 1
            return f":p{param_index[0]}"
        return ch

    i = 0
    while i < len(sql):
        ch = sql[i]
        if not in_string and ch in ("'", '"'):
            in_string = True
            string_char = ch
            result.append(ch)
        elif in_string and ch == string_char:
            if i + 1 < len(sql) and sql[i + 1] == string_char:
                result.append(ch)
                result.append(sql[i + 1])
                i += 1
            else:
                in_string = False
                string_char = None
                result.append(ch)
        else:
            result.append(repl(ch))
        i += 1
    return "".join(result)


def _params(params: tuple):
    """Return parameters as a dictionary for SQLAlchemy named binds."""
    return {f"p{i + 1}": v for i, v in enumerate(params)}


def _prepare_sql(sql: str) -> str:
    """Adapt SQL for the active dialect."""
    # Convert positional ? placeholders to named :pN placeholders so the same
    # parameter dictionary can be used for both SQLite and PostgreSQL.
    sql = _convert_placeholders(sql)
    if _IS_SQLITE:
        sql = sql.replace("q.sent_at::date", "date(q.sent_at)")
        sql = sql.replace("sent_at::date", "date(sent_at)")
        sql = sql.replace("TIMESTAMPTZ", "TEXT")
        sql = sql.replace("DATE NOT NULL", "TEXT NOT NULL")
        sql = sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    return sql


def execute(sql: str, params: tuple = ()) -> _CursorResult:
    """Execute a statement and return a cursor-like result."""
    sql = _prepare_sql(sql)
    with _engine.begin() as conn:
        result = conn.execute(text(sql), _params(params))
        lastrowid = None
        if result.is_insert:
            try:
                pk = result.inserted_primary_key
                lastrowid = pk[0] if pk else None
            except Exception:
                pass
        # SQLAlchemy text() INSERTs do not report is_insert. Capture the id via
        # RETURNING when present, or SQLite's last_insert_rowid() helper.
        if lastrowid is None:
            upper = sql.strip().upper()
            if result.returns_rows:
                lastrowid = result.scalar()
            elif _IS_SQLITE and upper.startswith("INSERT"):
                lastrowid = conn.execute(text("SELECT last_insert_rowid() as id")).scalar()
        return _CursorResult(result, lastrowid=lastrowid)


def fetchone(sql: str, params: tuple = ()) -> Optional[_RowProxy]:
    sql = _prepare_sql(sql)
    with _engine.connect() as conn:
        result = conn.execute(text(sql), _params(params))
        row = result.fetchone()
        return _RowProxy(row) if row else None


def fetchall(sql: str, params: tuple = ()) -> List[_RowProxy]:
    sql = _prepare_sql(sql)
    with _engine.connect() as conn:
        result = conn.execute(text(sql), _params(params))
        return [_RowProxy(row) for row in result.fetchall()]


MIGRATIONS = [
    # migration 0: initial schema (PostgreSQL syntax; translated for SQLite at runtime)
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS accounts (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        encrypted_password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('sender','peer')),
        provider TEXT DEFAULT 'gmail',
        status TEXT DEFAULT 'active',
        health_score INTEGER DEFAULT 100,
        fail_count INTEGER DEFAULT 0,
        last_check TIMESTAMPTZ,
        last_error TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS templates (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        subject_template TEXT NOT NULL,
        body_template TEXT NOT NULL,
        reply_template TEXT,
        variables_json TEXT,
        is_default INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS campaigns (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        domain_name TEXT NOT NULL,
        sender_account_id INTEGER NOT NULL,
        template_id INTEGER,
        status TEXT DEFAULT 'active',
        daily_target INTEGER DEFAULT 5,
        ramp_weeks INTEGER DEFAULT 12,
        current_week INTEGER DEFAULT 1,
        tick_interval INTEGER DEFAULT 5,
        active_start INTEGER DEFAULT 9,
        active_end INTEGER DEFAULT 20,
        timezone TEXT DEFAULT 'UTC',
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(sender_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
        FOREIGN KEY(template_id) REFERENCES templates(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS campaign_peers (
        campaign_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(campaign_id, account_id),
        FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
        FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS email_queue (
        id SERIAL PRIMARY KEY,
        campaign_id INTEGER NOT NULL,
        from_account_id INTEGER NOT NULL,
        to_account_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        retry_count INTEGER DEFAULT 0,
        error TEXT,
        scheduled_at TIMESTAMPTZ NOT NULL,
        sent_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
        FOREIGN KEY(from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
        FOREIGN KEY(to_account_id) REFERENCES accounts(id) ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_email_queue_status ON email_queue(status);
    CREATE INDEX IF NOT EXISTS idx_email_queue_scheduled ON email_queue(scheduled_at);

    CREATE TABLE IF NOT EXISTS engagements (
        id SERIAL PRIMARY KEY,
        queue_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('move','open','reply')),
        value INTEGER NOT NULL,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(queue_id) REFERENCES email_queue(id) ON DELETE CASCADE,
        FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS reputation (
        id SERIAL PRIMARY KEY,
        campaign_id INTEGER NOT NULL,
        date DATE NOT NULL,
        sent INTEGER DEFAULT 0,
        moved INTEGER DEFAULT 0,
        opened INTEGER DEFAULT 0,
        replied INTEGER DEFAULT 0,
        score REAL DEFAULT 0,
        inbox_rate REAL DEFAULT 0,
        spam_rate REAL DEFAULT 0,
        UNIQUE(campaign_id, date),
        FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS agent_logs (
        id SERIAL PRIMARY KEY,
        level TEXT NOT NULL,
        source TEXT,
        message TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_agent_logs_created ON agent_logs(created_at);

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    INSERT INTO schema_version (version) VALUES (0)
    ON CONFLICT (version) DO NOTHING;
    """,
    # migration 1: performance indexes
    """
    CREATE INDEX IF NOT EXISTS idx_accounts_role ON accounts(role);
    CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
    CREATE INDEX IF NOT EXISTS idx_accounts_role_status ON accounts(role, status);
    CREATE INDEX IF NOT EXISTS idx_campaigns_sender ON campaigns(sender_account_id);
    CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
    CREATE INDEX IF NOT EXISTS idx_campaign_peers_campaign ON campaign_peers(campaign_id);
    CREATE INDEX IF NOT EXISTS idx_campaign_peers_account ON campaign_peers(account_id);
    CREATE INDEX IF NOT EXISTS idx_email_queue_campaign ON email_queue(campaign_id);
    CREATE INDEX IF NOT EXISTS idx_email_queue_from_account ON email_queue(from_account_id);
    CREATE INDEX IF NOT EXISTS idx_email_queue_to_account ON email_queue(to_account_id);
    CREATE INDEX IF NOT EXISTS idx_email_queue_sent_at ON email_queue(sent_at);
    CREATE INDEX IF NOT EXISTS idx_engagements_queue ON engagements(queue_id);
    CREATE INDEX IF NOT EXISTS idx_engagements_type ON engagements(type);
    CREATE INDEX IF NOT EXISTS idx_reputation_campaign ON reputation(campaign_id);
    CREATE INDEX IF NOT EXISTS idx_reputation_date ON reputation(date);
    CREATE INDEX IF NOT EXISTS idx_reputation_campaign_date ON reputation(campaign_id, date);
    """,
]


def _split_statements(sql: str) -> List[str]:
    """Split migration SQL into individual statements."""
    statements = []
    current = []
    in_string = False
    string_char = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if not in_string and ch in ("'", '"'):
            in_string = True
            string_char = ch
            current.append(ch)
        elif in_string and ch == string_char:
            current.append(ch)
            if i + 1 < len(sql) and sql[i + 1] == string_char:
                current.append(sql[i + 1])
                i += 1
            else:
                in_string = False
                string_char = None
        elif not in_string and ch == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def init_db():
    """Apply any pending migrations."""
    with _engine.begin() as conn:
        create_sql = """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """
        if _IS_SQLITE:
            create_sql = create_sql.replace("TIMESTAMPTZ", "TEXT")
        conn.execute(text(create_sql))

    row = fetchone("SELECT MAX(version) as v FROM schema_version")
    current = row["v"] if row and row["v"] is not None else -1

    for i, migration in enumerate(MIGRATIONS):
        if i > current:
            for stmt in _split_statements(migration):
                execute(stmt)
            execute("INSERT INTO schema_version (version) VALUES (:p1) ON CONFLICT (version) DO NOTHING", (i,))


def now() -> str:
    return datetime.utcnow().isoformat()


def today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def days_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=n)).strftime("%Y-%m-%d")
