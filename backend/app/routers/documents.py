"""
Documents router: upload, status and validation of documents.

Upload is deliberately fast. The handler only authenticates, validates, stores
the file, creates the Document + ProcessingJob rows, enqueues the job and
returns **202 Accepted**. OCR and field extraction run later in a background
worker, so a large scan never blocks the HTTP response.

``GET /documents/{document_id}/status`` is the polling endpoint the UI uses to
follow a document from ``queued`` through every pipeline stage to completion or
failure.
"""

import math
import uuid
from pathlib import Path

import aiofiles
from fastapi import (
    APIRouter, File, Form, HTTPException, Query, UploadFile, status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import CurrentUser, DBSession, VerifierUser
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.land_record import LandRecord
from app.models.pipeline import ProcessingJob, ProcessingStatus
from app.services import pipeline_stages as stages
from app.services.audit_service import log_event
from app.services.job_dispatch import dispatch_job, record_queue_failure

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",   # some browsers/OS send this alias
    "image/png",
    "image/tiff",
    "image/tif",
}
# Content-type → acceptable extensions
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}

_EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


def _latest_job_query(document_id):
    return (
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )


def _job_with_fields_query(document_id):
    """Latest job for a document, with fields eager-loaded.

    ``extracted_fields`` is a lazy relationship; touching it in an async handler
    without this raises MissingGreenlet.
    """
    return (
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .options(selectinload(ProcessingJob.extracted_fields))
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )


