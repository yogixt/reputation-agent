"""
Security utilities: password hashing and credential encryption.
"""

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from config import settings


class DecryptionError(Exception):
    """Raised when a secret cannot be decrypted (likely wrong key or tampered data)."""
    pass


def _get_fernet() -> Fernet:
    """Return a Fernet instance configured with ENCRYPTION_KEY.

    ENCRYPTION_KEY must be a 32-byte URL-safe base64-encoded key. The helper
    scripts/generate_keys.py produces a valid key.
    """
    key = settings.encryption_key.strip()
    try:
        f = Fernet(key)
    except ValueError as exc:
        raise ValueError(
            "ENCRYPTION_KEY is not a valid Fernet key. "
            "Run: python scripts/generate_keys.py"
        ) from exc
    return f


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def encrypt_secret(secret: str) -> str:
    return _get_fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            "Failed to decrypt a stored credential. "
            "This usually means ENCRYPTION_KEY has changed since the credential was saved."
        ) from exc
