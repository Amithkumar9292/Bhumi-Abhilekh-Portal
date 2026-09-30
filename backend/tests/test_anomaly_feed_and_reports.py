"""
The anomaly screen and the Reports screen both run on live pipeline output.

`GET /pipeline/anomalies` returns bare anomaly rows, so a finding cannot be traced
back to the scan that produced it. The feed endpoint joins that provenance, and
the analytics endpoints below are what the Reports tabs read -- if any of them
count rows the pipeline never wrote, the report is fiction.
"""
import uuid

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, DocumentType
from app.models.land_record import LandRecord, LandUseType, RecordStatus
from app.models.pipeline import (
    AnomalyType, ExtractedField, FieldValidationStatus, PipelineAnomaly,
    ProcessingJob, ProcessingStatus,
)


@pytest_asyncio.fixture
async def upload(test_db: AsyncSession) -> dict:
    """One uploaded scan, mid-pipeline: a record, a document, a job, a finding
    and a couple of extracted fields."""
    record = LandRecord(
        id=uuid.uuid4(),
        khasra_number="KH-10142",
        state="Uttar Pradesh",
        district="Lucknow",
        tehsil="Sadar",
        village="Rampur",
        owner_name="Ramesh Prasad",
        area_hectares=2.45,
        land_use_type=LandUseType.AGRICULTURAL,
        status=RecordStatus.UNDER_REVIEW,
    )
    test_db.add(record)
    await test_db.flush()

    doc = Document(
        id=uuid.uuid4(),
        land_record_id=record.id,
        document_type=DocumentType.SURVEY_MAP,
        original_filename="khasra_nakal_KH-10142.pdf",
        stored_path=f"uploads/{record.id}/beef.pdf",
        file_size_bytes=4096,
        mime_type="application/pdf",
        status=DocumentStatus.PROCESSING,
    )
    test_db.add(doc)
    await test_db.flush()

    job = ProcessingJob(
        id=uuid.uuid4(),
        document_id=doc.id,
        land_record_id=record.id,
        status=ProcessingStatus.PENDING_REVIEW,
        current_stage="ANOMALY_CHECK",
        progress_pct=91,
        overall_confidence=0.83,
    )
    test_db.add(job)
    await test_db.flush()

    anomaly = PipelineAnomaly(
        id=uuid.uuid4(),
        job_id=job.id,
        anomaly_type=AnomalyType.AREA_MISMATCH,
        field_name="land_area",
        severity="HIGH",
        description="Land area on the deed does not match the cadastral map.",
        confidence=0.87,
    )
    test_db.add(anomaly)
    await test_db.flush()

    for name, display, value, status, confidence in [
        ("owner_name", "Owner Name", "Ramesh Prasad", FieldValidationStatus.AUTO_VALID, 0.94),
        ("land_area", "Land Area", "2.45", FieldValidationStatus.AUTO_INVALID, 0.41),
    ]:
        test_db.add(ExtractedField(
            job_id=job.id,
            field_name=name,
            field_display=display,
            raw_value=value,
            normalized_value=value,
            confidence_score=confidence,
            ocr_confidence=confidence,
            extraction_method="regex",
            validation_status=status,
            needs_review=(status == FieldValidationStatus.AUTO_INVALID),
        ))
    await test_db.flush()

    return {"record": record, "document": doc, "job": job, "anomaly": anomaly}


