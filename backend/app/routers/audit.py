"""
Audit Trail Router — Immutable event log query API.

Endpoints:
  GET /audit             — list audit events with filters
  GET /audit/actions     — list unique action types
  GET /audit/summary     — count by action/actor/resource
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DBSession
from app.services.audit_service import query_audit_logs

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("")
async def list_audit_events(
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """List audit events from MongoDB with comprehensive filtering."""
    skip = (page - 1) * page_size
    events = await query_audit_logs(
        action=action, actor_id=actor_id,
        resource_type=resource_type, resource_id=resource_id,
        skip=skip, limit=page_size,
        date_from=date_from, date_to=date_to,
    )

    # Serialize datetime objects
    def _serialize(e: dict) -> dict:
        for k, v in e.items():
            if isinstance(v, datetime):
                e[k] = v.isoformat()
        return e

    return {
        "items": [_serialize(e) for e in events],
        "page": page,
        "page_size": page_size,
        "note": "Audit trail is append-only. Events cannot be modified or deleted.",
    }


@router.get("/actions")
async def list_action_types(
    current_user: CurrentUser,
) -> dict:
    """Return the list of all known action types in the audit log."""
    return {
        "actions": [
            "LOGIN", "LOGOUT", "LOGIN_FAILED",
            "CREATE_LAND_RECORD", "UPDATE_LAND_RECORD", "DELETE_LAND_RECORD",
            "VERIFY_LAND_RECORD", "SUBMIT_REVIEW",
            "UPLOAD_DOCUMENT", "VALIDATE_DOCUMENT",
            "PIPELINE_TRIGGER", "PIPELINE_COMPLETE",
            "FIELD_VERIFIED",
            "ADD_MUTATION", "ADD_REGISTRATION",
            "SET_COORDINATES", "SEED_GIS",
            "RUN_VALIDATION", "CREATE_RULE", "UPDATE_RULE",
            "CREATE_USER", "UPDATE_USER", "DELETE_USER",
        ]
    }
