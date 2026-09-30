"""
Alembic Migration 0003 — Extended data platform tables.

Creates:
  - owners
  - land_record_owners  (M2M join)
  - plots
  - survey_details
  - mutations
  - registrations
  - validation_rules
  - validation_results
  - verification_actions
  - gis_coordinates
  - notifications

Plus a TSVECTOR column + GIN index on land_records for full-text search.

Run: alembic upgrade head
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_extended_platform"
down_revision = "0002_pipeline_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── New enum types ────────────────────────────────────────────────────────
    # `create_type=False` keeps create_table from emitting a second CREATE TYPE:
    # the type is created explicitly here and reused by the column definitions.
    enums: dict[str, postgresql.ENUM] = {}
    for name, values in [
        ("owner_type_enum",               ["INDIVIDUAL","JOINT","COMPANY","TRUST","GOVERNMENT"]),
        ("plot_status_enum",              ["ACTIVE","MERGED","SPLIT","DISPUTED"]),
        ("survey_type_enum",              ["CADASTRAL","TOPOGRAPHIC","REVENUE","DEMARCATION"]),
        ("mutation_type_enum",            ["SALE","INHERITANCE","GIFT","PARTITION","COURT_ORDER","GOVERNMENT_ORDER","CORRECTION","OTHER"]),
        ("mutation_status_enum",          ["APPLIED","PENDING","APPROVED","REJECTED"]),
        ("registration_type_enum",        ["SALE_DEED","GIFT_DEED","LEASE_DEED","MORTGAGE_DEED","PARTITION_DEED","WILL","POWER_OF_ATTORNEY","OTHER"]),
        ("rule_severity_enum",            ["ERROR","WARNING","INFO"]),
        ("verification_action_type_enum", ["SUBMITTED_FOR_REVIEW","APPROVED","REJECTED","RETURNED_FOR_CORRECTION","ESCALATED","COMMENT"]),
        ("coordinate_type_enum",          ["CENTROID","BOUNDARY","SURVEY_PEG"]),
        ("notification_type_enum",        ["RECORD_VERIFIED","RECORD_REJECTED","ANOMALY_DETECTED","DOC_PROCESSED","PIPELINE_COMPLETE","REVIEW_ASSIGNED","SYSTEM_NOTICE"]),
    ]:
        pg_enum = postgresql.ENUM(*values, name=name, create_type=False)
        pg_enum.create(conn, checkfirst=True)
        enums[name] = pg_enum

    # ── Add tsvector column to land_records for full-text search ─────────────
    op.add_column("land_records", sa.Column("search_vector", postgresql.TSVECTOR, nullable=True))
    op.create_index("ix_land_records_search_vector", "land_records", ["search_vector"], postgresql_using="gin")

    # ── owners ────────────────────────────────────────────────────────────────
    op.create_table("owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", enums["owner_type_enum"], nullable=False, server_default="INDIVIDUAL"),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("father_spouse_name", sa.String(255), nullable=True),
        sa.Column("date_of_birth", sa.String(20), nullable=True),
        sa.Column("gender", sa.String(16), nullable=True),
        sa.Column("aadhaar_last4", sa.String(4), nullable=True),
        sa.Column("pan_last4", sa.String(4), nullable=True),
        sa.Column("mobile_last4", sa.String(4), nullable=True),
        sa.Column("entity_name", sa.String(512), nullable=True),
        sa.Column("registration_number", sa.String(128), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("district", sa.String(128), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("pin_code", sa.String(10), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_owners_full_name", "owners", ["full_name"])
    op.create_index("ix_owners_search_vector", "owners", ["search_vector"], postgresql_using="gin")

    # ── land_record_owners ────────────────────────────────────────────────────
    op.create_table("land_record_owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("owners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ownership_share_pct", sa.Float, nullable=True),
        sa.Column("is_primary", sa.Boolean, server_default="true"),
        sa.Column("effective_from", sa.String(20), nullable=True),
        sa.Column("effective_to", sa.String(20), nullable=True),
        sa.CheckConstraint("ownership_share_pct IS NULL OR (ownership_share_pct >= 0 AND ownership_share_pct <= 100)", name="ck_ownership_share_pct"),
        sa.UniqueConstraint("land_record_id", "owner_id", name="uq_land_record_owner"),
    )
    op.create_index("ix_land_record_owners_land", "land_record_owners", ["land_record_id"])
    op.create_index("ix_land_record_owners_owner", "land_record_owners", ["owner_id"])

    # ── plots ─────────────────────────────────────────────────────────────────
    op.create_table("plots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plot_number", sa.String(64), nullable=False),
        sa.Column("area_hectares", sa.Numeric(12, 6), nullable=False),
        sa.Column("area_sq_meters", sa.Numeric(14, 4), nullable=True),
        sa.Column("soil_type", sa.String(64), nullable=True),
        sa.Column("irrigation_source", sa.String(128), nullable=True),
        sa.Column("crop_type", sa.String(128), nullable=True),
        sa.Column("revenue_circle", sa.String(128), nullable=True),
        sa.Column("status", enums["plot_status_enum"], nullable=False, server_default="ACTIVE"),
        sa.Column("parent_plot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("area_hectares > 0", name="ck_plot_area_positive"),
        sa.UniqueConstraint("land_record_id", "plot_number", name="uq_plot_per_record"),
    )
    op.create_index("ix_plots_land_record", "plots", ["land_record_id"])

    # ── survey_details ────────────────────────────────────────────────────────
    op.create_table("survey_details",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("survey_type", enums["survey_type_enum"], nullable=False, server_default="CADASTRAL"),
        sa.Column("surveyor_name", sa.String(255), nullable=True),
        sa.Column("survey_date", sa.String(20), nullable=True),
        sa.Column("settlement_year", sa.String(16), nullable=True),
        sa.Column("revision_year", sa.String(16), nullable=True),
        sa.Column("toposheet_number", sa.String(64), nullable=True),
        sa.Column("field_book_number", sa.String(64), nullable=True),
        sa.Column("boundary_marks", sa.Text, nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_survey_details_land", "survey_details", ["land_record_id"])

    # ── registrations (must come before mutations references it) ──────────────
    op.create_table("registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("registration_type", enums["registration_type_enum"], nullable=False),
        sa.Column("deed_number", sa.String(128), nullable=True),
        sa.Column("book_number", sa.String(64), nullable=True),
        sa.Column("volume_number", sa.String(64), nullable=True),
        sa.Column("registration_date", sa.String(20), nullable=True),
        sa.Column("execution_date", sa.String(20), nullable=True),
        sa.Column("sub_registrar_office", sa.String(255), nullable=True),
        sa.Column("sub_registrar_name", sa.String(255), nullable=True),
        sa.Column("district", sa.String(128), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("market_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("consideration_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("stamp_duty", sa.Numeric(14, 2), nullable=True),
        sa.Column("registration_fee", sa.Numeric(14, 2), nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("market_value IS NULL OR market_value >= 0", name="ck_market_value"),
    )
    op.create_index("ix_registrations_land", "registrations", ["land_record_id"])
    op.create_index("ix_registrations_deed", "registrations", ["deed_number"])

    # ── mutations ─────────────────────────────────────────────────────────────
    op.create_table("mutations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mutation_number", sa.String(64), nullable=False),
        sa.Column("mutation_type", enums["mutation_type_enum"], nullable=False),
        sa.Column("status", enums["mutation_status_enum"], nullable=False, server_default="PENDING"),
        sa.Column("transferor_name", sa.String(512), nullable=True),
        sa.Column("transferee_name", sa.String(512), nullable=True),
        sa.Column("application_date", sa.String(20), nullable=True),
        sa.Column("approval_date", sa.String(20), nullable=True),
        sa.Column("effective_date", sa.String(20), nullable=True),
        sa.Column("consideration_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("stamp_duty_paid", sa.Numeric(14, 2), nullable=True),
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tehsildar_name", sa.String(255), nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column("metadata_json", postgresql.JSON, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("consideration_amount IS NULL OR consideration_amount >= 0", name="ck_consideration"),
        sa.UniqueConstraint("land_record_id", "mutation_number", name="uq_mutation_per_record"),
    )
    op.create_index("ix_mutations_land", "mutations", ["land_record_id"])
    op.create_index("ix_mutations_number", "mutations", ["mutation_number"])

    # ── validation_rules ──────────────────────────────────────────────────────
    op.create_table("validation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_code", sa.String(64), nullable=False, unique=True),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", enums["rule_severity_enum"], nullable=False, server_default="WARNING"),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_blocking", sa.Boolean, server_default="false"),
        sa.Column("config", postgresql.JSON, nullable=True),
        sa.Column("applies_to", sa.String(32), server_default="LAND_RECORD"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_validation_rules_code", "validation_rules", ["rule_code"])
    op.create_index("ix_validation_rules_active", "validation_rules", ["is_active", "applies_to"])

    # ── validation_results ────────────────────────────────────────────────────
    op.create_table("validation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("validation_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("field_name", sa.String(64), nullable=True),
        sa.Column("actual_value", sa.Text, nullable=True),
        sa.Column("expected_pattern", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("resolved", sa.Boolean, server_default="false"),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("land_record_id", "rule_id", name="uq_validation_result"),
    )
    op.create_index("ix_validation_results_record_failed", "validation_results", ["land_record_id", "passed"])

    # ── verification_actions ──────────────────────────────────────────────────
    op.create_table("verification_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", enums["verification_action_type_enum"], nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("previous_status", sa.String(32), nullable=True),
        sa.Column("new_status", sa.String(32), nullable=True),
        sa.Column("metadata_json", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_verification_actions_record", "verification_actions", ["land_record_id", "created_at"])

    # ── gis_coordinates ───────────────────────────────────────────────────────
    op.create_table("gis_coordinates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("land_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("land_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("altitude_m", sa.Float, nullable=True),
        sa.Column("geojson", postgresql.JSON, nullable=True),
        sa.Column("coordinate_type", enums["coordinate_type_enum"], nullable=False, server_default="CENTROID"),
        sa.Column("accuracy_meters", sa.Float, nullable=True),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column("datum", sa.String(32), server_default="WGS84"),
        sa.Column("captured_at", sa.String(20), nullable=True),
        sa.Column("captured_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="ck_latitude"),
        sa.CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="ck_longitude"),
    )
    op.create_index("ix_gis_lat_lng", "gis_coordinates", ["latitude", "longitude"])
    op.create_index("ix_gis_land_record", "gis_coordinates", ["land_record_id"])

    # ── notifications ─────────────────────────────────────────────────────────
    op.create_table("notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notification_type", enums["notification_type_enum"], nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("is_read", sa.Boolean, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_recipient_unread", "notifications", ["recipient_id", "is_read", "created_at"])


def downgrade() -> None:
    for tbl in [
        "notifications", "gis_coordinates", "verification_actions",
        "validation_results", "validation_rules", "mutations", "registrations",
        "survey_details", "plots", "land_record_owners", "owners",
    ]:
        op.drop_table(tbl)

    # Remove added columns
    op.drop_index("ix_land_records_search_vector", "land_records")
    op.drop_column("land_records", "search_vector")

    for name in [
        "owner_type_enum", "plot_status_enum", "survey_type_enum",
        "mutation_type_enum", "mutation_status_enum", "registration_type_enum",
        "rule_severity_enum", "verification_action_type_enum",
        "coordinate_type_enum", "notification_type_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {name}")
