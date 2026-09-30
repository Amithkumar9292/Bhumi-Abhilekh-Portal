"""
SQLAlchemy ORM Models for Land Records.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.document import Document

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class LandUseType(str, enum.Enum):
    AGRICULTURAL = "AGRICULTURAL"
    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"
    FOREST = "FOREST"
    INDUSTRIAL = "INDUSTRIAL"
    WASTELAND = "WASTELAND"


class RecordStatus(str, enum.Enum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class LandRecord(Base):
    __tablename__ = "land_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Survey identifiers ──────────────────────────────────
    khasra_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    khatauni_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    survey_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Location ─────────────────────────────────────────────
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    district: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tehsil: Mapped[str] = mapped_column(String(128), nullable=False)
    village: Mapped[str] = mapped_column(String(128), nullable=False)
    pin_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # ── Area & Land use ──────────────────────────────────────
    area_hectares: Mapped[float] = mapped_column(Float, nullable=False)
    land_use_type: Mapped[LandUseType] = mapped_column(
        Enum(LandUseType, name="land_use_type_enum"), nullable=False
    )

    # ── Owner ────────────────────────────────────────────────
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    father_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    aadhaar_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # ── Status & Workflow ────────────────────────────────────
    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, name="record_status_enum"),
        nullable=False,
        default=RecordStatus.PENDING,
        index=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── GeoJSON geometry (parcel boundary) ───────────────────
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Audit ─────────────────────────────────────────────────
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="land_record", lazy="select"
    )
