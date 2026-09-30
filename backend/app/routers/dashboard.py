"""
Dashboard router: statistics and recent activity.
"""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession
from app.models.land_record import LandRecord, RecordStatus
from app.models.user import User
from app.models.document import Document

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_stats(db: DBSession, current_user: CurrentUser) -> dict:
    """Return aggregate statistics for the dashboard."""
    total_records = (await db.execute(select(func.count(LandRecord.id)))).scalar_one()
    pending = (
        await db.execute(
            select(func.count(LandRecord.id)).where(LandRecord.status == RecordStatus.PENDING)
        )
    ).scalar_one()
    under_review = (
        await db.execute(
            select(func.count(LandRecord.id)).where(LandRecord.status == RecordStatus.UNDER_REVIEW)
        )
    ).scalar_one()
    verified = (
        await db.execute(
            select(func.count(LandRecord.id)).where(LandRecord.status == RecordStatus.VERIFIED)
        )
    ).scalar_one()
    rejected = (
        await db.execute(
            select(func.count(LandRecord.id)).where(LandRecord.status == RecordStatus.REJECTED)
        )
    ).scalar_one()
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    total_documents = (await db.execute(select(func.count(Document.id)))).scalar_one()

    return {
        "records": {
            "total": total_records,
            "pending": pending,
            "under_review": under_review,
            "verified": verified,
            "rejected": rejected,
        },
        "users": {"total": total_users},
        "documents": {"total": total_documents},
        "disclaimer": "⚠️ All data is synthetic — demo purposes only.",
    }


@router.get("/activity")
async def get_recent_activity(
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Return the 10 most recently updated land records."""
    result = await db.execute(
        select(LandRecord).order_by(LandRecord.updated_at.desc()).limit(10)
    )
    records = result.scalars().all()
    return {
        "recent_records": [
            {
                "id": str(r.id),
                "khasra_number": r.khasra_number,
                "owner_name": r.owner_name,
                "district": r.district,
                "status": r.status.value,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in records
        ]
    }
