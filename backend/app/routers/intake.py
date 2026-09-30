"""
Document Intake Router -- upload-first workflow that does NOT require an
existing land record.

POST /intake/upload
  - Accepts any supported file (PDF, JPG, JPEG, PNG, TIFF)
  - Resolves a draft LandRecord: reuses a match on ``khasra_hint`` if one
    exists, otherwise creates a new DRAFT so a brand-new Survey/Khasra number
    never has to pre-exist in the database
  - Persists the file, creates a Document row and a ProcessingJob row
  - Enqueues the job and returns **202 Accepted** immediately

  No OCR, ML, NLP or any other heavy work happens before the response is sent.
  The upload path performs only: authenticate -> validate -> store -> create
  rows -> enqueue. A single audit write is time-boxed, so even an unreachable
  audit database cannot delay the response.

GET /intake/review/{job_id}
  - Returns extracted fields + current land record state for the review UI
  - Includes confidence scores, validation status, source page info per field

POST /intake/confirm/{job_id}/submit
  - Verifier submits corrected field values
  - Updates the LandRecord with verified data
  - Marks document as VALIDATED and job as COMPLETED
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import (
    APIRouter, File, Form, HTTPException, UploadFile, status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import settings
from app.dependencies import CurrentUser, DBSession
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.land_record import LandRecord, LandUseType, RecordStatus
from app.models.pipeline import (
    ExtractedField, FieldValidationStatus,
    ProcessingJob, ProcessingStatus, VerificationTask,
)
from app.services import pipeline_stages as stages
from app.services.audit_service import log_event
from app.services.job_dispatch import dispatch_job, record_queue_failure

log = logging.getLogger(__name__)

router = APIRouter(prefix="/intake", tags=["Document Intake"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
    "image/tif",
}
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}

_EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

# Values used for a draft record until OCR replaces them.
_DRAFT_PLACEHOLDER = "UNKNOWN — PENDING OCR"
_DRAFT_KHASRA = "DRAFT-PENDING-OCR"


class UploadRejected(Exception):
    """Fast, user-facing upload validation failure (never a 500)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def intake_upload(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    khasra_hint: Optional[str] = Form(None),
    remarks: Optional[str] = Form(None),
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Accept a land-record document and queue it for background processing.

    Returns 202 Accepted with ``document_id``, ``job_id`` and
    ``status="queued"`` as soon as the file is safely persisted. OCR runs
    afterwards in a worker, so the response is fast regardless of how long
    processing takes.

    - ``khasra_hint`` is optional. If provided we try to match an existing
      record; otherwise a new DRAFT record is created and populated from OCR.
    """

    # -- 1. Validate the upload (fast, no I/O beyond the request body) --------
    try:
        content, ext, mime_type, size = await _read_and_validate(file)
    except UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    # -- 2. Resolve or create the land record --------------------------------
    record, new_record_created = await _resolve_land_record(
        db, khasra_hint, current_user.id
    )
    record_id: uuid.UUID = record.id

    # -- 3. Persist the file --------------------------------------------------
    try:
        stored_path, stored_name = await _store_file(content, ext, record_id)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Storage failure: the uploaded file could not be saved ({exc}).",
        ) from exc

    # -- 4. Create the document + job rows -----------------------------------
    doc = Document(
        land_record_id=record_id,
        document_type=document_type,
        original_filename=file.filename or stored_name,
        stored_path=str(stored_path),
        file_size_bytes=size,
        mime_type=mime_type,
        status=DocumentStatus.UPLOADED,
        uploaded_by=current_user.id,
        validation_notes=remarks,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    doc_id = doc.id

    job = ProcessingJob(
        document_id=doc_id,
        land_record_id=record_id,
        status=ProcessingStatus.QUEUED,
        current_stage=stages.PipelineStage.QUEUED.value,
        stage_message=stages.message_for(stages.PipelineStage.QUEUED),
        progress_pct=0,
        triggered_by=current_user.id,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    job_id: uuid.UUID = job.id

    # Show the document as "processing" from the moment it is queued so it
    # renders with a live status on the Documents page straight away.
    doc.status = DocumentStatus.PROCESSING

    await db.commit()

    # -- 5. Queue the heavy work and return ---------------------------------
    dispatch = await dispatch_job(job_id, current_user.id)

    if not dispatch.get("queued"):
        # Nothing will ever process this job. Report it as unavailable instead of
        # returning a 202 that would poll "queued" forever.
        message = dispatch.get("detail") or "The processing queue is unavailable."
        await record_queue_failure(job_id, message)
        log.error("Intake upload %s could not be queued: %s", doc_id, message)
        raise HTTPException(status_code=503, detail=message)

    # Audit is a side effect: time-boxed, never able to delay or fail a 202.
    await log_event(
        "INTAKE_UPLOAD",
        current_user.id,
        "Document",
        doc_id,
        {
            "land_record_id": str(record_id),
            "job_id": str(job_id),
            "new_record_created": new_record_created,
            "khasra_hint": khasra_hint,
            "document_type": document_type.value,
            "filename": file.filename,
            "size_bytes": size,
            "dispatch": dispatch,
        },
    )

    return {
        "document_id": str(doc_id),
        "job_id": str(job_id),
        "land_record_id": str(record_id),
        "new_record_created": new_record_created,
        "khasra_matched": not new_record_created,
        "filename": file.filename,
        "file_size_bytes": size,
        "status": "queued",
        "stage": stages.PipelineStage.QUEUED.value,
        "progress": 0,
        "message": "Document uploaded successfully — processing started.",
        "status_url": f"/api/v1/documents/{doc_id}/status",
        "job_status_url": f"/api/v1/pipeline/jobs/{job_id}/status",
        "review_url": f"/api/v1/intake/review/{job_id}",
        "queue_warning": dispatch.get("detail")
        if dispatch.get("runner") == "in-process" else None,
    }


# -- Upload helpers ----------------------------------------------------------


async def _read_and_validate(file: UploadFile) -> tuple[bytes, str, str, int]:
    """Read and validate the upload. Raises UploadRejected on bad input."""
    content_type = (file.content_type or "").lower()
    ext = Path(file.filename or "doc").suffix.lower()

    if content_type not in ALLOWED_MIME_TYPES:
        # Some browsers/OSs send an empty or generic content type; trust a
        # known extension in that case.
        if ext not in ALLOWED_EXTENSIONS:
            raise UploadRejected(
                400,
                f"File type '{file.content_type or 'unknown'}' is not supported. "
                "Accepted formats: PDF, JPEG, PNG, TIFF",
            )
        content_type = _EXTENSION_TO_MIME.get(ext, content_type)

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) == 0:
        raise UploadRejected(400, "Uploaded file is empty.")
    if len(content) > max_bytes:
        raise UploadRejected(
            413,
            f"File too large ({len(content) / 1048576:.1f} MB). "
            f"Maximum allowed: {settings.max_upload_size_mb} MB",
        )
    return content, ext, content_type, len(content)


async def _resolve_land_record(
    db, khasra_hint: Optional[str], user_id: uuid.UUID
) -> tuple[LandRecord, bool]:
    """
    Find an existing record for ``khasra_hint`` or create a DRAFT.

    A Survey/Khasra number is never required to already exist: when there is no
    match we create a placeholder row that the background pipeline fills in from
    the document, and the whole record goes to verification afterwards.
    """
    if khasra_hint and khasra_hint.strip():
        result = await db.execute(
            select(LandRecord)
            .where(LandRecord.khasra_number.ilike(khasra_hint.strip()))
            .limit(1)
        )
        record = result.scalar_one_or_none()
        if record is not None:
            return record, False

    record = LandRecord(
        khasra_number=(
            khasra_hint.strip() if khasra_hint and khasra_hint.strip() else _DRAFT_KHASRA
        ),
        state=_DRAFT_PLACEHOLDER,
        district=_DRAFT_PLACEHOLDER,
        tehsil=_DRAFT_PLACEHOLDER,
        village=_DRAFT_PLACEHOLDER,
        area_hectares=0.0001,  # placeholder, overwritten by extraction
        land_use_type=LandUseType.AGRICULTURAL,
        owner_name=_DRAFT_PLACEHOLDER,
        status=RecordStatus.PENDING,
        created_by=user_id,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record, True


async def _store_file(
    content: bytes, ext: str, record_id: uuid.UUID
) -> tuple[Path, str]:
    """Write the upload to disk. Raises OSError on storage failure."""
    record_dir = Path(settings.upload_dir) / str(record_id)
    record_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = record_dir / stored_name
    async with aiofiles.open(stored_path, "wb") as fh:
        await fh.write(content)
    return stored_path, stored_name


@router.get("/review/{job_id}")
async def get_intake_review(
    job_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Return the full review payload for the post-upload review screen:
    - Processing job status and progress
    - Document metadata
    - All extracted fields (with confidence scores, validation status, source page)
    - Current draft land record values
    - Anomalies detected
    """
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .options(
            selectinload(ProcessingJob.extracted_fields),
            selectinload(ProcessingJob.anomalies),
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Processing job not found")

    # Load document
    doc = await db.get(Document, job.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load land record
    record: LandRecord | None = None
    if job.land_record_id:
        record = await db.get(LandRecord, job.land_record_id)

    def _field_out(ef: ExtractedField) -> dict:
        return {
            "id": str(ef.id),
            "field_name": ef.field_name,
            "field_display": ef.field_display,
            "raw_value": ef.raw_value,
            "normalized_value": ef.normalized_value,
            "confidence_score": ef.confidence_score,
            "confidence_pct": round(ef.confidence_score * 100),
            "ocr_confidence": ef.ocr_confidence,
            "extraction_method": ef.extraction_method,
            "source_page": ef.source_page,
            "bounding_box": ef.bounding_box,
            "validation_status": ef.validation_status.value if hasattr(ef.validation_status, "value") else ef.validation_status,
            "validation_message": ef.validation_message,
            "needs_review": ef.needs_review,
            "verified_value": ef.verified_value,
            "verified_at": ef.verified_at.isoformat() if ef.verified_at else None,
        }

    fields_out = [_field_out(ef) for ef in sorted(
        job.extracted_fields,
        key=lambda f: -f.confidence_score  # high confidence first
    )]

    record_out: dict = {}
    if record:
        record_out = {
            "id": str(record.id),
            "khasra_number": record.khasra_number,
            "khatauni_number": record.khatauni_number,
            "survey_number": record.survey_number,
            "state": record.state,
            "district": record.district,
            "tehsil": record.tehsil,
            "village": record.village,
            "area_hectares": record.area_hectares,
            "land_use_type": record.land_use_type.value if record.land_use_type else None,
            "owner_name": record.owner_name,
            "father_name": record.father_name,
            "address": record.address,
            "status": record.status.value,
        }

    return {
        "job_id": str(job.id),
        "status": stages.state_for(job.status).value,
        "stage_status": job.status.value,
        "current_stage": job.current_stage,
        "stage_message": job.stage_message,
        "failed_stage": job.failed_stage,
        "error_type": job.error_type,
        "progress_pct": job.progress_pct,
        "verification_status": job.verification_status,
        "detected_language": job.detected_language,
        "page_count": job.page_count,
        "image_quality_score": job.image_quality_score,
        "overall_confidence": job.overall_confidence,
        "overall_confidence_pct": round((job.overall_confidence or 0) * 100),
        "needs_human_review": job.needs_human_review,
        "has_anomalies": job.has_anomalies,
        "is_duplicate": job.is_duplicate,
        "error_message": job.error_message,
        "stage_timings": job.stage_timings,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "document": {
            "id": str(doc.id),
            "original_filename": doc.original_filename,
            "document_type": doc.document_type.value,
            "file_size_bytes": doc.file_size_bytes,
            "mime_type": doc.mime_type,
            "status": doc.status.value,
            "created_at": doc.created_at.isoformat(),
        },
        "land_record": record_out,
        "extracted_fields": fields_out,
        "anomalies": [
            {
                "id": str(a.id),
                "anomaly_type": a.anomaly_type.value if hasattr(a.anomaly_type, "value") else a.anomaly_type,
                "field_name": a.field_name,
                "severity": a.severity,
                "description": a.description,
                "confidence": a.confidence,
            }
            for a in job.anomalies
        ],
    }


class ConfirmPayload(BaseModel):
    """Verifier corrections. Omitted fields fall back to the extracted value."""

    corrections: dict[str, str] = Field(default_factory=dict)
    notes: Optional[str] = None


@router.post("/confirm/{job_id}/submit", status_code=status.HTTP_200_OK)
async def submit_confirm(
    job_id: uuid.UUID,
    payload: ConfirmPayload,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Save verified field values and update the draft land record.

    - Updates ExtractedField rows with HUMAN_VERIFIED status
    - Writes corrected values back to LandRecord columns
    - Sets document status to VALIDATED
    - Sets job status to COMPLETED
    - Sets land record status to UNDER_REVIEW (ready for officer/admin final approval)
    """
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job not found")

    state = stages.state_for(job.status)
    if state is stages.JobState.FAILED:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This document failed during {job.failed_stage or 'processing'}"
                f" ({job.error_type or 'UNKNOWN'}). It cannot be confirmed — "
                "upload a clearer scan or retry the job."
            ),
        )
    if not stages.is_confirmable(state):
        # Still queued or mid-pipeline: the extracted values are not final yet.
        raise HTTPException(
            status_code=409,
            detail=(
                f"Processing is still running (stage: {job.current_stage}, "
                f"{job.progress_pct or 0}%). Confirm once it has finished."
            ),
        )

    doc = await db.get(Document, job.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    record: LandRecord | None = None
    if job.land_record_id:
        record = await db.get(LandRecord, job.land_record_id)

    if record is None:
        raise HTTPException(status_code=404, detail="Land record not found")

    # ── Apply verified values to extracted fields ──────────────────────────────
    fields_result = await db.execute(
        select(ExtractedField).where(ExtractedField.job_id == job_id)
    )
    fields = list(fields_result.scalars().all())

    for ef in fields:
        if ef.field_name in payload.corrections:
            corrected = payload.corrections[ef.field_name]
            ef.verified_value = corrected
            ef.verified_by = current_user.id
            ef.verified_at = datetime.now(timezone.utc)
            ef.validation_status = FieldValidationStatus.HUMAN_VERIFIED
        elif ef.normalized_value and ef.validation_status.value == "AUTO_VALID":
            # Auto-valid fields count as implicitly accepted
            ef.verified_value = ef.normalized_value
            ef.verified_by = current_user.id
            ef.verified_at = datetime.now(timezone.utc)
            ef.validation_status = FieldValidationStatus.HUMAN_VERIFIED

    await db.flush()

    # Build a lookup: field_name → best value (correction > verified > normalized)
    def best(name: str) -> str | None:
        if name in payload.corrections:
            return payload.corrections[name].strip() or None
        for ef in fields:
            if ef.field_name == name:
                return ef.verified_value or ef.normalized_value or None
        return None

    # ── Update LandRecord with extracted/corrected values ─────────────────────
    _NOT_FOUND = ("UNKNOWN — PENDING OCR", "DRAFT-PENDING-OCR", None, "", "0.0001")

    def _set(attr: str, val: str | None, coerce=None):
        if val and str(val) not in _NOT_FOUND:
            try:
                setattr(record, attr, coerce(val) if coerce else val)
            except (ValueError, TypeError):
                pass

    _set("khasra_number", best("khasra_number") or best("survey_number") or record.khasra_number)
    _set("khatauni_number", best("khata_number"))
    _set("survey_number", best("survey_number"))
    _set("owner_name", best("owner_name"))
    _set("father_name", best("father_name"))
    _set("state", best("state"))
    _set("district", best("district"))
    _set("tehsil", best("tehsil"))
    _set("village", best("village"))
    _set("pin_code", best("pin_code"))
    _set("area_hectares", best("land_area"), coerce=float)

    # Land use type
    land_use_raw = best("land_classification")
    if land_use_raw:
        try:
            record.land_use_type = LandUseType(land_use_raw.upper())
        except ValueError:
            pass

    # Advance record status: PENDING → UNDER_REVIEW (so verifiers can see it)
    if record.status == RecordStatus.PENDING:
        record.status = RecordStatus.UNDER_REVIEW

    await db.flush()

    # ── Close verification tasks ───────────────────────────────────────────────
    tasks_result = await db.execute(
        select(VerificationTask)
        .where(VerificationTask.job_id == job_id, VerificationTask.status == "OPEN")
    )
    for task in tasks_result.scalars().all():
        task.status = "RESOLVED"
        task.resolution_notes = payload.notes or "Confirmed via intake review"
        task.resolved_at = datetime.now(timezone.utc)

    # -- Finalize job + document --------------------------------------------
    now = datetime.now(timezone.utc)
    job.status = ProcessingStatus.COMPLETED
    job.current_stage = stages.PipelineStage.COMPLETED.value
    job.stage_message = "Confirmed by verifier."
    job.progress_pct = 100
    job.needs_human_review = False
    job.verification_status = stages.VerificationStatus.RESOLVED.value
    job.error_message = None
    job.error_type = None
    job.failed_stage = None
    job.heartbeat_at = now
    job.completed_at = now

    doc.status = DocumentStatus.VALIDATED
    doc.validation_notes = payload.notes

    await log_event(
        "INTAKE_CONFIRMED",
        current_user.id,
        "ProcessingJob",
        job_id,
        {
            "land_record_id": str(record.id),
            "corrections_count": len(payload.corrections),
            "khasra_number": record.khasra_number,
        },
    )

    await db.commit()

    return {
        "job_id": str(job_id),
        "land_record_id": str(record.id),
        "document_id": str(doc.id),
        "khasra_number": record.khasra_number,
        "owner_name": record.owner_name,
        "status": "CONFIRMED",
        "land_record_status": record.status.value,
        "message": (
            f"Land record '{record.khasra_number}' saved successfully. "
            "Status set to UNDER_REVIEW for officer approval."
        ),
    }
