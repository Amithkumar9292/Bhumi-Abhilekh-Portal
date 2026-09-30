"""
GIS Service — Synthetic coordinate generation and spatial operations.

Provides:
  - generate_synthetic_coordinates(): produce realistic Indian coordinates
  - extract_document_coordinates(): read coordinates off an uploaded scan
  - parcel_geojson(): construct GeoJSON polygon for a plot
  - bbox_search(): find records within a lat/lng bounding box
  - nearest_records(): find records near a point
  
All coordinates are SYNTHETIC for demo — clearly marked.
Real implementation: replace with DGPS/Bhuvan API integration.
"""
from __future__ import annotations

import math
import random
import re

# Indian state bounding boxes (lat_min, lat_max, lng_min, lng_max)
STATE_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "Uttar Pradesh":     (23.87, 30.42, 77.09, 84.64),
    "Madhya Pradesh":    (21.08, 26.87, 74.03, 82.81),
    "Rajasthan":         (23.07, 30.19, 69.48, 78.27),
    "Maharashtra":       (15.61, 22.03, 72.66, 80.89),
    "Gujarat":           (20.17, 24.72, 68.16, 74.47),
    "Karnataka":         (11.59, 18.44, 74.05, 78.59),
    "Tamil Nadu":        (8.07,  13.35, 76.23, 80.34),
    "West Bengal":       (21.63, 27.23, 85.83, 89.92),
    "Bihar":             (24.30, 27.52, 83.33, 88.18),
    "Andhra Pradesh":    (12.62, 19.92, 76.76, 84.76),
    "Telangana":         (15.85, 19.92, 77.22, 81.34),
    "Punjab":            (29.55, 32.50, 73.88, 76.93),
    "Haryana":           (27.65, 30.90, 74.48, 77.62),
    "Jharkhand":         (21.97, 25.33, 83.32, 87.97),
    "Odisha":            (17.78, 22.57, 81.38, 87.50),
    "Himachal Pradesh":  (30.38, 33.20, 75.58, 79.00),
    "Uttarakhand":       (28.43, 31.47, 77.57, 81.03),
    "Chhattisgarh":      (17.78, 24.10, 80.23, 84.42),
    "Assam":             (24.10, 28.21, 89.70, 96.02),
}

DEFAULT_BOUNDS = (20.0, 28.0, 73.0, 84.0)   # generic India bounds


def get_state_bounds(state: str) -> tuple[float, float, float, float]:
    for k, v in STATE_BOUNDS.items():
        if k.lower() in state.lower() or state.lower() in k.lower():
            return v
    return DEFAULT_BOUNDS


def generate_synthetic_centroid(state: str, district: str, seed: str | None = None) -> tuple[float, float]:
    """
    Generate a deterministic synthetic centroid for a land record.
    Uses the khasra_number as seed for reproducibility.
    """
    rng = random.Random(seed or district)
    lat_min, lat_max, lng_min, lng_max = get_state_bounds(state)
    lat = round(rng.uniform(lat_min, lat_max), 6)
    lng = round(rng.uniform(lng_min, lng_max), 6)
    return lat, lng


def generate_parcel_polygon(
    centroid_lat: float,
    centroid_lng: float,
    area_hectares: float,
    sides: int = 4,
    seed: str | None = None,
) -> dict:
    """
    Generate a synthetic polygon around a centroid.
    Area in hectares → approximate radius in degrees.
    Returns GeoJSON Polygon feature.
    """
    rng = random.Random(seed)
    # 1 degree lat ≈ 111 km; 1 ha ≈ 0.01 km² → radius ≈ sqrt(area*10000/π) meters
    radius_m = math.sqrt(area_hectares * 10_000 / math.pi)
    radius_lat = radius_m / 111_000
    radius_lng = radius_m / (111_000 * math.cos(math.radians(centroid_lat)))

    # Generate irregular polygon
    coords = []
    angle_step = 2 * math.pi / sides
    for i in range(sides):
        angle = i * angle_step + rng.uniform(-angle_step * 0.3, angle_step * 0.3)
        r_lat = radius_lat * rng.uniform(0.7, 1.3)
        r_lng = radius_lng * rng.uniform(0.7, 1.3)
        lat = round(centroid_lat + r_lat * math.sin(angle), 7)
        lng = round(centroid_lng + r_lng * math.cos(angle), 7)
        coords.append([lng, lat])

    # Close the polygon
    coords.append(coords[0])

    return {
        "type": "Feature",
        "properties": {
            "area_hectares": area_hectares,
            "source": "Synthetic — Demo Only",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [coords],
        },
    }


def generate_gis_data(
    land_record_id: str,
    state: str,
    district: str,
    khasra_number: str,
    area_hectares: float,
) -> dict:
    """
    Generate complete GIS data for a land record.
    Returns dict suitable for GISCoordinate model.
    """
    seed = f"{khasra_number}-{district}"
    lat, lng = generate_synthetic_centroid(state, district, seed)
    polygon = generate_parcel_polygon(lat, lng, area_hectares, sides=4, seed=seed)

    return {
        "land_record_id": land_record_id,
        "latitude": lat,
        "longitude": lng,
        "geojson": polygon,
        "coordinate_type": "CENTROID",
        "accuracy_meters": None,
        "source": "Synthetic",
        "datum": "WGS84",
    }


