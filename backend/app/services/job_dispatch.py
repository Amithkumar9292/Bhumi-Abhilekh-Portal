"""
Job dispatch -- the single place a ProcessingJob is handed to a worker.

Upload handlers call :func:`dispatch_job` after committing their rows. It never
runs the pipeline inline, so the caller's response is unaffected by how long OCR
takes.

Two paths, in order of preference:

1. **Redis queue** -- push the job id and return. A worker
   (``python -m app.worker``) picks it up. This is the production path: the job
   survives an API restart and can be scaled independently.
2. **In-process task** -- used when Redis is unreachable and
   ``JOB_QUEUE_FALLBACK_TO_PROCESS`` allows it. Keeps single-process
   deployments working; the caller is told so it can report it.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from app.config import settings
from app.services import job_queue

log = logging.getLogger(__name__)

# In-process jobs are tracked so the event loop does not garbage-collect them.
_local_tasks: set[asyncio.Task] = set()


def _spawn_local(job_id: uuid.UUID, triggered_by: Optional[uuid.UUID]) -> None:
    """Run the pipeline in this process as a detached task."""

    async def _run() -> None:
        from app.services.document_processor import run_pipeline

        try:
            await run_pipeline(job_id, triggered_by)
        except Exception as exc:
            log.error("Local pipeline job %s crashed: %s", job_id, exc)

    task = asyncio.create_task(_run(), name=f"local-pipeline-{job_id}")
    _local_tasks.add(task)
    task.add_done_callback(_local_tasks.discard)


async def dispatch_job(
    job_id: uuid.UUID,
    triggered_by: Optional[uuid.UUID] = None,
) -> dict:
    """
    Queue a pipeline job. Returns a small report describing what happened so the
    HTTP handler can surface an honest status to the client.
    """
    try:
        depth = await job_queue.enqueue(job_id, triggered_by)
    except job_queue.QueueUnavailable as exc:
        if not settings.job_queue_fallback_to_process:
            log.error("Redis queue unavailable and fallback disabled: %s", exc)
            return {
                "queued": False,
                "runner": "none",
                "detail": "The processing queue is unavailable. Please retry shortly.",
            }
        log.warning(
            "Redis queue unavailable (%s) - running job %s in the API process. "
            "Start a worker (python -m app.worker) and ensure Redis is reachable "
            "for durable processing.", exc, job_id,
        )
        _spawn_local(job_id, triggered_by)
        return {
            "queued": True,
            "runner": "in-process",
            "queue_depth": -1,
            "detail": "Processing started in-process; the job will not survive a restart.",
        }

    return {
        "queued": True,
        "runner": "redis-queue",
        "queue_depth": depth,
        "detail": "Job queued for background processing.",
    }


async def record_queue_failure(job_id: uuid.UUID, detail: str) -> None:
    """
    Mark a job as failed because it could not be handed to a worker.

    A job left in ``QUEUED`` with nothing consuming the queue would show
    "processing" forever, so the failure is persisted instead.
    """
    from app.db.postgres import async_session_maker
    from app.models.document import Document, DocumentStatus
    from app.models.pipeline import ProcessingJob, ProcessingStatus
    from app.services.pipeline_stages import PipelineStage
    from datetime import datetime, timezone

    try:
        async with async_session_maker() as db:
            job = await db.get(ProcessingJob, job_id)
            if job is None or job.status == ProcessingStatus.COMPLETED:
                return
            now = datetime.now(timezone.utc)
            job.status = ProcessingStatus.FAILED
            job.failed_stage = PipelineStage.QUEUED.value
            job.current_stage = PipelineStage.FAILED.value
            job.error_type = "QUEUE"
            job.error_message = detail[:2000]
            job.stage_message = "Could not queue processing."
            job.progress_pct = 100
            job.completed_at = now
            job.heartbeat_at = now
            job.updated_at = now

            doc = await db.get(Document, job.document_id)
            if doc is not None and doc.status == DocumentStatus.PROCESSING:
                doc.status = DocumentStatus.REJECTED
                doc.validation_notes = f"[QUEUE] {detail}"
            await db.commit()
    except Exception as exc:
        log.error("Could not record queue failure for job %s: %s", job_id, exc)


async def shutdown_local_jobs(timeout_s: float = 5.0) -> None:
    """Cancel in-process pipeline tasks during application shutdown."""
    if not _local_tasks:
        return
    log.info("Cancelling %d in-process pipeline task(s)", len(_local_tasks))
    for task in list(_local_tasks):
        task.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(*_local_tasks, return_exceptions=True), timeout=timeout_s
        )
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass
    _local_tasks.clear()
