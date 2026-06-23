"""
Pytest fixtures and test configuration.
"""

import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

# Set test environment variables BEFORE importing project modules.
os.environ.setdefault("APP_NAME", "Reputation Agent Tests")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("ENV", "development")
os.environ.setdefault("HOST", "127.0.0.1")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_reputation_agent.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("CRON_SECRET", "test-cron-secret")
os.environ.setdefault("DISABLE_AUTH", "false")
os.environ.setdefault("GMAIL_IMAP_HOST", "imap.zoho.in")
os.environ.setdefault("GMAIL_IMAP_PORT", "993")
os.environ.setdefault("GMAIL_SMTP_HOST", "smtp.zoho.in")
os.environ.setdefault("GMAIL_SMTP_PORT", "587")
os.environ.setdefault("TICK_INTERVAL_MINUTES", "5")
os.environ.setdefault("MAX_RETRIES", "5")
os.environ.setdefault("ACTIVE_HOURS_START", "9")
os.environ.setdefault("ACTIVE_HOURS_END", "17")
os.environ.setdefault("DEFAULT_RAMP_WEEKS", "12")
os.environ.setdefault("DEFAULT_DAILY_TARGET", "5")
os.environ.setdefault("MAX_DAILY_TARGET", "200")
os.environ.setdefault("MOVE_PROBABILITY", "0.85")
os.environ.setdefault("OPEN_PROBABILITY", "0.90")
os.environ.setdefault("REPLY_PROBABILITY", "0.30")
os.environ.setdefault("LOGIN_RATE_LIMIT", "5/minute")
os.environ.setdefault("DEFAULT_RATE_LIMIT", "30/minute")

import db
import main


@pytest.fixture(scope="function")
def test_db(tmp_path: Path):
    """Provide an isolated SQLite database for each test."""
    db_file = tmp_path / "test.db"
    original_url = db.settings.database_url
    original_is_sqlite = db._IS_SQLITE
    db.settings.database_url = f"sqlite:///{db_file}"
    db._IS_SQLITE = True
    db._engine = db.create_engine(
        db.settings.database_url,
        poolclass=db.StaticPool,
        connect_args={"check_same_thread": False},
    )
    db.init_db()
    yield
    db.settings.database_url = original_url
    db._IS_SQLITE = original_is_sqlite


@pytest.fixture(scope="function")
def client(test_db):
    """Return a FastAPI TestClient with a fresh database."""
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="function")
def authenticated_client(client):
    """Return a TestClient logged in as the default admin."""
    from config import settings
    resp = client.post(
        "/api/auth/login",
        json={
            "email": settings.admin_email,
            "password": settings.admin_password,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    yield client


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear slowapi in-memory rate limiter storage between tests."""
    from limiter import limiter
    limiter._storage.reset()
    yield
    limiter._storage.reset()
