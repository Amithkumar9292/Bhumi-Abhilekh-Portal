"""
GIS Router — Spatial data API.

Endpoints:
  GET  /gis/records                  — all records with coordinates (GeoJSON FeatureCollection)
  GET  /gis/record/{record_id}       — coordinates for one record
  POST /gis/record/{record_id}/coordinates — create/update GIS data for a record
  GET  /gis/search                   — search by lat/lng bbox or radius
  GET  /gis/parcel/{khasra}          — find parcel by khasra number
  POST /gis/seed                     — auto-generate synthetic coordinates for all records
  GET  /gis/states                   — list states with coordinate bounds
"""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.dependencies import AdminUser, CurrentUser, DBSession, OfficerUser
from app.models.document import Document
from app.models.extended import GISCoordinate, CoordinateType
from app.models.land_record import LandRecord
from app.models.pipeline import ProcessingJob
from app.services.gis_service import (
    generate_gis_data, haversine_km, bbox_from_center, STATE_BOUNDS,
    generate_parcel_polygon,
)
from app.services.audit_service import log_event

router = APIRouter(prefix="/gis", tags=["GIS / Spatial"])


class CoordinateCreate(BaseModel):
    latitude: float
    longitude: float
    altitude_m: Optional[float] = None
    coordinate_type: str = "CENTROID"
    accuracy_meters: Optional[float] = None
    source: str = "Manual"


# ── GeoJSON for all records ───────────────────────────────────────────────────

