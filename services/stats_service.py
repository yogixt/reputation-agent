"""
Dashboard stats aggregation
"""

from datetime import datetime, timedelta

import db


def _day_bounds():
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    return today.isoformat(), tomorrow.isoformat()


def _week_start():
    now = datetime.utcnow()
    monday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    return monday.isoformat()


def get_stats() -> dict:
    today_start, today_end = _day_bounds()
    week_start = _week_start()

    row = db.fetchone(
        """SELECT
            (SELECT COUNT(*) FROM campaigns) AS campaigns,
            (SELECT COUNT(*) FROM accounts) AS accounts,
            (SELECT COUNT(*) FROM accounts WHERE role = 'sender') AS senders,
            (SELECT COUNT(*) FROM accounts WHERE role = 'peer') AS peers,
            (SELECT COUNT(*) FROM email_queue WHERE status = 'pending') AS pending,
            (SELECT COUNT(*) FROM email_queue WHERE status = 'sent') AS sent,
            (SELECT COUNT(*) FROM engagements WHERE type = 'open') AS opened,
            (SELECT COUNT(*) FROM engagements WHERE type = 'reply') AS replied,
            (SELECT COUNT(*) FROM engagements WHERE type = 'move') AS moved,
            (SELECT COUNT(*) FROM email_queue WHERE status = 'sent' AND sent_at >= ? AND sent_at < ?) AS sent_today,
            (SELECT COUNT(*) FROM email_queue WHERE status = 'sent' AND sent_at >= ?) AS sent_this_week,
            (SELECT AVG(score) FROM reputation WHERE date = (SELECT MAX(date) FROM reputation)) AS avg_score
        """,
        (today_start, today_end, week_start),
    )

    return {
        "campaigns": row["campaigns"] or 0,
        "accounts": row["accounts"] or 0,
        "senders": row["senders"] or 0,
        "peers": row["peers"] or 0,
        "pending": row["pending"] or 0,
        "sent": row["sent"] or 0,
        "opened": row["opened"] or 0,
        "replied": row["replied"] or 0,
        "moved": row["moved"] or 0,
        "sent_today": row["sent_today"] or 0,
        "sent_this_week": row["sent_this_week"] or 0,
        "avg_score": round(row["avg_score"] or 0, 1),
    }
