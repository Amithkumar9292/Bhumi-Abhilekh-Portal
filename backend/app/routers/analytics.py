"""
Analytics Router — System-wide statistics, KPIs and reports.

Every figure here is computed from the tables the intake pipeline writes, so an
uploaded document moves the numbers the moment it finishes processing.

Endpoints:
  GET /analytics/kpis              — top-level KPI snapshot
  GET /analytics/records-by-status — status distribution
  GET /analytics/records-by-district — district breakdown
  GET /analytics/records-by-state  — state breakdown
  GET /analytics/records-by-land-use — land use distribution
  GET /analytics/processing-throughput — daily processing counts (30d)
  GET /analytics/verification-rate — approval/rejection stats
  GET /analytics/area-distribution — area range histogram
  GET /analytics/anomaly-trends    — anomaly counts by type
  GET /analytics/documents         — upload pipeline summary
  GET /analytics/validation-health — pass/fail per extracted field
  GET /analytics/field-accuracy    — mean confidence per extracted field
  GET /analytics/officer-activity  — per-officer workload
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import select, func, case

from app.dependencies import CurrentUser, DBSession
from app.models.land_record import LandRecord, RecordStatus
from app.models.document import Document, DocumentStatus
from app.models.pipeline import (
    ExtractedField, FieldValidationStatus, ProcessingJob, ProcessingStatus,
    PipelineAnomaly,
)
from app.models.user import User, RoleEnum

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/kpis")
async def get_kpis(db: DBSession, current_user: CurrentUser) -> dict:
    """Top-level KPI snapshot."""
    # Record counts
    total_records = (await db.execute(select(func.count(LandRecord.id)))).scalar() or 0
    verified = (await db.execute(select(func.count(LandRecord.id)).where(LandRecord.status == RecordStatus.VERIFIED))).scalar() or 0
    pending = (await db.execute(select(func.count(LandRecord.id)).where(LandRecord.status == RecordStatus.PENDING))).scalar() or 0
    under_review = (await db.execute(select(func.count(LandRecord.id)).where(LandRecord.status == RecordStatus.UNDER_REVIEW))).scalar() or 0
    rejected = (await db.execute(select(func.count(LandRecord.id)).where(LandRecord.status == RecordStatus.REJECTED))).scalar() or 0

    # Documents
    total_docs = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    docs_processed = (await db.execute(select(func.count(Document.id)).where(Document.status == DocumentStatus.VALIDATED))).scalar() or 0
    # Records that exist because a scan was uploaded, as opposed to seeded ones.
    uploaded_records = (await db.execute(
        select(func.count(func.distinct(ProcessingJob.land_record_id)))
        .where(ProcessingJob.land_record_id.isnot(None))
    )).scalar() or 0
    docs_today = (await db.execute(
        select(func.count(Document.id)).where(
            Document.created_at >= datetime.now(timezone.utc) - timedelta(days=1)
        )
    )).scalar() or 0

    # Pipeline
    total_jobs = (await db.execute(select(func.count(ProcessingJob.id)))).scalar() or 0
    jobs_failed = (await db.execute(select(func.count(ProcessingJob.id)).where(ProcessingJob.status == ProcessingStatus.FAILED))).scalar() or 0
    jobs_pending_review = (await db.execute(select(func.count(ProcessingJob.id)).where(ProcessingJob.status == ProcessingStatus.PENDING_REVIEW))).scalar() or 0

    # Total area
    total_area = (await db.execute(select(func.sum(LandRecord.area_hectares)))).scalar() or 0.0

    # Anomalies open
    open_anomalies = (await db.execute(select(func.count(PipelineAnomaly.id)).where(PipelineAnomaly.resolved == False))).scalar() or 0

    # Active users
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar() or 0

    verification_rate = round(verified / total_records * 100, 1) if total_records else 0
    processing_success_rate = round((total_jobs - jobs_failed) / total_jobs * 100, 1) if total_jobs else 0

    return {
        "records": {
            "total": total_records,
            "verified": verified,
            "pending": pending,
            "under_review": under_review,
            "rejected": rejected,
            "verification_rate_pct": verification_rate,
        },
        "documents": {
            "total": total_docs,
            "processed": docs_processed,
            "processing_rate_pct": round(docs_processed / total_docs * 100, 1) if total_docs else 0,
            "uploaded_last_24h": docs_today,
            "records_from_upload": uploaded_records,
        },
        "pipeline": {
            "total_jobs": total_jobs,
            "failed": jobs_failed,
            "pending_review": jobs_pending_review,
            "success_rate_pct": processing_success_rate,
        },
        "area": {"total_hectares": round(float(total_area), 2)},
        "anomalies": {"open": open_anomalies},
        "users": {"active": active_users},
        "as_of": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "⚠ Demo data — synthetic and not legally binding",
    }


@router.get("/records-by-status")
async def records_by_status(db: DBSession, current_user: CurrentUser) -> dict:
    result = await db.execute(
        select(LandRecord.status, func.count(LandRecord.id))
        .group_by(LandRecord.status)
        .order_by(func.count(LandRecord.id).desc())
    )
    return {"data": [{"status": row[0].value, "count": row[1]} for row in result.all()]}


@router.get("/records-by-district")
async def records_by_district(
    limit: int = Query(15, ge=1, le=50),
    *,
    db: DBSession, current_user: CurrentUser,
) -> dict:
    result = await db.execute(
        select(LandRecord.district, LandRecord.state, func.count(LandRecord.id).label("count"),
               func.sum(LandRecord.area_hectares).label("total_area"))
        .group_by(LandRecord.district, LandRecord.state)
        .order_by(func.count(LandRecord.id).desc())
        .limit(limit)
    )
    return {"data": [
        {"district": row[0], "state": row[1], "count": row[2], "total_area_ha": round(float(row[3] or 0), 2)}
        for row in result.all()
    ]}


@router.get("/records-by-land-use")
async def records_by_land_use(db: DBSession, current_user: CurrentUser) -> dict:
    result = await db.execute(
        select(LandRecord.land_use_type, func.count(LandRecord.id).label("count"),
               func.sum(LandRecord.area_hectares).label("total_area"))
        .group_by(LandRecord.land_use_type)
        .order_by(func.count(LandRecord.id).desc())
    )
    return {"data": [
        {"land_use": row[0].value, "count": row[1], "total_area_ha": round(float(row[2] or 0), 2)}
        for row in result.all()
    ]}


@router.get("/processing-throughput")
async def processing_throughput(
    days: int = Query(30, ge=1, le=90),
    *,
    db: DBSession, current_user: CurrentUser,
) -> dict:
    """Daily job counts for the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            func.date_trunc("day", ProcessingJob.created_at).label("day"),
            func.count(ProcessingJob.id).label("total"),
            func.sum(case((ProcessingJob.status == ProcessingStatus.COMPLETED, 1), else_=0)).label("completed"),
            func.sum(case((ProcessingJob.status == ProcessingStatus.FAILED, 1), else_=0)).label("failed"),
        )
        .where(ProcessingJob.created_at >= cutoff)
        .group_by("day")
        .order_by("day")
    )
    return {"days": days, "data": [
        {
            "date": row[0].date().isoformat() if row[0] else None,
            "total": row[1], "completed": int(row[2] or 0), "failed": int(row[3] or 0),
        }
        for row in result.all()
    ]}


