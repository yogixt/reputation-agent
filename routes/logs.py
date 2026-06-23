"""
Logs API routes
"""

from fastapi import APIRouter, Depends, Query
import auth
import models
from services import log_service

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[models.LogOut])
async def get_logs(limit: int = Query(100, ge=1, le=1000), level: str = Query(None), session: dict = Depends(auth.require_auth)):
    return log_service.get_logs(limit=limit, level=level)