def _job_summary(job: ProcessingJob | None) -> dict:
    """Normalised pipeline summary shared by the status and list endpoints."""
    if job is None:
        return {
            "job_id": None,
            "status": None,
            "stage": None,
            "stage_status": None,
            "progress": 0,
            "message": None,
            "failed_stage": None,
            "error_type": None,
            "error_message": None,
            "confidence": None,
            "verification_status": None,
            "detected_language": None,
            "needs_human_review": None,
            "has_anomalies": None,
            "is_duplicate": None,
            "page_count": None,
            "started_at": None,
            "completed_at": None,
        }
    state = stages.state_for(job.status)
    return {
        "job_id": str(job.id),
        "status": state.value,
        "stage": job.current_stage or stages.PipelineStage.QUEUED.value,
        "stage_status": job.status.value,
        "progress": job.progress_pct or 0,
        "message": job.stage_message or stages.message_for(
            stages.resolve_stage(job.status)
        ),
        "failed_stage": job.failed_stage,
        "error_type": job.error_type,
        "error_message": job.error_message,
        "confidence": job.overall_confidence,
        "verification_status": job.verification_status,
        "detected_language": job.detected_language,
        "page_count": job.page_count,
        "needs_human_review": job.needs_human_review,
        "has_anomalies": job.has_anomalies,
        "is_duplicate": job.is_duplicate,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    land_record_id: str = Form(...),
    document_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    auto_process: bool = Form(True),
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Upload a document and attach it to a land record.

    Returns 202 Accepted as soon as the file is persisted and the job is queued.
    With ``auto_process=True`` (the default) OCR/AI processing continues in a
    background worker; poll ``/documents/{document_id}/status`` for progress.
    """
    # -- Validate ------------------------------------------------------------
    ext = Path(file.filename or "doc").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' is not allowed. "
                   "Accepted: PDF, JPEG, PNG, TIFF",
        )
    if (file.content_type or "") not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{file.content_type}' is not allowed. "
                f"Accepted: PDF, JPEG, PNG, TIFF"
            ),
        )

    try:
        record_uuid = uuid.UUID(land_record_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid land_record_id format") from e

    record = await db.get(LandRecord, record_uuid)
    if record is None:
        raise HTTPException(status_code=404, detail="Land record not found")

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed: {settings.max_upload_size_mb} MB",
        )

    # -- Store file ----------------------------------------------------------
    try:
        record_dir = Path(settings.upload_dir) / land_record_id
        record_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}{ext}"
        stored_path = record_dir / stored_name
        async with aiofiles.open(stored_path, "wb") as f:
            await f.write(content)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Storage failure: the file could not be saved ({exc}).",
        ) from exc

    # -- Create document -----------------------------------------------------
    doc = Document(
        land_record_id=record_uuid,
        document_type=document_type,
        original_filename=file.filename or stored_name,
        stored_path=str(stored_path),
        file_size_bytes=len(content),
        mime_type=_EXTENSION_TO_MIME.get(ext, file.content_type),
        status=DocumentStatus.UPLOADED,
        uploaded_by=current_user.id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    doc_id = doc.id

    response: dict = {
        "id": str(doc_id),
        "document_id": str(doc_id),
        "land_record_id": str(record_uuid),
        "original_filename": doc.original_filename,
        "document_type": doc.document_type.value,
        "file_size_bytes": doc.file_size_bytes,
        "status": "queued",
        "stage": stages.PipelineStage.QUEUED.value,
        "progress": 0,
        "created_at": doc.created_at.isoformat(),
    }

    # -- Queue processing ----------------------------------------------------
    job_id: uuid.UUID | None = None
    if auto_process and settings.pipeline_auto_trigger:
        job = ProcessingJob(
            document_id=doc_id,
            land_record_id=record_uuid,
            status=ProcessingStatus.QUEUED,
            current_stage=stages.PipelineStage.QUEUED.value,
            stage_message=stages.message_for(stages.PipelineStage.QUEUED),
            progress_pct=0,
            triggered_by=current_user.id,
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)
        job_id = job.id
        doc.status = DocumentStatus.PROCESSING

    # Commit so the worker's own session can see the document and job rows.
    await db.commit()

    if job_id is not None:
        dispatch = await dispatch_job(job_id, current_user.id)
        if not dispatch.get("queued"):
            # A 202 here would poll "queued" forever, since no worker will get it.
            message = dispatch.get("detail") or "The processing queue is unavailable."
            await record_queue_failure(job_id, message)
            raise HTTPException(status_code=503, detail=message)
        response.update({
            "pipeline_job_id": str(job_id),
            "job_id": str(job_id),
            "processing_status": "queued",
            "pipeline_status": "QUEUED",
            "message": "Document uploaded successfully — processing started.",
            "status_url": f"/api/v1/documents/{doc_id}/status",
            "job_status_url": f"/api/v1/pipeline/jobs/{job_id}/status",
        })
        if dispatch.get("runner") == "in-process":
            response["queue_warning"] = dispatch.get("detail")
    else:
        response["message"] = "Document uploaded. Processing not started."

    # Audit is time-boxed; it must not delay or fail the 202.
    await log_event(
        "UPLOAD_DOCUMENT",
        current_user.id,
        "Document",
        doc_id,
        {
            "land_record_id": land_record_id,
            "type": document_type.value,
            "filename": file.filename,
            "size_bytes": len(content),
            "auto_process": auto_process,
            "job_id": str(job_id) if job_id else None,
        },
    )

    return response


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: str,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Current processing state for a document.

    Reads the Redis mirror first and always falls back to PostgreSQL, which is
    the source of truth. Cheap enough to poll every couple of seconds.

    While running::

        {"status": "processing", "stage": "OCR", "progress": 45, ...}

    When finished::

        {"status": "completed", "stage": "COMPLETED", "progress": 100}

    On failure the payload carries ``failed_stage``, ``error_type`` and the real
    error message.
    """
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid document_id format") from exc

    doc = await db.get(Document, doc_uuid)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    job = (await db.execute(_latest_job_query(doc_uuid))).scalar_one_or_none()
    payload = _job_summary(job)
    if payload["status"] is None:
        # Uploaded but never queued for processing.
        payload.update({
            "status": "queued",
            "stage": stages.PipelineStage.QUEUED.value,
            "progress": 0,
            "message": "Document stored. Processing has not started.",
        })

    return {
        "document_id": str(doc.id),
        "job_id": payload["job_id"],
        # `status` is the coarse lifecycle the client polls on; `progress_pct`
        # and `stage_message` are the fields the UI binds its bar to.
        "status": payload["status"],
        "status_detail": payload["stage_status"],
        "stage": payload["stage"],
        "stage_message": payload["message"],
        "progress_pct": payload["progress"],
        "message": payload["message"],
        "filename": doc.original_filename,
        "document_type": doc.document_type.value,
        "document_status": doc.status.value,
        "land_record_id": str(doc.land_record_id),
        "file_size_bytes": doc.file_size_bytes,
        "uploaded_at": doc.created_at.isoformat(),
        "failed_stage": payload["failed_stage"],
        "error_type": payload["error_type"],
        "error_message": payload["error_message"],
        "confidence": payload["confidence"],
        "confidence_pct": round((payload["confidence"] or 0) * 100)
        if payload["confidence"] is not None else None,
        "verification_status": payload["verification_status"],
        "needs_human_review": payload["needs_human_review"],
        "detected_language": payload["detected_language"],
        "is_duplicate": payload["is_duplicate"],
        "has_anomalies": payload["has_anomalies"],
        "page_count": payload["page_count"],
        "started_at": payload["started_at"],
        "completed_at": payload["completed_at"],
    }


@router.get("")
async def list_all_documents(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    document_type: str | None = Query(None),
    doc_status: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
) -> dict:
    """
    List all documents across all land records (for the Documents page).

    Each row carries the document id, filename, type, Survey/Khasra number,
    upload date, upload status, processing status, current stage, confidence and
    verification status, so a freshly uploaded document is visible immediately
    and stays visible after a page refresh (everything here is read from
    PostgreSQL).
    """
    from sqlalchemy import func as sqlfunc, or_
    from app.models.user import User

    q = (
        select(
            Document,
            LandRecord.khasra_number,
            LandRecord.survey_number,
            LandRecord.owner_name,
            User.username.label("uploader_username"),
        )
        .join(LandRecord, Document.land_record_id == LandRecord.id)
        .outerjoin(User, Document.uploaded_by == User.id)
    )
    if document_type:
        q = q.where(Document.document_type == document_type)
    if doc_status:
        q = q.where(Document.status == doc_status)
    if search:
        q = q.where(
            or_(
                LandRecord.khasra_number.ilike(f"%{search}%"),
                LandRecord.survey_number.ilike(f"%{search}%"),
                LandRecord.owner_name.ilike(f"%{search}%"),
                Document.original_filename.ilike(f"%{search}%"),
            )
        )

    count_q = select(sqlfunc.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).all()

    # One query for every job on this page instead of one per document.
    doc_ids = [row[0].id for row in rows]
    latest_jobs: dict[uuid.UUID, ProcessingJob] = {}
    if doc_ids:
        job_rows = await db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.document_id.in_(doc_ids))
            .order_by(ProcessingJob.created_at.desc())
        )
        for job in job_rows.scalars().all():
            latest_jobs.setdefault(job.document_id, job)

    items = []
    for doc, khasra_number, survey_number, owner_name, uploader_username in rows:
        job = latest_jobs.get(doc.id)
        pipeline = _job_summary(job)
        items.append({
            "id": str(doc.id),
            "document_id": str(doc.id),
            "land_record_id": str(doc.land_record_id),
            "document_type": doc.document_type.value,
            "original_filename": doc.original_filename,
            "file_size_bytes": doc.file_size_bytes,
            "mime_type": doc.mime_type,
            # Upload lifecycle (UPLOADED / PROCESSING / VALIDATED / REJECTED)
            "status": doc.status.value,
            "validation_notes": doc.validation_notes,
            "created_at": doc.created_at.isoformat(),
            "khasra_number": khasra_number,
            "survey_number": survey_number,
            "owner_name": owner_name,
            "uploader_username": uploader_username,
            # Processing lifecycle
            "job_id": pipeline["job_id"],
            "processing_status": pipeline["status"],
            "current_stage": pipeline["stage"],
            "stage_message": pipeline["message"],
            "progress_pct": pipeline["progress"],
            "failed_stage": pipeline["failed_stage"],
            "error_type": pipeline["error_type"],
            "error_message": pipeline["error_message"],
            "confidence": round(pipeline["confidence"] * 100)
            if pipeline["confidence"] is not None else None,
            "verification_status": pipeline["verification_status"],
            "needs_human_review": pipeline["needs_human_review"],
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 0,
    }


@router.get("/by-record/{land_record_id}")
async def list_documents_for_record(
    land_record_id: str,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """List all documents attached to a land record."""
    result = await db.execute(
        select(Document)
        .where(Document.land_record_id == uuid.UUID(land_record_id))
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(d.id),
                "document_type": d.document_type.value,
                "original_filename": d.original_filename,
                "file_size_bytes": d.file_size_bytes,
                "mime_type": d.mime_type,
                "status": d.status.value,
                "validation_notes": d.validation_notes,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ],
        "total": len(docs),
    }


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Get a document by ID with its latest pipeline job status."""
    doc = await db.get(Document, uuid.UUID(document_id))
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    job = (await db.execute(_latest_job_query(doc.id))).scalar_one_or_none()

    return {
        "id": str(doc.id),
        "document_id": str(doc.id),
        "land_record_id": str(doc.land_record_id),
        "document_type": doc.document_type.value,
        "original_filename": doc.original_filename,
        "file_size_bytes": doc.file_size_bytes,
        "mime_type": doc.mime_type,
        "status": doc.status.value,
        "validation_notes": doc.validation_notes,
        "created_at": doc.created_at.isoformat(),
        "pipeline_job": _job_summary(job) if job else None,
    }


def _resolve_stored_path(doc: Document) -> Path:
    """
    Absolute path to a document's stored file.

    ``stored_path`` is written by the upload handler as
    ``Path(settings.upload_dir) / <record_id> / <name>``, so it is already
    relative to the configured upload dir (or absolute when the config is).
    Prefixing ``upload_dir`` again would double it, so only fall back to that
    when the bare path does not resolve.
    """
    path = Path(doc.stored_path)
    if path.is_file():
        return path
    candidate = Path(settings.upload_dir) / path
    return candidate if candidate.is_file() else path


@router.get("/{document_id}/file")
async def download_document_file(
    document_id: str,
    db: DBSession,
    current_user: CurrentUser,
) -> FileResponse:
    """
    Serve the original uploaded file so the UI can offer a real download.

    The stored name is a generated uuid, so the response uses the operator-facing
    ``original_filename`` and asks the browser to save rather than render.
    """
    doc = await db.get(Document, uuid.UUID(document_id))
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    path = _resolve_stored_path(doc)
    if not path.is_file():
        # The row exists but the blob is gone (manually cleaned, or a container
        # that did not persist the volume). Say so instead of returning a 500.
        raise HTTPException(
            status_code=410,
            detail=(
                "The stored file is no longer available on this server. "
                "Only the extracted data can be shown."
            ),
        )

    return FileResponse(
        path,
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.original_filename,
    )


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: str,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Everything extracted from a document, for the "View details" panel.

    Returns the raw OCR text, every extracted field with its confidence and
    validation state, plus the pipeline summary and the linked land record, so
    the UI does not have to stitch several endpoints together.
    """
    doc = await db.get(Document, uuid.UUID(document_id))
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    job = (await db.execute(_job_with_fields_query(doc.id))).scalar_one_or_none()
    record = await db.get(LandRecord, doc.land_record_id)

    fields = []
    if job is not None:
        for ef in sorted(job.extracted_fields, key=lambda f: -f.confidence_score):
            fields.append(
                {
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
                    "validation_status": (
                        ef.validation_status.value
                        if hasattr(ef.validation_status, "value")
                        else ef.validation_status
                    ),
                    "validation_message": ef.validation_message,
                    "needs_review": ef.needs_review,
                    "verified_value": ef.verified_value,
                    "verified_at": ef.verified_at.isoformat() if ef.verified_at else None,
                }
            )

    # The verbatim OCR text is not persisted, so reconstruct a readable dump from
    # the per-field raw reads. This is what the extractor actually saw, per field.
    raw_text = "\n".join(
        f"{f['field_display'] or f['field_name']}: {f['raw_value']}"
        for f in fields
        if f["raw_value"]
    ) or None

    return {
        "document": {
            "id": str(doc.id),
            "original_filename": doc.original_filename,
            "document_type": doc.document_type.value,
            "file_size_bytes": doc.file_size_bytes,
            "mime_type": doc.mime_type,
            "status": doc.status.value,
            "validation_notes": doc.validation_notes,
            "created_at": doc.created_at.isoformat(),
            # False when the blob is missing, so the UI can disable the download
            # button instead of letting the user click into a 410.
            "file_available": _resolve_stored_path(doc).is_file(),
        },
        "pipeline_job": _job_summary(job) if job else None,
        "extracted_fields": fields,
        "raw_ocr_text": raw_text,
        "land_record": (
            {
                "id": str(record.id),
                "khasra_number": record.khasra_number,
                "owner_name": record.owner_name,
                "village": record.village,
                "district": record.district,
                "state": record.state,
                "area_hectares": record.area_hectares,
                "status": record.status.value,
            }
            if record
            else None
        ),
    }


@router.post("/{document_id}/validate")
async def validate_document(
    document_id: str,
    approved: bool = Form(...),
    notes: str | None = Form(None),
    *,
    db: DBSession,
    current_user: VerifierUser,
) -> dict:
    """Mark a document as validated or rejected (VERIFIER/ADMIN only)."""
    doc = await db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    doc.status = DocumentStatus.VALIDATED if approved else DocumentStatus.REJECTED
    doc.validation_notes = notes
    await db.flush()
    await log_event(
        "VALIDATE_DOCUMENT", current_user.id, "Document", doc.id, {"approved": approved}
    )
    return {"id": str(doc.id), "status": doc.status.value, "notes": notes}


@router.post("/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    document_id: str,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Queue a fresh pipeline run for an already-uploaded document.

    Returns 202 immediately; the run happens in a background worker.
    """
    doc = await db.get(Document, uuid.UUID(document_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    job = ProcessingJob(
        document_id=doc.id,
        land_record_id=doc.land_record_id,
        status=ProcessingStatus.QUEUED,
        current_stage=stages.PipelineStage.QUEUED.value,
        stage_message=stages.message_for(stages.PipelineStage.QUEUED),
        progress_pct=0,
        triggered_by=current_user.id,
    )
    db.add(job)
    doc.status = DocumentStatus.PROCESSING
    await db.flush()
    await db.refresh(job)
    job_id = job.id
    await db.commit()

    dispatch = await dispatch_job(job_id, current_user.id)
    if not dispatch.get("queued"):
        message = dispatch.get("detail") or "The processing queue is unavailable."
        await record_queue_failure(job_id, message)
        raise HTTPException(status_code=503, detail=message)
    return {
        "document_id": str(doc.id),
        "pipeline_job_id": str(job_id),
        "status": "queued",
        "message": "Reprocessing queued.",
        "status_url": f"/api/v1/documents/{doc.id}/status",
        "queue_warning": dispatch.get("detail")
        if dispatch.get("runner") == "in-process" else None,
    }
