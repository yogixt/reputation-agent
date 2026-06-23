"""
Vercel Cron Job endpoints.

These endpoints are invoked by Vercel's cron scheduler. Each request must include
the Authorization header with the CRON_SECRET token.
"""

import secrets as secrets_module
from fastapi import APIRouter, Request, HTTPException

from services.health_service import run_health_check
from services.reputation_service import calculate_all_reputation
from services.email_queue_service import process_pending_jobs, detect_real_replies
from config import settings
from services.campaign_service import advance_campaign_weeks, campaign_tick_all
from services.log_service import cleanup_old_logs
from services.log_service import add_log

router = APIRouter(prefix="/api/cron", tags=["cron"])


def _verify_cron_secret(request: Request):
    expected = settings.cron_secret
    if not expected:
        raise HTTPException(status_code=500, detail="Server configuration error")
    auth = request.headers.get("authorization", "")
    token = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else ""
    if not secrets_module.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/health")
async def cron_health(request: Request):
    _verify_cron_secret(request)
    try:
        run_health_check()
        add_log("info", "Health check cron completed", "cron")
        return {"success": True}
    except Exception as e:
        add_log("error", f"Health check cron failed: {e}", "cron")
        raise HTTPException(status_code=500, detail="Cron job failed")


@router.post("/reputation")
async def cron_reputation(request: Request):
    _verify_cron_secret(request)
    try:
        calculate_all_reputation()
        add_log("info", "Reputation calc cron completed", "cron")
        return {"success": True}
    except Exception as e:
        add_log("error", f"Reputation calc cron failed: {e}", "cron")
        raise HTTPException(status_code=500, detail="Cron job failed")


@router.post("/queue")
async def cron_queue(request: Request):
    _verify_cron_secret(request)
    try:
        campaign_tick_all()
        # Process enough jobs to cover the full daily target from all campaigns.
        process_pending_jobs(limit=settings.max_daily_target)
        # Count real replies that landed back in the sender inbox.
        detect_real_replies()
        add_log("info", "Queue processor cron completed", "cron")
        return {"success": True}
    except Exception as e:
        add_log("error", f"Queue processor cron failed: {e}", "cron")
        raise HTTPException(status_code=500, detail="Cron job failed")


@router.post("/advance-weeks")
async def cron_advance_weeks(request: Request):
    _verify_cron_secret(request)
    try:
        advance_campaign_weeks()
        add_log("info", "Advance weeks cron completed", "cron")
        return {"success": True}
    except Exception as e:
        add_log("error", f"Advance weeks cron failed: {e}", "cron")
        raise HTTPException(status_code=500, detail="Cron job failed")


@router.post("/log-cleanup")
async def cron_log_cleanup(request: Request):
    _verify_cron_secret(request)
    try:
        cleanup_old_logs()
        add_log("info", "Log cleanup cron completed", "cron")
        return {"success": True}
    except Exception as e:
        add_log("error", f"Log cleanup cron failed: {e}", "cron")
        raise HTTPException(status_code=500, detail="Cron job failed")
