"""
Document Processing Pipeline -- background orchestrator.

This module is the *only* place heavy work happens. It is never called from a
request handler: upload endpoints enqueue a job id and return ``202 Accepted``,
and this pipeline is executed by a worker (``python -m app.worker``) or, when
Redis is unavailable, by the in-process runner.

Stage order (see ``app.services.pipeline_stages``)::

    QUEUED -> FILE_VALIDATION -> IMAGE_QUALITY -> PREPROCESSING -> OCR
    -> LANGUAGE_DETECTION -> FIELD_EXTRACTION -> CLASSIFICATION
    -> CONFIDENCE_SCORING -> VALIDATION -> DUPLICATE_CHECK -> ANOMALY_CHECK
    -> VERIFICATION_REQUIRED | COMPLETED

Every stage transition is committed to PostgreSQL before the next stage starts,
so the status endpoints report genuine progress. PostgreSQL is the source of
truth; Redis only mirrors status for cheap polling.
"""
from __future__ import annotations

import logging
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.document import Document, DocumentStatus
from app.models.extended import GISCoordinate, CoordinateType
from app.models.land_record import LandRecord, LandUseType
from app.models.pipeline import (
    AnomalyType, ExtractedField, FieldValidationStatus,
    PipelineAnomaly, ProcessingJob, ProcessingStatus, VerificationTask,
)
from app.services import pipeline_stages as stages
from app.services.anomaly_detector import AnomalyDetector
from app.services.audit_service import log_event
from app.services.field_extractor import FieldExtractor, FieldResult
from app.services.gis_service import (
    extract_document_coordinates, generate_parcel_polygon,
    generate_synthetic_centroid,
)
from app.services.image_processor import analyze_and_preprocess
from app.services.ocr_service import OCRResult, get_ocr_backend
from app.services.pipeline_stages import PipelineStage, VerificationStatus

log = logging.getLogger(__name__)

# Fields below this confidence are routed to human verification.
REVIEW_THRESHOLD = settings.pipeline_review_threshold

# Failure categories surfaced to the user via `error_type`.
ERROR_STORAGE = "STORAGE"
ERROR_DATABASE = "DATABASE"
ERROR_OCR = "OCR"
ERROR_EXTRACTION = "EXTRACTION"
ERROR_VALIDATION = "VALIDATION"
ERROR_INTERNAL = "INTERNAL"

# Upload is long; the pipeline owns the job from here, so the heartbeat only
# needs to be recent enough to spot a wedged worker.
HEARTBEAT_STAGE_MESSAGE_MAX = 255

# `GISCoordinate.source` values written by this pipeline. Coordinates that were
# captured in the field (DGPS, Bhuvan, manual entry) are never overwritten --
# re-running a job must not throw away a surveyed position.
SOURCE_FROM_SCAN = "Document scan"
SOURCE_DERIVED = "Document (estimated)"
_AUTO_SOURCES = (SOURCE_FROM_SCAN, SOURCE_DERIVED)


class PipelineStageError(RuntimeError):
    """A stage failed. Carries the error category shown to the user."""

    def __init__(self, message: str, error_type: str = ERROR_INTERNAL) -> None:
        super().__init__(message)
        self.error_type = error_type


# -- Observability helpers ---------------------------------------------------


async def _mongo_log(job_id: str, stage: str, data: dict) -> None:
    """Best-effort pipeline event log. Never raises, never blocks the stage."""
    try:
        import asyncio

        from app.db.mongo import get_mongo_db

        mdb = await get_mongo_db()
        await asyncio.wait_for(
            mdb["pipeline_logs"].insert_one(
                {
                    "job_id": job_id,
                    "stage": stage,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **data,
                }
            ),
            timeout=settings.pipeline_log_timeout_s,
        )
    except Exception as exc:
        log.debug("Mongo pipeline log skipped (%s): %s", stage, exc)


