"""
Tests for configuration validation.
"""

import os

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from config import Settings, get_settings


def test_placeholder_secret_key_rejected(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "change-me-in-production")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-password")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()


def test_placeholder_encryption_key_rejected(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ENCRYPTION_KEY", "change-me-in-production")
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-password")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()


def test_placeholder_admin_password_rejected(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ADMIN_PASSWORD", "admin123")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()


def test_disable_auth_rejected_in_non_development_envs(monkeypatch):
    for env in ["production", "staging", "test"]:
        monkeypatch.setenv("SECRET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("ADMIN_PASSWORD", "strong-password")
        monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
        monkeypatch.setenv("DISABLE_AUTH", "true")
        monkeypatch.setenv("ENV", env)
        get_settings.cache_clear()
        with pytest.raises(
            ValidationError,
            match="disable_auth can only be true when env=development",
        ):
            get_settings()


def test_disable_auth_allowed_in_development(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-password")
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
    monkeypatch.setenv("DISABLE_AUTH", "true")
    monkeypatch.setenv("ENV", "development")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.disable_auth is True


def test_disable_auth_false_allowed_in_production(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-password")
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
    monkeypatch.setenv("DISABLE_AUTH", "false")
    monkeypatch.setenv("ENV", "production")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.disable_auth is False
