"""
Background worker for document processing.

The API server only ever *enqueues* processing jobs; this process drains the
Redis queue and runs the OCR/AI pipeline. Keeping it separate is what makes
upload fast and reliable: OCR for a multi-page PDF can take minutes, which no
HTTP request (or serverless invocation) can hold open.

Run it alongside the API::

    python -m app.worker

Useful flags::

    python -m app.worker --concurrency 4     # parallel jobs
    python -m app.worker --once              # drain the queue, then exit

Deploy it as a long-running container next to the API. Because the queue lives
in Redis, you can run several workers to process documents in parallel.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import sys
import uuid

from app.config import settings
from app.services import job_queue

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("app.worker")


class Worker:
    """Consumes the Redis job queue and runs the pipeline for each job."""

    def __init__(self, concurrency: int | None = None) -> None:
        self.concurrency = max(1, concurrency or settings.job_queue_concurrency)
        self._stopping = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()
        self._active = 0
        self._processed = 0
        # A stable, per-process processing list keeps acknowledgements isolated
        # from other workers running on the same Redis instance.
        self.consumer = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"

    # -- lifecycle ---------------------------------------------------------

    def install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.request_stop)

    def request_stop(self) -> None:
        if not self._stopping.is_set():
            log.info("Shutdown requested — draining in-flight jobs")
            self._stopping.set()

    async def run(self, once: bool = False) -> int:
        log.info(
            "Worker starting (concurrency=%d, queue=%s)", self.concurrency,
            settings.job_queue_key,
        )
        await job_queue.recover_orphans()

        while not self._stopping.is_set():
            if await job_queue.queue_is_healthy_async() is False:
                log.error(
                    "Redis is not reachable at %s — cannot consume the queue. "
                    "Check REDIS_URL and that the server is running.", settings.redis_url,
                )
                if once:
                    return 1
                await asyncio.sleep(5)
                continue

            if self._tasks and len(self._tasks) >= self.concurrency:
                await self._reap()
                continue

            try:
                job = await job_queue.pop_blocking(timeout_s=1, consumer=self.consumer)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Queue poll failed: %s", exc)
                await asyncio.sleep(2)
                continue

            if job is None:
                if once:
                    break
                continue

            self._tasks.add(asyncio.create_task(self._handle(job)))
            log.info(
                "Picked up job %s (%d in flight)", job.message.job_id, len(self._tasks)
            )

        await self._reap(drain=True)
        log.info("Worker stopped after processing %d job(s)", self._processed)
        return 0

    async def _reap(self, drain: bool = False) -> None:
        if not self._tasks:
            return
        pending = [t for t in self._tasks if not t.done()]
        if pending and (drain or self._stopping.is_set()):
            await asyncio.gather(*pending, return_exceptions=True)
        for task in list(self._tasks):
            if task.done():
                exc = task.exception()
                if exc:
                    log.error("Job task raised: %s", exc)
                self._tasks.discard(task)

    # -- work --------------------------------------------------------------

    async def _handle(self, job: job_queue.DeliveredJob) -> None:
        """Run one pipeline job, then acknowledge exactly that payload."""
        from app.services.document_processor import run_pipeline

        message = job.message
        self._active += 1
        started = asyncio.get_running_loop().time()
        try:
            await run_pipeline(message.job_id, message.triggered_by)
            self._processed += 1
        except asyncio.CancelledError:
            # Shutting down mid-OCR: hand the job back so nothing is lost.
            log.warning("Job %s cancelled — requeueing", message.job_id)
            await job_queue.acknowledge(job.raw, self.consumer)
            if not await job_queue.requeue(message):
                log.error("Could not requeue cancelled job %s", message.job_id)
            raise
        except Exception as exc:
            # run_pipeline records the failure on the job row; log and move on.
            log.exception("Job %s failed: %s", message.job_id, exc)
        finally:
            self._active -= 1
            elapsed = asyncio.get_running_loop().time() - started
            await job_queue.acknowledge(job.raw, self.consumer)
            log.info(
                "Job %s finished in %.2fs (%d processed, %d in flight)",
                message.job_id, elapsed, self._processed, self._active,
            )


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Document processing worker")
    parser.add_argument(
        "--concurrency", type=int, default=None,
        help=f"Jobs to process in parallel (default: {settings.job_queue_concurrency})",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Drain the current queue and exit (useful for cron-style runners)",
    )
    args = parser.parse_args(argv)

    worker = Worker(concurrency=args.concurrency)
    worker.install_signal_handlers()
    return await worker.run(once=args.once)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        sys.exit(asyncio.run(main()))
