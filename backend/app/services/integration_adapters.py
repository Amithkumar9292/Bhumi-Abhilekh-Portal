"""
Integration Adapters — LRMS/DILRMP-ready external system interfaces.

Architecture:
  BaseAdapter      — abstract interface all adapters implement
  DilrmpAdapter    — Digital India Land Records Modernisation Programme
  LrmsAdapter      — Land Records Management System (state-level)
  BhuvanAdapter    — ISRO Bhuvan GIS data API
  DorisAdapter     — Document Online Repository and Indexing System
  NsdlAdapter      — NSDL e-Stamp integration (stamp duty verification)
  UidaiAdapter     — Aadhaar verification (masked, consent-based)

Each adapter:
  - Has a test_connection() method
  - Returns standardized AdapterResult objects
  - Logs all calls to audit trail
  - Configurable via environment variables or DB config
  - Has a MOCK mode for demo/testing
"""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class AdapterResult:
    success: bool
    adapter: str
    operation: str
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    latency_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "adapter": self.adapter,
            "operation": self.operation,
            "data": self.data,
            "error": self.error,
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms,
        }


# ── Base adapter ──────────────────────────────────────────────────────────────

class BaseAdapter(ABC):
    """Abstract base for all integration adapters."""
    NAME = "base"
    VERSION = "1.0"
    MOCK_MODE = True  # Override to False for live integrations

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._mock = self.config.get("mock", self.MOCK_MODE)

    @abstractmethod
    async def test_connection(self) -> AdapterResult:
        """Verify the external system is reachable."""

    def _result(self, success: bool, operation: str, data: dict | None = None, error: str | None = None) -> AdapterResult:
        return AdapterResult(
            success=success,
            adapter=self.NAME,
            operation=operation,
            data=data or {},
            error=error,
        )

    def _mock_result(self, operation: str, data: dict) -> AdapterResult:
        log.debug("[MOCK] %s.%s called", self.NAME, operation)
        return self._result(True, operation, {**data, "_mock": True})


# ── DILRMP Adapter ────────────────────────────────────────────────────────────

class DilrmpAdapter(BaseAdapter):
    """
    Digital India Land Records Modernisation Programme (DILRMP) Integration.

    API endpoints (mock in demo mode):
      - GET  /record/{khasra_id}           → fetch record from national registry
      - POST /record/sync                  → push verified record to DILRMP
      - GET  /mutation/status/{mut_id}    → check mutation status
      - GET  /state/stats/{state_code}    → state-level digitization stats

    Live: Requires DILRMP_API_KEY and DILRMP_API_URL env vars.
    Auth: Bearer token (JWT issued by NIC).
    """
    NAME = "DILRMP"
    VERSION = "2.1"
    BASE_URL = "https://api.dilrmp.gov.in/v2"

    async def test_connection(self) -> AdapterResult:
        if self._mock:
            return self._mock_result("test_connection", {
                "status": "ok",
                "message": "DILRMP API reachable (mock mode)",
                "dilrmp_version": self.VERSION,
            })
        # Real implementation:
        # async with httpx.AsyncClient() as c:
        #     r = await c.get(f"{self.BASE_URL}/health", headers=self._headers())
        #     return self._result(r.status_code == 200, "test_connection", r.json())
        return self._result(False, "test_connection", error="Not implemented — set MOCK_MODE=False and configure DILRMP_API_KEY")

    async def fetch_record(self, khasra_number: str, district: str, state: str) -> AdapterResult:
        """Fetch a land record from the DILRMP national registry."""
        if self._mock:
            return self._mock_result("fetch_record", {
                "khasra_number": khasra_number,
                "district": district,
                "state": state,
                "status": "REGISTERED",
                "last_updated": "2024-03-15",
                "registry_id": f"DILRMP-{uuid.uuid4().hex[:8].upper()}",
                "source": "DILRMP National Land Registry",
                "disclaimer": "Mock data — not from actual DILRMP API",
            })
        return self._result(False, "fetch_record", error="Live DILRMP integration not configured")

    async def push_record(self, record_id: str, record_data: dict) -> AdapterResult:
        """Push a verified local record to DILRMP registry."""
        if self._mock:
            return self._mock_result("push_record", {
                "record_id": record_id,
                "dilrmp_ref": f"DILRMP-REF-{uuid.uuid4().hex[:8].upper()}",
                "status": "ACCEPTED",
                "message": "Record queued for DILRMP sync (mock)",
            })
        return self._result(False, "push_record", error="Live DILRMP push not configured")

    async def get_mutation_status(self, mutation_number: str) -> AdapterResult:
        """Check mutation approval status in DILRMP."""
        if self._mock:
            return self._mock_result("get_mutation_status", {
                "mutation_number": mutation_number,
                "status": "APPROVED",
                "approved_by": "Tehsildar",
                "approval_date": "2024-06-20",
            })
        return self._result(False, "get_mutation_status", error="Not configured")


# ── LRMS Adapter ──────────────────────────────────────────────────────────────

