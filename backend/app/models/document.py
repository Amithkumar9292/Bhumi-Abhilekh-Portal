"""
SQLAlchemy ORM Model for Documents attached to Land Records.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base

if TYPE_CHECKING:
    # `land_record` imports `Document` at runtime, so importing it back here
    # would be circular. Under TYPE_CHECKING the name is only needed to resolve
    # the annotation; at runtime SQLAlchemy resolves the relationship by string.
    from app.models.land_record import LandRecord


class DocumentType(str, enum.Enum):
    TITLE_DEED = "TITLE_DEED"
    SURVEY_MAP = "SURVEY_MAP"
    TAX_RECEIPT = "TAX_RECEIPT"
    MUTATION_ORDER = "MUTATION_ORDER"
    COURT_ORDER = "COURT_ORDER"
    OTHER = "OTHER"


class DocumentStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    land_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("land_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type_enum"), nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ── Validation ────────────────────────────────────────────
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status_enum"),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Audit ─────────────────────────────────────────────────
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────
    land_record: Mapped["LandRecord"] = relationship(
        "LandRecord", back_populates="documents"
    )
