"""
Settings API routes
"""

from fastapi import APIRouter, Depends, Request
import auth
import models
from config import settings
from limiter import limiter
from services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(session: dict = Depends(auth.require_auth)):
    return {
        "tick_interval_minutes": settings_service.get_setting("tick_interval_minutes", settings.tick_interval_minutes),
        "active_hours_start": settings_service.get_setting("active_hours_start", settings.active_hours_start),
        "active_hours_end": settings_service.get_setting("active_hours_end", settings.active_hours_end),
        "move_probability": settings_service.get_setting("move_probability", settings.move_probability),
        "open_probability": settings_service.get_setting("open_probability", settings.open_probability),
        "reply_probability": settings_service.get_setting("reply_probability", settings.reply_probability),
    }


@router.post("")
@limiter.limit(settings.default_rate_limit)
async def update_settings(req: models.SettingsUpdate, request: Request, session: dict = Depends(auth.require_auth)):
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        settings_service.set_setting(k, v)
    return {"success": True}
