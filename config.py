"""
Application configuration and settings.

CRITICAL: SECRET_KEY and ENCRYPTION_KEY must be set in the environment or .env
file. ENCRYPTION_KEY is used to encrypt Gmail app passwords; losing it means
losing access to all stored credentials. Use scripts/generate_keys.py to create
new keys.
"""

import os
import secrets
from functools import lru_cache
from typing import Optional
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Reputation Agent"
    debug: bool = False
    env: str = "production"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str

    # Security — required, no defaults, because random defaults would invalidate
    # stored credentials and sessions on every restart.
    secret_key: str
    session_cookie_name: str = "ra_session"
    session_max_age: int = 7 * 24 * 60 * 60  # 7 days
    encryption_key: str

    # CORS: empty means same-origin only.
    cors_origins: Optional[str] = None

    # Auth — required, no defaults.
    admin_email: str
    admin_password: str

    # Email providers (all accounts are currently on Zoho Mail India)
    gmail_imap_host: str = "imap.zoho.in"
    gmail_imap_port: int = 993
    gmail_smtp_host: str = "smtp.zoho.in"
    gmail_smtp_port: int = 587

    # Queue / sending
    tick_interval_minutes: int = 5
    max_retries: int = 5
    active_hours_start: int = 9
    active_hours_end: int = 20

    # Ramp settings
    default_ramp_weeks: int = 12
    default_daily_target: int = 5
    max_daily_target: int = 200

    # Engagement probabilities
    move_probability: float = Field(0.85, ge=0.0, le=1.0)
    open_probability: float = Field(0.90, ge=0.0, le=1.0)
    reply_probability: float = Field(0.30, ge=0.0, le=1.0)

    # Rate limiting
    login_rate_limit: str = "5/minute"
    default_rate_limit: str = "30/minute"

    # Vercel Cron Jobs shared secret (Vercel auto-sets CRON_SECRET)
    cron_secret: str

    # Turso (optional). Only used when DATABASE_URL is a libsql:// / sqlite+libsql:// URL.
    turso_auth_token: Optional[str] = None

    # DANGER: disables login entirely. Useful for demos only.
    disable_auth: bool = False

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("secret_key", "encryption_key", "admin_email", "admin_password", mode="before")
    @classmethod
    def _reject_placeholder(cls, v: str, info) -> str:
        placeholders = {
            "",
            "change-me-in-production",
            "change-me-on-first-login",
            "admin123",
        }
        if isinstance(v, str) and v.strip().lower() in placeholders:
            raise ValueError(
                f"{info.field_name} must be set to a real value. "
                "Run: python scripts/generate_keys.py"
            )
        return v

    @field_validator("disable_auth", mode="after")
    @classmethod
    def _reject_disable_auth_in_production(cls, v: bool, info) -> bool:
        env = str(info.data.get("env", "production")).lower()
        if v and env != "development":
            raise ValueError("disable_auth can only be true when env=development")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_origins:
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
