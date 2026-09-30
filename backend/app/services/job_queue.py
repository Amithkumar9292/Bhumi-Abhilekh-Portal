"""
Redis-backed background job queue for document processing.

Why this exists
---------------
Document upload must answer the HTTP request immediately. OCR on a multi-page
PDF routinely takes 30-120 s, which is far longer than any sensible client or
proxy timeout, so it can never live inside the request. The upload handler does
only fast work (authenticate -> validate -> persist -> create rows), enqueues
the job id here, and returns ``202 Accepted``.

The queue is a plain Redis list, consumed with a reliable ``BRPOPLPUSH`` so a
worker crash mid-job leaves the payload in a ``processing`` list instead of
losing it. The same list powers both modes already present in this project:

* a dedicated worker process -- ``python -m app.worker`` (recommended, and what
  production should run), and
* an in-process ``asyncio`` task started by the API server, used as a fallback
  when Redis is unreachable so an upload is never rejected because the queue is
  down.

Status is mirrored into Redis under ``pipeline:job:{job_id}`` for cheap polling
by the status endpoints, with PostgreSQL remaining the source of truth.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings

log = logging.getLogger(__name__)

# Queue payloads are intentionally tiny: identifiers only, never file contents.
QUEUE_MESSAGE_VERSION = 1


@dataclass(frozen=True)
class JobMessage:
    """A unit of queued work. Only identifiers -- the worker reloads the rest."""

    job_id: uuid.UUID
    triggered_by: Optional[uuid.UUID] = None
    attempts: int = 0
    enqueued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        return json.dumps(
            {
                "v": QUEUE_MESSAGE_VERSION,
                "job_id": str(self.job_id),
                "triggered_by": str(self.triggered_by) if self.triggered_by else None,
                "attempts": self.attempts,
                "enqueued_at": self.enqueued_at,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "JobMessage":
        data = json.loads(raw)
        return cls(
            job_id=uuid.UUID(data["job_id"]),
            triggered_by=uuid.UUID(data["triggered_by"]) if data.get("triggered_by") else None,
            attempts=int(data.get("attempts", 0)),
            enqueued_at=data.get("enqueued_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(frozen=True)
class DeliveredJob:
    """
    A job plus the exact payload it occupies in the processing list.

    The raw payload is required to acknowledge safely: with several workers
    running, the processing list is shared, so removing the *oldest* entry on
    completion could drop a different worker's job. ``LREM`` on this specific
    value only ever removes this one.
    """

    message: JobMessage
    raw: str


# Each consumer process gets its own processing list, so a worker that dies
# strands its jobs in a list no other worker touches. That makes recovery
# well-defined even with many workers draining the queue at once.
def processing_key(consumer: str) -> str:
    return f"{settings.job_queue_processing_key}:{consumer}"


# -- Queue transport ---------------------------------------------------------


class QueueUnavailable(RuntimeError):
    """Raised when the Redis queue cannot accept work."""


def queue_is_healthy() -> bool:
    """Cheap non-blocking probe used by /health and diagnostics."""
    import redis

    client = redis.Redis.from_url(
        settings.redis_url, socket_connect_timeout=0.25, socket_timeout=0.25
    )
    try:
        return bool(client.ping())
    except Exception:
        return False
    finally:
        try:
            client.close()
        except Exception:
            pass


async def enqueue(
    job_id: uuid.UUID,
    triggered_by: Optional[uuid.UUID] = None,
    attempts: int = 0,
) -> int:
    """
    Push a job id onto the Redis queue.

    Returns the resulting queue depth. Raises :class:`QueueUnavailable` if the
    queue cannot be reached, so the caller can decide whether to fall back.
    """
    message = JobMessage(job_id=job_id, triggered_by=triggered_by, attempts=attempts)
    from app.db.redis_client import get_redis

    try:
        redis = await get_redis()
        depth = await redis.rpush(settings.job_queue_key, message.to_json())
    except Exception as exc:  # includes redis.ConnectionError / TimeoutError
        raise QueueUnavailable(str(exc)) from exc
    return int(depth or 0)


async def queue_depth() -> int:
    try:
        from app.db.redis_client import get_redis

        return int(await (await get_redis()).llen(settings.job_queue_key))
    except Exception:
        return -1


async def recover_orphans() -> int:
    """
    Re-queue payloads stranded in processing lists by dead workers.

    Recovery consults PostgreSQL rather than assuming every stranded payload is
    dead: a job still marked as running (a live worker, possibly a slow OCR) is
    left alone so starting another worker never duplicates work. Only jobs the
    database shows as not-running are returned to the queue.
    """
    from app.db.redis_client import get_redis

    try:
        redis = await get_redis()
    except Exception as exc:
        log.warning("Orphan recovery skipped: %s", exc)
        return 0

    try:
        candidates: list[str] = []
        pattern = f"{settings.job_queue_processing_key}*"
        for key in await redis.keys(pattern):
            # The legacy shared list (no consumer suffix) is included too.
            candidates.extend(await redis.lrange(key, 0, -1))
        if not candidates:
            return 0

        requeueable = await _partition_recoverable(candidates)
        if not requeueable:
            log.info(
                "Found %d stranded payload(s) but all are still marked running "
                "in the database; leaving them alone", len(candidates),
            )
            return 0

        moved = 0
        for raw in requeueable:
            if await redis.lrem(
                settings.job_queue_processing_key, 1, raw
            ) or await _remove_from_any_processing_list(redis, raw):
                await redis.rpush(settings.job_queue_key, raw)
                moved += 1
        if moved:
            log.warning("Recovered %d orphaned job(s) from processing lists", moved)
        return moved
    except Exception as exc:
        log.warning("Orphan recovery skipped: %s", exc)
        return 0


async def _remove_from_any_processing_list(redis: Any, raw: str) -> int:
    """LREM a payload from whichever per-consumer list currently holds it."""
    for key in await redis.keys(f"{settings.job_queue_processing_key}*"):
        if await redis.lrem(key, 1, raw):
            return 1
    return 0


async def _partition_recoverable(raws: list[str]) -> list[str]:
    """
    Split stranded payloads into recoverable and still-owned.

    Status alone is not enough: a worker that dies before its first stage commit
    leaves the job at ``QUEUED``, which must be recoverable. The reliable signal
    is the heartbeat, refreshed on every stage, so a job whose last heartbeat is
    older than the lease is treated as abandoned.
    """
    from app.db.postgres import async_session_maker
    from app.models.pipeline import ProcessingJob

    recoverable: list[str] = []
    for raw in raws:
        try:
            message = JobMessage.from_json(raw)
        except Exception:
            # Unparsable payloads can never succeed; dropping them is correct.
            recoverable.append(raw)
            continue
        try:
            async with async_session_maker() as db:
                job = await db.get(ProcessingJob, message.job_id)
                if job is None:
                    continue  # Row is gone; nothing to process.
                if _lease_is_live(job.heartbeat_at):
                    continue  # A worker is very likely still on it.
                recoverable.append(raw)
        except Exception as exc:
            log.debug("Could not inspect stranded job %s: %s", message.job_id, exc)
            # Cannot prove it is alive, so let recovery try rather than lose it.
            recoverable.append(raw)
    return recoverable


def _lease_is_live(heartbeat_at: Any) -> bool:
    """True when a heartbeat was written recently enough to mean 'in progress'."""
    if heartbeat_at is None:
        return False
    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - heartbeat_at).total_seconds()
    return age < settings.job_lease_ttl_s


# -- Status mirror -----------------------------------------------------------


async def publish_status(job_id: uuid.UUID | str, payload: dict[str, Any]) -> None:
    """Mirror the current job status into Redis for cheap status polling."""
    from app.db.redis_client import get_redis

    try:
        redis = await get_redis()
        key = f"{settings.job_queue_status_prefix}:{job_id}"
        await redis.set(key, json.dumps(payload, default=str), ex=settings.job_status_ttl_s)
    except Exception as exc:
        # Status mirroring is an optimisation; the DB is authoritative.
        log.debug("Status mirror skipped for job %s: %s", job_id, exc)


async def read_status(job_id: uuid.UUID | str) -> Optional[dict[str, Any]]:
    from app.db.redis_client import get_redis

    try:
        redis = await get_redis()
        raw = await redis.get(f"{settings.job_queue_status_prefix}:{job_id}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


# -- Consumers ---------------------------------------------------------------


async def pop_blocking(
    timeout_s: Optional[float] = None, consumer: str = "default"
) -> Optional[DeliveredJob]:
    """
    Reliably pop one job.

    Uses ``BRPOPLPUSH`` onto this consumer's processing list so an interrupted
    worker never loses a job. Returns ``None`` on timeout.
    """
    from app.db.redis_client import get_redis

    timeout = settings.job_queue_block_timeout_s if timeout_s is None else timeout_s
    redis = await get_redis()
    raw = await redis.brpoplpush(
        settings.job_queue_key,
        processing_key(consumer),
        timeout=timeout,
    )
    if not raw:
        return None
    try:
        return DeliveredJob(message=JobMessage.from_json(raw), raw=raw)
    except Exception as exc:
        log.error("Discarding unparsable queue payload: %s", exc)
        await acknowledge(raw, consumer)
        return None


async def acknowledge(raw: Optional[str] = None, consumer: str = "default") -> None:
    """
    Remove exactly this payload from its processing list.

    Uses ``LREM`` rather than ``LPOP`` so a finishing worker can never delete a
    different worker's in-flight job from the shared list.
    """
    if not raw:
        return
    from app.db.redis_client import get_redis

    try:
        redis = await get_redis()
        removed = await redis.lrem(processing_key(consumer), 1, raw)
        if not removed:
            removed = await _remove_from_any_processing_list(redis, raw)
        if not removed:
            log.debug("Acknowledge found no matching payload to remove")
    except Exception as exc:
        log.debug("Acknowledge failed: %s", exc)


async def requeue(message: JobMessage) -> bool:
    """Put a job back on the queue (used when the worker itself cannot run)."""
    try:
        await enqueue(message.job_id, message.triggered_by, message.attempts + 1)
        return True
    except QueueUnavailable:
        return False


async def requeue_raw(raw: str) -> bool:
    """Return a raw payload to the queue without re-encoding it."""
    from app.db.redis_client import get_redis

    try:
        redis = await get_redis()
        await redis.rpush(settings.job_queue_key, raw)
        return True
    except Exception as exc:
        log.error("Could not requeue payload: %s", exc)
        return False


class InProcessRunner:
    """
    Fallback consumer for deployments without a separate worker process.

    Consumes the same Redis queue, so once a real worker is started it will
    simply pick up whatever this runner has not already taken. If Redis is down
    it executes the job directly in the API process, which keeps single-process
    deployments functional at the cost of not surviving a restart.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._runner: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()
        self.consumer = f"api-{uuid.uuid4().hex[:8]}"

    @property
    def running(self) -> bool:
        return self._runner is not None and not self._runner.done()

    def start(self) -> None:
        if self.running:
            return
        self._stopping.clear()
        self._runner = asyncio.create_task(self._loop(), name="in-process-job-runner")
        log.info("In-process job runner started (Redis queue: %s)", settings.redis_url)

    async def stop(self) -> None:
        self._stopping.set()
        if self._runner is not None:
            self._runner.cancel()
            try:
                await self._runner
            except (asyncio.CancelledError, Exception):
                pass
            self._runner = None
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _loop(self) -> None:
        # Don't compete with an externally managed worker.
        if await queue_is_healthy_async() and settings.job_queue_fallback_to_process is False:
            return
        while not self._stopping.is_set():
            try:
                job = await pop_blocking(timeout_s=1, consumer=self.consumer)
            except QueueUnavailable:
                log.warning(
                    "Redis queue unavailable; in-process runner will rely on direct execution"
                )
                await asyncio.sleep(5)
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("In-process runner poll failed: %s", exc)
                await asyncio.sleep(2)
                continue

            if job is None:
                continue
            await self._dispatch(job)

    async def _dispatch(self, job: DeliveredJob) -> None:
        task = asyncio.create_task(self._execute(job), name=f"job-{job.message.job_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _execute(self, job: DeliveredJob) -> None:
        from app.services.document_processor import run_pipeline

        try:
            await run_pipeline(job.message.job_id, job.message.triggered_by)
        except asyncio.CancelledError:
            # Shutting down: put the work back so a real worker can take it.
            log.warning("Job %s cancelled — requeueing", job.message.job_id)
            await acknowledge(job.raw, self.consumer)
            await requeue_raw(job.raw)
            raise
        except Exception as exc:  # run_pipeline already records failures
            log.error("In-process job %s crashed: %s", job.message.job_id, exc)
        finally:
            if not self._stopping.is_set():
                await acknowledge(job.raw, self.consumer)


async def queue_is_healthy_async() -> bool:
    """Async Redis probe with a tight timeout (no event-loop blocking)."""
    from app.db.redis_client import get_redis

    try:
        redis = await get_redis()
        return bool(await asyncio.wait_for(redis.ping(), timeout=1.0))
    except Exception:
        return False
