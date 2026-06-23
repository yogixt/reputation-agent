"""
Queue / sends API routes
"""

from fastapi import APIRouter, Depends, Query
import auth
import models
from services import email_queue_service

router = APIRouter(prefix="/api/sends", tags=["sends"])


@router.get("", response_model=list[models.QueueOut])
async def list_sends(status: str = Query(None), limit: int = Query(50), session: dict = Depends(auth.require_auth)):
    return email_queue_service.get_queue(status=status, limit=limit)


@router.post("/process")
async def process_queue(limit: int = Query(100), session: dict = Depends(auth.require_auth)):
    email_queue_service.process_pending_jobs(limit=limit)
    return {"success": True}


@router.post("/bulk")
async def bulk_send(limit: int = Query(100), session: dict = Depends(auth.require_auth)):
    result = email_queue_service.bulk_send_all(limit=limit)
    return {"success": True, **result}


@router.post("/retry-failed")
async def retry_failed(session: dict = Depends(auth.require_auth)):
    email_queue_service.retry_failed_jobs()
    return {"success": True}


@router.post("/clear-pending")
async def clear_pending(session: dict = Depends(auth.require_auth)):
    email_queue_service.clear_pending_jobs()
    return {"success": True}
