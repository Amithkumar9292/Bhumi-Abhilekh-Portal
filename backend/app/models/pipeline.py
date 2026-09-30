"""
Document Processing Pipeline — Complete Data Models
PostgreSQL stores metadata + extracted fields.
MongoDB stores full processing logs + raw OCR output.
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, JSON, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


# ── Enumerations ──────────────────────────────────────────────────────────────

class ProcessingStatus(str, enum.Enum):
    """
    Coarse persisted job status.

    The fine-grained stage vocabulary lives in ``app.services.pipeline_stages``.
    Several canonical stages share a status value here (e.g. FILE_VALIDATION and
    VALIDATION are both VALIDATING), which is why ``ProcessingJob.current_stage``
    is stored separately.
    """
    QUEUED      = "QUEUED"
    VALIDATING  = "VALIDATING"        # file format / integrity check
    QUALITY_ANALYSIS = "QUALITY_ANALYSIS"  # sharpness, contrast, resolution
    PREPROCESSING = "PREPROCESSING"   # deskew, denoise, binarize
    OCR_RUNNING = "OCR_RUNNING"       # tesseract / cloud OCR
    LANGUAGE_DETECTION = "LANGUAGE_DETECTION"
    EXTRACTING  = "EXTRACTING"        # field extraction
    CLASSIFYING = "CLASSIFYING"       # document classification
    SCORING     = "SCORING"           # confidence scoring
    DEDUP_CHECK = "DEDUP_CHECK"       # duplicate detection
    ANOMALY_CHECK = "ANOMALY_CHECK"   # anomaly detection
    PENDING_REVIEW = "PENDING_REVIEW" # human verification needed
    COMPLETED   = "COMPLETED"
    FAILED      = "FAILED"

class FieldValidationStatus(str, enum.Enum):
    NOT_VALIDATED = "NOT_VALIDATED"
    AUTO_VALID    = "AUTO_VALID"        # passed regex/rule validation
    AUTO_INVALID  = "AUTO_INVALID"      # failed rule validation
    HUMAN_VERIFIED = "HUMAN_VERIFIED"   # verified by verifier
    HUMAN_REJECTED = "HUMAN_REJECTED"

class AnomalyType(str, enum.Enum):
    DUPLICATE_RECORD     = "DUPLICATE_RECORD"
    AREA_MISMATCH        = "AREA_MISMATCH"
    OWNER_CONFLICT       = "OWNER_CONFLICT"
    SURVEY_FORMAT_ERROR  = "SURVEY_FORMAT_ERROR"
    MISSING_REQUIRED     = "MISSING_REQUIRED"
    LOW_CONFIDENCE_FIELD = "LOW_CONFIDENCE_FIELD"
    BOUNDARY_CONFLICT    = "BOUNDARY_CONFLICT"

class DocumentLanguage(str, enum.Enum):
    ENGLISH = "en"
    HINDI   = "hi"
    MARATHI = "mr"
    TELUGU  = "te"
    KANNADA = "kn"
    TAMIL   = "ta"
    GUJARATI = "gu"
    BENGALI = "bn"
    UNKNOWN = "unknown"


# ── Processing Job ─────────────────────────────────────────────────────────────

class ProcessingJob(Base):
    """
    One row per document processing run.
    Tracks full pipeline state and timing.
    """
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    land_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("land_records.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # Pipeline state
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status_enum"),
        nullable=False, default=ProcessingStatus.QUEUED, index=True,
    )
    # Canonical stage name (app.services.pipeline_stages.PipelineStage)
    current_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    # Human-readable description of what the current stage is doing
    stage_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Stage that raised, set only when status == FAILED
    failed_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # NOT_REQUIRED | PENDING | IN_REVIEW | RESOLVED
    verification_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Error category: UPLOAD | STORAGE | DATABASE | QUEUE | OCR | EXTRACTION | VALIDATION
    error_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Detected metadata
    detected_language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overall_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Outcome flags
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    has_anomalies: Mapped[bool] = mapped_column(Boolean, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Error info
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Stage timing (ISO strings stored as JSON)
    stage_timings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Audit
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when a worker actually picks the job up (distinct from created_at)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last time a worker touched the job — used to spot stuck jobs
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    extracted_fields: Mapped[list["ExtractedField"]] = relationship(
        "ExtractedField", back_populates="job", cascade="all, delete-orphan"
    )
    anomalies: Mapped[list["PipelineAnomaly"]] = relationship(
        "PipelineAnomaly", back_populates="job", cascade="all, delete-orphan"
    )
    verification_tasks: Mapped[list["VerificationTask"]] = relationship(
        "VerificationTask", back_populates="job", cascade="all, delete-orphan"
    )


# ── Extracted Fields ──────────────────────────────────────────────────────────

class ExtractedField(Base):
    """
    Every field extracted from a document gets its own row.
    Stores value, confidence, source location, validation status.
    """
    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Field identity
    field_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    field_display: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Extracted value
    raw_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Confidence (0.0–1.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    extraction_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Source location
    source_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bounding_box: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # {"x": 0, "y": 0, "width": 100, "height": 20} in % of page

    # Validation
    validation_status: Mapped[FieldValidationStatus] = mapped_column(
        Enum(FieldValidationStatus, name="field_validation_status_enum"),
        nullable=False, default=FieldValidationStatus.NOT_VALIDATED,
    )
    validation_rule: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    validation_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    # Human verification
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    job: Mapped["ProcessingJob"] = relationship(
        "ProcessingJob", back_populates="extracted_fields"
    )


# ── Anomalies ─────────────────────────────────────────────────────────────────

class PipelineAnomaly(Base):
    """Anomalies detected during automated processing."""
    __tablename__ = "pipeline_anomalies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    anomaly_type: Mapped[AnomalyType] = mapped_column(
        Enum(AnomalyType, name="anomaly_type_enum"), nullable=False
    )
    field_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped["ProcessingJob"] = relationship("ProcessingJob", back_populates="anomalies")


# ── Human Verification Tasks ──────────────────────────────────────────────────

class VerificationTask(Base):
    """
    When a field has low confidence, a VerificationTask is created
    so a VERIFIER can inspect and correct it.
    """
    __tablename__ = "verification_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extracted_fields.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="OPEN")
    # OPEN | IN_PROGRESS | RESOLVED | SKIPPED
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    context_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    job: Mapped["ProcessingJob"] = relationship(
        "ProcessingJob", back_populates="verification_tasks"
    )
