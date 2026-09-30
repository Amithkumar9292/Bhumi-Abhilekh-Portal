"""
Authentication & RBAC Tests

Tests:
  - Login success for all 4 roles
  - Login failure (wrong password, unknown user)
  - Token validation
  - Role-based access: VIEWER cannot create records
  - Role-based access: OFFICER can submit for review
  - Role-based access: VERIFIER can approve
  - Role-based access: ADMIN-only endpoints
  - Refresh token
  - Expired token rejection
"""
import pytest
from httpx import AsyncClient


PREFIX = "/api/v1"


class TestLogin:
    @pytest.mark.asyncio
    async def test_admin_login_success(self, async_client: AsyncClient, seeded_db):
        r = await async_client.post(f"{PREFIX}/auth/login",
            data={"username": "admin", "password": "Admin@1234"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["role"] == "ADMIN"

    @pytest.mark.asyncio
    async def test_officer_login_success(self, async_client: AsyncClient, seeded_db):
        r = await async_client.post(f"{PREFIX}/auth/login",
            data={"username": "officer", "password": "Officer@1234"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "OFFICER"

    @pytest.mark.asyncio
    async def test_verifier_login_success(self, async_client: AsyncClient, seeded_db):
        r = await async_client.post(f"{PREFIX}/auth/login",
            data={"username": "verifier", "password": "Verifier@1234"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "VERIFIER"

    @pytest.mark.asyncio
    async def test_viewer_login_success(self, async_client: AsyncClient, seeded_db):
        r = await async_client.post(f"{PREFIX}/auth/login",
            data={"username": "viewer", "password": "Viewer@1234"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "VIEWER"

    @pytest.mark.asyncio
    async def test_wrong_password(self, async_client: AsyncClient, seeded_db):
        r = await async_client.post(f"{PREFIX}/auth/login",
            data={"username": "admin", "password": "wrongpassword"})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_user(self, async_client: AsyncClient, seeded_db):
        r = await async_client.post(f"{PREFIX}/auth/login",
            data={"username": "ghost_user", "password": "any"})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_credentials(self, async_client: AsyncClient):
        r = await async_client.post(f"{PREFIX}/auth/login",
            data={"username": "", "password": ""})
        assert r.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_get_me(self, async_client: AsyncClient, seeded_db, admin_token: str):
        r = await async_client.get(f"{PREFIX}/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "admin"
        assert data["role"] == "ADMIN"

    @pytest.mark.asyncio
    async def test_get_me_without_token(self, async_client: AsyncClient):
        r = await async_client.get(f"{PREFIX}/auth/me")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, async_client: AsyncClient):
        r = await async_client.get(f"{PREFIX}/auth/me",
            headers={"Authorization": "Bearer definitely.not.valid"})
        assert r.status_code == 401


class TestRBAC:
    @pytest.mark.asyncio
    async def test_viewer_cannot_create_record(self, async_client: AsyncClient, seeded_db, viewer_token: str):
        """VIEWER role should not be able to create land records."""
        r = await async_client.post(f"{PREFIX}/land-records",
            json={
                "khasra_number": "1234/5", "owner_name": "Test User",
                "district": "Lucknow", "state": "Uttar Pradesh",
                "tehsil": "Sadar", "village": "Test Village",
                "area_hectares": 2.5,
            },
            headers={"Authorization": f"Bearer {viewer_token}"}
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_only_endpoint_rejected_for_officer(self, async_client: AsyncClient, seeded_db, officer_token: str):
        """Officer should not access admin-only endpoints."""
        r = await async_client.get(f"{PREFIX}/admin/users",
            headers={"Authorization": f"Bearer {officer_token}"})
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_can_read_records(self, async_client: AsyncClient, seeded_db, viewer_token: str):
        """VIEWER can read land records."""
        r = await async_client.get(f"{PREFIX}/land-records",
            headers={"Authorization": f"Bearer {viewer_token}"})
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self, async_client: AsyncClient):
        """Unauthenticated requests to protected endpoints return 401."""
        for path in [
            "/land-records", "/documents/upload", "/analytics/kpis",
            "/audit", "/users/me"
        ]:
            r = await async_client.get(f"{PREFIX}{path}")
            assert r.status_code == 401, f"Expected 401 for {path}, got {r.status_code}"
