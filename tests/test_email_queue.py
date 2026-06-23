"""
Tests for email queue scheduling and recipient selection.
"""

from services import account_service, campaign_service, template_service
from services.email_queue_service import queue_emails_for_campaign
import db


def _create_sender(email="sender@test.local"):
    return account_service.create_account(email, "app-password-16", "sender")


def _create_peer(email):
    return account_service.create_account(email, "", "peer")


def _create_template(name="Test Template"):
    return template_service.create_template(
        name,
        "Hello",
        "Body",
        "Reply",
        "[]",
    )


def _create_campaign(sender_id, peer_ids, template_id, daily_target=5, current_week=1):
    campaign_id = campaign_service.create_campaign({
        "name": "Test Campaign",
        "domain_name": "test.local",
        "sender_account_id": sender_id,
        "template_id": template_id,
        "peer_account_ids": peer_ids,
        "daily_target": daily_target,
        "ramp_weeks": 12,
        "tick_interval": 5,
        "active_start": 0,
        "active_end": 24,
        "timezone": "UTC",
    })
    # create_campaign doesn't accept current_week, so update it afterwards.
    if current_week != 1:
        campaign_service.update_campaign(campaign_id, {"current_week": current_week})
    return campaign_id


def test_force_tick_queues_email_for_every_peer(test_db):
    sender_id = _create_sender()
    peer_ids = [_create_peer(f"peer{i}@test.local") for i in range(3)]
    template_id = _create_template()
    campaign_id = _create_campaign(sender_id, peer_ids, template_id, daily_target=1, current_week=1)
    campaign = campaign_service.get_campaign(campaign_id)

    queue_emails_for_campaign(campaign, force=True)

    rows = db.fetchall(
        "SELECT to_account_id FROM email_queue WHERE campaign_id = ?",
        (campaign_id,),
    )
    queued_peer_ids = {r["to_account_id"] for r in rows}
    assert len(rows) == 3
    assert queued_peer_ids == set(peer_ids)


def test_scheduled_tick_queues_email_for_every_peer(test_db):
    sender_id = _create_sender()
    peer_ids = [_create_peer(f"peer{i}@test.local") for i in range(3)]
    template_id = _create_template()
    campaign_id = _create_campaign(sender_id, peer_ids, template_id, daily_target=1, current_week=1)
    campaign = campaign_service.get_campaign(campaign_id)

    # Even a scheduled tick must reach every peer, regardless of the ramp target.
    queue_emails_for_campaign(campaign, force=False)

    rows = db.fetchall(
        "SELECT to_account_id FROM email_queue WHERE campaign_id = ?",
        (campaign_id,),
    )
    queued_peer_ids = {r["to_account_id"] for r in rows}
    assert len(rows) == 3
    assert queued_peer_ids == set(peer_ids)


def test_second_tick_fills_remaining_daily_target(test_db):
    sender_id = _create_sender()
    peer_ids = [_create_peer(f"peer{i}@test.local") for i in range(3)]
    template_id = _create_template()
    # Target 4 means first tick queues all 3 peers + 1 extra.
    campaign_id = _create_campaign(sender_id, peer_ids, template_id, daily_target=4, current_week=12)
    campaign = campaign_service.get_campaign(campaign_id)

    queue_emails_for_campaign(campaign, force=False)
    rows = db.fetchall(
        "SELECT to_account_id FROM email_queue WHERE campaign_id = ?",
        (campaign_id,),
    )
    assert len(rows) == 4
    assert set(r["to_account_id"] for r in rows) == set(peer_ids)

    # Mark one email to each peer as sent so every peer has been reached today.
    now = db.now()
    for peer_id in peer_ids:
        db.execute(
            "UPDATE email_queue SET status = 'sent', sent_at = ? WHERE campaign_id = ? AND to_account_id = ? LIMIT 1",
            (now, campaign_id, peer_id),
        )

    # Remove leftover pending rows so we can measure only what the next tick queues.
    db.execute("DELETE FROM email_queue WHERE campaign_id = ? AND status = 'pending'", (campaign_id,))

    # Second tick should queue 1 extra (daily target 4, 3 already sent).
    queue_emails_for_campaign(campaign, force=False)
    rows = db.fetchall(
        "SELECT to_account_id FROM email_queue WHERE campaign_id = ? AND status = 'pending'",
        (campaign_id,),
    )
    assert len(rows) == 1


