"""
Single-call bootstrap for the SPA.
Returns everything the frontend needs for the initial load in one request.
"""

from fastapi import APIRouter, Depends
import auth
from services import account_service, campaign_service, template_service, stats_service, log_service, reputation_service, settings_service
from config import settings

router = APIRouter(prefix="/api/bootstrap", tags=["bootstrap"])


@router.get("")
async def bootstrap(session: dict = Depends(auth.require_auth)):
    return {
        "accounts": account_service.list_accounts(),
        "campaigns": campaign_service.list_campaigns(),
        "templates": template_service.list_templates(),
        "stats": stats_service.get_stats(),
        "logs": log_service.get_logs(limit=100),
        "reputation": reputation_service.get_latest_scores(),
        "settings": {
            "tick_interval_minutes": settings_service.get_setting("tick_interval_minutes", settings.tick_interval_minutes),
            "active_hours_start": settings_service.get_setting("active_hours_start", settings.active_hours_start),
            "active_hours_end": settings_service.get_setting("active_hours_end", settings.active_hours_end),
            "move_probability": settings_service.get_setting("move_probability", settings.move_probability),
            "open_probability": settings_service.get_setting("open_probability", settings.open_probability),
            "reply_probability": settings_service.get_setting("reply_probability", settings.reply_probability),
        },
    }
