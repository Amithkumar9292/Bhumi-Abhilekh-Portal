"""The VALIDATION stage must not put unverified reads on a land record.

`_apply_to_land_record` fills the draft that intake created. A value that failed
its own validation rule, or that OCR read with low confidence, has to stay a
placeholder and reach a human through the verification queue instead.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.models.land_record import LandRecord, LandUseType, RecordStatus
from app.routers.intake import _DRAFT_PLACEHOLDER
from app.services.document_processor import _apply_to_land_record
from app.services.field_extractor import FieldResult

pytestmark = pytest.mark.asyncio


def _result(
    field_name: str,
    value: str | None,
    status: str = "AUTO_VALID",
    needs_review: bool = False,
    confidence: float = 0.8,
) -> FieldResult:
    return FieldResult(
        field_name=field_name,
        field_display=field_name,
        raw_value=value,
        normalized_value=value,
        confidence_score=confidence,
        ocr_confidence=0.9,
        extraction_method="regex",
        source_page=1,
        bounding_box=None,
        validation_status=status,
        validation_rule="test",
        validation_message=None,
        needs_review=needs_review,
    )


@pytest_asyncio.fixture
async def draft(seeded_db) -> LandRecord:
    record = LandRecord(
        id=uuid.uuid4(),
        khasra_number="TEST-DRAFT-1",
        state=_DRAFT_PLACEHOLDER,
        district=_DRAFT_PLACEHOLDER,
        tehsil=_DRAFT_PLACEHOLDER,
        village=_DRAFT_PLACEHOLDER,
        owner_name=_DRAFT_PLACEHOLDER,
        area_hectares=0.0001,
        land_use_type=LandUseType.AGRICULTURAL,
        status=RecordStatus.PENDING,
    )
    seeded_db.add(record)
    await seeded_db.flush()
    return record


@pytest_asyncio.fixture
async def job(draft) -> "object":
    class _Job:
        land_record_id = draft.id
    return _Job()


async def test_validated_values_are_written_to_the_draft(seeded_db, draft, job):
    results = [
        _result("owner_name", "Ramesh Prasad"),
        _result("village", "Rampur"),
        _result("district", "Lucknow"),
        _result("land_area", "2.45"),
    ]
    await _apply_to_land_record(job, results, seeded_db)

    await seeded_db.refresh(draft)
    assert draft.owner_name == "Ramesh Prasad"
    assert draft.village == "Rampur"
    assert draft.district == "Lucknow"
    assert draft.area_hectares == 2.45


async def test_record_key_is_never_rewritten_from_ocr(seeded_db, draft, job):
    """Intake keys the draft by the scanned Khasra number, so OCR must not
    replace the record's own identifier even with a valid-looking read."""
    await _apply_to_land_record(job, [_result("khasra_number", "KH-10142")], seeded_db)

    await seeded_db.refresh(draft)
    assert draft.khasra_number == "TEST-DRAFT-1"


async def test_rejected_read_is_not_written_to_the_draft(seeded_db, draft, job):
    """A failed validation rule must leave the placeholder in place."""
    results = [
        _result("khasra_number", "NAKAL", status="AUTO_INVALID", needs_review=True),
    ]
    await _apply_to_land_record(job, results, seeded_db)

    await seeded_db.refresh(draft)
    assert draft.khasra_number == "TEST-DRAFT-1"


async def test_low_confidence_read_is_not_written_to_the_draft(
    seeded_db, draft, job
):
    """needs_review is set below the confidence threshold; nothing gets written."""
    results = [
        _result("owner_name", "Ramesh Prasad", needs_review=True, confidence=0.43),
    ]
    await _apply_to_land_record(job, results, seeded_db)

    await seeded_db.refresh(draft)
    assert draft.owner_name == _DRAFT_PLACEHOLDER


async def test_missing_value_leaves_the_placeholder(seeded_db, draft, job):
    results = [_result("village", None, status="AUTO_INVALID", needs_review=True)]
    await _apply_to_land_record(job, results, seeded_db)

    await seeded_db.refresh(draft)
    assert draft.village == _DRAFT_PLACEHOLDER


async def test_existing_values_are_never_overwritten(seeded_db, draft, job):
    """A confirmed record must not be regressed by a later scan."""
    draft.owner_name = "Existing Owner"
    await seeded_db.flush()

    await _apply_to_land_record(job, [_result("owner_name", "Someone Else")], seeded_db)

    await seeded_db.refresh(draft)
    assert draft.owner_name == "Existing Owner"