def test_tick_skips_when_all_peers_already_mailed_and_target_met(test_db):
    sender_id = _create_sender()
    peer_ids = [_create_peer(f"peer{i}@test.local") for i in range(3)]
    template_id = _create_template()
    campaign_id = _create_campaign(sender_id, peer_ids, template_id, daily_target=3, current_week=12)

    db.execute(
        """INSERT INTO email_queue
        (campaign_id, from_account_id, to_account_id, subject, body, status, scheduled_at, sent_at)
        SELECT ?, ?, id, 's', 'b', 'sent', ?, ? FROM accounts WHERE id IN (?,?,?)""",
        (campaign_id, sender_id, db.now(), db.now(), *peer_ids),
    )

    campaign = campaign_service.get_campaign(campaign_id)
    queue_emails_for_campaign(campaign, force=False)

    rows = db.fetchall(
        "SELECT id FROM email_queue WHERE campaign_id = ? AND status = 'pending'",
        (campaign_id,),
    )
    assert len(rows) == 0


def test_sync_campaign_peers_is_additive(test_db):
    sender_id = _create_sender()
    peer_ids = [_create_peer(f"peer{i}@test.local") for i in range(3)]
    template_id = _create_template()
    campaign_id = _create_campaign(sender_id, [peer_ids[0]], template_id)

    campaign_service.sync_campaign_peers(campaign_id, peer_ids)
    campaign = campaign_service.get_campaign(campaign_id)

    linked_peer_ids = {p["id"] for p in campaign["peers"]}
    assert linked_peer_ids == set(peer_ids)


def test_ensure_warmup_campaigns_for_all_senders(test_db):
    sender_ids = [_create_sender(f"sender{i}@test.local") for i in range(2)]
    peer_ids = [_create_peer(f"peer{i}@test.local") for i in range(3)]
    template_id = _create_template("Warmup")

    result = campaign_service.ensure_warmup_campaigns_for_all_senders(template_id=template_id)

    assert len(result["created"]) == 2
    assert len(result["synced"]) == 0

    for campaign_id in result["created"]:
        campaign = campaign_service.get_campaign(campaign_id)
        linked_peer_ids = {p["id"] for p in campaign["peers"]}
        assert linked_peer_ids == set(peer_ids)


def test_ensure_warmup_campaigns_syncs_existing_and_creates_missing(test_db):
    sender_ids = [_create_sender(f"sender{i}@test.local") for i in range(2)]
    peer_ids = [_create_peer(f"peer{i}@test.local") for i in range(3)]
    template_id = _create_template("Warmup")

    # Pre-create a campaign for the first sender with only one peer.
    _create_campaign(sender_ids[0], [peer_ids[0]], template_id)

    result = campaign_service.ensure_warmup_campaigns_for_all_senders(template_id=template_id)

    assert len(result["synced"]) == 1
    assert len(result["created"]) == 1

    for campaign_id in result["created"] + result["synced"]:
        campaign = campaign_service.get_campaign(campaign_id)
        linked_peer_ids = {p["id"] for p in campaign["peers"]}
        assert linked_peer_ids == set(peer_ids)


def test_bulk_send_all_ticks_and_sends_for_every_sender(test_db, monkeypatch):
    """One bulk action should queue and send emails for all active senders."""
    from services import email_queue_service

    sender_ids = [_create_sender(f"bulk_sender{i}@test.local") for i in range(2)]
    peer_ids = [_create_peer(f"bulk_peer{i}@test.local") for i in range(2)]
    template_id = _create_template("Bulk Template")

    campaign_ids = []
    for sender_id in sender_ids:
        campaign_id = _create_campaign(
            sender_id,
            peer_ids,
            template_id,
            daily_target=len(peer_ids),
            current_week=1,
        )
        campaign_ids.append(campaign_id)

    sent_emails = []

    class FakeGmailClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def send_email(self, to, subject, body):
            sent_emails.append(to)
        def search_spam(self, criteria):
            return []
        def search_inbox(self, criteria):
            return []

    monkeypatch.setattr(email_queue_service, "GmailClient", FakeGmailClient)

    result = email_queue_service.bulk_send_all(limit=100)

    assert result["campaigns_ticked"] == 2
    assert result["queued"] == 4  # 2 senders * 2 peers
    assert result["sent"] == 4
    assert len(sent_emails) == 4
