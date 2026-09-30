"""
Notifications Router — User notification inbox.

Endpoints:
  GET  /notifications              — list my notifications (unread first)
  POST /notifications/{id}/read    — mark one as read
  POST /notifications/read-all     — mark all as read
  DELETE /notifications/{id}       — delete notification
  GET  /notifications/unread-count — lightweight count for badge

Helper: push_notification() — called by other services to create notifications
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUser, DBSession
from app.models.extended import Notification, NotificationType

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ── Public helper ─────────────────────────────────────────────────────────────

async def push_notification(
    db: AsyncSession,
    recipient_id: uuid.UUID,
    notif_type: str,
    title: str,
    body: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
) -> None:
    """Create a notification for a user. Fire-and-forget — errors logged only."""
    try:
        n_type = NotificationType(notif_type)
    except ValueError:
        n_type = NotificationType.SYSTEM_NOTICE
    notif = Notification(
        id=uuid.uuid4(),
        recipient_id=recipient_id,
        notification_type=n_type,
        title=title,
        body=body,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.add(notif)
    # Caller commits


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_notifications(
    unread_only: bool = False,
    page: int = 1,
    page_size: int = 30,
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    q = select(Notification).where(Notification.recipient_id == current_user.id)
    if unread_only:
        q = q.where(Notification.is_read == False)
    q = q.order_by(Notification.is_read.asc(), Notification.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    notifs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(n.id),
                "type": n.notification_type.value,
                "title": n.title,
                "body": n.body,
                "resource_type": n.resource_type,
                "resource_id": n.resource_id,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifs
        ],
        "total": total,
        "unread": sum(1 for n in notifs if not n.is_read),
    }


@router.get("/unread-count")
async def unread_count(db: DBSession, current_user: CurrentUser) -> dict:
    count = (await db.execute(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == current_user.id,
            Notification.is_read == False,
        )
    )).scalar() or 0
    return {"unread": count}


@router.post("/{notif_id}/read")
async def mark_read(
    notif_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    notif = await db.get(Notification, notif_id)
    if not notif or notif.recipient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    notif.read_at = datetime.now(timezone.utc)
    await db.flush()
    return {"id": str(notif_id), "is_read": True}


@router.post("/read-all")
async def mark_all_read(db: DBSession, current_user: CurrentUser) -> dict:
    await db.execute(
        update(Notification)
        .where(Notification.recipient_id == current_user.id, Notification.is_read == False)
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    return {"message": "All notifications marked as read"}


@router.delete("/{notif_id}", status_code=204)
async def delete_notification(
    notif_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    notif = await db.get(Notification, notif_id)
    if not notif or notif.recipient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.delete(notif)
    await db.flush()
