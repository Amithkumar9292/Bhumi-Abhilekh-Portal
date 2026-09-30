"""
GIS Service Unit Tests
"""
import pytest
from app.services.gis_service import (
    generate_synthetic_centroid, generate_parcel_polygon,
    generate_gis_data, haversine_km, bbox_from_center,
)


class TestSyntheticCoordinates:
    def test_centroid_within_india(self):
        lat, lng = generate_synthetic_centroid("Uttar Pradesh", "Lucknow")
        assert 8 <= lat <= 37, f"lat {lat} outside India bounds"
        assert 68 <= lng <= 97, f"lng {lng} outside India bounds"

    def test_centroid_deterministic(self):
        """Same seed → same coordinates."""
        lat1, lng1 = generate_synthetic_centroid("Rajasthan", "Jaipur", seed="KH-1234")
        lat2, lng2 = generate_synthetic_centroid("Rajasthan", "Jaipur", seed="KH-1234")
        assert lat1 == lat2
        assert lng1 == lng2

    def test_centroid_different_seeds_differ(self):
        lat1, lng1 = generate_synthetic_centroid("UP", "Agra", seed="SEED-A")
        lat2, lng2 = generate_synthetic_centroid("UP", "Agra", seed="SEED-B")
        assert (lat1, lng1) != (lat2, lng2)

    def test_up_centroid_in_up_bounds(self):
        lat, lng = generate_synthetic_centroid("Uttar Pradesh", "Varanasi")
        # UP bounds: lat 23.87–30.42, lng 77.09–84.64
        assert 23.5 <= lat <= 31.0
        assert 76.5 <= lng <= 85.5

    def test_unknown_state_uses_default(self):
        lat, lng = generate_synthetic_centroid("Atlantis", "Nowhere")
        assert 18 <= lat <= 30
        assert 71 <= lng <= 86


class TestParcelPolygon:
    def test_polygon_is_valid_geojson(self):
        polygon = generate_parcel_polygon(26.85, 80.95, 2.5)
        assert polygon["type"] == "Feature"
        assert polygon["geometry"]["type"] == "Polygon"
        coords = polygon["geometry"]["coordinates"][0]
        assert len(coords) >= 4  # at least 3 vertices + closing point
        assert coords[0] == coords[-1]  # closed ring

    def test_polygon_closes(self):
        polygon = generate_parcel_polygon(20.0, 75.0, 1.0, sides=6)
        ring = polygon["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]

    def test_small_area_small_polygon(self):
        poly_small = generate_parcel_polygon(26.85, 80.95, 0.1)
        poly_large = generate_parcel_polygon(26.85, 80.95, 100.0)
        # Large area polygon should have wider spread
        small_coords = poly_small["geometry"]["coordinates"][0]
        large_coords = poly_large["geometry"]["coordinates"][0]
        small_spread = max(c[0] for c in small_coords) - min(c[0] for c in small_coords)
        large_spread = max(c[0] for c in large_coords) - min(c[0] for c in large_coords)
        assert large_spread > small_spread


class TestGisData:
    def test_generate_gis_data_structure(self):
        data = generate_gis_data("test-id", "Maharashtra", "Pune", "KH-999", 5.0)
        assert "latitude" in data
        assert "longitude" in data
        assert "geojson" in data
        assert data["source"] == "Synthetic"
        assert data["datum"] == "WGS84"
        assert data["coordinate_type"] == "CENTROID"

    def test_coordinates_in_valid_range(self):
        data = generate_gis_data("id", "Karnataka", "Bangalore", "SRV-123", 3.0)
        assert -90 <= data["latitude"] <= 90
        assert -180 <= data["longitude"] <= 180


class TestSpatialMath:
    def test_haversine_known_distance(self):
        # Delhi to Mumbai is approximately 1150 km
        delhi_lat, delhi_lng = 28.6139, 77.2090
        mumbai_lat, mumbai_lng = 19.0760, 72.8777
        dist = haversine_km(delhi_lat, delhi_lng, mumbai_lat, mumbai_lng)
        assert 1100 <= dist <= 1200, f"Distance {dist} km not in expected range"

    def test_haversine_same_point(self):
        dist = haversine_km(26.85, 80.95, 26.85, 80.95)
        assert dist == pytest.approx(0, abs=0.001)

    def test_bbox_from_center(self):
        lat, lng, r = 26.85, 80.95, 10.0
        lat_min, lat_max, lng_min, lng_max = bbox_from_center(lat, lng, r)
        assert lat_min < lat < lat_max
        assert lng_min < lng < lng_max
        # Roughly 10km / 111km per degree ≈ 0.09 degrees
        assert abs((lat_max - lat) - (10 / 111)) < 0.05
