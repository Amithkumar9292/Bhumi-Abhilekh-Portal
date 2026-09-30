"""
Users router: profile management for authenticated users.
"""

from fastapi import APIRouter, HTTPException

from app.core.security import hash_password, verify_password
from app.dependencies import CurrentUser, DBSession
from app.schemas.auth import PasswordChangeRequest
from app.schemas.user import UserMeResponse, UserUpdate
from app.services.audit_service import log_event

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserMeResponse)
async def get_profile(current_user: CurrentUser) -> UserMeResponse:
    return UserMeResponse.model_validate(current_user)


@router.put("/me", response_model=UserMeResponse)
async def update_profile(
    payload: UserUpdate,
    db: DBSession,
    current_user: CurrentUser,
) -> UserMeResponse:
    """Update own profile (non-privileged fields only)."""
    allowed = {"full_name", "email"}
    for field, value in payload.model_dump(exclude_none=True).items():
        if field in allowed:
            setattr(current_user, field, value)
    await db.flush()
    await db.refresh(current_user)
    await log_event("UPDATE_PROFILE", current_user.id, "User", current_user.id)
    return UserMeResponse.model_validate(current_user)


@router.post("/me/change-password", status_code=204)
async def change_password(
    payload: PasswordChangeRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    current_user.hashed_password = hash_password(payload.new_password)
    await db.flush()
    await log_event("CHANGE_PASSWORD", current_user.id, "User", current_user.id)