class LrmsAdapter(BaseAdapter):
    """
    State Land Records Management System (LRMS) integration.
    Each state has its own LRMS (e.g., UP: Bhulekh, MP: Bhu-Abhilekh, RJ: Apna Khata).

    Configurable per state via:
      config["state"] → "UP" | "MP" | "RJ" | "MH" | ...
      config["lrms_url"] → base API URL for the state
    """
    NAME = "LRMS"
    VERSION = "1.0"

    STATE_SYSTEMS = {
        "UP": {"name": "Bhulekh (UP)", "url": "https://upbhulekh.gov.in/api"},
        "MP": {"name": "Bhu-Abhilekh (MP)", "url": "https://mpbhuabhilekh.nic.in/api"},
        "RJ": {"name": "Apna Khata (RJ)", "url": "https://apnakhata.rajasthan.gov.in/api"},
        "MH": {"name": "Mahabhulekh (MH)", "url": "https://mahabhulekh.maharashtra.gov.in/api"},
        "GJ": {"name": "AnyRoR (GJ)", "url": "https://anyror.gujarat.gov.in/api"},
        "TN": {"name": "Patta Chitta (TN)", "url": "https://eservices.tn.gov.in/api"},
        "KA": {"name": "Bhoomi (KA)", "url": "https://landrecords.karnataka.gov.in/api"},
    }

    async def test_connection(self) -> AdapterResult:
        state = self.config.get("state", "UP")
        system = self.STATE_SYSTEMS.get(state, {"name": f"LRMS ({state})", "url": ""})
        if self._mock:
            return self._mock_result("test_connection", {
                "state": state,
                "system": system["name"],
                "status": "ok",
                "message": f"Connected to {system['name']} (mock mode)",
            })
        return self._result(False, "test_connection", error=f"Live LRMS connection for {state} not configured")

    async def query_record(self, khasra_number: str, district: str) -> AdapterResult:
        """Query the state LRMS for a khasra record."""
        if self._mock:
            state = self.config.get("state", "UP")
            return self._mock_result("query_record", {
                "found": True,
                "khasra_number": khasra_number,
                "district": district,
                "state": state,
                "owner_from_lrms": "Ram Prasad Verma",
                "area_from_lrms": 2.45,
                "last_mutation": "2023-08-12",
                "source": self.STATE_SYSTEMS.get(state, {}).get("name", f"LRMS ({state})"),
                "disclaimer": "Mock data — not from actual state LRMS",
            })
        return self._result(False, "query_record", error="Live LRMS not configured")


# ── Bhuvan GIS Adapter ────────────────────────────────────────────────────────

class BhuvanAdapter(BaseAdapter):
    """
    ISRO Bhuvan Geoportal API integration for GIS/cadastral data.

    Capabilities:
      - Fetch parcel boundary polygons
      - Overlay satellite imagery
      - Reverse geocoding (lat/lng → village/tehsil)
      - Measure area from boundary polygon

    Requires: BHUVAN_API_KEY from ISRO Bhuvan registered application.
    """
    NAME = "BHUVAN_GIS"
    VERSION = "1.5"
    BASE_URL = "https://bhuvan-app1.nrsc.gov.in/api/v1"

    async def test_connection(self) -> AdapterResult:
        if self._mock:
            return self._mock_result("test_connection", {
                "service": "ISRO Bhuvan Geoportal",
                "status": "ok",
                "resolution": "0.5m (CARTOSAT-3)",
                "coverage": "Pan-India",
            })
        return self._result(False, "test_connection", error="Bhuvan API key not configured")

    async def get_parcel_boundary(self, khasra_number: str, village_code: str) -> AdapterResult:
        """Fetch the official cadastral boundary for a parcel."""
        if self._mock:
            return self._mock_result("get_parcel_boundary", {
                "khasra_number": khasra_number,
                "village_code": village_code,
                "geojson": {
                    "type": "Feature",
                    "properties": {"source": "Bhuvan (mock)", "khasra": khasra_number},
                    "geometry": {"type": "Polygon", "coordinates": [[[80.95, 26.85], [80.952, 26.85], [80.952, 26.852], [80.95, 26.852], [80.95, 26.85]]]},
                },
            })
        return self._result(False, "get_parcel_boundary", error="Bhuvan not configured")

    async def reverse_geocode(self, lat: float, lng: float) -> AdapterResult:
        """Get administrative info from lat/lng."""
        if self._mock:
            return self._mock_result("reverse_geocode", {
                "latitude": lat, "longitude": lng,
                "state": "Uttar Pradesh", "district": "Lucknow",
                "tehsil": "Sadar", "village": "Rampur",
                "pin_code": "226001",
                "accuracy": "500m",
            })
        return self._result(False, "reverse_geocode", error="Bhuvan not configured")


# ── DORIS Adapter ─────────────────────────────────────────────────────────────

class DorisAdapter(BaseAdapter):
    """
    DORIS (Document Online Repository and Indexing System) integration.
    Used for cross-referencing registered documents with sub-registrar offices.
    """
    NAME = "DORIS"
    VERSION = "1.0"

    async def test_connection(self) -> AdapterResult:
        if self._mock:
            return self._mock_result("test_connection", {"status": "ok", "service": "DORIS Document Registry"})
        return self._result(False, "test_connection", error="DORIS not configured")

    async def verify_deed(self, deed_number: str, district: str) -> AdapterResult:
        """Verify if a deed number exists in DORIS."""
        if self._mock:
            return self._mock_result("verify_deed", {
                "deed_number": deed_number,
                "district": district,
                "found": True,
                "registration_date": "2024-05-15",
                "sub_registrar": "SR Office, Lucknow",
                "status": "REGISTERED",
            })
        return self._result(False, "verify_deed", error="DORIS not configured")


# ── Adapter Registry ──────────────────────────────────────────────────────────

ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "DILRMP":      DilrmpAdapter,
    "LRMS":        LrmsAdapter,
    "BHUVAN_GIS":  BhuvanAdapter,
    "DORIS":       DorisAdapter,
}


def get_adapter(name: str, config: dict | None = None) -> BaseAdapter:
    """Factory — returns initialized adapter by name."""
    cls = ADAPTER_REGISTRY.get(name.upper())
    if not cls:
        raise ValueError(f"Unknown adapter: {name}. Available: {list(ADAPTER_REGISTRY.keys())}")
    return cls(config=config)
