"""
End-to-end check of the asynchronous upload pipeline.

Runs the real pipeline against the real services: a real image on disk, real
Tesseract, real PostgreSQL rows and the real Redis queue. Nothing is mocked.

Usage:
    python -m scripts.e2e_upload [path-to-image]
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.postgres import async_session_maker  # noqa: E402
from app.models.document import Document, DocumentStatus  # noqa: E402
from app.models.land_record import (  # noqa: E402
    LandRecord, LandUseType, RecordStatus,
)
from app.models.pipeline import (  # noqa: E402
    ExtractedField, PipelineAnomaly, ProcessingJob, VerificationTask,
)
from app.models.user import User, RoleEnum  # noqa: E402
from app.services.job_queue import enqueue  # noqa: E402
from app.services.pipeline_stages import JobState, state_for  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
# SQLAlchemy's own engine logging drowns out the pipeline stage lines; the run
# output is meant to be read, so it is quietened to WARNING.
for noisy in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.pool",
              "sqlalchemy.dialects", "asyncpg", "aiosqlite"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

log = logging.getLogger("e2e")

TEST_IMAGE = Path(
    r"C:\Users\Admin\AppData\Local\Temp\opencode\test_khasra.png"
)


def _banner(text: str) -> None:
    print(f"\n{'=' * 74}\n{text}\n{'=' * 74}")


async def _ensure_user(db) -> User:
    user = (
        await db.execute(
            __import__("sqlalchemy").select(User).where(
                User.username == "e2e_officer"
            )
        )
    ).scalar_one_or_none()
    if user is None:
        from app.core.security import hash_password

        user = User(
            id=uuid.uuid4(),
            username="e2e_officer",
            email="e2e_officer@demo.in",
            full_name="E2E Officer",
            hashed_password=hash_password("E2ePass@123"),
            role=RoleEnum.OFFICER,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def run(image_path: Path) -> int:
    if not image_path.exists():
        log.error("Test image not found: %s", image_path)
        return 1

    _banner("1. Verifying the real OCR engine is available")
    from app.services.ocr_service import (
        _available_languages, _resolve_tesseract_cmd, get_ocr_backend,
    )

    cmd = _resolve_tesseract_cmd()
    if not cmd:
        log.error("Tesseract binary not found — refusing to run a fake pipeline")
        return 1
    backend = get_ocr_backend()
    if backend.name == "mock":
        log.error("Mock OCR backend selected — this E2E must use real OCR")
        return 1
    log.info("Tesseract: %s", cmd)
    log.info("Language packs: %s", sorted(_available_languages()))
    log.info("Backend: %s (real)", backend.name)

    _banner("2. Redis queue health")
    from app.services.job_queue import queue_depth, queue_is_healthy_async

    if not await queue_is_healthy_async():
        log.error("Redis is not reachable — the queue is required for this test")
        return 1
    log.info("Queue depth before upload: %d", await queue_depth())

    _banner("3. Creating document + QUEUED job (what the upload handler does)")
    async with async_session_maker() as db:
        from sqlalchemy import select as sa_select

        user = await _ensure_user(db)

        # A genuinely blank draft, exactly as POST /intake/upload creates it.
        # Pre-filling real values would make the "did OCR write the record?"
        # assertion pass without the pipeline writing anything at all.
        from app.routers.intake import _DRAFT_PLACEHOLDER

        record = (
            await db.execute(
                sa_select(LandRecord).where(
                    LandRecord.khasra_number == "E2E-DRAFT-BLANK"
                )
            )
        ).scalar_one_or_none()
        if record is None:
            record = LandRecord(
                id=uuid.uuid4(),
                khasra_number="E2E-DRAFT-BLANK",
                state=_DRAFT_PLACEHOLDER,
                district=_DRAFT_PLACEHOLDER,
                tehsil=_DRAFT_PLACEHOLDER,
                village=_DRAFT_PLACEHOLDER,
                owner_name=_DRAFT_PLACEHOLDER,
                area_hectares=0.0001,
                land_use_type=LandUseType.AGRICULTURAL,
                status=RecordStatus.PENDING,
                created_by=user.id,
            )
            db.add(record)
            await db.flush()
        else:
            # Reset to placeholder state so a rerun still tests the write path.
            for attr in ("state", "district", "tehsil", "village", "owner_name"):
                setattr(record, attr, _DRAFT_PLACEHOLDER)
            record.area_hectares = 0.0001
            await db.flush()
        log.info("Draft record %s created with placeholder values", record.id)

        doc = Document(
            id=uuid.uuid4(),
            land_record_id=record.id,
            document_type="SURVEY_MAP",
            original_filename=image_path.name,
            stored_path=str(image_path),
            file_size_bytes=image_path.stat().st_size,
            mime_type="image/png",
            status=DocumentStatus.PROCESSING,
            uploaded_by=user.id,
        )
        db.add(doc)
        await db.flush()

        job = ProcessingJob(
            document_id=doc.id,
            land_record_id=record.id,
            status="QUEUED",
            current_stage="QUEUED",
            stage_message="Upload accepted. Waiting for a processing worker…",
            progress_pct=0,
            triggered_by=user.id,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        job_id, doc_id, record_id = job.id, doc.id, record.id
        log.info("document_id = %s", doc_id)
        log.info("job_id      = %s", job_id)
        log.info("status      = %s (this is the state a 202 returns)", job.status.value)

    depth = await enqueue(job_id, None)
    log.info("Enqueued. Queue depth is now %d — a 202 returns at this point.", depth)

    _banner("4. Draining the queue exactly as `python -m app.worker` does")
    from app.worker import Worker

    worker = Worker(concurrency=1)
    t0 = time.time()
    await worker.run(once=True)
    elapsed = time.time() - t0
    log.info("Worker finished in %.2fs", elapsed)

    _banner("5. Final persisted state")
    async with async_session_maker() as db:
        from sqlalchemy import func, select as sa_select

        job = await db.get(ProcessingJob, job_id)
        doc = await db.get(Document, doc_id)
        record = await db.get(LandRecord, record_id)

        state = state_for(job.status)
        log.info("job.status             = %s", job.status.value)
        log.info("job.current_stage      = %s", job.current_stage)
        log.info("job.failed_stage       = %s", job.failed_stage)
        log.info("job.error_type         = %s", job.error_type)
        log.info("job.error_message      = %s", job.error_message)
        log.info("job.progress_pct       = %s", job.progress_pct)
        log.info("job.started_at         = %s", job.started_at)
        log.info("job.completed_at       = %s", job.completed_at)
        log.info("job.overall_confidence = %s", job.overall_confidence)
        log.info("job.detected_language  = %s", job.detected_language)
        log.info("job.page_count         = %s", job.page_count)
        log.info("job.has_anomalies      = %s", job.has_anomalies)
        log.info("job.needs_human_review = %s", job.needs_human_review)
        log.info("job.verification_status= %s", job.verification_status)
        log.info("job.stage_timings      = %s", job.stage_timings)
        log.info("document.status        = %s", doc.status.value)
        log.info("land_record.owner_name = %r", record.owner_name)
        log.info("land_record.village    = %r", record.village)
        log.info("land_record.area_ha    = %s", record.area_hectares)
        log.info("land_record.status     = %s", record.status.value)

        fields = (
            await db.execute(
                sa_select(ExtractedField).where(ExtractedField.job_id == job_id)
            )
        ).scalars().all()
        log.info("extracted fields       = %d", len(fields))
        for f in fields:
            if f.normalized_value:
                log.info(
                    "   %-24s = %-34s conf=%.2f src=%s",
                    f.field_name,
                    str(f.normalized_value)[:34],
                    f.confidence_score or 0.0,
                    f.extraction_method,
                )

        anomalies = (
            await db.execute(
                sa_select(PipelineAnomaly).where(PipelineAnomaly.job_id == job_id)
            )
        ).scalars().all()
        log.info("anomalies persisted    = %d", len(anomalies))
        for a in anomalies:
            log.info("   [%s] %s: %s", a.severity, a.anomaly_type, a.description)

        tasks = (
            await db.execute(
                sa_select(VerificationTask).where(VerificationTask.job_id == job_id)
            )
        ).scalars().all()
        log.info("verification tasks     = %d", len(tasks))

        open_tasks = (
            await db.scalar(
                sa_select(func.count())
                .select_from(VerificationTask)
                .where(VerificationTask.job_id == job_id, VerificationTask.status == "OPEN")
            )
        ) or 0

    _banner("6. Assertions")
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        log.info("%-46s %s%s", label, "PASS" if ok else "FAIL", f" — {detail}" if detail else "")
        if not ok:
            failures.append(label)

    check("Reached a terminal state", state in {JobState.COMPLETED, JobState.VERIFICATION_REQUIRED}, state.value)
    check("Did not fall over to FAILED", state is not JobState.FAILED)
    check("started_at was stamped", job.started_at is not None)
    check("completed_at was stamped", job.completed_at is not None)
    check("Reached the last stage", job.current_stage in {"COMPLETED", "VERIFICATION_REQUIRED"}, str(job.current_stage))
    check("Confidence was scored", job.overall_confidence is not None, f"overall={job.overall_confidence}")
    check("Extracted fields persisted", len(fields) > 0, f"{len(fields)} fields")
    check("Real OCR produced text", job.detected_language is not None, f"lang={job.detected_language}")
    check("A stage failed is not silently swallowed", state is not JobState.FAILED or job.failed_stage is not None)

    # The draft started as "UNKNOWN — PENDING OCR", so a real value here can only
    # have come from the OCR extraction stage.
    from app.routers.intake import _DRAFT_PLACEHOLDER

    check(
        "Land record was updated from OCR",
        record.owner_name not in (None, "", _DRAFT_PLACEHOLDER),
        f"owner={record.owner_name!r}",
    )
    check(
        "Land record geography came from OCR",
        record.village not in (None, "", _DRAFT_PLACEHOLDER),
        f"village={record.village!r}, district={record.district!r}",
    )
    check(
        "Land area came from OCR",
        record.area_hectares and record.area_hectares > 0.0001,
        f"area={record.area_hectares}",
    )
    check(
        "Verification state matches open tasks",
        (open_tasks > 0) == (state is JobState.VERIFICATION_REQUIRED),
        f"open_tasks={open_tasks}, state={state.value}",
    )

    _banner("RESULT")
    if failures:
        log.error("%d check(s) failed:", len(failures))
        for f in failures:
            log.error("  - %s", f)
        return 1
    log.info("All checks passed. Real OCR -> real extraction -> real persistence, via the queue.")
    return 0


async def _run_and_dispose(image: Path) -> int:
    """Run the test, then release every pooled connection on the same loop.

    Disposing outside this loop would try to close sockets from an already-closed
    event loop, which is what produces the noisy asyncpg/redis teardown errors.
    """
    from app.db.postgres import engine

    try:
        return await run(image)
    finally:
        await engine.dispose()
        try:
            from app.db.redis_client import close_redis

            await close_redis()
        except Exception:
            pass


def main() -> int:
    image = Path(sys.argv[1]) if len(sys.argv) > 1 else TEST_IMAGE
    return asyncio.run(_run_and_dispose(image))


if __name__ == "__main__":
    sys.exit(main())
