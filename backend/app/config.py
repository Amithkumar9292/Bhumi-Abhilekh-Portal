"""
Application Configuration
Reads from environment variables / .env file using Pydantic Settings.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# `env_file` is resolved against the process working directory, so a bare
# ".env" silently misses the repository-root file whenever the server is
# started from `backend/`. Use absolute paths instead. A `backend/.env` is
# still honoured and takes precedence, for per-developer overrides.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent

_ENV_FILES: tuple[Path | str, ...] = tuple(
    p for p in (_REPO_ROOT / ".env", _BACKEND_DIR / ".env") if p.is_file()
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES or (_REPO_ROOT / ".env",),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_name: str = "Intelligent Land Record System"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # ── JWT / Security ───────────────────────────────────────
    secret_key: str = "dev-secret-key-CHANGE-IN-PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── PostgreSQL ───────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://land_user:land_password@localhost:5432/land_records_db"
    )

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── MongoDB ──────────────────────────────────────────────
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db: str = "land_audit_db"
    # Hard ceiling on any single MongoDB operation. MUST stay well under the
    # frontend's request timeout -- the PyMongo default of 30s used to stall
    # every request that wrote an audit event.
    mongo_timeout_ms: int = 2000
    # Per-call budget for a single audit write.
    audit_write_timeout_s: float = 1.5
    # Same idea for the pipeline event log (never on the request path).
    pipeline_log_timeout_s: float = 2.0

    # ── Rate Limiting ────────────────────────────────────────
    rate_limit_login: str = "5/minute"
    rate_limit_api: str = "100/minute"

    # ── File Storage ─────────────────────────────────────────
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 20

    # -- Background Job Queue (Redis) --------------------------
    # Uploads enqueue a ProcessingJob here and return 202 immediately; a
    # separate worker (`python -m app.worker`) drains the queue.
    job_queue_key: str = "pipeline:jobs:queue"
    # Base name; each worker appends its own id, so concurrent workers never
    # acknowledge each other's in-flight jobs.
    job_queue_processing_key: str = "pipeline:jobs:processing"
    job_queue_status_prefix: str = "pipeline:job"
    job_status_ttl_s: int = 86_400
    # How long the worker waits for work in one blocking pop.
    job_queue_block_timeout_s: int = 5
    # Allow N jobs to run concurrently inside one worker process.
    job_queue_concurrency: int = 2
    # How long a worker's heartbeat keeps a stranded job out of orphan recovery.
    # Must comfortably exceed the slowest plausible gap between two stage
    # updates, since recovery re-queues any job whose heartbeat is older.
    job_lease_ttl_s: int = 300
    # If Redis is unreachable, fall back to an in-process background task so an
    # upload is never rejected just because the queue is down. Set to False in
    # deployments where silent in-process processing is not acceptable.
    job_queue_fallback_to_process: bool = True
    # Also run a queue consumer inside the API process. Leave False in production
    # and run `python -m app.worker` as its own service instead; turn it on for
    # single-process dev setups so uploads get processed without a second process.
    run_worker_in_api: bool = True

    # ── Document Processing Pipeline ─────────────────────────
    # OCR backend: "mock" (demo) | "tesseract" | "easyocr" | "google" | "azure"
    ocr_backend: str = "tesseract"
    # Explicit tesseract binary path. Empty = auto-detect from PATH plus the
    # usual Windows/macOS install locations.
    tesseract_cmd: str = ""
    # Preferred language packs, intersected with the packs actually installed so
    # a missing `hin` pack can never break OCR entirely.
    tesseract_languages: str = "hin+eng"
    # Fields with confidence below this go to human review queue
    pipeline_review_threshold: float = 0.60
    # Auto-trigger pipeline on document upload
    pipeline_auto_trigger: bool = True
    # Max concurrent pipeline workers (for future task queue)
    pipeline_max_workers: int = 4


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — import this everywhere."""
    return Settings()


settings = get_settings()
