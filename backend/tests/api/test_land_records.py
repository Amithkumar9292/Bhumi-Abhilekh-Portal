"""
Land Records API Tests

Tests:
  - CRUD operations on land records
  - Pagination and filtering
  - Status transitions
  - Full-text search
"""
import pytest
import uuid
from httpx import AsyncClient

PREFIX = "/api/v1"

VALID_RECORD = {
    "khasra_number": "TEST-001",
    "survey_number": "SRV-001",
    "khatauni_number": "KH-001",
    "state": "Uttar Pradesh",
    "district": "Lucknow",
    "tehsil": "Sadar",
    "village": "Test Village",
    "pin_code": "226001",
    "area_hectares": 2.5,
    "land_use_type": "AGRICULTURAL",
    "owner_name": "Ram Prasad Verma",
    "father_name": "Shiv Prasad Verma",
    "address": "Village Test, District Lucknow",
    "aadhaar_last4": "1234",
}


class TestLandRecordsCRUD:
    @pytest.mark.asyncio
    async def test_list_records_authenticated(self, async_client: AsyncClient, officer_token: str, seeded_db):
        r = await async_client.get(f"{PREFIX}/land-records",
            headers={"Authorization": f"Bearer {officer_token}"})
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_create_record_as_officer(self, async_client: AsyncClient, officer_token: str, seeded_db):
        r = await async_client.post(f"{PREFIX}/land-records",
            json=VALID_RECORD,
            headers={"Authorization": f"Bearer {officer_token}"})
        assert r.status_code == 201
        data = r.json()
        assert "id" in data
        assert data["khasra_number"] == "TEST-001"
        return data["id"]

    @pytest.mark.asyncio
    async def test_create_record_missing_required_fields(self, async_client: AsyncClient, officer_token: str, seeded_db):
        r = await async_client.post(f"{PREFIX}/land-records",
            json={"khasra_number": "INCOMPLETE"},  # missing required fields
            headers={"Authorization": f"Bearer {officer_token}"})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_get_record_not_found(self, async_client: AsyncClient, viewer_token: str, seeded_db):
        fake_id = str(uuid.uuid4())
        r = await async_client.get(f"{PREFIX}/land-records/{fake_id}",
            headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_pagination(self, async_client: AsyncClient, viewer_token: str, seeded_db):
        r = await async_client.get(f"{PREFIX}/land-records?page=1&page_size=5",
            headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) <= 5

    @pytest.mark.asyncio
    async def test_filter_by_status(self, async_client: AsyncClient, viewer_token: str, seeded_db):
        r = await async_client.get(f"{PREFIX}/land-records?status=PENDING",
            headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_filter_by_district(self, async_client: AsyncClient, viewer_token: str, seeded_db):
        r = await async_client.get(f"{PREFIX}/land-records?district=Lucknow",
            headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_full_text_search(self, async_client: AsyncClient, viewer_token: str, seeded_db):
        r = await async_client.get(f"{PREFIX}/land-records/search?q=Lucknow",
            headers={"Authorization": f"Bearer {viewer_token}"})
        if r.status_code != 200:
            print(r.json())
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_update_record(self, async_client: AsyncClient, officer_token: str, seeded_db):
        # First create
        create_r = await async_client.post(f"{PREFIX}/land-records",
            json={**VALID_RECORD, "khasra_number": "UPDATE-TEST"},
            headers={"Authorization": f"Bearer {officer_token}"})
        assert create_r.status_code == 201
        record_id = create_r.json()["id"]

        # Update area
        update_r = await async_client.put(f"{PREFIX}/land-records/{record_id}",
            json={"area_hectares": 3.7},
            headers={"Authorization": f"Bearer {officer_token}"})
        assert update_r.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_requires_admin(self, async_client: AsyncClient, officer_token: str, seeded_db):
        """OFFICER cannot delete records — admin only."""
        fake_id = str(uuid.uuid4())
        r = await async_client.delete(f"{PREFIX}/land-records/{fake_id}",
            headers={"Authorization": f"Bearer {officer_token}"})
        assert r.status_code in (403, 404)
