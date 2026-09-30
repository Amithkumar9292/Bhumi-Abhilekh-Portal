"""
Land Records router: full CRUD + verification workflow.
"""

import math
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.dependencies import CurrentUser, DBSession, OfficerUser, VerifierUser
from app.models.land_record import LandRecord, RecordStatus
from app.models.user import RoleEnum
from app.schemas.common import PaginatedResponse
from app.schemas.land_record import (
    LandRecordCreate,
    LandRecordListItem,
    LandRecordResponse,
    LandRecordUpdate,
    VerifyRequest,
)
from app.services.audit_service import log_event
from datetime import datetime, timezone

router = APIRouter(prefix="/land-records", tags=["Land Records"])


@router.get("", response_model=PaginatedResponse[LandRecordListItem])
async def list_land_records(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: RecordStatus | None = None,
    district: str | None = None,
    search: str | None = None,
) -> PaginatedResponse[LandRecordListItem]:
    """List land records with pagination and filters."""
    q = select(LandRecord)
    if status:
        q = q.where(LandRecord.status == status)
    if district:
        q = q.where(LandRecord.district.ilike(f"%{district}%"))
    if search:
        q = q.where(
            or_(
                LandRecord.khasra_number.ilike(f"%{search}%"),
                LandRecord.owner_name.ilike(f"%{search}%"),
                LandRecord.village.ilike(f"%{search}%"),
            )
        )
    count_q = select(func.count()).select_from(q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    q = q.offset((page - 1) * page_size).limit(page_size).order_by(LandRecord.created_at.desc())
    result = await db.execute(q)
    records = result.scalars().all()

    return PaginatedResponse(
        items=[LandRecordListItem.model_validate(r) for r in records],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.post("", response_model=LandRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_land_record(
    payload: LandRecordCreate,
    db: DBSession,
    current_user: OfficerUser,
) -> LandRecordResponse:
    """Create a new land record (OFFICER/ADMIN only)."""
    record = LandRecord(**payload.model_dump(), created_by=current_user.id)
    db.add(record)
    await db.flush()
    await db.refresh(record)
    await log_event(
        action="CREATE_LAND_RECORD",
        actor_id=current_user.id,
        resource_type="LandRecord",
        resource_id=record.id,
        details={"khasra_number": record.khasra_number},
    )
    return LandRecordResponse.model_validate(record)


@router.get("/{record_id}", response_model=LandRecordResponse)
async def get_land_record(
    record_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> LandRecordResponse:
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found.")
    return LandRecordResponse.model_validate(record)


@router.put("/{record_id}", response_model=LandRecordResponse)
async def update_land_record(
    record_id: UUID,
    payload: LandRecordUpdate,
    db: DBSession,
    current_user: OfficerUser,
) -> LandRecordResponse:
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found.")
    if record.status == RecordStatus.VERIFIED:
        raise HTTPException(status_code=409, detail="Verified records cannot be edited.")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(record, field, value)
    await db.flush()
    await db.refresh(record)
    await log_event("UPDATE_LAND_RECORD", current_user.id, "LandRecord", record.id)
    return LandRecordResponse.model_validate(record)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_land_record(
    record_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only ADMIN can delete records.")
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found.")
    await db.delete(record)
    await db.flush()
    await log_event("DELETE_LAND_RECORD", current_user.id, "LandRecord", record_id)


@router.post("/{record_id}/verify", response_model=LandRecordResponse)
async def verify_land_record(
    record_id: UUID,
    payload: VerifyRequest,
    db: DBSession,
    current_user: VerifierUser,
) -> LandRecordResponse:
    """Approve or reject a land record (VERIFIER/ADMIN only)."""
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found.")
    if record.status not in (RecordStatus.PENDING, RecordStatus.UNDER_REVIEW):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot verify a record with status '{record.status}'.",
        )

    record.status = RecordStatus.VERIFIED if payload.approved else RecordStatus.REJECTED
    record.verified_by = current_user.id
    record.verified_at = datetime.now(timezone.utc)
    record.rejection_reason = payload.rejection_reason if not payload.approved else None
    await db.flush()
    await db.refresh(record)
    await log_event(
        "VERIFY_LAND_RECORD",
        current_user.id,
        "LandRecord",
        record.id,
        {"approved": payload.approved, "reason": payload.rejection_reason},
    )
    return LandRecordResponse.model_validate(record)
