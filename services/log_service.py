"""
Logging service
"""

from datetime import datetime, timedelta
import db


def add_log(level: str, message: str, source: str = "agent"):
    try:
        db.execute(
            "INSERT INTO agent_logs (level, source, message, created_at) VALUES (?, ?, ?, ?)",
            (level, source, message, db.now()),
        )
    except Exception:
        pass


def get_logs(limit: int = 100, level: str = None):
    if level:
        rows = db.fetchall(
            "SELECT * FROM agent_logs WHERE level = ? ORDER BY created_at DESC LIMIT ?",
            (level, limit),
        )
    else:
        rows = db.fetchall(
            "SELECT * FROM agent_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
    return [dict(r) for r in rows]


def cleanup_old_logs(days: int = 7):
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    db.execute("DELETE FROM agent_logs WHERE created_at < ?", (cutoff,))
