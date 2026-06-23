"""
Campaign service
"""

import db
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
from config import settings
from services.account_service import get_account
from services.log_service import add_log


VALID_TIMEZONES = frozenset(available_timezones())


def _now_for_tz(tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name) if tz_name in VALID_TIMEZONES else ZoneInfo("UTC")
    return datetime.now(tz)


def create_campaign(data: dict) -> int:
    cur = db.execute(
        """INSERT INTO campaigns
        (name, domain_name, sender_account_id, template_id, daily_target, ramp_weeks,
         tick_interval, active_start, active_end, timezone)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        RETURNING id""",
        (
            data["name"],
            data["domain_name"],
            data["sender_account_id"],
            data["template_id"],
            data["daily_target"],
            data["ramp_weeks"],
            data["tick_interval"],
            data["active_start"],
            data["active_end"],
            data["timezone"],
        ),
    )
    campaign_id = cur.lastrowid
    for peer_id in data.get("peer_account_ids", []):
        db.execute(
            "INSERT INTO campaign_peers (campaign_id, account_id) VALUES (?,?) ON CONFLICT DO NOTHING",
            (campaign_id, peer_id),
        )
    add_log("info", f"Campaign created: {data['name']}", "campaign_service")
    return campaign_id


def list_campaigns() -> list:
    rows = db.fetchall("""
        SELECT c.*,
               a.email as sender_email,
               t.name as template_name,
               (SELECT COUNT(*) FROM campaign_peers WHERE campaign_id = c.id) as peer_count
        FROM campaigns c
        LEFT JOIN accounts a ON c.sender_account_id = a.id
        LEFT JOIN templates t ON c.template_id = t.id
        ORDER BY c.created_at DESC
    """)
    return [dict(r) for r in rows]


