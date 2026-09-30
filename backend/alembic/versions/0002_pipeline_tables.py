"""
Alembic Migration: Add document processing pipeline tables.

Tables added:
  - processing_jobs
  - extracted_fields
  - pipeline_anomalies
  - verification_tasks

New enum types:
  - processing_status_enum
  - field_validation_status_enum
  - anomaly_type_enum

Run: alembic upgrade head
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_pipeline_tables"
down_revision = "0001_initial_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────────
    processing_status_enum = postgresql.ENUM(
        "QUEUED", "VALIDATING", "PREPROCESSING", "OCR_RUNNING",
        "EXTRACTING", "CLASSIFYING", "SCORING", "DEDUP_CHECK",
        "ANOMALY_CHECK", "PENDING_REVIEW", "COMPLETED", "FAILED",
        name="processing_status_enum", create_type=False,
    )
    processing_status_enum.create(op.get_bind(), checkfirst=True)

    field_validation_status_enum = postgresql.ENUM(
        "NOT_VALIDATED", "AUTO_VALID", "AUTO_INVALID",
        "HUMAN_VERIFIED", "HUMAN_REJECTED",
        name="field_validation_status_enum", create_type=False,
    )
    field_validation_status_enum.create(op.get_bind(), checkfirst=True)

    anomaly_type_enum = postgresql.ENUM(
        "DUPLICATE_RECORD", "AREA_MISMATCH", "OWNER_CONFLICT",
        "SURVEY_FORMAT_ERROR", "MISSING_REQUIRED", "LOW_CONFIDENCE_FIELD",
        "BOUNDARY_CONFLICT",
        name="anomaly_type_enum", create_type=False,
    )
    anomaly_type_enum.create(op.get_bind(), checkfirst=True)

    # ── processing_jobs ───────────────────────────────────────────────────────
    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("status", processing_status_enum, nullable=False, default="QUEUED"),
        sa.Column("current_stage", sa.String(64), nullable=True),
        sa.Column("progress_pct", sa.Integer, default=0),
        sa.Column("detected_language", sa.String(16), nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("image_quality_score", sa.Float, nullable=True),
        sa.Column("overall_confidence", sa.Float, nullable=True),
        sa.Column("needs_human_review", sa.Boolean, default=False),
        sa.Column("has_anomalies", sa.Boolean, default=False),
        sa.Column("is_duplicate", sa.Boolean, default=False),
        sa.Column("duplicate_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("stage_timings", postgresql.JSON, nullable=True),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    # ix_processing_jobs_document_id is already created by index=True on the column

    # ── extracted_fields ──────────────────────────────────────────────────────
    op.create_table(
        "extracted_fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("field_name", sa.String(64), nullable=False, index=True),
        sa.Column("field_display", sa.String(128), nullable=True),
        sa.Column("raw_value", sa.Text, nullable=True),
        sa.Column("normalized_value", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Float, default=0.0),
        sa.Column("ocr_confidence", sa.Float, nullable=True),
        sa.Column("extraction_method", sa.String(32), nullable=True),
        sa.Column("source_page", sa.Integer, nullable=True),
        sa.Column("bounding_box", postgresql.JSON, nullable=True),
        sa.Column("validation_status", field_validation_status_enum, nullable=False, default="NOT_VALIDATED"),
        sa.Column("validation_rule", sa.String(128), nullable=True),
        sa.Column("validation_message", sa.Text, nullable=True),
        sa.Column("needs_review", sa.Boolean, default=False),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_value", sa.Text, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── pipeline_anomalies ────────────────────────────────────────────────────
    op.create_table(
        "pipeline_anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("anomaly_type", anomaly_type_enum, nullable=False),
        sa.Column("field_name", sa.String(64), nullable=True),
        sa.Column("severity", sa.String(16), default="MEDIUM"),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, default=0.8),
        sa.Column("resolved", sa.Boolean, default=False),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── verification_tasks ────────────────────────────────────────────────────
    op.create_table(
        "verification_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("field_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("extracted_fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), default="OPEN"),
        sa.Column("priority", sa.String(16), default="MEDIUM"),
        sa.Column("context_snippet", sa.Text, nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("verification_tasks")
    op.drop_table("pipeline_anomalies")
    op.drop_table("extracted_fields")
    op.drop_table("processing_jobs")
    op.execute("DROP TYPE IF EXISTS anomaly_type_enum")
    op.execute("DROP TYPE IF EXISTS field_validation_status_enum")
    op.execute("DROP TYPE IF EXISTS processing_status_enum")
