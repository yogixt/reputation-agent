"""
SQLite database for Reputation Agent
"""

import sqlite3
from datetime import datetime, timedelta

DB = "reputation.db"

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS domains (
        id INTEGER PRIMARY KEY,
        domain_name TEXT NOT NULL,
        sender_email TEXT,
        status TEXT DEFAULT 'active',
        daily_target INTEGER DEFAULT 5,
        current_week INTEGER DEFAULT 1,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password TEXT,
        role TEXT DEFAULT 'peer',
        status TEXT DEFAULT 'active',
        health TEXT DEFAULT 'good',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS sends (
        id INTEGER PRIMARY KEY,
        domain_id INTEGER,
        from_email TEXT,
        to_email TEXT,
        subject TEXT,
        body TEXT,
        status TEXT,
        sent_at TEXT
    );

    CREATE TABLE IF NOT EXISTS engagements (
        id INTEGER PRIMARY KEY,
        send_id INTEGER,
        type TEXT,
        value INTEGER,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS reputation (
        id INTEGER PRIMARY KEY,
        domain_id INTEGER,
        date TEXT,
        sent INTEGER DEFAULT 0,
        moved INTEGER DEFAULT 0,
        opened INTEGER DEFAULT 0,
        replied INTEGER DEFAULT 0,
        score REAL DEFAULT 0,
        inbox_rate REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS agent_logs (
        id INTEGER PRIMARY KEY,
        level TEXT,
        message TEXT,
        created_at TEXT
    );
    ''')
    c.commit()
    c.close()

# ─── Domains ───
def add_domain(domain_name, sender_email, daily_target=5):
    c = conn()
    cur = c.execute(
        "INSERT INTO domains (domain_name, sender_email, daily_target, created_at) VALUES (?,?,?,?)",
        (domain_name, sender_email, daily_target, now())
    )
    c.commit()
    c.close()
    return cur.lastrowid

def get_domains():
    c = conn()
    rows = c.execute("SELECT * FROM domains ORDER BY created_at DESC").fetchall()
    c.close()
    return rows

def delete_domain(domain_id):
    c = conn()
    c.execute("DELETE FROM domains WHERE id = ?", (domain_id,))
    c.commit()
    c.close()

# ─── Accounts ───
def add_account(email, password, role='peer'):
    c = conn()
    try:
        cur = c.execute(
            "INSERT INTO accounts (email, password, role, created_at) VALUES (?,?,?,?)",
            (email, password, role, now())
        )
        c.commit()
        c.close()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        c.close()
        return None

def get_accounts():
    c = conn()
    rows = c.execute("SELECT * FROM accounts ORDER BY created_at DESC").fetchall()
    c.close()
    return rows

def delete_account(account_id):
    c = conn()
    c.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    c.commit()
    c.close()

def get_peers(domain_id=None):
    c = conn()
    rows = c.execute("SELECT email, password FROM accounts WHERE role = 'peer' AND status = 'active'").fetchall()
    c.close()
    return rows

def get_sender():
    c = conn()
    row = c.execute("SELECT email, password FROM accounts WHERE role = 'sender' AND status = 'active' LIMIT 1").fetchone()
    c.close()
    return row

# ─── Sends ───
def add_send(domain_id, from_email, to_email, subject, body):
    c = conn()
    cur = c.execute(
        "INSERT INTO sends (domain_id, from_email, to_email, subject, body, status, sent_at) VALUES (?,?,?,?,?,?,?)",
        (domain_id, from_email, to_email, subject, body, 'sent', now())
    )
    c.commit()
    c.close()
    return cur.lastrowid

def get_recent_sends(limit=50):
    c = conn()
    rows = c.execute("SELECT * FROM sends ORDER BY sent_at DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return rows

def update_send_status(send_id, status):
    c = conn()
    c.execute("UPDATE sends SET status = ? WHERE id = ?", (status, send_id))
    c.commit()
    c.close()

# ─── Engagement ───
def add_engagement(send_id, etype, value):
    c = conn()
    c.execute("INSERT INTO engagements (send_id, type, value, created_at) VALUES (?,?,?,?)",
              (send_id, etype, value, now()))
    c.commit()
    c.close()

def get_today_engagements(domain_id):
    c = conn()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = c.execute('''
        SELECT type, COUNT(*) FROM engagements e
        JOIN sends s ON e.send_id = s.id
        WHERE s.domain_id = ? AND date(e.created_at) = ?
        GROUP BY type
    ''', (domain_id, today)).fetchall()
    c.close()
    return {r[0]: r[1] for r in rows}

# ─── Reputation ───
def record_reputation(domain_id, sent, moved, opened, replied, score, inbox_rate):
    c = conn()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute('''
        INSERT INTO reputation (domain_id, date, sent, moved, opened, replied, score, inbox_rate)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT DO UPDATE SET
        sent=excluded.sent, moved=excluded.moved, opened=excluded.opened,
        replied=excluded.replied, score=excluded.score, inbox_rate=excluded.inbox_rate
    ''', (domain_id, today, sent, moved, opened, replied, score, inbox_rate))
    c.commit()
    c.close()

def get_reputation_history(domain_id, days=30):
    c = conn()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = c.execute('''
        SELECT date, sent, moved, opened, replied, score, inbox_rate
        FROM reputation WHERE domain_id = ? AND date >= ? ORDER BY date
    ''', (domain_id, since)).fetchall()
    c.close()
    return rows

# ─── Stats ───
def get_stats():
    c = conn()
    domains = c.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
    peers = c.execute("SELECT COUNT(*) FROM accounts WHERE role = 'peer'").fetchone()[0]
    sent = c.execute("SELECT COUNT(*) FROM sends WHERE status = 'sent'").fetchone()[0]
    opened = c.execute("SELECT COUNT(*) FROM engagements WHERE type = 'open'").fetchone()[0]
    replied = c.execute("SELECT COUNT(*) FROM engagements WHERE type = 'reply'").fetchone()[0]
    moved = c.execute("SELECT COUNT(*) FROM engagements WHERE type = 'move'").fetchone()[0]
    c.close()
    return {"domains": domains, "peers": peers, "sent": sent, "opened": opened, "replied": replied, "moved": moved}

# ─── Logs ───
def add_log(level, message):
    c = conn()
    c.execute("INSERT INTO agent_logs (level, message, created_at) VALUES (?,?,?)", (level, message, now()))
    c.commit()
    c.close()
    # Cleanup old logs
    c = conn()
    c.execute("DELETE FROM agent_logs WHERE created_at < datetime('now', '-7 days')")
    c.commit()
    c.close()

def get_agent_logs(limit=100):
    c = conn()
    rows = c.execute("SELECT * FROM agent_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return rows

def now():
    return datetime.now().isoformat()
