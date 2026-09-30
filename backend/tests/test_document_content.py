"""
Tests for the document view/download endpoints.

`GET /documents/{id}/file` serves the original upload (there was no file route
at all before, so the UI's Download button could not work), and
`GET /documents/{id}/content` returns everything the pipeline extracted.
"""

import uuid
from pathlib import Path

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.land_record import LandRecord, LandUseType
from app.models.pipeline import ExtractedField, ProcessingJob, ProcessingStatus


@pytest_asyncio.fixture
async def document_with_file(test_db: AsyncSession, tmp_path: Path) -> tuple[Document, bytes]:
    """A document whose stored file really exists on disk."""
    record = LandRecord(
        id=uuid.uuid4(),
        khasra_number=f"KH-{uuid.uuid4().hex[:6]}",
        khatauni_number="KHAT-1",
        state="Uttar Pradesh",
        district="Lucknow",
        tehsil="Lucknow",
        village="Rampur",
        pin_code="226001",
        area_hectares=2.45,
        land_use_type=LandUseType.AGRICULTURAL,
        owner_name="Ramesh Prasad",
    )
    test_db.add(record)
    await test_db.flush()

    payload = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes" * 40
    # Write into the configured upload dir layout so the endpoint resolves the
    # same way it does in production.
    record_dir = Path(settings.upload_dir) / str(record.id)
    record_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.png"
    (record_dir / stored_name).write_bytes(payload)

    doc = Document(
        id=uuid.uuid4(),
        land_record_id=record.id,
        document_type=DocumentType.TITLE_DEED,
        original_filename="deed.png",
        stored_path=str(record_dir / stored_name),
        file_size_bytes=len(payload),
        mime_type="image/png",
        status=DocumentStatus.VALIDATED,
    )
    test_db.add(doc)
    await test_db.flush()
    return doc, payload


class TestDownloadFile:
    async def test_serves_the_original_file_with_the_operator_filename(
        self, async_client: AsyncClient, officer_token: str, document_with_file
    ):
        doc, payload = document_with_file
        r = await async_client.get(
            f"/api/v1/documents/{doc.id}/file",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        # The stored name is a uuid; the browser must save the real filename.
        assert r.content == payload
        assert "deed.png" in r.headers["content-disposition"]
        assert r.headers["content-type"].startswith("image/png")

    async def test_missing_file_returns_410_not_500(
        self, async_client: AsyncClient, officer_token: str, test_db: AsyncSession,
        document_with_file,
    ):
        """A row whose blob was cleaned up must say so clearly."""
        doc, _ = document_with_file
        Path(doc.stored_path).unlink()

        r = await async_client.get(
            f"/api/v1/documents/{doc.id}/file",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 410
        assert "no longer available" in r.json()["detail"]

    async def test_unknown_document_is_404(
        self, async_client: AsyncClient, officer_token: str
    ):
        r = await async_client.get(
            f"/api/v1/documents/{uuid.uuid4()}/file",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 404

    async def test_requires_authentication(
        self, async_client: AsyncClient, document_with_file
    ):
        doc, _ = document_with_file
        r = await async_client.get(f"/api/v1/documents/{doc.id}/file")
        assert r.status_code in (401, 403)


class TestDocumentContent:
    async def test_returns_fields_confidence_and_ocr_reads(
        self, async_client: AsyncClient, officer_token: str,
        test_db: AsyncSession, document_with_file,
    ):
        doc, _ = document_with_file
        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=doc.id,
            land_record_id=doc.land_record_id,
            status=ProcessingStatus.COMPLETED,
            current_stage="COMPLETED",
            progress_pct=100,
            overall_confidence=0.78,
            detected_language="en",
            page_count=1,
            needs_human_review=False,
        )
        test_db.add(job)
        await test_db.flush()

        test_db.add_all([
            ExtractedField(
                id=uuid.uuid4(), job_id=job.id, field_name="khasra_number",
                field_display="Khasra Number", raw_value="KH-10142",
                normalized_value="KH-10142", confidence_score=0.78,
                validation_status="AUTO_VALID", needs_review=False,
            ),
            ExtractedField(
                id=uuid.uuid4(), job_id=job.id, field_name="owner_name",
                field_display="Owner Name", raw_value="ramesh prasad",
                normalized_value="Ramesh Prasad", confidence_score=0.44,
                validation_status="AUTO_INVALID", needs_review=True,
            ),
        ])
        await test_db.flush()

        r = await async_client.get(
            f"/api/v1/documents/{doc.id}/content",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        body = r.json()

        assert body["document"]["original_filename"] == "deed.png"
        assert body["document"]["file_available"] is True
        # Sorted by confidence descending.
        names = [f["field_name"] for f in body["extracted_fields"]]
        assert names == ["khasra_number", "owner_name"]
        assert body["extracted_fields"][0]["confidence_pct"] == 78
        assert body["extracted_fields"][1]["needs_review"] is True
        # Low-confidence fields are surfaced, not silently dropped.
        assert "ramesh prasad" in body["raw_ocr_text"]
        assert body["land_record"]["owner_name"] == "Ramesh Prasad"
        assert body["pipeline_job"]["status"] == "completed"

    async def test_unprocessed_document_reports_no_fields(
        self, async_client: AsyncClient, officer_token: str, document_with_file
    ):
        doc, _ = document_with_file
        r = await async_client.get(
            f"/api/v1/documents/{doc.id}/content",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["extracted_fields"] == []
        assert body["raw_ocr_text"] is None
        assert body["pipeline_job"] is None
        assert body["document"]["file_available"] is True

    async def test_missing_blob_is_flagged_so_the_ui_can_disable_download(
        self, async_client: AsyncClient, officer_token: str, document_with_file
    ):
        doc, _ = document_with_file
        Path(doc.stored_path).unlink()
        r = await async_client.get(
            f"/api/v1/documents/{doc.id}/content",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.json()["document"]["file_available"] is False

    async def test_unknown_document_is_404(
        self, async_client: AsyncClient, officer_token: str
    ):
        r = await async_client.get(
            f"/api/v1/documents/{uuid.uuid4()}/content",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 404
