"""
Email queue service: queue, send, retry, engage
"""

import email as email_lib
import random
import re
from datetime import datetime, timedelta
from config import settings
import db
from services.account_service import get_account, get_plain_password, get_peers
from services.template_service import get_template
from services.log_service import add_log
from services.reputation_service import calculate_reputation_for_campaign
from providers.gmail import GmailClient, GmailError
from templates import emails


def queue_emails_for_campaign(campaign: dict, force: bool = False):
    """Add pending emails to the queue for this campaign tick"""
    if not campaign or campaign["status"] != "active":
        return

    from services.campaign_service import is_active_hour, get_target_for_today
    if not force and not is_active_hour(campaign):
        return

    sender = get_account(campaign["sender_account_id"])
    if not sender or sender["status"] != "active":
        add_log("warning", f"Campaign {campaign['id']}: no active sender", "email_queue")
        return

    peers = get_peers(campaign["id"])
    if not peers:
        add_log("warning", f"Campaign {campaign['id']}: no peers", "email_queue")
        return

    template = get_template(campaign["template_id"]) if campaign.get("template_id") else None
    if not template:
        add_log("warning", f"Campaign {campaign['id']}: no template selected", "email_queue")
        return

    today_target = get_target_for_today(campaign)
    today_sent = count_today_sent(campaign["id"])

    # Strong guarantee: every peer must receive at least one email today.
    # Compute peers that have not been mailed yet today, then queue at least
    # those peers plus any extras needed to hit the daily ramp target.
    sent_peer_ids = set(get_today_sent_peer_ids(campaign["id"]))
    missing_peers = [p for p in peers if p["id"] not in sent_peer_ids]

    per_tick = max(0, today_target - today_sent)
    per_tick = max(per_tick, len(missing_peers))

    if per_tick == 0:
        return

    variables = emails.generate_variables()

    # Always include missing peers first, then fill the rest of the daily budget
    # with random peers so stronger peers don't dominate.
    selected_peers = missing_peers[:]
    random.shuffle(selected_peers)
    extra = per_tick - len(selected_peers)
    if extra > 0:
        selected_peers.extend(random.choice(peers) for _ in range(extra))

    for peer in selected_peers:
        subject, body = emails.render_email(
            template["subject_template"],
            template["body_template"],
            variables,
        )
        # Include a marker in subject for peer engagement tracking
        marker = f"[RA-{campaign['id']}-{random.randint(100000, 999999)}]"
        subject = f"{subject} {marker}"

        scheduled = db.now()
        db.execute(
            """INSERT INTO email_queue
            (campaign_id, from_account_id, to_account_id, subject, body, status, scheduled_at)
            VALUES (?,?,?,?,?,?,?)""",
            (campaign["id"], sender["id"], peer["id"], subject, body, "pending", scheduled),
        )

    add_log("info", f"Queued {len(selected_peers)} emails for campaign {campaign['name']}", "email_queue")


def process_pending_jobs(limit: int = 100):
    """Send pending emails and trigger engagement.

    Groups jobs by sender so each sender only opens one SMTP/IMAP session.
    This is important on serverless platforms where the max execution time is
    short (e.g. Vercel's 60s limit) and creating a connection per email is too
    slow for larger daily batches.
    """
    rows = db.fetchall(
        """SELECT q.*, a1.email as from_email, a2.email as to_email
           FROM email_queue q
           JOIN accounts a1 ON q.from_account_id = a1.id
           JOIN accounts a2 ON q.to_account_id = a2.id
           WHERE q.status = 'pending' AND q.scheduled_at <= ?
           ORDER BY q.scheduled_at
           LIMIT ?""",
        (db.now(), limit),
    )

    # Group by sender to reuse a single Gmail connection per sender.
    jobs_by_sender = {}
    for row in rows:
        sender_id = row["from_account_id"]
        jobs_by_sender.setdefault(sender_id, []).append(dict(row))

    for sender_id, jobs in jobs_by_sender.items():
        sender_email = jobs[0]["from_email"]
        sender_pass = get_plain_password(sender_id)
        if not sender_pass:
            for job in jobs:
                handle_send_failure(job["id"], "Sender password not found")
            continue

        try:
            with GmailClient(sender_email, sender_pass, smtp_only=True) as gmail:
                for job in jobs:
                    _send_one(job, gmail)
        except Exception as e:
            # If the whole connection fails, mark all jobs for retry.
            for job in jobs:
                handle_send_failure(job["id"], str(e))


def _send_one(job: dict, gmail: GmailClient):
    """Send a single email using an already-open Gmail client."""
    job_id = job["id"]
    db.execute("UPDATE email_queue SET status = 'running' WHERE id = ?", (job_id,))

    try:
        gmail.send_email(job["to_email"], job["subject"], job["body"])

        db.execute(
            "UPDATE email_queue SET status = 'sent', sent_at = ?, error = NULL WHERE id = ?",
            (db.now(), job_id),
        )
        add_log("info", f"Sent to {job['to_email']}: {job['subject'][:50]}...", "email_queue")

        # Trigger peer engagement asynchronously-ish
        simulate_peer_engagement(job)

    except Exception as e:
        handle_send_failure(job_id, str(e))