@router.get("/records")
async def get_all_gis_records(
    state: Optional[str] = None,
    district: Optional[str] = None,
    land_use: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Return a GeoJSON FeatureCollection of all land records with coordinates.
    Filters: state, district, land_use_type.
    """
    # Join land_records → gis_coordinates
    q = (
        select(LandRecord, GISCoordinate)
        .join(GISCoordinate, GISCoordinate.land_record_id == LandRecord.id)
        .where(GISCoordinate.coordinate_type == CoordinateType.CENTROID)
    )
    if state:
        q = q.where(LandRecord.state.ilike(f"%{state}%"))
    if district:
        q = q.where(LandRecord.district.ilike(f"%{district}%"))
    if land_use:
        q = q.where(LandRecord.land_use_type == land_use)
    q = q.limit(limit)

    result = await db.execute(q)
    rows = result.all()

    sources = await _uploaded_document_by_record(
        db, [record.id for record, _ in rows]
    )

    features = []
    for record, coord in rows:
        geom = coord.geojson.get("geometry") if coord.geojson else {
            "type": "Point",
            "coordinates": [coord.longitude, coord.latitude],
        }
        upload = sources.get(record.id)
        features.append({
            "type": "Feature",
            "id": str(record.id),
            "geometry": geom,
            "properties": {
                "id": str(record.id),
                "khasra_number": record.khasra_number,
                "owner_name": record.owner_name,
                "district": record.district,
                "state": record.state,
                "village": record.village,
                "area_hectares": record.area_hectares,
                "land_use_type": record.land_use_type.value,
                "status": record.status.value,
                "latitude": coord.latitude,
                "longitude": coord.longitude,
                "source": coord.source,
                # An uploaded scan is what put this parcel on the map, so the
                # GIS view can label it as coming from a processed document.
                "from_upload": upload is not None,
                "document_id": upload["document_id"] if upload else None,
                "document_name": upload["document_name"] if upload else None,
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "total": len(features),
        "from_upload": sum(1 for f in features if f["properties"]["from_upload"]),
        "disclaimer": (
            "⚠ Coordinates are SYNTHETIC unless read from the document — demo use only"
        ),
    }


async def _uploaded_document_by_record(
    db: DBSession, record_ids: list[uuid.UUID]
) -> dict:
    """Newest uploaded document per land record, keyed by record id.

    Without this the map cannot tell a parcel that came in through intake from
    one that was seeded, which is exactly the distinction an operator needs when
    they ask why a scan is not visible.
    """
    if not record_ids:
        return {}
    result = await db.execute(
        select(
            ProcessingJob.land_record_id,
            Document.id,
            Document.original_filename,
        )
        .join(Document, Document.id == ProcessingJob.document_id)
        .where(ProcessingJob.land_record_id.in_(record_ids))
        .order_by(ProcessingJob.land_record_id, Document.created_at.desc())
    )
    newest: dict = {}
    for record_id, doc_id, filename in result.all():
        if record_id not in newest:
            newest[record_id] = {
                "document_id": str(doc_id),
                "document_name": filename,
            }
    return newest


# ── Single record coordinates ─────────────────────────────────────────────────

@router.get("/record/{record_id}")
async def get_record_coordinates(
    record_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")

    result = await db.execute(
        select(GISCoordinate).where(GISCoordinate.land_record_id == record_id)
    )
    coords = result.scalars().all()

    if not coords:
        # Auto-generate on demand
        gis_data = generate_gis_data(
            str(record.id), record.state, record.district,
            record.khasra_number, record.area_hectares,
        )
        coord = GISCoordinate(id=uuid.uuid4(), **gis_data)
        db.add(coord)
        await db.flush()
        coords = [coord]

    return {
        "record_id": str(record_id),
        "khasra_number": record.khasra_number,
        "coordinates": [
            {
                "id": str(c.id),
                "latitude": c.latitude,
                "longitude": c.longitude,
                "coordinate_type": c.coordinate_type.value,
                "geojson": c.geojson,
                "source": c.source,
                "accuracy_meters": c.accuracy_meters,
            }
            for c in coords
        ],
    }


# ── Create / update coordinates ───────────────────────────────────────────────

@router.post("/record/{record_id}/coordinates", status_code=201)
async def set_coordinates(
    record_id: uuid.UUID,
    body: CoordinateCreate,
    db: DBSession,
    current_user: OfficerUser,
) -> dict:
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")

    # Generate polygon around this centroid
    polygon = generate_parcel_polygon(
        body.latitude, body.longitude, record.area_hectares,
        seed=record.khasra_number
    )
    coord = GISCoordinate(
        id=uuid.uuid4(),
        land_record_id=record_id,
        latitude=body.latitude,
        longitude=body.longitude,
        altitude_m=body.altitude_m,
        geojson=polygon,
        coordinate_type=CoordinateType(body.coordinate_type),
        accuracy_meters=body.accuracy_meters,
        source=body.source,
        datum="WGS84",
        captured_by=current_user.id,
    )
    db.add(coord)
    await db.flush()
    await log_event("SET_COORDINATES", current_user.id, "GISCoordinate", coord.id,
                    {"land_record_id": str(record_id), "lat": body.latitude, "lng": body.longitude})
    return {"id": str(coord.id), "latitude": body.latitude, "longitude": body.longitude}


# ── Spatial search ────────────────────────────────────────────────────────────

@router.get("/search")
async def spatial_search(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(10.0, ge=0.1, le=500.0),
    limit: int = Query(50, ge=1, le=200),
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Find land records within radius_km of a point."""
    lat_min, lat_max, lng_min, lng_max = bbox_from_center(lat, lng, radius_km)

    q = (
        select(LandRecord, GISCoordinate)
        .join(GISCoordinate, GISCoordinate.land_record_id == LandRecord.id)
        .where(
            GISCoordinate.latitude.between(lat_min, lat_max),
            GISCoordinate.longitude.between(lng_min, lng_max),
        )
        .limit(limit * 2)  # over-fetch to filter by exact distance
    )
    result = await db.execute(q)
    rows = result.all()

    # Filter by exact haversine distance
    nearby = []
    for record, coord in rows:
        if coord.latitude and coord.longitude:
            dist = haversine_km(lat, lng, coord.latitude, coord.longitude)
            if dist <= radius_km:
                nearby.append({
                    "id": str(record.id),
                    "khasra_number": record.khasra_number,
                    "owner_name": record.owner_name,
                    "district": record.district,
                    "village": record.village,
                    "area_hectares": record.area_hectares,
                    "land_use_type": record.land_use_type.value,
                    "status": record.status.value,
                    "latitude": coord.latitude,
                    "longitude": coord.longitude,
                    "distance_km": round(dist, 3),
                })
    nearby.sort(key=lambda x: x["distance_km"])
    return {"center": {"lat": lat, "lng": lng}, "radius_km": radius_km, "results": nearby[:limit]}


# ── Parcel by khasra ──────────────────────────────────────────────────────────

@router.get("/parcel/{khasra}")
async def get_parcel_by_khasra(
    khasra: str,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    q = select(LandRecord, GISCoordinate).join(
        GISCoordinate, GISCoordinate.land_record_id == LandRecord.id
    ).where(LandRecord.khasra_number.ilike(khasra))
    result = await db.execute(q)
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No records found for khasra '{khasra}'")
    items = []
    for record, coord in rows:
        items.append({
            "record_id": str(record.id),
            "khasra_number": record.khasra_number,
            "geojson": coord.geojson,
            "latitude": coord.latitude,
            "longitude": coord.longitude,
        })
    return {"khasra": khasra, "parcels": items}


# ── Seed synthetic coordinates ────────────────────────────────────────────────

@router.post("/seed", status_code=202)
async def seed_gis_coordinates(
    db: DBSession,
    current_user: AdminUser,
) -> dict:
    """
    Auto-generate synthetic GIS coordinates for all land records
    that don't yet have coordinates. ADMIN only.
    """
    # Get records without coordinates
    subq = select(GISCoordinate.land_record_id)
    q = select(LandRecord).where(~LandRecord.id.in_(subq)).limit(500)
    result = await db.execute(q)
    records = result.scalars().all()

    count = 0
    for record in records:
        gis_data = generate_gis_data(
            str(record.id), record.state, record.district,
            record.khasra_number, record.area_hectares,
        )
        coord = GISCoordinate(id=uuid.uuid4(), **gis_data)
        db.add(coord)
        count += 1

    await db.flush()
    await log_event("SEED_GIS", current_user.id, "System", None, {"seeded": count})
    return {
        "message": f"Generated synthetic coordinates for {count} records",
        "disclaimer": "⚠ All coordinates are SYNTHETIC — demo only",
    }


# ── State bounds reference ────────────────────────────────────────────────────

@router.get("/states")
async def list_state_bounds(current_user: CurrentUser) -> dict:
    return {
        "states": [
            {"name": name, "bounds": {"lat_min": b[0], "lat_max": b[1], "lng_min": b[2], "lng_max": b[3]}}
            for name, b in STATE_BOUNDS.items()
        ]
    }
