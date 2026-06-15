"""Secret encryption for per-tenant credentials.

Tenant-supplied secrets (Splunk tokens, model API keys) are encrypted at rest
with Fernet (AES-128-CBC + HMAC) using an app-managed key from
``SENTINEL_SECRET_KEY``. Secrets are decrypted only at the moment a backend
client is constructed for a request; they are never returned to the API or
written to logs.

Honest gap (documented): the Fernet key is app-managed via env. A production
deployment should source it from a KMS / Key Vault and rotate it. The interface
here (`encrypt`/`decrypt`) is unchanged by that swap.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class SecretCipherError(Exception):
    """Raised when a secret cannot be decrypted (wrong/rotated key or corruption)."""


def _fernet() -> Fernet:
    """Derive a stable Fernet key from the configured secret.

    We hash the configured secret to a 32-byte key so any sufficiently strong
    ``SENTINEL_SECRET_KEY`` works without requiring it to be a Fernet-format key.
    """
    settings = get_settings()
    raw = settings.secret_key.encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string; returns a URL-safe token for storage."""
    if plaintext == "":
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    """Decrypt a stored secret token back to plaintext."""
    if token == "":
        return ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise SecretCipherError("Secret could not be decrypted (key rotated?)") from exc