def simulate_peer_engagement(job: dict):
    """Peer opens email, moves from spam, replies"""
    peer = get_account(job["to_account_id"])
    if not peer:
        return

    peer_pass = get_plain_password(peer["id"])
    if not peer_pass:
        return

    # Extract marker from subject
    marker = ""
    if "[RA-" in job["subject"]:
        marker = job["subject"].split("[RA-")[1].split("]")[0]
        marker = f"[RA-{marker}]"

    try:
        with GmailClient(peer["email"], peer_pass) as gmail:
            # Check spam
            spam_ids = gmail.search_spam(f"SUBJECT {marker}") if marker else []
            inbox_ids = gmail.search_inbox(f"SUBJECT {marker}") if marker else []

            if spam_ids and random.random() < settings.move_probability:
                if gmail.move_to_inbox(spam_ids[0]):
                    add_engagement(job["id"], peer["id"], "move", 3)
                    add_log("info", f"Peer {peer['email']} moved email to inbox", "engagement")

            if (spam_ids or inbox_ids) and random.random() < settings.open_probability:
                add_engagement(job["id"], peer["id"], "open", 1)
                add_log("info", f"Peer {peer['email']} opened email", "engagement")

            if (spam_ids or inbox_ids) and random.random() < settings.reply_probability:
                template = get_template_for_campaign(job["campaign_id"])
                reply_body = emails.render_reply(template["reply_template"] if template else None)
                sender_email = job["from_email"]
                gmail.send_reply(sender_email, f"Re: {job['subject']}", reply_body)
                add_engagement(job["id"], peer["id"], "reply", 5)
                add_log("info", f"Peer {peer['email']} replied", "engagement")

    except Exception as e:
        add_log("warning", f"Peer engagement failed for {peer['email']}: {e}", "engagement")

    # Update reputation after engagement
    try:
        calculate_reputation_for_campaign(job["campaign_id"])
    except Exception:
        pass


def bulk_send_all(limit: int = 100, force: bool = True) -> dict:
    """One-click bulk action: queue emails for all active campaigns and send them.

    Replaces per-campaign ticking when the user wants to warm up every sender
    with a single click.
    """
    from services.campaign_service import campaign_tick_all, list_campaigns

    total_campaigns = len(list_campaigns())
    active_campaigns = db.fetchall("SELECT id FROM campaigns WHERE status = 'active'")

    pending_before = db.fetchone("SELECT COUNT(*) as c FROM email_queue WHERE status = 'pending'")["c"]
    sent_before = db.fetchone("SELECT COUNT(*) as c FROM email_queue WHERE status = 'sent'")["c"]

    campaign_tick_all(force=force)

    pending_after_tick = db.fetchone("SELECT COUNT(*) as c FROM email_queue WHERE status = 'pending'")["c"]
    process_pending_jobs(limit=limit)

    sent_after = db.fetchone("SELECT COUNT(*) as c FROM email_queue WHERE status = 'sent'")["c"]

    queued = pending_after_tick - pending_before
    sent = sent_after - sent_before
    campaigns_ticked = len(active_campaigns)

    if campaigns_ticked == 0:
        message = "No active campaigns. Activate a campaign first."
    elif queued == 0:
        message = "No emails queued. Daily target may already be met."
    else:
        message = f"Bulk send complete: {queued} queued, {sent} sent."

    add_log("info", f"Bulk send: ticked {campaigns_ticked} campaign(s), queued {queued}, sent {sent}", "email_queue")

    return {
        "total_campaigns": total_campaigns,
        "campaigns_ticked": campaigns_ticked,
        "queued": queued,
        "sent": sent,
        "message": message,
    }


def handle_send_failure(job_id: int, error: str):
    row = db.fetchone("SELECT retry_count FROM email_queue WHERE id = ?", (job_id,))
    retries = row["retry_count"] if row else 0
    if retries >= settings.max_retries:
        db.execute(
            "UPDATE email_queue SET status = 'failed', error = ?, retry_count = ? WHERE id = ?",
            (error, retries + 1, job_id),
        )
        add_log("error", f"Job {job_id} failed permanently: {error}", "email_queue")
    else:
        backoff = [60, 300, 900, 1800, 3600][min(retries, 4)]
        next_try = (datetime.utcnow() + timedelta(seconds=backoff)).isoformat()
        db.execute(
            "UPDATE email_queue SET status = 'pending', error = ?, retry_count = ?, scheduled_at = ? WHERE id = ?",
            (error, retries + 1, next_try, job_id),
        )
        add_log("warning", f"Job {job_id} failed, retrying in {backoff}s: {error}", "email_queue")


def add_engagement(queue_id: int, account_id: int, etype: str, value: int):
    db.execute(
        "INSERT INTO engagements (queue_id, account_id, type, value, created_at) VALUES (?,?,?,?,?)",
        (queue_id, account_id, etype, value, db.now()),
    )