@router.get("/verification-rate")
async def verification_rate_over_time(
    days: int = Query(30, ge=1, le=90),
    *,
    db: DBSession, current_user: CurrentUser,
) -> dict:
    """Daily verification decisions for the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            func.date_trunc("day", LandRecord.verified_at).label("day"),
            LandRecord.status,
            func.count(LandRecord.id).label("count"),
        )
        .where(
            LandRecord.verified_at >= cutoff,
            LandRecord.status.in_([RecordStatus.VERIFIED, RecordStatus.REJECTED]),
        )
        .group_by("day", LandRecord.status)
        .order_by("day")
    )
    return {"days": days, "data": [
        {"date": row[0].date().isoformat() if row[0] else None, "status": row[1].value, "count": row[2]}
        for row in result.all()
    ]}


@router.get("/area-distribution")
async def area_distribution(db: DBSession, current_user: CurrentUser) -> dict:
    """Histogram of area ranges."""
    buckets = [
        ("0–0.5 ha",   0,     0.5),
        ("0.5–1 ha",   0.5,   1.0),
        ("1–2 ha",     1.0,   2.0),
        ("2–5 ha",     2.0,   5.0),
        ("5–10 ha",    5.0,   10.0),
        ("10–50 ha",   10.0,  50.0),
        ("50–100 ha",  50.0,  100.0),
        (">100 ha",    100.0, 1e9),
    ]
    data = []
    for label, lo, hi in buckets:
        count = (await db.execute(
            select(func.count(LandRecord.id)).where(
                LandRecord.area_hectares >= lo, LandRecord.area_hectares < hi
            )
        )).scalar() or 0
        data.append({"range": label, "count": count})
    return {"data": data}


@router.get("/anomaly-trends")
async def anomaly_trends(db: DBSession, current_user: CurrentUser) -> dict:
    result = await db.execute(
        select(PipelineAnomaly.anomaly_type, PipelineAnomaly.severity, func.count(PipelineAnomaly.id).label("count"))
        .group_by(PipelineAnomaly.anomaly_type, PipelineAnomaly.severity)
        .order_by(func.count(PipelineAnomaly.id).desc())
    )
    return {"data": [
        {"type": row[0].value, "severity": row[1], "count": row[2]}
        for row in result.all()
    ]}


@router.get("/records-by-state")
async def records_by_state(
    limit: int = Query(20, ge=1, le=50),
    *,
    db: DBSession, current_user: CurrentUser,
) -> dict:
    """State-wise digitization progress.

    Aggregates the district rows the report screen already shows, so the state
    tab can never disagree with the district tab.
    """
    result = await db.execute(
        select(
            LandRecord.state,
            func.count(LandRecord.id).label("count"),
            func.sum(case((LandRecord.status == RecordStatus.VERIFIED, 1), else_=0)).label("verified"),
            func.sum(LandRecord.area_hectares).label("total_area"),
        )
        .group_by(LandRecord.state)
        .order_by(func.count(LandRecord.id).desc())
        .limit(limit)
    )
    return {"data": [
        {
            "state": row[0],
            "count": row[1],
            "verified": int(row[2] or 0),
            "total_area_ha": round(float(row[3] or 0), 2),
        }
        for row in result.all()
    ]}


@router.get("/documents")
async def documents_summary(db: DBSession, current_user: CurrentUser) -> dict:
    """Upload pipeline summary: where every scanned file currently sits.

    This is the section-level view of the intake queue — without it a report can
    say how many records exist but not how many got there from a scan.
    """
    by_status = await db.execute(
        select(Document.status, func.count(Document.id))
        .group_by(Document.status)
        .order_by(func.count(Document.id).desc())
    )
    by_type = await db.execute(
        select(Document.document_type, func.count(Document.id))
        .group_by(Document.document_type)
        .order_by(func.count(Document.id).desc())
    )
    records_with_docs = (await db.execute(
        select(func.count(func.distinct(ProcessingJob.land_record_id)))
        .where(ProcessingJob.land_record_id.isnot(None))
    )).scalar() or 0
    records_flagged = (await db.execute(
        select(func.count(func.distinct(ProcessingJob.land_record_id)))
        .join(PipelineAnomaly, PipelineAnomaly.job_id == ProcessingJob.id)
        .where(ProcessingJob.land_record_id.isnot(None))
    )).scalar() or 0

    return {
        "by_status": [
            {"status": row[0].value, "count": row[1]} for row in by_status.all()
        ],
        "by_type": [
            {"document_type": row[0].value, "count": row[1]} for row in by_type.all()
        ],
        "records_from_upload": records_with_docs,
        "records_with_anomalies": records_flagged,
    }


@router.get("/validation-health")
async def validation_health(db: DBSession, current_user: CurrentUser) -> dict:
    """Pass/fail counts per extracted field, straight from the pipeline.

    Replaces a hand-maintained table of validation rules: a field only appears
    here once a document has actually been read, so the numbers are whatever the
    current upload traffic produced.
    """
    result = await db.execute(
        select(
            ExtractedField.field_name,
            func.count(ExtractedField.id).label("total"),
            func.sum(case((ExtractedField.validation_status == FieldValidationStatus.AUTO_VALID, 1), else_=0)).label("auto_valid"),
            func.sum(case((ExtractedField.validation_status == FieldValidationStatus.AUTO_INVALID, 1), else_=0)).label("auto_invalid"),
            func.sum(case((ExtractedField.validation_status == FieldValidationStatus.HUMAN_VERIFIED, 1), else_=0)).label("human_verified"),
            func.sum(case((ExtractedField.validation_status == FieldValidationStatus.HUMAN_REJECTED, 1), else_=0)).label("human_rejected"),
            func.sum(case((ExtractedField.needs_review.is_(True), 1), else_=0)).label("needs_review"),
        )
        .group_by(ExtractedField.field_name)
        .order_by(func.count(ExtractedField.id).desc())
    )
    data = []
    for row in result.all():
        total = row[1] or 0
        accepted = int(row[2] or 0) + int(row[4] or 0)
        data.append({
            "field_name": row[0],
            "total": total,
            "auto_valid": int(row[2] or 0),
            "auto_invalid": int(row[3] or 0),
            "human_verified": int(row[4] or 0),
            "human_rejected": int(row[5] or 0),
            "needs_review": int(row[6] or 0),
            "accepted": accepted,
            "rejected": total - accepted,
            "pass_rate_pct": round(accepted / total * 100, 1) if total else 0.0,
        })
    return {"data": data}


@router.get("/field-accuracy")
async def field_accuracy(db: DBSession, current_user: CurrentUser) -> dict:
    """Mean extraction confidence per field — the honest accuracy chart.

    Averaging the per-field confidence the pipeline actually recorded replaces
    the hand-written percentages, so a drop in extraction quality shows up here
    instead of staying invisible behind a static number.
    """
    result = await db.execute(
        select(
            ExtractedField.field_name,
            func.max(ExtractedField.field_display),
            func.count(ExtractedField.id).label("total"),
            func.avg(ExtractedField.confidence_score).label("avg_confidence"),
            func.avg(ExtractedField.ocr_confidence).label("avg_ocr_confidence"),
            func.sum(case((ExtractedField.normalized_value.isnot(None), 1), else_=0)).label("extracted"),
        )
        .group_by(ExtractedField.field_name)
        .order_by(func.count(ExtractedField.id).desc())
    )
    data = []
    for row in result.all():
        avg = float(row[3] or 0)
        data.append({
            "field_name": row[0],
            "field_display": row[1] or row[0],
            "samples": row[2] or 0,
            "extracted": int(row[5] or 0),
            "found_rate_pct": round((row[5] or 0) / row[2] * 100, 1) if row[2] else 0.0,
            "avg_confidence_pct": round(avg * 100, 1),
            "avg_ocr_confidence_pct": round(float(row[4] or 0) * 100, 1),
        })
    overall = (
        (await db.execute(select(func.avg(ProcessingJob.overall_confidence)))).scalar()
    )
    return {
        "data": data,
        "overall_confidence_pct": round(float(overall or 0) * 100, 1),
    }


@router.get("/officer-activity")
async def officer_activity(
    days: int = Query(30, ge=1, le=90),
    *,
    db: DBSession, current_user: CurrentUser,
) -> dict:
    """Per-officer record creation and verification counts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            User.full_name, User.role, User.username,
            func.count(LandRecord.id).label("records_created"),
        )
        .join(LandRecord, LandRecord.created_by == User.id, isouter=True)
        .where(User.role.in_([RoleEnum.OFFICER, RoleEnum.VERIFIER, RoleEnum.ADMIN]))
        .where(LandRecord.created_at >= cutoff)
        .group_by(User.id, User.full_name, User.role, User.username)
        .order_by(func.count(LandRecord.id).desc())
    )
    return {"days": days, "data": [
        {"name": row[0], "role": row[1].value, "username": row[2], "records_created": row[3]}
        for row in result.all()
    ]}
