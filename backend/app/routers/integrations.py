"""
Integrations Router — Manage and test external system adapters.

Endpoints:
  GET  /integrations              — list all adapter statuses
  POST /integrations/{name}/test  — test connection to an adapter
  POST /integrations/{name}/fetch-record — fetch a record from external system
  POST /integrations/{name}/push-record  — push a record to external system
  GET  /integrations/dilrmp/mutation/{mutation_number} — check mutation status
  GET  /integrations/bhuvan/geocode — reverse geocode coordinates
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.dependencies import AdminUser, CurrentUser, OfficerUser
from app.services.integration_adapters import ADAPTER_REGISTRY, get_adapter
from app.services.audit_service import log_event

router = APIRouter(prefix="/integrations", tags=["Integrations"])


class FetchRecordRequest(BaseModel):
    khasra_number: str
    district: str
    state: str
    config: Optional[dict] = None


class PushRecordRequest(BaseModel):
    record_id: str
    record_data: dict
    config: Optional[dict] = None


# ── List adapters ─────────────────────────────────────────────────────────────

@router.get("")
async def list_integrations(current_user: CurrentUser) -> dict:
    """List all available integration adapters and their status."""
    adapters = []
    for name, cls in ADAPTER_REGISTRY.items():
        adapter = cls()
        result = await adapter.test_connection()
        adapters.append({
            "name": name,
            "version": cls.VERSION,
            "mock_mode": cls.MOCK_MODE,
            "status": "ok" if result.success else "error",
            "message": result.data.get("message") or result.error,
            "description": cls.__doc__.strip().split('\n')[0] if cls.__doc__ else "",
        })
    return {
        "adapters": adapters,
        "total": len(adapters),
        "disclaimer": "All adapters are in MOCK mode. Configure env vars for live integration.",
    }


# ── Test connection ───────────────────────────────────────────────────────────

@router.post("/{adapter_name}/test")
async def test_adapter(
    adapter_name: str,
    config: Optional[dict] = None,
    *,
    current_user: AdminUser,
) -> dict:
    """Test connectivity to an external integration."""
    try:
        adapter = get_adapter(adapter_name, config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    result = await adapter.test_connection()
    await log_event("TEST_INTEGRATION", current_user.id, "Integration", None, {"adapter": adapter_name})
    return result.to_dict()


# ── Fetch record ──────────────────────────────────────────────────────────────

@router.post("/{adapter_name}/fetch-record")
async def fetch_record(
    adapter_name: str,
    body: FetchRecordRequest,
    current_user: OfficerUser,
) -> dict:
    """Fetch a land record from an external system."""
    try:
        adapter = get_adapter(adapter_name, body.config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    fn = getattr(adapter, "fetch_record", None) or getattr(adapter, "query_record", None)
    if fn is None:
        raise HTTPException(status_code=400, detail=f"Adapter '{adapter_name}' does not support record fetching")
    result = await fn(body.khasra_number, body.district)
    await log_event("FETCH_EXTERNAL_RECORD", current_user.id, "Integration", None,
                    {"adapter": adapter_name, "khasra": body.khasra_number})
    return result.to_dict()


# ── Push record ───────────────────────────────────────────────────────────────

@router.post("/dilrmp/push-record")
async def push_record_to_dilrmp(
    body: PushRecordRequest,
    current_user: OfficerUser,
) -> dict:
    """Push a verified record to the DILRMP national registry."""
    from app.services.integration_adapters import DilrmpAdapter
    adapter = DilrmpAdapter()
    result = await adapter.push_record(body.record_id, body.record_data)
    await log_event("PUSH_DILRMP", current_user.id, "Integration", None,
                    {"record_id": body.record_id, "success": result.success})
    return result.to_dict()


# ── Mutation status ───────────────────────────────────────────────────────────

@router.get("/dilrmp/mutation/{mutation_number}")
async def check_mutation_status(
    mutation_number: str,
    current_user: CurrentUser,
) -> dict:
    from app.services.integration_adapters import DilrmpAdapter
    adapter = DilrmpAdapter()
    result = await adapter.get_mutation_status(mutation_number)
    return result.to_dict()


# ── Bhuvan reverse geocode ────────────────────────────────────────────────────

@router.get("/bhuvan/geocode")
async def bhuvan_reverse_geocode(
    lat: float,
    lng: float,
    current_user: CurrentUser,
) -> dict:
    from app.services.integration_adapters import BhuvanAdapter
    adapter = BhuvanAdapter()
    result = await adapter.reverse_geocode(lat, lng)
    return result.to_dict()
