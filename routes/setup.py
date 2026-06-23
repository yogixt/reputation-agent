"""
One-click warm-up setup route.
"""

from fastapi import APIRouter, Depends, Request
import auth
import models
from config import settings
from limiter import limiter
from services import template_service, account_service, campaign_service

router = APIRouter(prefix="/api/setup", tags=["setup"])


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


@router.post("/warmup", response_model=dict)
@limiter.limit(settings.default_rate_limit)
async def setup_warmup(req: models.WarmupSetupRequest, request: Request, session: dict = Depends(auth.require_auth)):
    # 1. Create or reuse template
    template_id = None
    for t in template_service.list_templates():
        if t["name"] == TEMPLATE_NAME:
            template_id = t["id"]
            break
    if template_id is None:
        template_id = template_service.create_template(
            TEMPLATE_NAME, TEMPLATE_SUBJECT, TEMPLATE_BODY, TEMPLATE_REPLY, TEMPLATE_VARIABLES
        )

    # 2. Fetch accounts
    accounts = account_service.list_accounts()
    senders = [a for a in accounts if a["role"] == "sender"]
    peers = [a for a in accounts if a["role"] == "peer"]

    if not senders:
        return {"success": False, "error": "No sender accounts found. Add senders first."}
    if not peers:
        return {"success": False, "error": "No peer accounts found. Add peers first."}

    peer_ids = [p["id"] for p in peers]

    # 3. Update sender passwords only when a password is supplied and the sender
    # has no password, or the user explicitly asks to overwrite. This supports
    # Zoho, where each sender has its own app password saved beforehand.
    if req.sender_app_password:
        for sender in senders:
            existing = account_service.get_plain_password(sender["id"])
            if req.overwrite_passwords or not existing:
                account_service.update_account(sender["id"], password=req.sender_app_password)

    # 4. Ensure every active sender has a warm-up campaign linked to every peer.
    result = campaign_service.ensure_warmup_campaigns_for_all_senders(
        template_id=template_id,
        daily_target=req.daily_target,
        ramp_weeks=req.ramp_weeks,
        tick_interval=req.tick_interval,
        active_start=req.active_start,
        active_end=req.active_end,
        timezone=req.timezone,
    )
    created = result["created"]
    synced = result["synced"]

    # 5. Optional: tick immediately (new and existing warmup campaigns)
    if req.tick_now:
        for cid in created + synced:
            try:
                campaign_service.campaign_tick(cid, force=True)
            except Exception:
                pass

    return {
        "success": True,
        "template_id": template_id,
        "senders_updated": len(senders),
        "campaigns_created": len(created),
        "campaigns_synced": len(synced),
        "campaign_ids": created + synced,
        "peers_used": len(peers),
    }
