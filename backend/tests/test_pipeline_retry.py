"""
Tests for POST /pipeline/jobs/{id}/retry.

Retry used to accept only FAILED and COMPLETED jobs. A job parked in
PENDING_REVIEW -- which is where a job with bad extractions ends up, because
"extract these fields" is a human task and every field arrived empty -- could
therefore never be re-run. The only remedy was re-uploading the same file as a
second document, which duplicates the record and defeats duplicate detection.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, DocumentType
from app.models.land_record import LandRecord, LandUseType
from app.models.pipeline import ProcessingJob, ProcessingStatus

RETRY_URL = "/api/v1/pipeline/jobs/{job_id}/retry"


@pytest_asyncio.fixture
async def officer_headers(officer_token: str) -> dict:
    return {"Authorization": f"Bearer {officer_token}"}


@pytest_asyncio.fixture
async def finished_job(test_db: AsyncSession):
    """A document plus a job in the state a mis-read document ends up in."""
    record = LandRecord(
        id=uuid.uuid4(),
        khasra_number="KH-10142",
        state="Uttar Pradesh",
        district="Lucknow",
        tehsil="Sadar",
        village="Rampur",
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
        original_filename="survey.png",
        stored_path=f"uploads/{record.id}/survey.png",
        file_size_bytes=2048,
        mime_type="image/png",
        status=DocumentStatus.VALIDATED,
    )
    test_db.add(doc)
    await test_db.flush()

    job = ProcessingJob(
        id=uuid.uuid4(),
        document_id=doc.id,
        land_record_id=record.id,
        status=ProcessingStatus.PENDING_REVIEW,
        current_stage="VERIFICATION_REQUIRED",
        progress_pct=94,
        overall_confidence=0.18,
    )
    test_db.add(job)
    await test_db.flush()
    return job, doc


async def _retry(client: AsyncClient, job_id: uuid.UUID, headers: dict):
    return await client.post(RETRY_URL.format(job_id=job_id), headers=headers)


class TestRetryGate:
    async def test_awaiting_review_job_can_be_reprocessed(
        self, async_client: AsyncClient, officer_headers, finished_job
    ):
        """The state a mis-read document lands in must still be re-runnable."""
        job, _ = finished_job
        with patch(
            "app.routers.pipeline.dispatch_job",
            new=AsyncMock(return_value={"queued": True, "runner": "redis"}),
        ):
            r = await _retry(async_client, job.id, officer_headers)

        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "queued"
        assert body["job_id"] == str(job.id)

    async def test_retry_resets_progress_and_error_state(
        self, async_client: AsyncClient, test_db: AsyncSession,
        officer_headers, finished_job
    ):
        job, _ = finished_job
        job.error_message = "stale failure"
        job.failed_stage = "OCR"
        await test_db.flush()

        with patch(
            "app.routers.pipeline.dispatch_job",
            new=AsyncMock(return_value={"queued": True, "runner": "redis"}),
        ):
            await _retry(async_client, job.id, officer_headers)

        await test_db.refresh(job)
        assert job.status == ProcessingStatus.QUEUED
        assert job.current_stage == "QUEUED"
        assert job.progress_pct == 0
        assert job.error_message is None
        assert job.failed_stage is None
        assert job.completed_at is None

    @pytest.mark.parametrize(
        "status", [ProcessingStatus.FAILED, ProcessingStatus.COMPLETED]
    )
    async def test_failed_and_completed_remain_retryable(
        self, async_client: AsyncClient, officer_headers, finished_job, status
    ):
        job, _ = finished_job
        job.status = status
        with patch(
            "app.routers.pipeline.dispatch_job",
            new=AsyncMock(return_value={"queued": True, "runner": "redis"}),
        ):
            r = await _retry(async_client, job.id, officer_headers)
        assert r.status_code == 202

    @pytest.mark.parametrize(
        "status",
        [
            ProcessingStatus.QUEUED,
            ProcessingStatus.VALIDATING,
            ProcessingStatus.OCR_RUNNING,
            ProcessingStatus.EXTRACTING,
        ],
    )
    async def test_in_flight_jobs_are_not_retryable(
        self, async_client: AsyncClient, officer_headers, finished_job, status
    ):
        """Re-queueing a running job would double-process the same document."""
        job, _ = finished_job
        job.status = status
        with patch(
            "app.routers.pipeline.dispatch_job",
            new=AsyncMock(return_value={"queued": True, "runner": "redis"}),
        ) as dispatch:
            r = await _retry(async_client, job.id, officer_headers)

        assert r.status_code == 400
        assert "retried" in r.json()["detail"]
        dispatch.assert_not_awaited()

    async def test_missing_job_is_404(self, async_client: AsyncClient, officer_headers):
        r = await _retry(async_client, uuid.uuid4(), officer_headers)
        assert r.status_code == 404

    async def test_viewer_cannot_retry(self, async_client: AsyncClient, viewer_token, finished_job):
        job, _ = finished_job
        r = await async_client.post(
            RETRY_URL.format(job_id=job.id),
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert r.status_code == 403


class TestRetryDispatchFailure:
    async def test_queue_failure_is_persisted_and_reported(
        self, async_client: AsyncClient, test_db: AsyncSession,
        officer_headers, finished_job
    ):
        """A retry that cannot be queued must not leave the job looking re-run."""
        job, _ = finished_job
        with patch(
            "app.routers.pipeline.dispatch_job",
            new=AsyncMock(return_value={"queued": False, "detail": "Redis unreachable"}),
        ), patch(
            "app.routers.pipeline.record_queue_failure", new=AsyncMock()
        ) as record:
            r = await _retry(async_client, job.id, officer_headers)

        assert r.status_code == 503
        assert r.json()["detail"] == "Redis unreachable"
        record.assert_awaited_once()
        assert record.await_args.args[0] == job.id
