"""
Account API routes
"""

from fastapi import APIRouter, Depends, Request
import auth
import models
from config import settings
from limiter import limiter
from services import account_service
from services.log_service import add_log

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[models.AccountOut])
async def list_accounts(session: dict = Depends(auth.require_auth)):
    return account_service.list_accounts()


@router.post("", response_model=dict)
@limiter.limit(settings.default_rate_limit)
async def create_account(req: models.AccountCreate, request: Request, session: dict = Depends(auth.require_auth)):
    account_id = account_service.create_account(req.email, req.password, req.role, req.provider)
    return {"success": True, "id": account_id}


@router.post("/bulk-import", response_model=dict)
@limiter.limit(settings.default_rate_limit)
async def bulk_import_accounts(req: models.BulkAccountImport, request: Request, session: dict = Depends(auth.require_auth)):
    result = account_service.bulk_create_accounts([item.model_dump() for item in req.accounts])
    return {"success": True, **result}


@router.delete("/{account_id}")
@limiter.limit(settings.default_rate_limit)
async def delete_account(account_id: int, request: Request, session: dict = Depends(auth.require_auth)):
    account_service.delete_account(account_id)
    return {"success": True}


@router.patch("/{account_id}")
@limiter.limit(settings.default_rate_limit)
async def update_account(account_id: int, req: models.AccountUpdate, request: Request, session: dict = Depends(auth.require_auth)):
    account_service.update_account(account_id, status=req.status, password=req.password)
    return {"success": True}


@router.post("/{account_id}/check")
@limiter.limit(settings.default_rate_limit)
async def check_account(account_id: int, request: Request, session: dict = Depends(auth.require_auth)):
    account = account_service.get_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}
    password = account_service.get_plain_password(account_id)
    if not password:
        return {"success": False, "error": "No password"}
    try:
        from providers.gmail import GmailClient
        with GmailClient(account["email"], password) as client:
            ok = client.health_check()
        return {"success": True, "healthy": ok}
    except Exception as e:
        add_log("warning", f"Account health check failed for {account_id}: {e}", "accounts")
        return {"success": False, "error": "Health check failed"}
