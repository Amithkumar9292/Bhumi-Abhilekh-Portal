"""
Alembic Migration 0004 -- asynchronous document processing.

Supports the non-blocking upload workflow: an upload creates a QUEUED
ProcessingJob and returns 202 immediately, while a background worker drives the
document through IMAGE_QUALITY and LANGUAGE_DETECTION and reports per-stage
progress and the stage that failed.

New enum labels on `processing_status_enum`:
  QUALITY_ANALYSIS, LANGUAGE_DETECTION

New columns on `processing_jobs`:
  stage_message, failed_stage, verification_status, error_type,
  started_at, heartbeat_at

Run: alembic upgrade head
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_async_processing"
down_revision = "0003_extended_platform"
branch_labels = None
depends_on = None

NEW_STATUSES = ("QUALITY_ANALYSIS", "LANGUAGE_DETECTION")

NEW_COLUMNS = (
    ("stage_message", sa.String(length=255)),
    ("failed_stage", sa.String(length=64)),
    ("verification_status", sa.String(length=32)),
    ("error_type", sa.String(length=32)),
    ("started_at", sa.DateTime(timezone=True)),
    ("heartbeat_at", sa.DateTime(timezone=True)),
)


def _enum_labels(bind) -> list[str]:
    return [row[0] for row in bind.execute(
        sa.text("SELECT enumlabel FROM pg_enum "
                "JOIN pg_type ON pg_type.oid = pg_enum.enumtypid "
                "WHERE pg_type.typname = 'processing_status_enum'")
    )]


def upgrade() -> None:
    bind = op.get_bind()

    # SQLite (the test database) has no ALTER TYPE; its schema is built from
    # the ORM metadata, which already reflects the new labels.
    if bind.dialect.name == "postgresql":
        existing = set(_enum_labels(bind))
        for label in NEW_STATUSES:
            if label in existing:
                continue
            # Since PostgreSQL 12 this may run inside a transaction, as long as
            # the new label is not *used* in the same transaction -- which holds
            # here because no row is written with it.
            bind.execute(
                sa.text(f"ALTER TYPE processing_status_enum ADD VALUE '{label}'")
            )

    # New columns on processing_jobs. Guarded so the migration is re-runnable.
    present = {
        row[0] for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'processing_jobs'"
            )
        )
    }
    for name, coltype in NEW_COLUMNS:
        if name in present:
            continue
        op.add_column("processing_jobs", sa.Column(name, coltype, nullable=True))

    # Indexes that keep status polling cheap.
    op.create_index(
        "ix_processing_jobs_status_created",
        "processing_jobs",
        ["status", "created_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_processing_jobs_status_created", table_name="processing_jobs",
                  if_exists=True)

    present = {
        row[0] for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'processing_jobs'"
            )
        )
    }
    for name, _ in reversed(NEW_COLUMNS):
        if name in present:
            op.drop_column("processing_jobs", name)

    if bind.dialect.name != "postgresql":
        return

    if bind.dialect.name != "postgresql":
        return

    # PostgreSQL cannot drop enum labels, so the type is rebuilt without the
    # ones this migration added. Rows holding a dropped label would break the
    # cast, so they are reset to FAILED first rather than aborting the downgrade.
    bind.execute(sa.text(
        "UPDATE processing_jobs SET status = 'FAILED'::processing_status_enum "
        "WHERE status IN ('QUALITY_ANALYSIS', 'LANGUAGE_DETECTION')"
    ))
    bind.execute(sa.text("DROP TYPE IF EXISTS processing_status_enum_new"))
    bind.execute(sa.text("""
        CREATE TYPE processing_status_enum_new AS ENUM (
            'QUEUED', 'VALIDATING', 'PREPROCESSING', 'OCR_RUNNING',
            'EXTRACTING', 'CLASSIFYING', 'SCORING', 'DEDUP_CHECK',
            'ANOMALY_CHECK', 'PENDING_REVIEW', 'COMPLETED', 'FAILED'
        )
    """))
    bind.execute(sa.text("""
        ALTER TABLE processing_jobs
            ALTER COLUMN status TYPE processing_status_enum_new
            USING status::text::processing_status_enum_new
    """))
    bind.execute(sa.text("DROP TYPE processing_status_enum"))
    bind.execute(sa.text(
        "ALTER TYPE processing_status_enum_new RENAME TO processing_status_enum"
    ))
