"""
Extended PostgreSQL Models — Complete normalized schema.

New tables added to existing foundation:
  owners           — dedicated owner entities (person/company)
  plots            — normalized plot/parcel data (1 record → many plots)
  survey_details   — detailed survey information per record
  mutations        — mutation/transfer history
  registrations    — sub-registrar registration records
  validation_rules — configurable business rule definitions
  validation_results — per-record rule evaluation outcomes
  verification_actions — history of verifier decisions
  gis_coordinates  — GIS / cadastral coordinate data
  notifications    — user notification inbox

All tables use:
  - UUID primary keys
  - timezone-aware timestamps
  - proper FKs with cascade/set-null semantics
  - column-level check constraints
  - GIN indexes on JSON / tsvector columns for full-text search
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, Float,
    ForeignKey, Index, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSON, TSVECTOR, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


@compiles(TSVECTOR, 'sqlite')
def compile_tsvector_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "TEXT"


@compiles(UUID, 'sqlite')
def compile_uuid_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "CHAR(36)"


@compiles(JSON, 'sqlite')
def compile_json_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "TEXT"


# ── Owner entity ──────────────────────────────────────────────────────────────

class OwnerType(str, enum.Enum):
    INDIVIDUAL = "INDIVIDUAL"
    JOINT       = "JOINT"       # multiple individuals
    COMPANY     = "COMPANY"
    TRUST       = "TRUST"
    GOVERNMENT  = "GOVERNMENT"


class Owner(Base):
    """
    Normalized owner entity decoupled from LandRecord.
    A single owner can hold multiple records.
    """
    __tablename__ = "owners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_type: Mapped[OwnerType] = mapped_column(
        Enum(OwnerType, name="owner_type_enum"), nullable=False, default=OwnerType.INDIVIDUAL
    )

    # Individual fields
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    father_spouse_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # ISO date string
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Identity (stored masked — never store full Aadhaar)
    aadhaar_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    pan_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    mobile_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)

    # Company/Trust fields
    entity_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    registration_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Contact
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    pin_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Full-text search vector (maintained by trigger or app)
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    land_record_owners: Mapped[list["LandRecordOwner"]] = relationship(
        "LandRecordOwner", back_populates="owner", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_owners_search_vector", "search_vector", postgresql_using="gin"),
    )


class LandRecordOwner(Base):
    """M2M join table: land_record ↔ owner, with share percentage."""
    __tablename__ = "land_record_owners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ownership_share_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0–100
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    effective_to: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    owner: Mapped["Owner"] = relationship("Owner", back_populates="land_record_owners")

    __table_args__ = (
        UniqueConstraint("land_record_id", "owner_id", name="uq_land_record_owner"),
        CheckConstraint("ownership_share_pct IS NULL OR (ownership_share_pct >= 0 AND ownership_share_pct <= 100)",
                        name="ck_ownership_share_pct"),
    )


# ── Plot / Parcel ──────────────────────────────────────────────────────────────

class PlotStatus(str, enum.Enum):
    ACTIVE   = "ACTIVE"
    MERGED   = "MERGED"
    SPLIT    = "SPLIT"
    DISPUTED = "DISPUTED"


class Plot(Base):
    """
    A land record may contain multiple plots/sub-parcels.
    Normalized from LandRecord to allow split/merge tracking.
    """
    __tablename__ = "plots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plot_number: Mapped[str] = mapped_column(String(64), nullable=False)
    area_hectares: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    area_sq_meters: Mapped[Optional[float]] = mapped_column(Numeric(14, 4), nullable=True)

    # Topographic classification
    soil_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    irrigation_source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    crop_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    revenue_circle: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    status: Mapped[PlotStatus] = mapped_column(
        Enum(PlotStatus, name="plot_status_enum"), nullable=False, default=PlotStatus.ACTIVE
    )
    # If split/merged, reference parent plot
    parent_plot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plots.id", ondelete="SET NULL"), nullable=True
    )

    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("area_hectares > 0", name="ck_plot_area_positive"),
        UniqueConstraint("land_record_id", "plot_number", name="uq_plot_per_record"),
    )


# ── Survey Details ────────────────────────────────────────────────────────────

class SurveyType(str, enum.Enum):
    CADASTRAL     = "CADASTRAL"
    TOPOGRAPHIC   = "TOPOGRAPHIC"
    REVENUE       = "REVENUE"
    DEMARCATION   = "DEMARCATION"


class SurveyDetail(Base):
    """Survey metadata for a land record."""
    __tablename__ = "survey_details"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("land_records.id", ondelete="CASCADE"),
        nullable=False, index=True, unique=True  # one survey detail per record
    )
    survey_type: Mapped[SurveyType] = mapped_column(
        Enum(SurveyType, name="survey_type_enum"), nullable=False, default=SurveyType.CADASTRAL
    )
    surveyor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    survey_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    settlement_year: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    revision_year: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    toposheet_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    field_book_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    boundary_marks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-like description
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Mutations ─────────────────────────────────────────────────────────────────

class MutationType(str, enum.Enum):
    SALE             = "SALE"
    INHERITANCE      = "INHERITANCE"
    GIFT             = "GIFT"
    PARTITION        = "PARTITION"
    COURT_ORDER      = "COURT_ORDER"
    GOVERNMENT_ORDER = "GOVERNMENT_ORDER"
    CORRECTION       = "CORRECTION"
    OTHER            = "OTHER"


class MutationStatus(str, enum.Enum):
    APPLIED  = "APPLIED"
    PENDING  = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Mutation(Base):
    """
    Mutation (Dakhil-Kharij) — transfer of ownership or change of record.
    Linked to both source and destination land records.
    """
    __tablename__ = "mutations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mutation_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mutation_type: Mapped[MutationType] = mapped_column(
        Enum(MutationType, name="mutation_type_enum"), nullable=False
    )
    status: Mapped[MutationStatus] = mapped_column(
        Enum(MutationStatus, name="mutation_status_enum"), nullable=False, default=MutationStatus.PENDING
    )

    # Transfer parties (names only — owners normalized separately)
    transferor_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    transferee_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Dates
    application_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    approval_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    effective_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Financial
    consideration_amount: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    stamp_duty_paid: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)

    # Cross-ref
    registration_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True
    )
    tehsildar_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("land_record_id", "mutation_number", name="uq_mutation_per_record"),
        CheckConstraint("consideration_amount IS NULL OR consideration_amount >= 0", name="ck_consideration"),
    )


# ── Registrations ─────────────────────────────────────────────────────────────

class RegistrationType(str, enum.Enum):
    SALE_DEED         = "SALE_DEED"
    GIFT_DEED         = "GIFT_DEED"
    LEASE_DEED        = "LEASE_DEED"
    MORTGAGE_DEED     = "MORTGAGE_DEED"
    PARTITION_DEED    = "PARTITION_DEED"
    WILL              = "WILL"
    POWER_OF_ATTORNEY = "POWER_OF_ATTORNEY"
    OTHER             = "OTHER"


class Registration(Base):
    """Sub-registrar registration event for a land record."""
    __tablename__ = "registrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    registration_type: Mapped[RegistrationType] = mapped_column(
        Enum(RegistrationType, name="registration_type_enum"), nullable=False
    )

    # Registration identifiers
    deed_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    book_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    volume_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    registration_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    execution_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Office
    sub_registrar_office: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sub_registrar_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Financial
    market_value: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    consideration_value: Mapped[Optional[float]] = mapped_column(Numeric(18, 2), nullable=True)
    stamp_duty: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    registration_fee: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)

    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("market_value IS NULL OR market_value >= 0", name="ck_market_value"),
    )


# ── Validation Rules & Results ────────────────────────────────────────────────

class RuleSeverity(str, enum.Enum):
    ERROR   = "ERROR"    # fails validation
    WARNING = "WARNING"  # flags for review
    INFO    = "INFO"     # informational only


class ValidationRule(Base):
    """
    Configurable business rules for land record validation.
    Rules are applied by the validation engine and can be
    enabled/disabled/configured at runtime.
    """
    __tablename__ = "validation_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[RuleSeverity] = mapped_column(
        Enum(RuleSeverity, name="rule_severity_enum"), nullable=False, default=RuleSeverity.WARNING
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    # e.g. "COMPLETENESS" | "CONSISTENCY" | "DUPLICATE" | "FORMAT" | "CROSS_RECORD"

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    # blocking = True → record cannot be verified until resolved

    # Configurable thresholds stored as JSON
    # e.g. {"min_area": 0.01, "max_area": 1000, "confidence_threshold": 0.65}
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    applies_to: Mapped[str] = mapped_column(String(32), default="LAND_RECORD")
    # "LAND_RECORD" | "DOCUMENT" | "MUTATION" | "REGISTRATION" | "OWNER"

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ValidationResult(Base):
    """Per-record result of applying a validation rule."""
    __tablename__ = "validation_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("validation_rules.id", ondelete="CASCADE"), nullable=False
    )
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)  # denormalized for query speed
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    field_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actual_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_pattern: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("land_record_id", "rule_id", name="uq_validation_result"),
        Index("ix_validation_results_record_failed", "land_record_id", "passed"),
    )


# ── Verification Actions ──────────────────────────────────────────────────────

class VerificationActionType(str, enum.Enum):
    SUBMITTED_FOR_REVIEW = "SUBMITTED_FOR_REVIEW"
    APPROVED             = "APPROVED"
    REJECTED             = "REJECTED"
    RETURNED_FOR_CORRECTION = "RETURNED_FOR_CORRECTION"
    ESCALATED            = "ESCALATED"
    COMMENT              = "COMMENT"


class VerificationAction(Base):
    """
    Full immutable history of every verification decision/comment on a land record.
    Cannot be deleted — forms the official audit trail.
    """
    __tablename__ = "verification_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[VerificationActionType] = mapped_column(
        Enum(VerificationActionType, name="verification_action_type_enum"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_verification_actions_record", "land_record_id", "created_at"),
    )


# ── GIS Coordinates ───────────────────────────────────────────────────────────

class CoordinateType(str, enum.Enum):
    CENTROID   = "CENTROID"   # representative point
    BOUNDARY   = "BOUNDARY"   # polygon vertices
    SURVEY_PEG = "SURVEY_PEG" # physical survey marker

class GISCoordinate(Base):
    """
    GIS spatial data for a land parcel.
    Stores both centroid (single point) and boundary (GeoJSON polygon).
    PostGIS extension is optional — JSON fallback used when not available.
    """
    __tablename__ = "gis_coordinates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("land_records.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    plot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plots.id", ondelete="SET NULL"), nullable=True
    )

    # Centroid (WGS-84)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Boundary as GeoJSON FeatureCollection stored in JSON column
    geojson: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Schema: { "type": "Feature", "geometry": { "type": "Polygon", "coordinates": [...] } }

    coordinate_type: Mapped[CoordinateType] = mapped_column(
        Enum(CoordinateType, name="coordinate_type_enum"), nullable=False, default=CoordinateType.CENTROID
    )

    # Accuracy / source
    accuracy_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # e.g. "DGPS", "Differential_GPS", "Bhuvan_API", "Manual", "Synthetic"
    datum: Mapped[str] = mapped_column(String(32), default="WGS84")
    captured_at: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    captured_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="ck_latitude"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="ck_longitude"),
        Index("ix_gis_lat_lng", "latitude", "longitude"),
    )


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationType(str, enum.Enum):
    RECORD_VERIFIED    = "RECORD_VERIFIED"
    RECORD_REJECTED    = "RECORD_REJECTED"
    ANOMALY_DETECTED   = "ANOMALY_DETECTED"
    DOC_PROCESSED      = "DOC_PROCESSED"
    PIPELINE_COMPLETE  = "PIPELINE_COMPLETE"
    REVIEW_ASSIGNED    = "REVIEW_ASSIGNED"
    SYSTEM_NOTICE      = "SYSTEM_NOTICE"


class Notification(Base):
    """User notification inbox — supports read/unread, links to records."""
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type_enum"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional link to a resource
    resource_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_notifications_recipient_unread", "recipient_id", "is_read", "created_at"),
    )
