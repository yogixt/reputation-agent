"""
Account health monitoring service
"""

import db
from services.account_service import list_accounts, get_plain_password, update_health
from services.log_service import add_log
from providers.gmail import GmailClient


def run_health_check():
    accounts = list_accounts()
    for account in accounts:
        if account["status"] != "active":
            continue
        password = get_plain_password(account["id"])
        if not password:
            if account["role"] == "peer":
                # Peers without a password are used only as recipients;
                # engagement simulation is skipped.
                update_health(account["id"], 100, "No peer password; engagement skipped")
                continue
            update_health(account["id"], 0, "No password")
            continue
        try:
            client = GmailClient(account["email"], password)
            if client.health_check():
                update_health(account["id"], 100)
                add_log("info", f"Health check passed: {account['email']}", "health")
            else:
                update_health(account["id"], 0, "Login failed")
                add_log("error", f"Health check failed: {account['email']}", "health")
        except Exception as e:
            update_health(account["id"], 0, str(e)[:200])
            add_log("error", f"Health check error for {account['email']}: {e}", "health")

    # Auto-pause campaigns with unhealthy sender
    unhealthy_senders = db.fetchall(
        "SELECT id FROM accounts WHERE role = 'sender' AND (health_score < 50 OR status != 'active')"
    )
    for row in unhealthy_senders:
        db.execute(
            "UPDATE campaigns SET status = 'paused' WHERE sender_account_id = ? AND status = 'active'",
            (row["id"],),
        )
        add_log("warning", f"Campaigns paused due to unhealthy sender {row['id']}", "health")