class TestAnomalyFeed:
    async def test_finding_carries_its_document_and_record(
        self, async_client: AsyncClient, officer_token: str, upload, seeded_db
    ):
        r = await async_client.get(
            "/api/v1/pipeline/anomalies/feed",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1

        item = next(i for i in body["items"] if i["id"] == str(upload["anomaly"].id))
        assert item["document_name"] == "khasra_nakal_KH-10142.pdf"
        assert item["document_type"] == "SURVEY_MAP"
        assert item["document_id"] == str(upload["document"].id)
        assert item["khasra_number"] == "KH-10142"
        assert item["land_record_id"] == str(upload["record"].id)
        assert item["anomaly_type"] == "AREA_MISMATCH"
        assert item["severity"] == "HIGH"

    async def test_confidence_is_exposed_as_a_percentage(
        self, async_client: AsyncClient, officer_token: str, upload, seeded_db
    ):
        """The row stores 0-1; the screen renders a percentage."""
        r = await async_client.get(
            "/api/v1/pipeline/anomalies/feed",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        item = next(
            i for i in r.json()["items"] if i["id"] == str(upload["anomaly"].id)
        )
        assert item["confidence"] == 0.87
        assert item["confidence_pct"] == 87

    async def test_filters_by_severity(
        self, async_client: AsyncClient, officer_token: str, upload, seeded_db
    ):
        headers = {"Authorization": f"Bearer {officer_token}"}
        high = await async_client.get(
            "/api/v1/pipeline/anomalies/feed", params={"severity": "high"},
            headers=headers,
        )
        assert high.json()["total"] == 1

        low = await async_client.get(
            "/api/v1/pipeline/anomalies/feed", params={"severity": "low"}, headers=headers,
        )
        assert low.json()["total"] == 0
        assert low.json()["items"] == []

    async def test_filters_by_record(
        self, async_client: AsyncClient, officer_token: str, upload, seeded_db
    ):
        headers = {"Authorization": f"Bearer {officer_token}"}
        mine = await async_client.get(
            "/api/v1/pipeline/anomalies/feed",
            params={"land_record_id": str(upload["record"].id)},
            headers=headers,
        )
        assert mine.json()["total"] == 1

        other = await async_client.get(
            "/api/v1/pipeline/anomalies/feed",
            params={"land_record_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert other.json()["total"] == 0

    async def test_unresolved_is_the_default_view(
        self, async_client: AsyncClient, officer_token: str, upload, seeded_db
    ):
        headers = {"Authorization": f"Bearer {officer_token}"}
        r = await async_client.get(
            "/api/v1/pipeline/anomalies/feed", params={"resolved": False}, headers=headers,
        )
        assert r.json()["total"] == 1

    async def test_requires_authentication(self, async_client: AsyncClient):
        r = await async_client.get("/api/v1/pipeline/anomalies/feed")
        assert r.status_code in (401, 403)


class TestAnalyticsUploads:
    async def test_document_summary_counts_the_uploaded_scan(
        self, async_client: AsyncClient, officer_token: str, upload, seeded_db
    ):
        r = await async_client.get(
            "/api/v1/analytics/documents",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        body = r.json()
        # A record that exists only because a scan was processed must be
        # counted as upload-sourced, not as hand-entered registry data.
        assert body["records_from_upload"] == 1
        assert body["records_with_anomalies"] == 1
        assert {"status": "PROCESSING", "count": 1} in body["by_status"]
        assert {"document_type": "SURVEY_MAP", "count": 1} in body["by_type"]

    async def test_records_by_state_aggregates_records(
        self, async_client: AsyncClient, officer_token: str, upload, seeded_db
    ):
        r = await async_client.get(
            "/api/v1/analytics/records-by-state",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        row = next(s for s in r.json()["data"] if s["state"] == "Uttar Pradesh")
        assert row["count"] == 1
        assert row["total_area_ha"] == 2.45
        assert row["verified"] == 0

    async def test_validation_health_comes_from_extracted_fields(
        self, async_client: AsyncClient, officer_token: str, upload, seeded_db
    ):
        r = await async_client.get(
            "/api/v1/analytics/validation-health",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        rows = {row["field_name"]: row for row in r.json()["data"]}
        assert set(rows) == {"owner_name", "land_area"}
        assert rows["owner_name"]["auto_valid"] == 1
        assert rows["owner_name"]["accepted"] == 1
        assert rows["owner_name"]["pass_rate_pct"] == 100.0
        assert rows["land_area"]["auto_invalid"] == 1
        assert rows["land_area"]["needs_review"] == 1
        assert rows["land_area"]["pass_rate_pct"] == 0.0

    async def test_field_accuracy_averages_recorded_confidence(
        self, async_client: AsyncClient, officer_token: str, upload, seeded_db
    ):
        r = await async_client.get(
            "/api/v1/analytics/field-accuracy",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        rows = {row["field_name"]: row for row in r.json()["data"]}
        assert rows["owner_name"]["field_display"] == "Owner Name"
        assert rows["owner_name"]["avg_confidence_pct"] == 94.0
        assert rows["owner_name"]["found_rate_pct"] == 100.0
        assert rows["land_area"]["avg_confidence_pct"] == 41.0
        assert r.json()["overall_confidence_pct"] == 83.0

    async def test_reports_endpoints_require_authentication(self, async_client: AsyncClient):
        for path in (
            "/api/v1/analytics/documents",
            "/api/v1/analytics/records-by-state",
            "/api/v1/analytics/validation-health",
            "/api/v1/analytics/field-accuracy",
        ):
            r = await async_client.get(path)
            assert r.status_code in (401, 403), path
