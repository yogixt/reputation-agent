"""
Template service
"""

import json
import db


def create_template(name: str, subject: str, body: str, reply: str = None, variables: str = None) -> int:
    cur = db.execute(
        "INSERT INTO templates (name, subject_template, body_template, reply_template, variables_json) VALUES (?,?,?,?,?) RETURNING id",
        (name, subject, body, reply, variables),
    )
    return cur.lastrowid


def list_templates() -> list:
    rows = db.fetchall("SELECT * FROM templates ORDER BY is_default DESC, created_at DESC")
    return [dict(r) for r in rows]


def get_template(template_id: int) -> dict:
    row = db.fetchone("SELECT * FROM templates WHERE id = ?", (template_id,))
    return dict(row) if row else None


def get_default_template() -> dict:
    row = db.fetchone("SELECT * FROM templates WHERE is_default = 1 LIMIT 1")
    return dict(row) if row else None


def delete_template(template_id: int):
    db.execute("DELETE FROM templates WHERE id = ?", (template_id,))


def update_template(template_id: int, data: dict):
    fields = []
    values = []
    for k in ["name", "subject_template", "body_template", "reply_template", "variables_json"]:
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if not fields:
        return
    values.append(template_id)
    db.execute(f"UPDATE templates SET {', '.join(fields)} WHERE id = ?", values)
