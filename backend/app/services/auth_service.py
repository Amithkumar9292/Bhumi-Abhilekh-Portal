"""
Auth service: login, token refresh, logout.
"""

import sys
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, Response, status
from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    verify_refresh_token,
)
from app.db.redis_client import get_redis_client
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserInToken
from app.config import settings


REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = settings.refresh_token_expire_days * 86400


async def login(
    payload: LoginRequest,
    db: AsyncSession,
    response: Response,
) -> TokenResponse:
    """Authenticate user, issue access + refresh tokens."""
    result = await db.execute(
        select(User).where(User.username == payload.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    access_token = create_access_token(str(user.id), user.role.value)
    refresh_token = create_refresh_token(str(user.id))

    # Store refresh token in Redis for revocation support.
    # If Redis is unavailable, login still succeeds (revocation is degraded).
    try:
        redis = await get_redis_client()
        await redis.setex(
            f"refresh:{user.id}",
            REFRESH_COOKIE_MAX_AGE,
            refresh_token,
        )
        # NOTE: do NOT call redis.aclose() here — we use a shared connection pool.
    except Exception as redis_err:
        print(
            f"[auth] WARNING: Redis unavailable, skipping refresh token storage: {redis_err}",
            file=sys.stderr,
        )

    # Update last_login
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(last_login=datetime.now(timezone.utc))
    )
    await db.commit()

    # Set httpOnly cookie for refresh token
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=False,  # set True in production with HTTPS
        samesite="lax",
        max_age=REFRESH_COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserInToken(
            id=str(user.id),
            username=user.username,
            full_name=user.full_name,
            email=user.email,
            role=user.role.value,
            is_active=user.is_active,
        )
    )


async def refresh_access_token(refresh_token: str) -> TokenResponse:
    """Exchange a valid refresh token for a new access token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token.",
    )
    try:
        payload = verify_refresh_token(refresh_token)
        user_id = payload.get("sub")
    except JWTError:
        raise credentials_exception from None

    # Validate against Redis (skip validation if Redis is unavailable).
    try:
        redis = await get_redis_client()
        stored = await redis.get(f"refresh:{user_id}")
        # NOTE: do NOT call redis.aclose() here — we use a shared connection pool.
        if stored is not None and stored != refresh_token:
            raise credentials_exception
    except HTTPException:
        raise
    except Exception as redis_err:
        print(
            f"[auth] WARNING: Redis unavailable, skipping refresh token validation: {redis_err}",
            file=sys.stderr,
        )

    # We need role from DB for new access token
    from app.db.postgres import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise credentials_exception

    new_access = create_access_token(str(user.id), user.role.value)
    return TokenResponse(
        access_token=new_access,
        expires_in=settings.access_token_expire_minutes * 60,
    )


async def logout(user_id: str, response: Response) -> None:
    """Revoke refresh token and clear cookie."""
    try:
        redis = await get_redis_client()
        await redis.delete(f"refresh:{user_id}")
        # NOTE: do NOT call redis.aclose() here — we use a shared connection pool.
    except Exception as redis_err:
        print(
            f"[auth] WARNING: Redis unavailable, skipping refresh token revocation: {redis_err}",
            file=sys.stderr,
        )
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/v1/auth")