def count_today_sent(campaign_id: int) -> int:
    row = db.fetchone(
        "SELECT COUNT(*) as c FROM email_queue WHERE campaign_id = ? AND status = 'sent' AND sent_at::date = ?",
        (campaign_id, db.today()),
    )
    return row["c"] if row else 0


def get_today_sent_peer_ids(campaign_id: int) -> list[int]:
    rows = db.fetchall(
        "SELECT to_account_id FROM email_queue WHERE campaign_id = ? AND status = 'sent' AND sent_at::date = ?",
        (campaign_id, db.today()),
    )
    return [r["to_account_id"] for r in rows]


def get_queue(status: str = None, limit: int = 100) -> list:
    if status:
        rows = db.fetchall(
            """SELECT q.*, c.name as campaign_name, a1.email as from_email, a2.email as to_email
               FROM email_queue q
               JOIN campaigns c ON q.campaign_id = c.id
               JOIN accounts a1 ON q.from_account_id = a1.id
               JOIN accounts a2 ON q.to_account_id = a2.id
               WHERE q.status = ? ORDER BY q.created_at DESC LIMIT ?""",
            (status, limit),
        )
    else:
        rows = db.fetchall(
            """SELECT q.*, c.name as campaign_name, a1.email as from_email, a2.email as to_email
               FROM email_queue q
               JOIN campaigns c ON q.campaign_id = c.id
               JOIN accounts a1 ON q.from_account_id = a1.id
               JOIN accounts a2 ON q.to_account_id = a2.id
               ORDER BY q.created_at DESC LIMIT ?""",
            (limit,),
        )
    return [dict(r) for r in rows]


def get_template_for_campaign(campaign_id: int) -> dict:
    from services.campaign_service import get_campaign
    campaign = get_campaign(campaign_id)
    if campaign and campaign.get("template_id"):
        from services.template_service import get_template
        return get_template(campaign["template_id"])
    from services.template_service import get_default_template
    return get_default_template()


def retry_failed_jobs():
    """Manually reschedule all failed jobs"""
    db.execute(
        "UPDATE email_queue SET status = 'pending', retry_count = 0, scheduled_at = ? WHERE status = 'failed'",
        (db.now(),),
    )


def clear_pending_jobs():
    """Delete all pending jobs"""
    db.execute("DELETE FROM email_queue WHERE status = 'pending'")
    add_log("info", "Cleared all pending emails", "email_queue")


# Regex to extract the reply marker we embed in warm-up subjects, e.g. [RA-4-123456]
_REPLY_MARKER_RE = re.compile(r"\[RA-(\d+)-(\d+)\]")


def detect_real_replies():
    """Scan sender inboxes for real replies from peers and record them.

    This lets the dashboard count genuine replies (e.g. Mohit replying from his
    own Gmail) without needing the peer account's app password. Opens and moves
    still require peer access, but replies are the strongest signal anyway.
    """
    senders = db.fetchall(
        "SELECT id, email FROM accounts WHERE role = 'sender' AND status = 'active'"
    )
    total_detected = 0
    for sender in senders:
        sender_id = sender["id"]
        sender_email = sender["email"]
        sender_pass = get_plain_password(sender_id)
        if not sender_pass:
            continue
        try:
            with GmailClient(sender_email, sender_pass) as gmail:
                reply_ids = gmail.search_inbox('SUBJECT "RA-"')
                if not reply_ids:
                    continue
                for msg_id in reply_ids:
                    try:
                        gmail.imap.select("INBOX")
                        _, data = gmail.imap.fetch(msg_id, "(RFC822)")
                        if not data or not data[0]:
                            continue
                        raw = data[0][1]
                        if not isinstance(raw, bytes):
                            continue
                        msg = email_lib.message_from_bytes(raw)
                        subject = msg.get("Subject", "")
                        match = _REPLY_MARKER_RE.search(subject)
                        if not match:
                            continue
                        marker = match.group(0)
                        # Find the original sent email by marker
                        job = db.fetchone(
                            "SELECT id, campaign_id, to_account_id FROM email_queue WHERE subject LIKE ? AND status = 'sent' ORDER BY id DESC LIMIT 1",
                            (f"%{marker}%",),
                        )
                        if not job:
                            continue
                        queue_id = job["id"]
                        campaign_id = job["campaign_id"]
                        peer_id = job["to_account_id"]
                        # Avoid duplicate counting
                        existing = db.fetchone(
                            "SELECT 1 FROM engagements WHERE queue_id = ? AND type = 'reply'",
                            (queue_id,),
                        )
                        if existing:
                            continue
                        add_engagement(queue_id, peer_id, "reply", 5)
                        add_log(
                            "info",
                            f"Real reply detected from {sender_email} for {marker}",
                            "engagement",
                        )
                        calculate_reputation_for_campaign(campaign_id)
                        total_detected += 1
                    except Exception as e:
                        add_log("warning", f"Reply detection error for {sender_email}: {e}", "engagement")
        except Exception as e:
            add_log("warning", f"Reply detection failed for {sender_email}: {e}", "engagement")

    if total_detected:
        add_log("info", f"Detected {total_detected} real reply(s)", "engagement")
