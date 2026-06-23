"""
Campaign API routes
"""

from fastapi import APIRouter, Depends, Request
import auth
import models
from config import settings
from limiter import limiter
from services import campaign_service

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.get("", response_model=list[models.CampaignOut])
async def list_campaigns(session: dict = Depends(auth.require_auth)):
    return campaign_service.list_campaigns()


@router.post("", response_model=dict)
@limiter.limit(settings.default_rate_limit)
async def create_campaign(req: models.CampaignCreate, request: Request, session: dict = Depends(auth.require_auth)):
    data = req.model_dump()
    campaign_id = campaign_service.create_campaign(data)
    return {"success": True, "id": campaign_id}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: int, session: dict = Depends(auth.require_auth)):
    return campaign_service.get_campaign(campaign_id)


@router.patch("/{campaign_id}")
@limiter.limit(settings.default_rate_limit)
async def update_campaign(campaign_id: int, req: models.CampaignUpdate, request: Request, session: dict = Depends(auth.require_auth)):
    data = req.model_dump(exclude_unset=True)
    campaign_service.update_campaign(campaign_id, data)
    return {"success": True}


@router.delete("/{campaign_id}")
@limiter.limit(settings.default_rate_limit)
async def delete_campaign(campaign_id: int, request: Request, session: dict = Depends(auth.require_auth)):
    campaign_service.delete_campaign(campaign_id)
    return {"success": True}


@router.post("/{campaign_id}/tick")
@limiter.limit(settings.default_rate_limit)
async def tick_campaign(campaign_id: int, request: Request, session: dict = Depends(auth.require_auth)):
    campaign_service.campaign_tick(campaign_id, force=True)
    # Also process the queue immediately so emails actually send in one click.
    from services import email_queue_service
    email_queue_service.process_pending_jobs(limit=50)
    return {"success": True}
