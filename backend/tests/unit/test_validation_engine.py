"""
Validation Engine Unit Tests

Tests:
  - Individual rule evaluation
  - Required fields detection
  - Area range checks
  - Khasra format validation
  - Duplicate detection (cross-record)
  - ValidationReport structure
  - Rule persistence
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.validation_engine import (
    ValidationEngine, RULE_REGISTRY,
)
from app.models.land_record import LandRecord, LandUseType, RecordStatus


def make_record(**kwargs) -> LandRecord:
    """Create a minimal valid LandRecord for testing."""
    defaults = dict(
        id=uuid.uuid4(),
        khasra_number="1234/5",
        khatauni_number="KH-12345",
        survey_number="SRV-001",
        state="Uttar Pradesh",
        district="Lucknow",
        tehsil="Sadar",
        village="Test Village",
        pin_code="226001",
        area_hectares=2.5,
        land_use_type=LandUseType.AGRICULTURAL,
        owner_name="Ram Prasad Verma",
        status=RecordStatus.PENDING,
    )
    defaults.update(kwargs)
    r = LandRecord(**defaults)
    return r


def make_mock_db(scalar_return=0):
    """Return a minimal async mock DB that returns scalar_return for count queries."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar.return_value = scalar_return
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result
    return db


class TestVR001RequiredFields:
    @pytest.mark.asyncio
    async def test_all_required_present(self):
        record = make_record()
        db = make_mock_db()
        result = await RULE_REGISTRY["VR001"](record, db, {})
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_missing_khasra(self):
        record = make_record(khasra_number=None)
        db = make_mock_db()
        result = await RULE_REGISTRY["VR001"](record, db, {})
        assert result.passed is False
        assert result.severity == "ERROR"
        assert "khasra_number" in result.field_name

    @pytest.mark.asyncio
    async def test_missing_owner_name(self):
        record = make_record(owner_name="")
        db = make_mock_db()
        result = await RULE_REGISTRY["VR001"](record, db, {})
        assert result.passed is False
        assert "owner_name" in result.field_name

    @pytest.mark.asyncio
    async def test_missing_district(self):
        record = make_record(district=None)
        db = make_mock_db()
        result = await RULE_REGISTRY["VR001"](record, db, {})
        assert result.passed is False


class TestVR002AreaRange:
    @pytest.mark.asyncio
    async def test_valid_area(self):
        record = make_record(area_hectares=5.0)
        db = make_mock_db()
        result = await RULE_REGISTRY["VR002"](record, db, {})
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_zero_area(self):
        record = make_record(area_hectares=0)
        db = make_mock_db()
        result = await RULE_REGISTRY["VR002"](record, db, {})
        assert result.passed is False
        assert result.severity == "ERROR"

    @pytest.mark.asyncio
    async def test_negative_area(self):
        record = make_record(area_hectares=-1.5)
        db = make_mock_db()
        result = await RULE_REGISTRY["VR002"](record, db, {})
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_very_small_area_warning(self):
        record = make_record(area_hectares=0.0001)
        db = make_mock_db()
        result = await RULE_REGISTRY["VR002"](record, db, {"min_area": 0.001})
        assert result.passed is False
        assert result.severity == "WARNING"

    @pytest.mark.asyncio
    async def test_oversized_area(self):
        record = make_record(area_hectares=10000.0)
        db = make_mock_db()
        result = await RULE_REGISTRY["VR002"](record, db, {"max_area": 5000.0})
        assert result.passed is False
        assert result.severity == "ERROR"

    @pytest.mark.asyncio
    async def test_custom_max(self):
        record = make_record(area_hectares=100.0)
        db = make_mock_db()
        result = await RULE_REGISTRY["VR002"](record, db, {"max_area": 50.0})
        assert result.passed is False


class TestVR003KhasraFormat:
    @pytest.mark.asyncio
    async def test_valid_khasra(self):
        for khasra in ["1234/5", "ABC-123", "KH001", "999/99"]:
            record = make_record(khasra_number=khasra)
            db = make_mock_db()
            result = await RULE_REGISTRY["VR003"](record, db, {})
            assert result.passed is True, f"Expected {khasra} to pass"

    @pytest.mark.asyncio
    async def test_invalid_khasra_special_chars(self):
        record = make_record(khasra_number="@#$%!")
        db = make_mock_db()
        result = await RULE_REGISTRY["VR003"](record, db, {})
        assert result.passed is False


class TestVR006OwnerName:
    @pytest.mark.asyncio
    async def test_valid_name(self):
        record = make_record(owner_name="Ram Prasad Verma")
        result = await RULE_REGISTRY["VR006"](record, make_mock_db(), {})
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_too_short(self):
        record = make_record(owner_name="AB")
        result = await RULE_REGISTRY["VR006"](record, make_mock_db(), {})
        assert result.passed is False
        assert result.severity == "ERROR"

    @pytest.mark.asyncio
    async def test_numeric_string(self):
        record = make_record(owner_name="1234567890 Test")
        result = await RULE_REGISTRY["VR006"](record, make_mock_db(), {})
        assert result.passed is False


class TestVR008DuplicateKhasra:
    @pytest.mark.asyncio
    async def test_no_duplicate(self):
        record = make_record(khasra_number="UNIQUE-001")
        db = make_mock_db(scalar_return=0)
        result = await RULE_REGISTRY["VR008"](record, db, {})
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_duplicate_found(self):
        record = make_record(khasra_number="DUPE-999")
        db = make_mock_db(scalar_return=2)  # 2 existing records with same khasra
        result = await RULE_REGISTRY["VR008"](record, db, {})
        assert result.passed is False
        assert result.severity == "ERROR"


class TestValidationEngine:
    @pytest.mark.asyncio
    async def test_engine_runs_all_rules(self):
        record = make_record()
        db = make_mock_db()
        engine = ValidationEngine()
        report = await engine.validate(record, db)
        assert report.record_id == record.id
        assert len(report.results) == len(RULE_REGISTRY)

    @pytest.mark.asyncio
    async def test_engine_report_passed_valid_record(self):
        record = make_record()
        db = make_mock_db(scalar_return=0)
        engine = ValidationEngine()
        report = await engine.validate(record, db)
        # Valid record should pass (errors == 0)
        assert report.error_count == 0
        assert report.passed is True

    @pytest.mark.asyncio
    async def test_engine_report_failed_invalid_record(self):
        record = make_record(khasra_number=None, owner_name="", area_hectares=0)
        db = make_mock_db(scalar_return=0)
        engine = ValidationEngine()
        report = await engine.validate(record, db)
        assert report.passed is False
        assert report.error_count > 0

    @pytest.mark.asyncio
    async def test_engine_custom_config(self):
        """Engine respects custom rule configs."""
        record = make_record(area_hectares=0.5)
        db = make_mock_db()
        engine = ValidationEngine({"VR002": {"min_area": 1.0, "max_area": 100.0}})
        report = await engine.validate(record, db, rule_codes=["VR002"])
        # Should warn because 0.5 < 1.0 (custom min)
        vr002 = next(r for r in report.results if r.rule_code == "VR002")
        assert vr002.passed is False

    @pytest.mark.asyncio
    async def test_engine_specific_rules_only(self):
        record = make_record()
        db = make_mock_db()
        engine = ValidationEngine()
        report = await engine.validate(record, db, rule_codes=["VR001", "VR002"])
        assert len(report.results) == 2
