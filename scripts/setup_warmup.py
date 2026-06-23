#!/usr/bin/env python3
"""
Set a shared app password for all sender accounts, create the warm-up template,
and create one campaign per sender using all peer accounts.

Usage:
    python scripts/setup_warmup.py "Vijay@2026"

Or set via environment:
    SENDER_APP_PASSWORD="Vijay@2026" python scripts/setup_warmup.py

Requires a valid .env with DATABASE_URL and all required secrets.
"""

import os
import sys

from services import template_service, account_service, campaign_service


TEMPLATE_NAME = "Email Validation"
TEMPLATE_SUBJECT = "Quick email validation request"
TEMPLATE_BODY = """Hey,

I'm validating our new email system and would really appreciate your help. If this lands in your inbox, could you:

* Reply to this email
* Mark it as important (if possible)
* Let me know if it ended up in Spam or Promotions

Thank you!

– Bijoy"""
TEMPLATE_REPLY = "Got it — your email landed in my inbox and I've marked it as important."
TEMPLATE_VARIABLES = "[]"


def main():
    password = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SENDER_APP_PASSWORD")
    if not password:
        print("Usage: python scripts/setup_warmup.py <sender_app_password>")
        print("Or set SENDER_APP_PASSWORD environment variable.")
        sys.exit(1)

    # Create template
    template_id = None
    existing_templates = template_service.list_templates()
    for t in existing_templates:
        if t["name"] == TEMPLATE_NAME:
            template_id = t["id"]
            print(f"Using existing template '{TEMPLATE_NAME}' (ID: {template_id})")
            break
    if template_id is None:
        template_id = template_service.create_template(
            TEMPLATE_NAME,
            TEMPLATE_SUBJECT,
            TEMPLATE_BODY,
            TEMPLATE_REPLY,
            TEMPLATE_VARIABLES,
        )
        print(f"Created template '{TEMPLATE_NAME}' (ID: {template_id})")

    # Fetch accounts
    accounts = account_service.list_accounts()
    senders = [a for a in accounts if a["role"] == "sender"]
    peers = [a for a in accounts if a["role"] == "peer"]

    if not senders:
        print("No sender accounts found. Add sender accounts first.")
        return
    if not peers:
        print("No peer accounts found. Add peer accounts first.")
        return

    peer_ids = [p["id"] for p in peers]
    print(f"Found {len(senders)} sender(s) and {len(peers)} peer(s).")

    # Update sender passwords
    for sender in senders:
        account_service.update_account(sender["id"], password=password)
        print(f"Updated app password for sender {sender['email']}")

    # Ensure every active sender has a warm-up campaign linked to every peer.
    result = campaign_service.ensure_warmup_campaigns_for_all_senders(template_id=template_id)
    created_campaigns = result["created"]
    synced_campaigns = result["synced"]

    print(f"\nUpdated {len(senders)} sender password(s).")
    print(f"Created {len(created_campaigns)} new campaign(s).")
    print(f"Synced peers for {len(synced_campaigns)} existing campaign(s).")
    print("\nTo send emails immediately, run:")
    for cid in created_campaigns + synced_campaigns:
        print(f"  python -c 'from services import campaign_service; campaign_service.campaign_tick({cid})'")


if __name__ == "__main__":
    main()
