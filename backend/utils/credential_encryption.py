"""Application-level encryption for database-backed runtime credentials."""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


CIPHERTEXT_PREFIX = "enc:v1:"
_DERIVATION_CONTEXT = b"agent-teams/database-credentials/v1"


class CredentialDecryptionError(ValueError):
    """Raised when a versioned database credential cannot be decrypted."""


def _application_secret() -> str:
    # Lazy import avoids a config -> models -> encryption import cycle.
    from config import Config

    secret = Config.SECRET_KEY
    if not secret:
        raise RuntimeError("SECRET_KEY is required for database credential encryption")
    return secret


@lru_cache(maxsize=4)
def _fernet_for_secret(application_secret: str) -> Fernet:
    digest = hashlib.sha256(
        _DERIVATION_CONTEXT + b"\0" + application_secret.encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted_value(value: object) -> bool:
    return isinstance(value, str) and value.startswith(CIPHERTEXT_PREFIX)


def encrypt_value(value: Optional[str]) -> Optional[str]:
    """Encrypt a string unless it already carries the current ciphertext prefix."""
    if value is None:
        return None
    value = str(value)
    if is_encrypted_value(value):
        return value
    token = _fernet_for_secret(_application_secret()).encrypt(value.encode("utf-8"))
    return CIPHERTEXT_PREFIX + token.decode("ascii")


def decrypt_value(value: Optional[str]) -> Optional[str]:
    """Decrypt versioned ciphertext; return legacy plaintext for migration safety."""
    if value is None or not is_encrypted_value(value):
        return value
    token = value[len(CIPHERTEXT_PREFIX):]
    try:
        plaintext = _fernet_for_secret(_application_secret()).decrypt(
            token.encode("ascii")
        )
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise CredentialDecryptionError(
            "Database credential cannot be decrypted with the configured SECRET_KEY"
        ) from exc
    return plaintext.decode("utf-8")


class EncryptedText(TypeDecorator):
    """SQLAlchemy text type that stores versioned ciphertext at rest."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)
