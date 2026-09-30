"""
Re-running a job must replace its results, not add to them.

A job can be retried (see test_pipeline_retry), and the retry path re-derives
fields and anomalies from a fresh OCR pass. Both stages appended rows, so a
retried job ended up with two rows per field -- the stale value and the new one
-- which doubled every count the review UI and the analytics endpoints report.
Human-verified fields are the exception: a reviewer's decision outranks a fresh
machine reading, so those rows survive and are not re-inserted.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.land_record import LandRecord, LandUseType
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.pipeline import ExtractedField, PipelineAnomaly, ProcessingJob
from app.services.document_processor import _persist_anomalies, _persist_fields
from app.services.field_extractor import FieldExtractor
from app.services.ocr_service import OCRResult, TextBlock

RECORD = """Owner Name: Ramesh Kumar Naik
Khasra Number: 124/3A
Village: Brahmavara
District: Udupi
"""


def _ocr(text: str) -> OCRResult:
    return OCRResult(
        full_text=text,
        blocks=[TextBlock(text=ln.strip(), confidence=0.9, page=1) for ln in text.splitlines() if ln.strip()],
        page_count=1,
        detected_language="en",
        avg_confidence=0.9,
        backend_name="tesseract",
    )


def _results(text: str = RECORD):
    return FieldExtractor().extract(_ocr(text))


@pytest_asyncio.fixture
async def job(test_db: AsyncSession):
    record = LandRecord(
        id=uuid.uuid4(),
        khasra_number="KH-1",
        state="Karnataka",
        district="Udupi",
        tehsil="Udupi",
        village="Brahmavara",
        area_hectares=0.32,
        land_use_type=LandUseType.AGRICULTURAL,
        owner_name="Ramesh Kumar Naik",
    )
    test_db.add(record)
    await test_db.flush()

    doc = Document(
        id=uuid.uuid4(),
        land_record_id=record.id,
        document_type=DocumentType.TITLE_DEED,
        original_filename="a.png",
        stored_path=f"uploads/{record.id}/a.png",
        file_size_bytes=10,
        mime_type="image/png",
        status=DocumentStatus.VALIDATED,
    )
    test_db.add(doc)
    await test_db.flush()

    j = ProcessingJob(id=uuid.uuid4(), document_id=doc.id, land_record_id=record.id)
    test_db.add(j)
    await test_db.flush()
    return j


async def _count_fields(db: AsyncSession, job_id) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(ExtractedField).where(ExtractedField.job_id == job_id)
        )
    ).scalar() or 0


class TestFieldsAreReplacedNotAppended:
    async def test_rerun_leaves_one_row_per_field(self, test_db: AsyncSession, job):
        await _persist_fields(job.id, _results(), test_db)
        first = await _count_fields(test_db, job.id)
        assert first == 14

        await _persist_fields(job.id, _results(), test_db)
        assert await _count_fields(test_db, job.id) == first, "re-run duplicated fields"

    async def test_rerun_replaces_the_stale_value(self, test_db: AsyncSession, job):
        """A re-read must win over the previous machine reading."""
        await _persist_fields(job.id, _results("Khasra Number: OLD-1"), test_db)
        await _persist_fields(job.id, _results("Khasra Number: 124/3A"), test_db)

        rows = (
            await test_db.execute(
                select(ExtractedField).where(ExtractedField.job_id == job.id)
            )
        ).scalars().all()
        khasra = [r for r in rows if r.field_name == "khasra_number"]
        assert len(khasra) == 1
        assert khasra[0].normalized_value == "124/3A"

    async def test_verified_fields_survive_a_rerun(
        self, test_db: AsyncSession, job
    ):
        """A human decision must not be overwritten by a fresh machine reading."""
        await _persist_fields(job.id, _results("Khasra Number: 124/3A"), test_db)
        row = (
            await test_db.execute(
                select(ExtractedField).where(
                    ExtractedField.job_id == job.id,
                    ExtractedField.field_name == "khasra_number",
                )
            )
        ).scalar_one()
        row.verified_value = "HUMAN-1"
        row.verified_at = datetime.now(timezone.utc)
        await test_db.commit()

        await _persist_fields(job.id, _results("Khasra Number: 999/9Z"), test_db)

        rows = (
            await test_db.execute(
                select(ExtractedField).where(
                    ExtractedField.job_id == job.id,
                    ExtractedField.field_name == "khasra_number",
                )
            )
        ).scalars().all()
        assert len(rows) == 1, "verified field was duplicated"
        assert rows[0].verified_value == "HUMAN-1"
        assert rows[0].verified_at is not None

    async def test_only_the_verified_field_is_pinned(
        self, test_db: AsyncSession, job
    ):
        await _persist_fields(job.id, _results(), test_db)
        row = (
            await test_db.execute(
                select(ExtractedField).where(
                    ExtractedField.job_id == job.id,
                    ExtractedField.field_name == "khasra_number",
                )
            )
        ).scalar_one()
        row.verified_at = datetime.now(timezone.utc)
        await test_db.commit()

        await _persist_fields(job.id, _results(), test_db)
        assert await _count_fields(test_db, job.id) == 14

    async def test_another_jobs_fields_are_untouched(
        self, test_db: AsyncSession, job
    ):
        """The delete must be scoped to this job."""
        other = ProcessingJob(id=uuid.uuid4(), document_id=job.document_id, land_record_id=job.land_record_id)
        test_db.add(other)
        await test_db.flush()
        await _persist_fields(other.id, _results(), test_db)

        await _persist_fields(job.id, _results(), test_db)
        assert await _count_fields(test_db, other.id) == 14


class TestAnomaliesAreReplaced:
    async def test_rerun_does_not_duplicate_anomalies(
        self, test_db: AsyncSession, job
    ):
        results = [
            type("A", (), {
                "anomaly_type": "MISSING_REQUIRED",
                "field_name": "state",
                "severity": "HIGH",
                "description": "Required field 'State' could not be extracted.",
                "confidence": 0.9,
            })()
        ]
        await _persist_anomalies(job.id, results, test_db)
        await _persist_anomalies(job.id, results, test_db)

        n = (
            await test_db.execute(
                select(func.count()).select_from(PipelineAnomaly).where(PipelineAnomaly.job_id == job.id)
            )
        ).scalar() or 0
        assert n == 1, f"re-run duplicated anomalies ({n})"

    async def test_rerun_removes_anomalies_that_no_longer_apply(
        self, test_db: AsyncSession, job
    ):
        stale = [
            type("A", (), {
                "anomaly_type": "MISSING_REQUIRED",
                "field_name": "state",
                "severity": "HIGH",
                "description": "gone",
                "confidence": 0.9,
            })()
        ]
        await _persist_anomalies(job.id, stale, test_db)
        await _persist_anomalies(job.id, [], test_db)

        n = (
            await test_db.execute(
                select(func.count()).select_from(PipelineAnomaly).where(PipelineAnomaly.job_id == job.id)
            )
        ).scalar() or 0
        assert n == 0, "stale anomaly survived a re-run"


@pytest.mark.parametrize("field_count", [14])
def test_extractor_yields_the_full_field_set(field_count):
    assert len(_results()) == field_count
