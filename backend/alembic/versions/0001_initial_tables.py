"""
Alembic Migration: Initial base tables.

Tables created:
  - users
  - land_records
  - documents

New enum types:
  - role_enum
  - land_use_type_enum
  - record_status_enum
  - document_type_enum
  - document_status_enum

Run: alembic upgrade head
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0001_initial_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────────
    role_enum = postgresql.ENUM("ADMIN", "OFFICER", "VERIFIER", "VIEWER", name="role_enum", create_type=False)
    role_enum.create(op.get_bind(), checkfirst=True)

    land_use_type_enum = postgresql.ENUM(
        "AGRICULTURAL", "RESIDENTIAL", "COMMERCIAL", "FOREST", "INDUSTRIAL", "WASTELAND",
        name="land_use_type_enum", create_type=False,
    )
    land_use_type_enum.create(op.get_bind(), checkfirst=True)

    record_status_enum = postgresql.ENUM(
        "PENDING", "UNDER_REVIEW", "VERIFIED", "REJECTED", "ARCHIVED",
        name="record_status_enum", create_type=False,
    )
    record_status_enum.create(op.get_bind(), checkfirst=True)

    document_type_enum = postgresql.ENUM(
        "TITLE_DEED", "SURVEY_MAP", "TAX_RECEIPT", "MUTATION_ORDER", "COURT_ORDER", "OTHER",
        name="document_type_enum", create_type=False,
    )
    document_type_enum.create(op.get_bind(), checkfirst=True)

    document_status_enum = postgresql.ENUM(
        "UPLOADED", "PROCESSING", "VALIDATED", "REJECTED",
        name="document_status_enum", create_type=False,
    )
    document_status_enum.create(op.get_bind(), checkfirst=True)

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("district_code", sa.String(16), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])

    # ── land_records ──────────────────────────────────────────────────────────
    op.create_table(
        "land_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("khasra_number", sa.String(64), nullable=False),
        sa.Column("khatauni_number", sa.String(64), nullable=True),
        sa.Column("survey_number", sa.String(64), nullable=True),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("district", sa.String(128), nullable=False),
        sa.Column("tehsil", sa.String(128), nullable=False),
        sa.Column("village", sa.String(128), nullable=False),
        sa.Column("pin_code", sa.String(10), nullable=True),
        sa.Column("area_hectares", sa.Float, nullable=False),
        sa.Column("land_use_type", land_use_type_enum, nullable=False),
        sa.Column("owner_name", sa.String(255), nullable=False),
        sa.Column("father_name", sa.String(255), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("aadhaar_last4", sa.String(4), nullable=True),
        sa.Column("status", record_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("geometry", postgresql.JSON, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_land_records_khasra_number", "land_records", ["khasra_number"])
    op.create_index("ix_land_records_district", "land_records", ["district"])
    op.create_index("ix_land_records_status", "land_records", ["status"])

    # ── documents ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_type", document_type_enum, nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("stored_path", sa.String(1024), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("status", document_status_enum, nullable=False, server_default="UPLOADED"),
        sa.Column("validation_notes", sa.Text, nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_land_record_id", "documents", ["land_record_id"])


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("land_records")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS document_status_enum")
    op.execute("DROP TYPE IF EXISTS document_type_enum")
    op.execute("DROP TYPE IF EXISTS record_status_enum")
    op.execute("DROP TYPE IF EXISTS land_use_type_enum")
    op.execute("DROP TYPE IF EXISTS role_enum")
