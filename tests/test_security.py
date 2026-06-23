"""
Tests for security utilities.
"""

import pytest
from cryptography.fernet import Fernet

import security


def test_password_hashing():
    hashed = security.hash_password("my-secret-password")
    assert security.verify_password("my-secret-password", hashed) is True
    assert security.verify_password("wrong-password", hashed) is False


def test_encrypt_decrypt_roundtrip():
    secret = "gmail-app-password-1234"
    encrypted = security.encrypt_secret(secret)
    assert encrypted != secret
    decrypted = security.decrypt_secret(encrypted)
    assert decrypted == secret


def test_decrypt_with_wrong_key_fails():
    secret = "gmail-app-password-1234"
    encrypted = security.encrypt_secret(secret)

    # Temporarily swap to a different key
    from config import settings, get_settings
    original_key = settings.encryption_key
    settings.encryption_key = Fernet.generate_key().decode()
    try:
        with pytest.raises(security.DecryptionError):
            security.decrypt_secret(encrypted)
    finally:
        settings.encryption_key = original_key
