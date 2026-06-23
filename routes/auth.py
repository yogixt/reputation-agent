"""
Auth API routes
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

import auth as auth_module
import models
from config import settings
from limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=models.LoginResponse)
@limiter.limit(settings.login_rate_limit)
async def login(req: models.LoginRequest, request: Request):
    user = auth_module.authenticate_user(req.email, req.password)
    request.session["user_id"] = user["user_id"]
    request.session["email"] = user["email"]
    return JSONResponse(content={"success": True, "email": user["email"]})


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    response = JSONResponse(content={"success": True})
    response.delete_cookie(settings.session_cookie_name)
    return response


@router.get("/me")
async def me(session: dict = Depends(auth_module.require_auth)):
    return {"email": session["email"], "user_id": session["user_id"]}