# ── Coordinates read off an uploaded document ────────────────────────────────
#
# Scans of khasra/khatauni papers often print a survey coordinate, but OCR of
# those lines is unreliable, so a coordinate is only accepted when it is
# *labelled* and lands inside India's landmass. Anything looser happily reads a
# PIN code, a plot area or a page number as a location and pins the parcel in
# the middle of the Arabian Sea.

# India envelope, with slack for border districts.
INDIA_LAT_RANGE = (6.0, 37.5)
INDIA_LNG_RANGE = (68.0, 98.0)

_LAT_LABEL = r"(?:latitude|lat\b|y\s*coord(?:inate)?)"
_LNG_LABEL = r"(?:longitude|long\b|lng|lon|longit(?:ude)?\b|x\s*coord(?:inate)?)"

# The value of a labelled coordinate. Every alternative is *self-delimiting*
# and they are tried longest-form first, because an alternation like
# `(\d+)|(\d+°\d+'\d")` lets the short branch win and the rest of the token is
# silently dropped -- "26°50'48\"N" then reads as the whole degree 26.0 and the
# parcel lands 55 km from the survey mark.
_DECIMAL = r"(-?\d{1,3}(?:\.\d+)?)"
# 26°50'48"N, 26°50'48, 26.5°N, N 26.8467
_DMS_SYMBOLIC = (
    r"(?:[NSEW]\s*)?(-?\d{1,3})\s*[°º]\s*(\d{1,2})\s*['′]?\s*"
    r"(\d{1,2}(?:\.\d+)?)?\s*[\"″]?\s*([NSEW])?"
)
# 26 50 48 N -- OCR often drops the degree/minute symbols
_DMS_SPACED = r"(-?\d{1,3})\s+(\d{1,2})\s+(\d{1,2}(?:\.\d+)?)?\s*([NSEW])?"

_DMS_FORMS = (_DMS_SYMBOLIC, _DMS_SPACED)
_COORD_VALUE = rf"({_DMS_SYMBOLIC}|{_DMS_SPACED}|{_DECIMAL})"

_LAT_RE = re.compile(rf"{_LAT_LABEL}\s*[:=\-–]?\s*{_COORD_VALUE}", re.IGNORECASE)
_LNG_RE = re.compile(rf"{_LNG_LABEL}\s*[:=\-–]?\s*{_COORD_VALUE}", re.IGNORECASE)
# A coordinate pair written without labels, e.g. "26.8467, 80.9467".
_PAIR_RE = re.compile(
    r"(?<![\d.])(\d{1,2}\.\d{3,})\s*[,/]?\s*(\d{1,3}\.\d{3,})(?![\d.])"
)


def _dms_to_decimal(value: str) -> float | None:
    """Convert one captured coordinate token to signed decimal degrees."""
    text = value.strip()
    if not text:
        return None

    decimal = re.fullmatch(_DECIMAL, text)
    if decimal:
        return float(text)

    for form in _DMS_FORMS:
        dms = re.fullmatch(form, text, re.IGNORECASE)
        if not dms:
            continue
        degrees = float(dms.group(1))
        minutes = float(dms.group(2) or 0)
        seconds = float(dms.group(3) or 0)
        if minutes >= 60 or seconds >= 60:
            return None
        value_dec = degrees + minutes / 60 + seconds / 3600
        hemisphere = (dms.group(4) or "").upper()
        if hemisphere in ("S", "W"):
            return -value_dec
        # "N"/"E" needs no sign flip; with no hemisphere at all a negative sign
        # already carries the direction.
        return value_dec
    return None


def _in_india(value: float | None, low: float, high: float) -> bool:
    return value is not None and low <= value <= high


def extract_document_coordinates(text: str) -> tuple[float, float] | None:
    """
    Read a (latitude, longitude) pair out of a document's OCR text.

    Returns None when the document carries no usable coordinate. The caller is
    expected to fall back to a derived position, so a miss is normal and must
    never raise.
    """
    if not text:
        return None

    lat = lng = None
    lat_match = _LAT_RE.search(text)
    if lat_match:
        lat = _dms_to_decimal(lat_match.group(1))
    lng_match = _LNG_RE.search(text)
    if lng_match:
        lng = _dms_to_decimal(lng_match.group(1))

    if not (_in_india(lat, *INDIA_LAT_RANGE) and _in_india(lng, *INDIA_LNG_RANGE)):
        pair = _PAIR_RE.search(text)
        if pair:
            lat = float(pair.group(1))
            lng = float(pair.group(2))

    if not (_in_india(lat, *INDIA_LAT_RANGE) and _in_india(lng, *INDIA_LNG_RANGE)):
        return None
    return round(float(lat), 6), round(float(lng), 6)  # type: ignore[arg-type]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in km between two WGS-84 points."""
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lng2 - lng1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bbox_from_center(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return (lat_min, lat_max, lng_min, lng_max) for a radius around a point."""
    Δlat = radius_km / 111.0
    Δlng = radius_km / (111.0 * math.cos(math.radians(lat)))
    return (lat - Δlat, lat + Δlat, lng - Δlng, lng + Δlng)
