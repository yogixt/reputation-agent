#!/usr/bin/env python3
"""
Generate secure SECRET_KEY and ENCRYPTION_KEY values for .env.

Usage:
    python scripts/generate_keys.py

Copy the output into your .env file. Keep ENCRYPTION_KEY backed up; losing it
means stored Gmail app passwords cannot be decrypted.
"""

import secrets
from cryptography.fernet import Fernet


def main():
    secret_key = secrets.token_urlsafe(32)
    encryption_key = Fernet.generate_key().decode()

    print("# Add these to your .env file (do not commit .env):")
    print(f"SECRET_KEY={secret_key}")
    print(f"ENCRYPTION_KEY={encryption_key}")


if __name__ == "__main__":
    main()
