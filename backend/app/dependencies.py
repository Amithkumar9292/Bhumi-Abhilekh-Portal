"""
FastAPI dependencies: authentication, authorization, DB sessions.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_access_token
from app.db.postgres import get_db
from app.models.user import RoleEnum, User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extracts and validates JWT from Authorization: Bearer header."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise credentials_exception
    try:
        payload = verify_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception from None

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


# ── RBAC helper factory ───────────────────────────────────────────────────────

def require_roles(*roles: RoleEnum):
    """Returns a dependency that enforces one of the given roles."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted to perform this action.",
            )
        return current_user
    return _check


# ── Typed dependency aliases ──────────────────────────────────────────────────
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_roles(RoleEnum.ADMIN))]
OfficerUser = Annotated[User, Depends(require_roles(RoleEnum.ADMIN, RoleEnum.OFFICER))]
VerifierUser = Annotated[User, Depends(require_roles(RoleEnum.ADMIN, RoleEnum.VERIFIER))]
DBSession = Annotated[AsyncSession, Depends(get_db)]