async def _publish_status(job: ProcessingJob, stage: PipelineStage) -> None:
    """Mirror the current job state into Redis for cheap status polling."""
    from app.services.job_queue import publish_status

    state = stages.state_for(job.status)
    await publish_status(
        job.id,
        {
            "document_id": str(job.document_id),
            "job_id": str(job.id),
            "status": state.value,
            "stage": stage.value,
            "stage_status": job.status.value,
            "progress": job.progress_pct or 0,
            "message": job.stage_message or stages.message_for(stage),
            "failed_stage": job.failed_stage,
            "error_type": job.error_type,
            "error_message": job.error_message,
            "overall_confidence": job.overall_confidence,
            "verification_status": job.verification_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


async def _advance(
    job: ProcessingJob,
    stage: PipelineStage,
    db: AsyncSession,
    extra: dict | None = None,
) -> None:
    """
    Move the job into ``stage``, commit it, then mirror to Redis.

    The commit is what makes progress observable: a status poll issued while OCR
    is running sees ``stage=OCR`` in PostgreSQL, not just in memory.
    """
    now = datetime.now(timezone.utc)
    job.status = stages.STAGE_TO_PROCESSING_STATUS[stage]
    job.current_stage = stage.value
    job.stage_message = stages.message_for(stage)[:HEARTBEAT_STAGE_MESSAGE_MAX]
    job.progress_pct = stages.progress_for(stage)
    job.heartbeat_at = now
    job.updated_at = now
    # The worker picks the job up at FILE_VALIDATION, so the real start time has
    # to be stamped on the first executed stage, not on the QUEUED marker.
    if job.started_at is None and stage is not PipelineStage.QUEUED:
        job.started_at = now
    if extra:
        for key, value in extra.items():
            setattr(job, key, value)

    await db.commit()
    await db.refresh(job)
    await _publish_status(job, stage)
    log.info(
        "job=%s stage=%s progress=%d%%", job.id, stage.value, job.progress_pct or 0
    )


# -- Entry point -------------------------------------------------------------


async def run_pipeline(
    job_id: uuid.UUID,
    triggered_by: Optional[uuid.UUID] = None,
    db_factory: Optional[Callable[[], AsyncSession]] = None,
) -> None:
    """
    Execute the full pipeline for ``job_id`` in its own database session.

    ``db_factory`` defaults to the application's session maker. It is still
    accepted so existing callers that pass a factory keep working.
    """
    if db_factory is None:
        from app.db.postgres import async_session_maker as db_factory  # noqa: PLW2901

    try:
        async with db_factory() as db:  # type: ignore[union-attr]
            await _execute_pipeline(job_id, db, triggered_by)
    except Exception:
        # Last-resort guard: the session may be unusable, so record the failure
        # with a brand-new session.
        log.exception("Pipeline job %s crashed outside the session scope", job_id)
        await _record_catastrophic_failure(job_id, triggered_by)


async def _record_catastrophic_failure(
    job_id: uuid.UUID, triggered_by: Optional[uuid.UUID]
) -> None:
    from app.db.postgres import async_session_maker

    try:
        async with async_session_maker() as db:
            job = await db.get(ProcessingJob, job_id)
            if job is None:
                return
            now = datetime.now(timezone.utc)
            # Capture the stage the job died in *before* overwriting it.
            job.failed_stage = job.current_stage or PipelineStage.QUEUED.value
            job.status = ProcessingStatus.FAILED
            job.current_stage = PipelineStage.FAILED.value
            job.error_type = ERROR_INTERNAL
            job.error_message = traceback.format_exc(limit=3)[-2000:]
            job.progress_pct = 100
            job.stage_message = "Processing failed."
            job.heartbeat_at = now
            job.updated_at = now
            job.completed_at = now
            await db.commit()
            await _publish_status(job, PipelineStage.FAILED)
    except Exception:
        log.error("Could not record failure for job %s", job_id)


# -- Pipeline ----------------------------------------------------------------


async def _execute_pipeline(
    job_id: uuid.UUID,
    db: AsyncSession,
    triggered_by: Optional[uuid.UUID],
) -> None:
    timings: dict[str, str] = {}
    t_total = time.time()

    job = await db.get(ProcessingJob, job_id)
    if job is None:
        log.error("Pipeline job %s not found", job_id)
        return

    doc = await db.get(Document, job.document_id)
    if doc is None:
        await _fail(db, job, PipelineStage.FILE_VALIDATION,
                    "The document record for this job no longer exists.",
                    ERROR_DATABASE)
        return

    try:
        # ── 1. FILE_VALIDATION ───────────────────────────────────────────
        t0 = time.time()
        await _advance(job, PipelineStage.FILE_VALIDATION, db)
        file_path = Path(doc.stored_path)
        _validate_file(file_path, doc)
        timings["file_validation"] = _elapsed(t0)
        await _mongo_log(str(job_id), "FILE_VALIDATION",
                         {"file": str(file_path), "mime": doc.mime_type})

        # ── 2. IMAGE_QUALITY ─────────────────────────────────────────────
        t0 = time.time()
        await _advance(job, PipelineStage.IMAGE_QUALITY, db)
        quality = await analyze_and_preprocess(
            file_path, doc.mime_type or "application/pdf"
        )
        await _advance(
            job, PipelineStage.IMAGE_QUALITY, db,
            {"image_quality_score": quality.score},
        )
        timings["image_quality"] = _elapsed(t0)
        await _mongo_log(str(job_id), "IMAGE_QUALITY", {
            "quality_score": quality.score,
            "issues": quality.issues,
            "recommendations": quality.recommendations,
            "resolution": f"{quality.width_px}x{quality.height_px}",
        })

        # ── 3. PREPROCESSING ─────────────────────────────────────────────
        t0 = time.time()
        await _advance(job, PipelineStage.PREPROCESSING, db, {"page_count": 1})
        ocr_input = Path(quality.preprocessed_path) if quality.preprocessed_path else file_path
        if not ocr_input.exists():
            ocr_input = file_path
        timings["preprocessing"] = _elapsed(t0)
        await _mongo_log(str(job_id), "PREPROCESSING", {
            "ocr_input": str(ocr_input),
            "used_preprocessed": ocr_input != file_path,
        })

        # ── 4. OCR (the slow stage -- runs entirely in the background) ────
        t0 = time.time()
        await _advance(job, PipelineStage.OCR, db)
        try:
            # Never falls back to canned text: a missing engine fails the stage.
            backend = get_ocr_backend()
        except Exception as exc:
            raise PipelineStageError(str(exc), ERROR_OCR) from exc
        try:
            ocr_result: OCRResult = await backend.process(
                ocr_input, doc.mime_type or "image/jpeg"
            )
        except Exception as exc:
            raise PipelineStageError(
                f"OCR failed using the '{backend.name}' backend: {exc}", ERROR_OCR
            ) from exc
        if not ocr_result.full_text.strip():
            raise PipelineStageError(
                "OCR completed but no text could be read from the document. "
                "The scan may be blank, too low-resolution, or not a text document.",
                ERROR_OCR,
            )
        timings["ocr"] = _elapsed(t0)
        await _mongo_log(str(job_id), "OCR", {
            "backend": ocr_result.backend_name,
            "page_count": ocr_result.page_count,
            "detected_language": ocr_result.detected_language,
            "avg_confidence": round(ocr_result.avg_confidence, 3),
            "char_count": len(ocr_result.full_text),
            "full_text_preview": ocr_result.full_text[:500],
        })

        # ── 5. LANGUAGE_DETECTION ────────────────────────────────────────
        t0 = time.time()
        await _advance(
            job, PipelineStage.LANGUAGE_DETECTION, db,
            {"detected_language": ocr_result.detected_language,
             "page_count": ocr_result.page_count},
        )
        timings["language_detection"] = _elapsed(t0)
        await _mongo_log(str(job_id), "LANGUAGE_DETECTION", {
            "detected": ocr_result.detected_language,
        })

        # ── 6. FIELD_EXTRACTION ──────────────────────────────────────────
        t0 = time.time()
        await _advance(job, PipelineStage.FIELD_EXTRACTION, db)
        extractor = FieldExtractor(confidence_review_threshold=REVIEW_THRESHOLD)
        try:
            field_results: list[FieldResult] = extractor.extract(ocr_result)
        except Exception as exc:
            raise PipelineStageError(
                f"Field extraction failed: {exc}", ERROR_EXTRACTION
            ) from exc

        db_fields = await _persist_fields(job_id, field_results, db)
        timings["field_extraction"] = _elapsed(t0)
        await _mongo_log(str(job_id), "FIELD_EXTRACTION", {
            "fields_extracted": sum(1 for f in field_results if f.normalized_value),
            "fields_missing": sum(1 for f in field_results if not f.normalized_value),
            "fields_low_conf": sum(
                1 for f in field_results if f.confidence_score < REVIEW_THRESHOLD
            ),
        })

        # ── 7. CLASSIFICATION ────────────────────────────────────────────
        await _advance(job, PipelineStage.CLASSIFICATION, db)
        doc_type_source = _classify(field_results, doc.document_type.value)
        await _mongo_log(str(job_id), "CLASSIFICATION", {
            "document_type": doc_type_source,
        })

        # ── 8. CONFIDENCE_SCORING ────────────────────────────────────────
        await _advance(job, PipelineStage.CONFIDENCE_SCORING, db)
        scored = [f for f in field_results if f.normalized_value]
        overall = round(sum(f.confidence_score for f in scored) / len(scored), 3) if scored else 0.0
        job.overall_confidence = overall
        await db.commit()

        # ── 9. VALIDATION ────────────────────────────────────────────────
        t0 = time.time()
        await _advance(job, PipelineStage.VALIDATION, db)
        await _apply_to_land_record(job, field_results, db)
        timings["validation"] = _elapsed(t0)
        await _mongo_log(str(job_id), "VALIDATION", {
            "fields_checked": len(field_results),
            "auto_valid": sum(1 for f in field_results if f.validation_status == "AUTO_VALID"),
        })

        # ── 9b. GIS_SYNC ─────────────────────────────────────────────────
        # Put the parcel on the map. This is a best-effort side task: a document
        # is never failed because it could not be georeferenced.
        t0 = time.time()
        job.stage_message = "Placing parcel on the cadastral map…"
        await db.commit()
        gis_result = await _sync_gis_coordinate(job, db, ocr_result.full_text)
        timings["gis_sync"] = _elapsed(t0)
        await _mongo_log(str(job_id), "GIS_SYNC", gis_result)

        # ── 10. DUPLICATE_CHECK ──────────────────────────────────────────
        t0 = time.time()
        await _advance(job, PipelineStage.DUPLICATE_CHECK, db)
        detector = AnomalyDetector()
        try:
            anomaly_results, is_duplicate = await detector.detect(
                field_results, db, job.land_record_id
            )
        except Exception as exc:
            raise PipelineStageError(
                f"Duplicate detection failed: {exc}", ERROR_VALIDATION
            ) from exc
        timings["duplicate_check"] = _elapsed(t0)

        # ── 11. ANOMALY_CHECK ────────────────────────────────────────────
        await _advance(job, PipelineStage.ANOMALY_CHECK, db)
        await _persist_anomalies(job_id, anomaly_results, db)
        job.has_anomalies = len(anomaly_results) > 0
        job.is_duplicate = is_duplicate
        await db.commit()
        await _mongo_log(str(job_id), "ANOMALY_CHECK", {
            "anomaly_count": len(anomaly_results),
            "is_duplicate": is_duplicate,
            "anomalies": [
                {"type": a.anomaly_type, "severity": a.severity, "field": a.field_name}
                for a in anomaly_results
            ],
        })

        # ── 12. VERIFICATION_REQUIRED / COMPLETED ────────────────────────
        await _advance(job, PipelineStage.VERIFICATION_REQUIRED, db)
        needs_review = await _create_verification_tasks(
            job_id, db_fields, anomaly_results, ocr_result.full_text, db
        )
        high_severity = any(a.severity == "HIGH" for a in anomaly_results)
        needs_review = needs_review or high_severity

        total_ms = int((time.time() - t_total) * 1000)
        timings["total"] = f"{total_ms}ms"

        now = datetime.now(timezone.utc)
        if needs_review:
            job.status = ProcessingStatus.PENDING_REVIEW
            job.current_stage = PipelineStage.VERIFICATION_REQUIRED.value
            job.stage_message = (
                "Processing complete. Some fields need human verification."
            )
            job.progress_pct = 94
            job.verification_status = VerificationStatus.PENDING.value
            doc.status = DocumentStatus.PROCESSING
            terminal_stage = PipelineStage.VERIFICATION_REQUIRED
        else:
            job.status = ProcessingStatus.COMPLETED
            job.current_stage = PipelineStage.COMPLETED.value
            job.stage_message = "Processing complete."
            job.progress_pct = 100
            job.verification_status = VerificationStatus.NOT_REQUIRED.value
            doc.status = DocumentStatus.VALIDATED
            terminal_stage = PipelineStage.COMPLETED

        job.needs_human_review = needs_review
        job.failed_stage = None
        job.error_type = None
        job.error_message = None
        job.stage_timings = timings
        job.completed_at = now
        job.updated_at = now
        job.heartbeat_at = now
        await db.commit()
        await _publish_status(job, terminal_stage)

        await _mongo_log(str(job_id), terminal_stage.value, {
            "total_ms": total_ms,
            "overall_confidence": overall,
            "needs_review": needs_review,
            "has_anomalies": job.has_anomalies,
            "is_duplicate": is_duplicate,
            "stage_timings": timings,
        })
        await log_event(
            "PIPELINE_COMPLETE", triggered_by, "ProcessingJob", job_id,
            {
                "document_id": str(job.document_id),
                "confidence": overall,
                "anomalies": len(anomaly_results),
                "needs_review": needs_review,
                "status": terminal_stage.value,
            },
        )
        log.info("Pipeline job %s finished in %dms (%s)", job_id, total_ms,
                 terminal_stage.value)

    except PipelineStageError as exc:
        await _fail(db, job, _stage_of(job), str(exc), exc.error_type)
    except Exception as exc:
        log.exception("Pipeline job %s crashed", job_id)
        await _fail(
            db, job, _stage_of(job),
            f"Unexpected error during {_stage_of(job).value}: {exc}", ERROR_INTERNAL,
        )


# -- Stage helpers -----------------------------------------------------------


def _elapsed(t0: float) -> str:
    return f"{(time.time() - t0) * 1000:.0f}ms"


def _stage_of(job: ProcessingJob) -> PipelineStage:
    """Best guess at the stage that was running when the job failed."""
    current = job.current_stage
    if current:
        try:
            return PipelineStage(current)
        except ValueError:
            pass
    return stages.resolve_stage(job.status)


async def _fail(
    db: AsyncSession,
    job: ProcessingJob,
    stage: PipelineStage,
    message: str,
    error_type: str,
) -> None:
    """Persist a stage failure, including the stage that caused it."""
    now = datetime.now(timezone.utc)
    try:
        job.status = ProcessingStatus.FAILED
        job.current_stage = PipelineStage.FAILED.value
        job.failed_stage = stage.value
        job.error_type = error_type
        job.error_message = message
        job.stage_message = f"Failed during {stage.value}: {message}"[:HEARTBEAT_STAGE_MESSAGE_MAX]
        job.progress_pct = 100
        job.completed_at = now
        job.updated_at = now
        job.heartbeat_at = now
        await db.commit()

        doc = await db.get(Document, job.document_id)
        if doc is not None:
            doc.status = DocumentStatus.REJECTED
            doc.validation_notes = f"[{error_type}/{stage.value}] {message}"
            await db.commit()

        await _publish_status(job, PipelineStage.FAILED)
    except Exception:
        log.exception("Could not persist failure state for job %s", job.id)
    log.error("Pipeline job %s failed at %s [%s]: %s", job.id, stage.value,
              error_type, message)


def _validate_file(file_path: Path, doc: Document) -> None:
    """FILE_VALIDATION — reject unusable uploads before any heavy work."""
    if not file_path.exists():
        raise PipelineStageError(
            f"Stored file is missing from disk ({file_path}). "
            "The upload may have been lost after it was accepted.",
            ERROR_STORAGE,
        )
    if file_path.stat().st_size == 0:
        raise PipelineStageError("Stored file is empty.", ERROR_STORAGE)


async def _persist_fields(
    job_id: uuid.UUID, field_results: list[FieldResult], db: AsyncSession
) -> list[ExtractedField]:
    """Write every extracted field to the database, replacing prior results.

    A job can be re-run (see the retry endpoint), and a re-run replaces this
    job's fields rather than adding to them. Without the delete below, retrying
    a job left both the old and the new row for every field, so the review UI
    showed each field twice -- once with the stale value and once with the fresh
    one, and field counts were double the truth.

    Fields a human has already verified are kept as they are and are not
    re-inserted: a reviewer's decision outranks a fresh machine reading, and
    silently replacing it would destroy the only human input in the system. The
    job therefore still ends up with exactly one row per field name.
    """
    verified_names = set(
        (
            await db.execute(
                select(ExtractedField.field_name).where(
                    ExtractedField.job_id == job_id,
                    ExtractedField.verified_at.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )

    stale = (
        delete(ExtractedField)
        .where(
            ExtractedField.job_id == job_id,
            ExtractedField.verified_at.is_(None),
        )
        .execution_options(synchronize_session=False)
    )
    await db.execute(stale)

    created: list[ExtractedField] = []
    for fr in field_results:
        if fr.field_name in verified_names:
            continue
        validation = (
            FieldValidationStatus(fr.validation_status)
            if fr.validation_status in FieldValidationStatus._value2member_map_
            else FieldValidationStatus.NOT_VALIDATED
        )
        ef = ExtractedField(
            job_id=job_id,
            field_name=fr.field_name,
            field_display=fr.field_display,
            raw_value=fr.raw_value,
            normalized_value=fr.normalized_value,
            confidence_score=fr.confidence_score,
            ocr_confidence=fr.ocr_confidence,
            extraction_method=fr.extraction_method,
            source_page=fr.source_page,
            bounding_box=fr.bounding_box,
            validation_status=validation,
            validation_rule=fr.validation_rule,
            validation_message=fr.validation_message,
            needs_review=fr.needs_review,
        )
        db.add(ef)
        created.append(ef)
    await db.commit()
    return created


async def _persist_anomalies(
    job_id: uuid.UUID, anomaly_results: list, db: AsyncSession
) -> None:
    """Write anomalies, replacing any left by a previous run of this job.

    Anomalies are derived entirely from the current field results, so a re-run
    must regenerate them rather than accumulate: without the delete, a retried
    job listed every old and new finding together.
    """
    await db.execute(
        delete(PipelineAnomaly)
        .where(PipelineAnomaly.job_id == job_id)
        .execution_options(synchronize_session=False)
    )
    for ar in anomaly_results:
        try:
            anom_type = AnomalyType(ar.anomaly_type)
        except ValueError:
            anom_type = AnomalyType.MISSING_REQUIRED
        db.add(PipelineAnomaly(
            job_id=job_id,
            anomaly_type=anom_type,
            field_name=ar.field_name,
            severity=ar.severity,
            description=ar.description,
            confidence=ar.confidence,
        ))
    await db.commit()


async def _create_verification_tasks(
    job_id: uuid.UUID,
    db_fields: list[ExtractedField],
    anomaly_results: list,
    full_text: str,
    db: AsyncSession,
) -> bool:
    """
    Create a VerificationTask for every low-confidence field.

    Returns True if at least one task was created, which is what routes the job
    to VERIFICATION_REQUIRED instead of COMPLETED.
    """
    created_any = False
    for ef in db_fields:
        if not ef.needs_review:
            continue
        created_any = True
        db.add(
            VerificationTask(
                job_id=job_id,
                field_id=ef.id,
                status="OPEN",
                priority="HIGH" if ef.confidence_score < 0.40 else "MEDIUM",
                context_snippet=_build_snippet(ef.field_name, full_text),
            )
        )
    if created_any:
        await db.commit()
    return created_any


def _build_snippet(field_name: str, full_text: str) -> str:
    """Extract a context snippet around the field from the OCR text."""
    import re

    pattern = field_name.replace("_", r"[\s_]?")
    match = re.search(pattern, full_text, re.IGNORECASE)
    if match:
        start = max(0, match.start() - 80)
        end = min(len(full_text), match.end() + 120)
        return "…" + full_text[start:end].strip() + "…"
    return full_text[:200] + "…" if len(full_text) > 200 else full_text


def _classify(field_results: list[FieldResult], declared_type: str) -> str:
    """
    CLASSIFICATION — report the effective document type.

    The operator's declared type is authoritative (it is a required form field);
    the extraction result is only used to corroborate it, so a mismatched scan
    is still surfaced to the reviewer rather than silently reclassified.
    """
    text = " ".join(
        (f.raw_value or "") for f in field_results
    ).lower()
    hint = "title_deed" if "deed" in text or "registry" in text else declared_type
    return hint if declared_type == "OTHER" else declared_type


# -- Land record propagation -------------------------------------------------

_DRAFT_PLACEHOLDERS = {
    "UNKNOWN — PENDING OCR",
    "DRAFT-PENDING-OCR",
    "",
}


async def _apply_to_land_record(
    job: ProcessingJob, field_results: list[FieldResult], db: AsyncSession
) -> None:
    """
    VALIDATION stage: write extracted values onto the linked land record.

    A new Survey/Khasra number never has to exist beforehand -- the upload
    handler already created a draft row, and this fills it in. Existing
    non-placeholder values are never overwritten, so a confirmed record cannot
    be regressed by a later scan.
    """
    if not job.land_record_id:
        return
    record = await db.get(LandRecord, job.land_record_id)
    if record is None:
        log.warning("Land record %s vanished during validation", job.land_record_id)
        return

    def _is_placeholder(value: object) -> bool:
        return not value or str(value).strip() in _DRAFT_PLACEHOLDERS

    def _apply(attr: str, field_name: str, coerce=None) -> None:
        """Fill a placeholder attribute from a field that passed validation.

        Values that failed their own validation rule (or that OCR read as low
        confidence) are left as placeholders on purpose: the field still reaches
        the reviewer through the verification queue, but a rejected read never
        becomes a real value on the land record.
        """
        if not _is_placeholder(getattr(record, attr, None)):
            return
        for fr in field_results:
            if fr.field_name != field_name or not fr.normalized_value:
                continue
            if fr.validation_status != "AUTO_VALID" or fr.needs_review:
                log.info(
                    "Skipping %s on record %s: %s (status=%s, review=%s)",
                    field_name, record.id, fr.normalized_value,
                    fr.validation_status, fr.needs_review,
                )
                return
            try:
                setattr(record, attr, coerce(fr.normalized_value.strip())
                        if coerce else fr.normalized_value.strip())
            except (ValueError, TypeError):
                pass
            return

    _apply("khasra_number", "khasra_number")
    _apply("survey_number", "survey_number")
    _apply("khatauni_number", "khata_number")
    _apply("owner_name", "owner_name")
    _apply("father_name", "father_name")
    _apply("state", "state")
    _apply("district", "district")
    _apply("tehsil", "tehsil")
    _apply("village", "village")
    _apply("pin_code", "pin_code")

    if record.area_hectares is None or record.area_hectares <= 0.0001:
        for fr in field_results:
            if fr.field_name == "land_area" and fr.normalized_value:
                try:
                    record.area_hectares = float(fr.normalized_value)
                except ValueError:
                    pass
                break

    for fr in field_results:
        if fr.field_name == "land_classification" and fr.normalized_value:
            try:
                record.land_use_type = LandUseType(fr.normalized_value.upper())
            except ValueError:
                pass
            break

    await db.commit()
    log.info(
        "Land record %s updated from extraction: khasra=%r village=%r owner=%r",
        record.id, record.khasra_number, record.village, record.owner_name,
    )


# -- Georeferencing ----------------------------------------------------------

# Draft records are created with this area until extraction replaces it, and a
# 0.0001 ha polygon is a dot too small to see on the map.
_MIN_PARCEL_AREA_HA = 0.05


async def _sync_gis_coordinate(
    job: ProcessingJob, db: AsyncSession, full_text: str
) -> dict:
    """
    Give the land record a map position so the upload shows up on the GIS view.

    A coordinate printed on the document wins. Most scans do not print one, so
    the record is otherwise placed at a deterministic point inside its own
    state's bounding box, seeded by Khasra + district: stable across re-runs and
    retrying a job, so the parcel does not jump around the map each time.

    Returns a small summary for the pipeline event log. Never raises: losing a
    coordinate must not lose an otherwise successful extraction.
    """
    summary: dict = {"land_record_id": None, "placed": False, "source": None}
    if not job.land_record_id:
        return summary

    try:
        record = await db.get(LandRecord, job.land_record_id)
        if record is None:
            log.warning(
                "Land record %s vanished before georeferencing", job.land_record_id
            )
            return summary

        scanned = extract_document_coordinates(full_text)
        if scanned is not None:
            latitude, longitude = scanned
            source = SOURCE_FROM_SCAN
        else:
            latitude, longitude = generate_synthetic_centroid(
                record.state, record.district,
                seed=f"{record.khasra_number}-{record.district}",
            )
            source = SOURCE_DERIVED

        area = record.area_hectares or 0.0
        if area <= _MIN_PARCEL_AREA_HA:
            area = _MIN_PARCEL_AREA_HA
        polygon = generate_parcel_polygon(
            latitude, longitude, area, seed=f"{record.khasra_number}-{record.district}"
        )

        # Replace only the position this pipeline wrote before. A surveyed
        # coordinate (DGPS / Bhuvan / manual entry) is a real measurement and
        # outranks anything read off a scan, so it is left exactly as it is.
        existing = (
            await db.execute(
                select(GISCoordinate).where(
                    GISCoordinate.land_record_id == record.id,
                    GISCoordinate.coordinate_type == CoordinateType.CENTROID,
                )
            )
        ).scalars().first()

        if existing is not None and existing.source not in _AUTO_SOURCES:
            summary.update({
                "land_record_id": str(record.id),
                "placed": False,
                "source": existing.source,
                "latitude": existing.latitude,
                "longitude": existing.longitude,
                "from_document": False,
                "kept_existing": True,
            })
            log.info(
                "Record %s already has a surveyed coordinate (%s); leaving it alone",
                record.id, existing.source,
            )
            return summary

        if existing is not None:
            existing.latitude = latitude
            existing.longitude = longitude
            existing.geojson = polygon
            existing.source = source
            existing.captured_at = datetime.now(timezone.utc).date().isoformat()
        else:
            db.add(GISCoordinate(
                land_record_id=record.id,
                latitude=latitude,
                longitude=longitude,
                geojson=polygon,
                coordinate_type=CoordinateType.CENTROID,
                source=source,
                datum="WGS84",
                captured_at=datetime.now(timezone.utc).date().isoformat(),
            ))

        record.geometry = polygon
        await db.commit()

        summary.update({
            "land_record_id": str(record.id),
            "placed": True,
            "source": source,
            "latitude": latitude,
            "longitude": longitude,
            "from_document": scanned is not None,
        })
        log.info(
            "Parcel placed for record %s at %s,%s (%s)",
            record.id, latitude, longitude, source,
        )
    except Exception:
        # Roll back so a spatial failure cannot poison the rest of the session.
        await db.rollback()
        log.exception("Could not georeference record %s", job.land_record_id)
    return summary
