"""
Reputation Agent - FastAPI entry point for Vercel/serverless deployment.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from slowapi.middleware import SlowAPIMiddleware

import db
import auth as auth_module
from config import settings
from limiter import limiter
from routes import (
    auth,
    accounts,
    templates,
    campaigns,
    sends,
    reputation,
    logs,
    settings_api,
    stats,
    websocket,
    cron,
    setup,
    bootstrap,
)
from services.log_service import add_log


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: keep the app alive even if the database is not configured yet so
    # the health endpoint can report the issue clearly.
    try:
        db.init_db()
        auth_module.create_default_admin()
        add_log("info", f"{settings.app_name} started", "main")
    except Exception as exc:
        add_log("error", f"Startup failed (database likely missing): {exc}", "main")
    yield
    # Shutdown
    add_log("info", f"{settings.app_name} stopped", "main")


import time

app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    if duration > 500:
        print(f"SLOW {request.method} {request.url.path} {int(duration)}ms")
    return response

# CORS: same-origin by default; explicit origins when configured.
if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=not settings.debug,
)

# Include API routers
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(templates.router)
app.include_router(campaigns.router)
app.include_router(sends.router)
app.include_router(reputation.router)
app.include_router(logs.router)
app.include_router(settings_api.router)
app.include_router(stats.router)
app.include_router(websocket.router)
app.include_router(cron.router)
app.include_router(setup.router)
app.include_router(bootstrap.router)

# Static files (used for local development; Vercel serves static/ directly)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health_check():
    """Public health endpoint for load balancers and monitoring."""
    detail = {}
    try:
        row = db.fetchone("SELECT 1 as ok")
        detail["database"] = "ok" if row and row["ok"] == 1 else "error"
    except Exception as e:
        detail["database"] = f"error: {e}"
        return JSONResponse(content={"status": "unhealthy", "detail": detail}, status_code=503)

    return JSONResponse(content={"status": "healthy", "detail": detail}, status_code=200)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    try:
        auth_module.get_session(request)
        return RedirectResponse(url="/")
    except Exception:
        with open("static/login.html") as f:
            return f.read()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        auth_module.get_session(request)
        with open("static/index.html") as f:
            return f.read()
    except Exception:
        return RedirectResponse(url="/login")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
