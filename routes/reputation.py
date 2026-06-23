"""
Reputation API routes
"""

from fastapi import APIRouter, Depends, Query
import auth
import models
from services import reputation_service

router = APIRouter(prefix="/api/reputation", tags=["reputation"])


@router.get("/{campaign_id}", response_model=list[models.ReputationOut])
async def get_history(campaign_id: int, days: int = Query(30, ge=1, le=365), session: dict = Depends(auth.require_auth)):
    return reputation_service.get_reputation_history(campaign_id, days)


@router.get("", response_model=list)
async def latest_scores(session: dict = Depends(auth.require_auth)):
    return reputation_service.get_latest_scores()
