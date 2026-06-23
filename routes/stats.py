"""
Stats API routes
"""

from fastapi import APIRouter, Depends
import auth
from services import stats_service

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
async def get_stats(session: dict = Depends(auth.require_auth)):
    return stats_service.get_stats()
