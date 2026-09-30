"""
Tests for GET /pipeline/jobs.

The pipeline queue used to return only job-internal columns, so the UI had no
document filename, Khasra, language, page count or quality score to show. The
operator recognises a scan by its name, not by a job uuid, so the endpoint now
joins Document and LandRecord.
"""

import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, DocumentType
from app.models.land_record import LandRecord, LandUseType
from app.models.pipeline import (
    PipelineAnomaly, ProcessingJob, ProcessingStatus,
)


@pytest_asyncio.fixture
async def job_with_document(test_db: AsyncSession):
    record = LandRecord(
        id=uuid.uuid4(),
        khasra_number="KH-10142",
        khatauni_number="KT-5032",
        state="Uttar Pradesh",
        district="Lucknow",
        tehsil="Sadar",
        village="Rampur",
        pin_code="226001",
        area_hectares=2.45,
        land_use_type=LandUseType.AGRICULTURAL,
        owner_name="Ramesh Prasad",
    )
    test_db.add(record)
    await test_db.flush()

    doc = Document(
        id=uuid.uuid4(),
        land_record_id=record.id,
        document_type=DocumentType.TITLE_DEED,
        original_filename="khasra_nakal_KH-10142.pdf",
        stored_path=f"uploads/{record.id}/deadbeef.pdf",
        file_size_bytes=1024,
        mime_type="application/pdf",
        status=DocumentStatus.VALIDATED,
    )
    test_db.add(doc)
    await test_db.flush()

    job = ProcessingJob(
        id=uuid.uuid4(),
        document_id=doc.id,
        land_record_id=record.id,
        status=ProcessingStatus.COMPLETED,
        current_stage="COMPLETED",
        progress_pct=100,
        overall_confidence=0.83,
        detected_language="hi+en",
        page_count=2,
        image_quality_score=0.87,
        needs_human_review=True,
        has_anomalies=True,
    )
    test_db.add(job)
    await test_db.flush()

    test_db.add(PipelineAnomaly(
        id=uuid.uuid4(),
        job_id=job.id,
        anomaly_type="MISSING_REQUIRED",
        field_name="state",
        severity="HIGH",
        description="Required field 'State' could not be extracted.",
        confidence=0.95,
    ))
    await test_db.flush()

    return job, doc, record


class TestListJobs:
    async def test_includes_document_name_and_khasra(
        self, async_client: AsyncClient, officer_token: str, job_with_document
    ):
        """The queue row must identify the scan, not just a job uuid."""
        job, doc, record = job_with_document
        r = await async_client.get(
            "/api/v1/pipeline/jobs",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        item = next(i for i in r.json()["items"] if i["id"] == str(job.id))
        assert item["document_name"] == "khasra_nakal_KH-10142.pdf"
        assert item["document_type"] == "TITLE_DEED"
        assert item["khasra_number"] == "KH-10142"
        assert item["document_id"] == str(doc.id)

    async def test_includes_processing_metrics(
        self, async_client: AsyncClient, officer_token: str, job_with_document
    ):
        job, _, _ = job_with_document
        r = await async_client.get(
            "/api/v1/pipeline/jobs",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        item = next(i for i in r.json()["items"] if i["id"] == str(job.id))
        assert item["overall_confidence"] == 0.83
        assert item["detected_language"] == "hi+en"
        assert item["page_count"] == 2
        assert item["image_quality_score"] == 0.87
        # Coarse lowercase state, matching the frontend JobState union.
        assert item["status"] == "completed"
        assert item["progress_pct"] == 100

    async def test_filters_by_status(
        self, async_client: AsyncClient, officer_token: str, job_with_document
    ):
        job, _, _ = job_with_document
        r = await async_client.get(
            "/api/v1/pipeline/jobs",
            params={"status": "COMPLETED"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        ids = [i["id"] for i in r.json()["items"]]
        assert str(job.id) in ids

    async def test_invalid_status_is_400(
        self, async_client: AsyncClient, officer_token: str
    ):
        r = await async_client.get(
            "/api/v1/pipeline/jobs",
            params={"status": "NOT_A_STATUS"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 400

    async def test_requires_authentication(self, async_client: AsyncClient):
        r = await async_client.get("/api/v1/pipeline/jobs")
        assert r.status_code in (401, 403)
