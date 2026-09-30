"""
Admin router: user management and audit log viewing.
"""

import math

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.mongo import get_audit_db
from app.dependencies import AdminUser, DBSession
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.audit_service import log_event

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=PaginatedResponse[UserResponse])
async def list_users(
    db: DBSession,
    current_user: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[UserResponse]:
    total = (await db.execute(select(func.count(User.id)))).scalar_one()
    result = await db.execute(
        select(User).offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().all()
    return PaginatedResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: DBSession,
    current_user: AdminUser,
) -> UserResponse:
    existing = (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists.")

    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        district_code=payload.district_code,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await log_event("CREATE_USER", current_user.id, "User", user.id, {"role": user.role.value})
    return UserResponse.model_validate(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    db: DBSession,
    current_user: AdminUser,
) -> UserResponse:
    from uuid import UUID
    user = await db.get(User, UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.flush()
    await db.refresh(user)
    await log_event("UPDATE_USER", current_user.id, "User", user.id)
    return UserResponse.model_validate(user)


@router.get("/audit-logs")
async def get_audit_logs(
    current_user: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    """Fetch recent audit logs from MongoDB (ADMIN only)."""
    db = get_audit_db()
    skip = (page - 1) * page_size
    cursor = db["audit_logs"].find({}).sort("timestamp", -1).skip(skip).limit(page_size)
    logs = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        logs.append(doc)
    total = await db["audit_logs"].count_documents({})
    return {
        "items": logs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 0,
    }
