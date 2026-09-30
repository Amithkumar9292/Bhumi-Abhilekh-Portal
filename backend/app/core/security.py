"""
Security utilities: password hashing, JWT token creation and verification.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import settings

BCRYPT_ROUNDS = 12
# bcrypt silently ignores anything past 72 bytes, so inputs are truncated
# explicitly and identically on both the hashing and verifying side.
BCRYPT_MAX_BYTES = 72


# ── Password ──────────────────────────────────────────────────────────────────

def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed or non-bcrypt stored hash: treat as a failed match rather
        # than a 500, so a bad row cannot be used to break authentication.
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────

def _create_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    payload["iat"] = datetime.now(timezone.utc)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str, role: str, extra: dict | None = None) -> str:
    data: dict[str, Any] = {"sub": subject, "role": role, "type": "access"}
    if extra:
        data.update(extra)
    return _create_token(
        data, timedelta(minutes=settings.access_token_expire_minutes)
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        {"sub": subject, "type": "refresh"},
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Raises JWTError on invalid / expired tokens."""
    return dict(jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm]))


def verify_access_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    return payload


def verify_refresh_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise JWTError("Not a refresh token")
    return payload
