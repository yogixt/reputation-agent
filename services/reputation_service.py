"""
Reputation calculation service
"""

import db
from services.log_service import add_log


def calculate_reputation_for_campaign(campaign_id: int):
    today = db.today()
    row = db.fetchone(
        """SELECT
            COUNT(CASE WHEN q.status = 'sent' THEN 1 END) as sent,
            COUNT(CASE WHEN e.type = 'move' THEN 1 END) as moved,
            COUNT(CASE WHEN e.type = 'open' THEN 1 END) as opened,
            COUNT(CASE WHEN e.type = 'reply' THEN 1 END) as replied
        FROM email_queue q
        LEFT JOIN engagements e ON q.id = e.queue_id
        WHERE q.campaign_id = ? AND q.sent_at::date = ?""",
        (campaign_id, today),
    )

    sent = row["sent"] or 0
    moved = row["moved"] or 0
    opened = row["opened"] or 0
    replied = row["replied"] or 0

    if sent > 0:
        # Weighted score per send: max possible per email = 5 (move=3, open=1, reply=5 => actually max 9, cap at 100)
        raw = (moved * 3 + opened * 1 + replied * 5) / (sent * 5)
        score = min(100.0, raw * 100)
        inbox_rate = (moved / sent) * 100
        spam_rate = 100 - inbox_rate
    else:
        score = 0.0
        inbox_rate = 0.0
        spam_rate = 0.0

    db.execute(
        """INSERT INTO reputation
        (campaign_id, date, sent, moved, opened, replied, score, inbox_rate, spam_rate)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(campaign_id, date) DO UPDATE SET
        sent=excluded.sent, moved=excluded.moved, opened=excluded.opened,
        replied=excluded.replied, score=excluded.score, inbox_rate=excluded.inbox_rate,
        spam_rate=excluded.spam_rate""",
        (campaign_id, today, sent, moved, opened, replied, round(score, 1), round(inbox_rate, 1), round(spam_rate, 1)),
    )


def calculate_all_reputation():
    rows = db.fetchall("SELECT id FROM campaigns")
    for row in rows:
        try:
            calculate_reputation_for_campaign(row["id"])
        except Exception as e:
            add_log("error", f"Reputation calc failed for {row['id']}: {e}", "reputation")


def get_reputation_history(campaign_id: int, days: int = 30) -> list:
    since = db.days_ago(days)
    rows = db.fetchall(
        """SELECT * FROM reputation
           WHERE campaign_id = ? AND date >= ? ORDER BY date""",
        (campaign_id, since),
    )
    return [dict(r) for r in rows]


def get_latest_scores() -> list:
    rows = db.fetchall(
        """SELECT r.*, c.name as campaign_name
           FROM reputation r
           JOIN campaigns c ON r.campaign_id = c.id
           WHERE r.date = (SELECT MAX(date) FROM reputation WHERE campaign_id = r.campaign_id)
           ORDER BY r.score DESC"""
    )
    return [dict(r) for r in rows]


def get_global_avg_score() -> float:
    row = db.fetchone(
        """SELECT AVG(score) as avg_score FROM reputation
           WHERE date = (SELECT MAX(date) FROM reputation)"""
    )
    return round(row["avg_score"] or 0, 1)
