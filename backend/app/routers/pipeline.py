"""
Pipeline Router — REST API for the document processing pipeline.

Endpoints:
  POST   /pipeline/trigger             — queue a pipeline run for a document
  GET    /pipeline/jobs/{job_id}       — get full job status + results
  GET    /pipeline/jobs/{job_id}/status — lightweight status poll (Redis-backed)
  GET    /pipeline/jobs               — list jobs (paginated)
  GET    /pipeline/verification-queue — list open human-verification tasks
  POST   /pipeline/fields/{field_id}/verify — submit human verification
  GET    /pipeline/jobs/{job_id}/fields  — get all extracted fields
  POST   /pipeline/jobs/{job_id}/retry   — retry a failed job
  GET    /pipeline/anomalies           — list all anomalies (paginated)
  GET    /pipeline/anomalies/feed      — anomalies joined to their document/record
  POST   /pipeline/anomalies/{id}/resolve — mark anomaly resolved

Every trigger/retry returns 202 immediately: the pipeline itself always runs in
a background worker, never inside the request.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func

from app.dependencies import CurrentUser, DBSession, OfficerUser, VerifierUser
from app.models.document import Document
from app.models.land_record import LandRecord
from app.models.pipeline import (
    ExtractedField, FieldValidationStatus, PipelineAnomaly,
    ProcessingJob, ProcessingStatus, VerificationTask,
)
from app.schemas.pipeline import (
    AnomalyFeedOut, AnomalyOut, ExtractedFieldOut, FieldVerificationIn,
    JobTriggerIn, ProcessingJobOut,
)
from app.services import pipeline_stages as stages
from app.services.audit_service import log_event
from app.services.job_dispatch import dispatch_job, record_queue_failure

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


# -- Helpers ------------------------------------------------------------------


async def _get_job_or_404(job_id: uuid.UUID, db: DBSession) -> ProcessingJob:
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job not found")
    return job


async def _is_open_verification(document_id: uuid.UUID, db: DBSession) -> bool:
    """True when a pending review still has unresolved verification tasks."""
    from sqlalchemy import func, select

    open_tasks = await db.scalar(
        select(func.count())
        .select_from(VerificationTask)
        .join(ProcessingJob, VerificationTask.job_id == ProcessingJob.id)
        .where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.status == ProcessingStatus.PENDING_REVIEW,
            VerificationTask.status == "OPEN",
        )
    )
    return bool(open_tasks)


# -- Trigger ------------------------------------------------------------------


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline(
    body: JobTriggerIn,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Queue the processing pipeline for a document.

    Returns 202 Accepted straight away; OCR and field extraction run in a
    background worker. Poll ``/pipeline/jobs/{job_id}/status`` for progress.
    """
    doc = await db.get(Document, body.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    job = ProcessingJob(
        document_id=body.document_id,
        land_record_id=body.land_record_id,
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
    await db.commit()

    dispatch = await dispatch_job(job_id, current_user.id)
    if not dispatch.get("queued"):
        message = dispatch.get("detail") or "The processing queue is unavailable."
        await record_queue_failure(job_id, message)
        raise HTTPException(status_code=503, detail=message)

    await log_event(
        "PIPELINE_TRIGGER",
        current_user.id,
        "ProcessingJob",
        job_id,
        {"document_id": str(body.document_id), "dispatch": dispatch},
    )

    return {
        "job_id": str(job_id),
        "document_id": str(body.document_id),
        "status": "queued",
        "stage": stages.PipelineStage.QUEUED.value,
        "progress": 0,
        "message": "Pipeline queued. Poll /api/v1/pipeline/jobs/{job_id}/status for updates.",
        "poll_url": f"/api/v1/pipeline/jobs/{job_id}/status",
        "queue_warning": dispatch.get("detail")
        if dispatch.get("runner") == "in-process" else None,
    }


# -- Status Poll (Redis-backed lightweight endpoint) --------------------------


@router.get("/jobs/{job_id}/status")
async def get_job_status(
    job_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Lightweight status check for a processing job.

    Serves the Redis mirror when it is available and always falls back to
    PostgreSQL, which is the source of truth.

    While running::

        {"status": "processing", "stage": "OCR", "progress": 45, ...}

    When finished::

        {"status": "completed", "stage": "COMPLETED", "progress": 100}

    On failure, ``failed_stage``, ``error_type`` and the real error message are
    returned so the client can show which stage broke.
    """
    from app.services.job_queue import read_status

    job = await _get_job_or_404(job_id, db)
    state = stages.state_for(job.status)
    stage = job.current_stage or stages.resolve_stage(job.status).value

    payload = {
        "job_id": str(job.id),
        "document_id": str(job.document_id),
        "status": state.value,
        "stage": stage,
        "stage_status": job.status.value,
        "progress": job.progress_pct or 0,
        "message": job.stage_message
        or stages.message_for(stages.resolve_stage(job.status)),
        "failed_stage": job.failed_stage,
        "error_type": job.error_type,
        "error_message": job.error_message,
        "overall_confidence": job.overall_confidence,
        "verification_status": job.verification_status,
        "detected_language": job.detected_language,
        "page_count": job.page_count,
        "needs_human_review": job.needs_human_review,
        "has_anomalies": job.has_anomalies,
        "is_duplicate": job.is_duplicate,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "source": "db",
    }

    cached = await read_status(job_id)
    if cached and stages.is_terminal(state) is False:
        # In-flight: the cached copy is at least as fresh as the DB row.
        payload = {**cached, "job_id": str(job_id), "source": "cache"}
    return payload


# ── Full Job Detail ───────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_model=ProcessingJobOut)
async def get_job(
    job_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJob:
    """Full job result including extracted fields and anomalies."""
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .options(
            selectinload(ProcessingJob.extracted_fields),
            selectinload(ProcessingJob.anomalies),
            selectinload(ProcessingJob.verification_tasks),
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ── List Jobs ─────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs(
    document_id: Optional[uuid.UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = 1,
    page_size: int = 20,
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    q = select(ProcessingJob).order_by(ProcessingJob.created_at.desc())
    if document_id:
        q = q.where(ProcessingJob.document_id == document_id)
    if status_filter:
        try:
            q = q.where(ProcessingJob.status == ProcessingStatus(status_filter))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}") from e

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    jobs = result.scalars().all()

    # The pipeline queue is a document list as much as a job list: the operator
    # recognises a scan by its filename and Khasra, not a job uuid. Join the
    # document and its land record in one query rather than N+1 lookups.
    doc_ids = {j.document_id for j in jobs}
    record_ids = {j.land_record_id for j in jobs if j.land_record_id}
    docs: dict = {}
    records: dict = {}
    if doc_ids:
        for d in (await db.execute(
            select(Document).where(Document.id.in_(doc_ids))
        )).scalars():
            docs[d.id] = d
    if record_ids:
        for r in (await db.execute(
            select(LandRecord).where(LandRecord.id.in_(record_ids))
        )).scalars():
            records[r.id] = r

    return {
        "items": [
            {
                "id": str(j.id),
                "document_id": str(j.document_id),
                "status": stages.state_for(j.status).value,
                "stage": j.current_stage,
                "stage_status": j.status.value,
                "progress_pct": j.progress_pct,
                "message": j.stage_message,
                "failed_stage": j.failed_stage,
                "error_type": j.error_type,
                "error_message": j.error_message,
                "overall_confidence": j.overall_confidence,
                "verification_status": j.verification_status,
                "needs_human_review": j.needs_human_review,
                "has_anomalies": j.has_anomalies,
                "is_duplicate": j.is_duplicate,
                "detected_language": j.detected_language,
                "page_count": j.page_count,
                "image_quality_score": j.image_quality_score,
                # Context for the queue row.
                "document_name": (
                    docs[j.document_id].original_filename if j.document_id in docs else None
                ),
                "document_type": (
                    docs[j.document_id].document_type.value if j.document_id in docs else None
                ),
                "khasra_number": (
                    records[j.land_record_id].khasra_number
                    if j.land_record_id in records else None
                ),
                "created_at": j.created_at.isoformat(),
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


# ── Extracted Fields ──────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/fields", response_model=list[ExtractedFieldOut])
async def get_extracted_fields(
    job_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> list[ExtractedField]:
    result = await db.execute(
        select(ExtractedField)
        .where(ExtractedField.job_id == job_id)
        .order_by(ExtractedField.confidence_score.asc())
    )
    return list(result.scalars().all())


# ── Human Verification ────────────────────────────────────────────────────────

@router.get("/verification-queue")
async def get_verification_queue(
    assigned_to_me: bool = False,
    priority: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """List open verification tasks for human review."""
    q = (
        select(VerificationTask)
        .where(VerificationTask.status == "OPEN")
        .order_by(VerificationTask.created_at.asc())
    )
    if assigned_to_me:
        q = q.where(VerificationTask.assigned_to == current_user.id)
    if priority:
        q = q.where(VerificationTask.priority == priority)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    tasks = result.scalars().all()

    return {
        "items": [
            {
                "id": str(t.id),
                "job_id": str(t.job_id),
                "field_id": str(t.field_id),
                "status": t.status,
                "priority": t.priority,
                "context_snippet": t.context_snippet,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ],
        "total": total,
        "page": page,
    }


@router.post("/fields/{field_id}/verify", status_code=200)
async def verify_field(
    field_id: uuid.UUID,
    body: FieldVerificationIn,
    db: DBSession,
    current_user: VerifierUser,
) -> dict:
    """
    Submit a human verification for an extracted field.
    VERIFIER or ADMIN role required.
    """
    field = await db.get(ExtractedField, field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    field.verified_value = body.verified_value
    field.verified_by = current_user.id
    field.verified_at = datetime.now(timezone.utc)
    field.validation_status = FieldValidationStatus.HUMAN_VERIFIED

    # Close the verification task
    result = await db.execute(
        select(VerificationTask).where(VerificationTask.field_id == field_id)
    )
    task = result.scalar_one_or_none()
    if task:
        task.status = "RESOLVED"
        task.resolution_notes = body.notes
        task.resolved_at = datetime.now(timezone.utc)

    await db.flush()
    await log_event(
        "FIELD_VERIFIED",
        current_user.id,
        "ExtractedField",
        field_id,
        {"verified_value": body.verified_value},
    )

    # Check if all fields for this job are now verified
    job_id = field.job_id
    open_tasks = await db.execute(
        select(func.count())
        .where(VerificationTask.job_id == job_id, VerificationTask.status == "OPEN")
    )
    open_count = open_tasks.scalar() or 0

    if open_count == 0:
        job = await db.get(ProcessingJob, job_id)
        if job and job.status == ProcessingStatus.PENDING_REVIEW:
            # Every open task is resolved: the job no longer needs review.
            job.status = ProcessingStatus.COMPLETED
            job.current_stage = stages.PipelineStage.COMPLETED.value
            job.stage_message = "All fields verified."
            job.needs_human_review = False
            job.progress_pct = 100
            job.verification_status = stages.VerificationStatus.RESOLVED.value
            from app.models.document import Document, DocumentStatus
            doc = await db.get(Document, job.document_id)
            if doc:
                doc.status = DocumentStatus.VALIDATED

    return {
        "field_id": str(field_id),
        "verified_value": body.verified_value,
        "status": "HUMAN_VERIFIED",
        "remaining_open_tasks": open_count - 1,
    }


# ── Anomalies ─────────────────────────────────────────────────────────────────

@router.get("/anomalies", response_model=list[AnomalyOut])
async def list_anomalies(
    job_id: Optional[uuid.UUID] = None,
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    page: int = 1,
    page_size: int = 30,
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> list[PipelineAnomaly]:
    q = select(PipelineAnomaly).order_by(PipelineAnomaly.created_at.desc())
    if job_id:
        q = q.where(PipelineAnomaly.job_id == job_id)
    if severity:
        q = q.where(PipelineAnomaly.severity == severity)
    if resolved is not None:
        q = q.where(PipelineAnomaly.resolved == resolved)
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    return list(result.scalars().all())


@router.get("/anomalies/feed", response_model=AnomalyFeedOut)
async def anomaly_feed(
    severity: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    resolved: Optional[bool] = None,
    land_record_id: Optional[uuid.UUID] = None,
    page: int = 1,
    page_size: int = Query(50, ge=1, le=500),
    *,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """
    Anomaly log joined to the document and land record each finding came from.

    ``/pipeline/anomalies`` returns bare rows, which is all a job-scoped caller
    needs. The anomaly screen has to answer "which scan is this?" and "which
    Khasra does it belong to?", and those links live two joins away, so they are
    resolved here once instead of per row.
    """
    q = (
        select(PipelineAnomaly, ProcessingJob, Document, LandRecord)
        .join(ProcessingJob, ProcessingJob.id == PipelineAnomaly.job_id)
        .join(Document, Document.id == ProcessingJob.document_id)
        .outerjoin(LandRecord, LandRecord.id == ProcessingJob.land_record_id)
        .order_by(PipelineAnomaly.created_at.desc())
    )
    if severity:
        q = q.where(PipelineAnomaly.severity == severity.upper())
    if anomaly_type:
        q = q.where(PipelineAnomaly.anomaly_type == anomaly_type.upper())
    if resolved is not None:
        q = q.where(PipelineAnomaly.resolved == resolved)
    if land_record_id:
        q = q.where(ProcessingJob.land_record_id == land_record_id)

    total = (await db.execute(
        select(func.count()).select_from(q.order_by(None).subquery())
    )).scalar() or 0

    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))

    items = [
        {
            "id": str(anom.id),
            "job_id": str(job.id),
            "document_id": str(doc.id),
            "document_name": doc.original_filename,
            "document_type": doc.document_type.value,
            "land_record_id": str(record.id) if record else None,
            "khasra_number": record.khasra_number if record else None,
            "village": record.village if record else None,
            "district": record.district if record else None,
            "anomaly_type": anom.anomaly_type.value,
            "field_name": anom.field_name,
            "severity": anom.severity,
            "description": anom.description,
            # 0-1 on the row; the UI renders a percentage.
            "confidence": anom.confidence,
            "confidence_pct": round((anom.confidence or 0) * 100),
            "resolved": anom.resolved,
            "resolved_by": str(anom.resolved_by) if anom.resolved_by else None,
            "created_at": anom.created_at.isoformat(),
        }
        for anom, job, doc, record in result.all()
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
    }


@router.post("/anomalies/{anomaly_id}/resolve", status_code=200)
async def resolve_anomaly(
    anomaly_id: uuid.UUID,
    db: DBSession,
    current_user: VerifierUser,
) -> dict:
    anom = await db.get(PipelineAnomaly, anomaly_id)
    if not anom:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    anom.resolved = True
    anom.resolved_by = current_user.id
    await db.flush()
    return {"id": str(anomaly_id), "resolved": True}


# ── Retry ─────────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    job_id: uuid.UUID,
    db: DBSession,
    current_user: OfficerUser,
) -> dict:
    """Re-queue a pipeline job. Returns 202 immediately.

    Any job whose automatic processing has finished may be re-run: FAILED,
    COMPLETED, and also PENDING_REVIEW. A job parked in PENDING_REVIEW still has
    queued *fields* to verify, but the person looking at it may just as well want
    the OCR re-run -- for example when the engine misread the page and every
    field came back empty. Refusing to retry that state strands the document:
    the only remedy would be re-uploading the same file, which creates a second
    document and breaks duplicate tracking.
    """
    job = await _get_job_or_404(job_id, db)
    if job.status not in stages.RETRYABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Job is in state '{job.status.value}' — only jobs that have "
                "finished processing (failed, completed, or awaiting review) can "
                "be retried"
            ),
        )
    job.status = ProcessingStatus.QUEUED
    job.current_stage = stages.PipelineStage.QUEUED.value
    job.stage_message = stages.message_for(stages.PipelineStage.QUEUED)
    job.progress_pct = 0
    job.error_message = None
    job.error_type = None
    job.failed_stage = None
    job.completed_at = None
    await db.commit()

    dispatch = await dispatch_job(job_id, current_user.id)
    if not dispatch.get("queued"):
        message = dispatch.get("detail") or "The processing queue is unavailable."
        await record_queue_failure(job_id, message)
        raise HTTPException(status_code=503, detail=message)
    return {
        "job_id": str(job_id),
        "document_id": str(job.document_id),
        "status": "queued",
        "message": "Pipeline re-queued. Poll /api/v1/pipeline/jobs/{job_id}/status",
        "queue_warning": dispatch.get("detail")
        if dispatch.get("runner") == "in-process" else None,
    }