def get_campaign(campaign_id: int) -> dict:
    row = db.fetchone("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not row:
        return None
    camp = dict(row)
    peers = db.fetchall(
        "SELECT a.* FROM accounts a JOIN campaign_peers cp ON a.id = cp.account_id WHERE cp.campaign_id = ?",
        (campaign_id,),
    )
    camp["peers"] = [dict(p) for p in peers]
    return camp


def update_campaign(campaign_id: int, data: dict):
    allowed = ["name", "domain_name", "sender_account_id", "template_id", "daily_target",
               "ramp_weeks", "tick_interval", "active_start", "active_end", "status", "current_week", "timezone"]
    fields = []
    values = []
    for k in allowed:
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if fields:
        fields.append("updated_at = ?")
        values.append(db.now())
        values.append(campaign_id)
        db.execute(f"UPDATE campaigns SET {', '.join(fields)} WHERE id = ?", values)

    if "peer_account_ids" in data:
        db.execute("DELETE FROM campaign_peers WHERE campaign_id = ?", (campaign_id,))
        for peer_id in data["peer_account_ids"]:
            db.execute("INSERT INTO campaign_peers (campaign_id, account_id) VALUES (?,?) ON CONFLICT DO NOTHING",
                       (campaign_id, peer_id))


def sync_campaign_peers(campaign_id: int, peer_account_ids: list[int]):
    """Ensure the campaign is linked to every peer in the list (idempotent)."""
    for peer_id in peer_account_ids:
        db.execute(
            "INSERT INTO campaign_peers (campaign_id, account_id) VALUES (?,?) ON CONFLICT DO NOTHING",
            (campaign_id, peer_id),
        )
    add_log("info", f"Synced {len(peer_account_ids)} peer(s) to campaign {campaign_id}", "campaign_service")


def ensure_warmup_campaigns_for_all_senders(
    template_id: int,
    daily_target: int = None,
    ramp_weeks: int = None,
    tick_interval: int = None,
    active_start: int = None,
    active_end: int = None,
    timezone: str = "UTC",
) -> dict:
    """Create (or sync peers for) one warm-up campaign per active sender.

    Returns {"created": [ids], "synced": [ids]} so callers know what changed.
    """
    daily_target = daily_target or settings.default_daily_target
    ramp_weeks = ramp_weeks or settings.default_ramp_weeks
    tick_interval = tick_interval or settings.tick_interval_minutes
    active_start = active_start or settings.active_hours_start
    active_end = active_end or settings.active_hours_end

    senders = db.fetchall("SELECT * FROM accounts WHERE role = 'sender' AND status = 'active'")
    peers = db.fetchall("SELECT * FROM accounts WHERE role = 'peer' AND status = 'active'")
    peer_ids = [p["id"] for p in peers]

    existing = list_campaigns()
    created = []
    synced = []

    for sender in senders:
        domain = sender["email"].split("@")[-1]
        name = f"{domain} Warm-up"

        campaign = next(
            (c for c in existing if c["sender_account_id"] == sender["id"] and c["template_id"] == template_id),
            None,
        )
        if campaign:
            sync_campaign_peers(campaign["id"], peer_ids)
            synced.append(campaign["id"])
        else:
            campaign_id = create_campaign({
                "name": name,
                "domain_name": domain,
                "sender_account_id": sender["id"],
                "template_id": template_id,
                "peer_account_ids": peer_ids,
                "daily_target": daily_target,
                "ramp_weeks": ramp_weeks,
                "tick_interval": tick_interval,
                "active_start": active_start,
                "active_end": active_end,
                "timezone": timezone,
            })
            created.append(campaign_id)

    return {"created": created, "synced": synced}


def delete_campaign(campaign_id: int):
    db.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
    add_log("info", f"Campaign deleted: {campaign_id}", "campaign_service")


def get_target_for_today(campaign: dict) -> int:
    """Ramp curve: target increases each week."""
    week = max(1, min(campaign.get("current_week", 1), campaign.get("ramp_weeks", 12)))
    max_target = campaign["daily_target"]
    # Linear ramp: week 1 = ~8%, week 12 = 100%
    return max(1, int(max_target * (week / campaign.get("ramp_weeks", 12))))


def is_active_hour(campaign: dict) -> bool:
    """Check whether current time is inside the campaign's active window.

    Respects the campaign timezone if set; falls back to UTC.
    Handles windows that cross midnight (e.g. 23:00 - 01:00).
    """
    tz_name = campaign.get("timezone") or "UTC"
    now = _now_for_tz(tz_name)
    hour = now.hour
    start = campaign["active_start"]
    end = campaign["active_end"]
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def campaign_tick(campaign_id: int, force: bool = False):
    """Scheduled job: queue emails for a campaign.

    When force=True, active-hour checks are skipped (used by manual ticks).
    """
    from services.email_queue_service import queue_emails_for_campaign
    campaign = get_campaign(campaign_id)
    if not campaign or campaign["status"] != "active":
        return
    try:
        queue_emails_for_campaign(campaign, force=force)
    except Exception as e:
        add_log("error", f"Campaign tick failed for {campaign_id}: {e}", "campaign_service")


def campaign_tick_all(force: bool = False):
    """Queue emails for all active campaigns. Used by Vercel Cron."""
    for camp in list_campaigns():
        if camp["status"] == "active":
            campaign_tick(camp["id"], force=force)


def advance_campaign_weeks():
    """Advance current_week by 1 for active campaigns until ramp_weeks is reached.

    Called weekly by the scheduler.
    """
    rows = db.fetchall("SELECT id, current_week, ramp_weeks FROM campaigns WHERE status = 'active'")
    for row in rows:
        new_week = min(row["current_week"] + 1, row["ramp_weeks"])
        db.execute(
            "UPDATE campaigns SET current_week = ?, updated_at = ? WHERE id = ?",
            (new_week, db.now(), row["id"]),
        )
    add_log("info", f"Advanced weeks for {len(rows)} active campaign(s)", "campaign_service")
