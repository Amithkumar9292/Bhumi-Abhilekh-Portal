"""
FastAPI Application Entry Point.
Configures middleware, routers, rate limiting, OpenAPI metadata.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import settings
from app.db.mongo import close_mongo
from app.db.postgres import engine
from app.services.ocr_service import ocr_diagnostics
from app.routers import (
    auth, land_records, dashboard, admin, documents, users, pipeline,
    validation, gis, land_records_extended, analytics, notifications, audit, integrations,
    intake,
)


# -- Lifespan -----------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Only start an in-process consumer when no dedicated worker is expected to
    # drain the queue. Upload handlers only ever enqueue, so a deployment that
    # runs `python -m app.worker` needs nothing extra here.
    from app.config import settings as _settings
    from app.services.job_dispatch import shutdown_local_jobs
    from app.services.job_queue import InProcessRunner

    runner: InProcessRunner | None = None
    if _settings.run_worker_in_api:
        runner = InProcessRunner()
        runner.start()
        app.state.job_runner = runner

    try:
        yield
    finally:
        if runner is not None:
            await runner.stop()
        await shutdown_local_jobs()
        await close_mongo()
        await engine.dispose()


# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


# ── App Factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Intelligent Land Record Digitization & Validation System",
    description=(
        "## ⚠️ DEMO SYSTEM\n\n"
        "All data shown in this system is **synthetic** and generated for demonstration purposes only. "
        "No records in this system are legally binding or constitute official government documents.\n\n"
        "---\n\n"
        "### Features\n"
        "- JWT-based authentication with refresh tokens\n"
        "- Role-Based Access Control (ADMIN, OFFICER, VERIFIER, VIEWER)\n"
        "- Land record lifecycle: Pending → Under Review → Verified / Rejected\n"
        "- Document upload and validation\n"
        "- Audit trail via MongoDB\n"
        "- Redis-backed token revocation and caching\n"
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "Land Records System — Demo",
        "email": "demo@landrecords.example",
    },
    license_info={
        "name": "MIT — Demo Only",
    },
)

# ── State ─────────────────────────────────────────────────────────────────────
app.state.limiter = limiter

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)

# ── Exception Handlers ────────────────────────────────────────────────────────
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import traceback
    import sys
    traceback.print_exc(file=sys.stderr)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
PREFIX = settings.api_v1_prefix

app.include_router(auth.router, prefix=PREFIX)
app.include_router(land_records_extended.router, prefix=PREFIX)
app.include_router(land_records.router, prefix=PREFIX)
app.include_router(dashboard.router, prefix=PREFIX)
app.include_router(admin.router, prefix=PREFIX)
app.include_router(documents.router, prefix=PREFIX)
app.include_router(users.router, prefix=PREFIX)
app.include_router(pipeline.router, prefix=PREFIX)
app.include_router(validation.router, prefix=PREFIX)
app.include_router(gis.router, prefix=PREFIX)
app.include_router(analytics.router, prefix=PREFIX)
app.include_router(notifications.router, prefix=PREFIX)
app.include_router(audit.router, prefix=PREFIX)
app.include_router(integrations.router, prefix=PREFIX)
app.include_router(intake.router, prefix=PREFIX)


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"], include_in_schema=False)
async def health() -> dict:
    from app.services.job_queue import queue_depth, queue_is_healthy_async

    queue_ok = await queue_is_healthy_async()
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        # Redis drives the background job queue; MongoDB is an optional
        # observability store, so its absence is reported but not fatal.
        "redis": "up" if queue_ok else "down",
        "queue_depth": await queue_depth() if queue_ok else -1,
        # OCR cannot work if the process is running an interpreter that lacks
        # pytesseract, so surface the interpreter alongside the binary. This is
        # the check that catches "Tesseract not found" misdiagnoses.
        "ocr": ocr_diagnostics(),
        "disclaimer": "DEMO SYSTEM - All data is synthetic. Not legally binding.",
    }


@app.get("/", tags=["System"], include_in_schema=False)
async def root() -> dict:
    return {
        "system": "Intelligent Land Record Digitization & Validation System",
        "api_docs": "/api/docs",
        "status": "operational",
        "disclaimer": "⚠️ DEMO SYSTEM — All data is synthetic. Not legally binding.",
    }
