"""
Audit service: writes structured event logs to MongoDB.
Also provides a query interface for the audit trail API.

Audit logging is a *side effect* and must never delay the caller's response.
Every write is therefore wrapped in a hard timeout so that an unreachable or
slow MongoDB can only ever cost a few milliseconds of latency, not the whole
request budget. If audit writes time out or fail, the event is dropped and the
failure is reported through the return value / stderr — never raised.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.config import settings
from app.db.mongo import get_audit_db


async def log_event(
    action: str,
    actor_id: str | UUID | None,
    resource_type: str,
    resource_id: str | UUID | None,
    details: dict[str, Any] | None = None,
    status: str = "SUCCESS",
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    timeout_s: Optional[float] = None,
) -> bool:
    """
    Writes an immutable audit event to MongoDB.

    Time-boxed and non-fatal: returns True on success, False if the event could
    not be persisted. Callers should never branch on the result for control flow.

    All sensitive actions (login, record changes, verifications, user admin,
    document uploads, pipeline triggers) must call this.
    """
    document = {
        "action": action,
        "actor_id": str(actor_id) if actor_id else None,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id else None,
        "details": details or {},
        "status": status,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "timestamp": datetime.now(timezone.utc),
    }
    budget = timeout_s if timeout_s is not None else settings.audit_write_timeout_s
    try:
        db = get_audit_db()
        await asyncio.wait_for(db["audit_logs"].insert_one(document), timeout=budget)
        return True
    except asyncio.TimeoutError:
        _warn(f"audit write '{action}' exceeded {budget}s budget and was dropped")
        return False
    except Exception as exc:
        _warn(f"failed to write audit log '{action}': {exc!r}")
        return False


def _warn(message: str) -> None:
    import sys

    print(f"[AUDIT] {message}", file=sys.stderr)


async def query_audit_logs(
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> list[dict]:
    """Query audit logs from MongoDB with filters."""
    db = get_audit_db()
    query: dict[str, Any] = {}
    if action:
        query["action"] = {"$regex": action, "$options": "i"}
    if actor_id:
        query["actor_id"] = actor_id
    if resource_type:
        query["resource_type"] = resource_type
    if resource_id:
        query["resource_id"] = resource_id
    if date_from or date_to:
        ts_filter: dict = {}
        if date_from:
            ts_filter["$gte"] = date_from
        if date_to:
            ts_filter["$lte"] = date_to
        query["timestamp"] = ts_filter

    cursor = db["audit_logs"].find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def count_audit_logs(query: dict) -> int:
    db = get_audit_db()
    return await db["audit_logs"].count_documents(query)
