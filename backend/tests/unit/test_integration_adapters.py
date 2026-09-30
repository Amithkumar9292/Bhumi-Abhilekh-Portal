"""
Integration Adapter Tests

Tests all adapters in MOCK mode (no live API calls).
"""
import pytest
from app.services.integration_adapters import (
    DilrmpAdapter, LrmsAdapter, BhuvanAdapter, get_adapter, ADAPTER_REGISTRY, AdapterResult,
)


class TestAdapterRegistry:
    def test_all_adapters_registered(self):
        assert "DILRMP" in ADAPTER_REGISTRY
        assert "LRMS" in ADAPTER_REGISTRY
        assert "BHUVAN_GIS" in ADAPTER_REGISTRY
        assert "DORIS" in ADAPTER_REGISTRY

    def test_get_adapter_valid_name(self):
        adapter = get_adapter("DILRMP")
        assert isinstance(adapter, DilrmpAdapter)

    def test_get_adapter_case_insensitive(self):
        adapter = get_adapter("dilrmp")
        assert isinstance(adapter, DilrmpAdapter)

    def test_get_adapter_invalid_name(self):
        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("NONEXISTENT")


class TestDilrmpAdapter:
    @pytest.mark.asyncio
    async def test_test_connection_mock(self):
        adapter = DilrmpAdapter(config={"mock": True})
        result = await adapter.test_connection()
        assert isinstance(result, AdapterResult)
        assert result.success is True
        assert result.adapter == "DILRMP"
        assert result.data.get("_mock") is True

    @pytest.mark.asyncio
    async def test_fetch_record_mock(self):
        adapter = DilrmpAdapter(config={"mock": True})
        result = await adapter.fetch_record("1234/5", "Lucknow", "Uttar Pradesh")
        assert result.success is True
        assert result.data["khasra_number"] == "1234/5"
        assert "registry_id" in result.data
        assert result.data["status"] == "REGISTERED"

    @pytest.mark.asyncio
    async def test_push_record_mock(self):
        adapter = DilrmpAdapter(config={"mock": True})
        result = await adapter.push_record("test-uuid", {"khasra_number": "1234/5"})
        assert result.success is True
        assert "dilrmp_ref" in result.data
        assert result.data["status"] == "ACCEPTED"

    @pytest.mark.asyncio
    async def test_mutation_status_mock(self):
        adapter = DilrmpAdapter(config={"mock": True})
        result = await adapter.get_mutation_status("MUT-2024-1234")
        assert result.success is True
        assert result.data["mutation_number"] == "MUT-2024-1234"


class TestLrmsAdapter:
    @pytest.mark.asyncio
    async def test_connection_mock(self):
        adapter = LrmsAdapter(config={"mock": True, "state": "UP"})
        result = await adapter.test_connection()
        assert result.success is True
        assert "Bhulekh" in result.data["system"]

    @pytest.mark.asyncio
    async def test_query_record_mock(self):
        adapter = LrmsAdapter(config={"mock": True, "state": "RJ"})
        result = await adapter.query_record("999/1", "Jaipur")
        assert result.success is True
        assert result.data["found"] is True
        assert "Apna Khata" in result.data["source"]

    @pytest.mark.asyncio
    async def test_all_state_systems(self):
        for state in LrmsAdapter.STATE_SYSTEMS:
            adapter = LrmsAdapter(config={"mock": True, "state": state})
            result = await adapter.test_connection()
            assert result.success is True, f"Failed for state {state}"


class TestBhuvanAdapter:
    @pytest.mark.asyncio
    async def test_connection_mock(self):
        adapter = BhuvanAdapter(config={"mock": True})
        result = await adapter.test_connection()
        assert result.success is True
        assert "Bhuvan" in result.data["service"]

    @pytest.mark.asyncio
    async def test_parcel_boundary_mock(self):
        adapter = BhuvanAdapter(config={"mock": True})
        result = await adapter.get_parcel_boundary("KH-123", "VL-456")
        assert result.success is True
        geo = result.data["geojson"]
        assert geo["geometry"]["type"] == "Polygon"

    @pytest.mark.asyncio
    async def test_reverse_geocode_mock(self):
        adapter = BhuvanAdapter(config={"mock": True})
        result = await adapter.reverse_geocode(26.85, 80.95)
        assert result.success is True
        assert result.data["state"] == "Uttar Pradesh"
        assert result.data["district"] == "Lucknow"


class TestAdapterResult:
    def test_result_to_dict(self):
        r = AdapterResult(success=True, adapter="TEST", operation="op", data={"key": "val"})
        d = r.to_dict()
        assert d["success"] is True
        assert d["adapter"] == "TEST"
        assert "request_id" in d
        assert "timestamp" in d
        assert d["data"]["key"] == "val"

    def test_result_has_request_id(self):
        r1 = AdapterResult(success=True, adapter="A", operation="test")
        r2 = AdapterResult(success=True, adapter="A", operation="test")
        assert r1.request_id != r2.request_id  # UUID should be unique
