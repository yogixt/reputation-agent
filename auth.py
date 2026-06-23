"""
Authentication helpers
"""

from fastapi import Request, HTTPException, Depends
import security
import db
from config import settings


def get_session(request: Request) -> dict:
    if settings.disable_auth:
        return {"user_id": 1, "email": settings.admin_email}
    session = request.session
    if not session.get("user_id"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": session["user_id"], "email": session.get("email", "")}


def get_session_from_scope(scope: dict) -> dict:
    """Validate a session from an ASGI scope (used by WebSocket)."""
    if settings.disable_auth:
        return {"user_id": 1, "email": settings.admin_email}
    session = scope.get("session", {})
    if not session.get("user_id"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": session["user_id"], "email": session.get("email", "")}


def require_auth(request: Request = None) -> dict:
    return get_session(request)


def authenticate_user(email: str, password: str) -> dict:
    if settings.disable_auth:
        return {"user_id": 1, "email": email}
    row = db.fetchone("SELECT * FROM users WHERE email = ?", (email,))
    if not row or not security.verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"user_id": row["id"], "email": row["email"]}


def create_default_admin():
    existing = db.fetchone("SELECT id FROM users WHERE email = ?", (settings.admin_email,))
    if existing:
        return
    db.execute(
        "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
        (settings.admin_email, security.hash_password(settings.admin_password), "Administrator"),
    )
