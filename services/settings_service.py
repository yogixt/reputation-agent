"""
Application settings service
"""

import json
import db


def get_setting(key: str, default=None):
    row = db.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def set_setting(key: str, value):
    serialized = json.dumps(value) if not isinstance(value, str) else value
    db.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, serialized, db.now()),
    )


def get_all_settings() -> dict:
    rows = db.fetchall("SELECT key, value FROM settings")
    result = {}
    for row in rows:
        try:
            result[row["key"]] = json.loads(row["value"])
        except Exception:
            result[row["key"]] = row["value"]
    return result
