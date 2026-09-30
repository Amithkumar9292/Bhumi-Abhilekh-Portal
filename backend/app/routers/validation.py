"""
Validation Router — REST API for the validation engine.

Endpoints:
  POST /validation/run/{record_id}          — run all rules on a record
  GET  /validation/results/{record_id}      — get latest results for a record
  POST /validation/results/{result_id}/resolve — mark a validation result resolved
  GET  /validation/rules                    — list all rules
  POST /validation/rules                    — create a new rule
  PUT  /validation/rules/{rule_id}          — update rule config
  DELETE /validation/rules/{rule_id}        — deactivate a rule
  GET  /validation/summary                  — system-wide validation health
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.dependencies import AdminUser, CurrentUser, DBSession, VerifierUser
from app.models.extended import ValidationResult, ValidationRule
from app.models.land_record import LandRecord
from app.services.audit_service import log_event
from app.services.validation_engine import ValidationEngine, RULE_REGISTRY

router = APIRouter(prefix="/validation", tags=["Validation"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    rule_code: str = Field(..., min_length=2, max_length=64)
    rule_name: str = Field(..., min_length=3)
    description: str
    severity: str = "WARNING"
    category: str = "CONSISTENCY"
    is_blocking: bool = False
    applies_to: str = "LAND_RECORD"
    config: Optional[dict] = None


class RuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    is_active: Optional[bool] = None
    is_blocking: Optional[bool] = None
    config: Optional[dict] = None


class RunOptions(BaseModel):
    rule_codes: Optional[list[str]] = None   # None = run all
    persist: bool = True


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _load_rule_configs(db: DBSession) -> dict[str, dict]:
    """Load all active rule configs from DB."""
    result = await db.execute(
        select(ValidationRule).where(ValidationRule.is_active == True)
    )
    rows = result.scalars().all()
    return {r.rule_code: (r.config or {}) for r in rows}


async def _load_rule_id_map(db: DBSession) -> dict[str, uuid.UUID]:
    """Map rule_code → rule UUID for persisting results."""
    result = await db.execute(select(ValidationRule.rule_code, ValidationRule.id))
    return {row[0]: row[1] for row in result.all()}


async def _ensure_default_rules(db: DBSession) -> None:
    """Idempotently create default rules if they don't exist."""
    DEFAULT_RULES = [
        ("VR001", "Required Fields", "All required fields must be present", "ERROR", "COMPLETENESS", True),
        ("VR002", "Area Range",      "Area must be within 0.001–5000 ha",   "ERROR", "CONSISTENCY",  True),
        ("VR003", "Khasra Format",   "Khasra number format validation",     "WARNING", "FORMAT",     False),
        ("VR004", "PIN Code Format", "PIN code must be 6 digits",           "WARNING", "FORMAT",     False),
        ("VR005", "Land Use/Area",   "Land use vs area consistency",        "WARNING", "CONSISTENCY", False),
        ("VR006", "Owner Name",      "Owner name quality check",            "ERROR", "COMPLETENESS", False),
        ("VR007", "Location",        "Distinct location field values",      "WARNING", "CONSISTENCY", False),
        ("VR008", "Duplicate Khasra","Duplicate khasra in same district",   "ERROR", "DUPLICATE",    True),
        ("VR009", "Area Consistency","Area deviation vs existing records",   "WARNING", "CROSS_RECORD",False),
        ("VR010", "Village/Tehsil",  "Village-tehsil cross-record check",   "WARNING", "CROSS_RECORD",False),
    ]
    for code, name, desc, sev, cat, blocking in DEFAULT_RULES:
        stmt = pg_insert(ValidationRule).values(
            id=uuid.uuid4(), rule_code=code, rule_name=name, description=desc,
            severity=sev, category=cat, is_active=True, is_blocking=blocking,
            applies_to="LAND_RECORD",
        ).on_conflict_do_nothing(index_elements=["rule_code"])
        await db.execute(stmt)
    await db.flush()


# ── Run validation ─────────────────────────────────────────────────────────────

@router.post("/run/{record_id}")
async def run_validation(
    record_id: uuid.UUID,
    *,
    db: DBSession,
    current_user: CurrentUser,
    options: RunOptions = Body(default_factory=RunOptions),
) -> dict:
    """Run all active validation rules on a land record."""
    record = await db.get(LandRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Land record not found")

    await _ensure_default_rules(db)
    db_configs = await _load_rule_configs(db)
    engine = ValidationEngine(db_configs)
    report = await engine.validate(record, db, options.rule_codes)

    if options.persist:
        rule_id_map = await _load_rule_id_map(db)
        await engine.persist_results(report, db, rule_id_map)

    await log_event("RUN_VALIDATION", current_user.id, "LandRecord", record_id,
                    {"errors": report.error_count, "warnings": report.warning_count})

    return {
        "record_id": str(record_id),
        "passed": report.passed,
        "is_blocking": report.is_blocking,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "info_count": report.info_count,
        "results": [
            {
                "rule_code": r.rule_code,
                "passed": r.passed,
                "severity": r.severity,
                "message": r.message,
                "field_name": r.field_name,
                "actual_value": r.actual_value,
                "confidence": r.confidence,
            }
            for r in report.results
        ],
    }


# ── Results ────────────────────────────────────────────────────────────────────

@router.get("/results/{record_id}")
async def get_validation_results(
    record_id: uuid.UUID,
    *,
    db: DBSession,
    current_user: CurrentUser,
    only_failures: bool = False,
) -> dict:
    q = select(ValidationResult).where(ValidationResult.land_record_id == record_id)
    if only_failures:
        q = q.where(ValidationResult.passed == False)
    result = await db.execute(q.order_by(ValidationResult.evaluated_at.desc()))
    rows = result.scalars().all()
    return {
        "record_id": str(record_id),
        "total": len(rows),
        "failures": sum(1 for r in rows if not r.passed),
        "results": [
            {
                "id": str(r.id),
                "rule_code": r.rule_code,
                "passed": r.passed,
                "severity": r.severity,
                "message": r.message,
                "field_name": r.field_name,
                "actual_value": r.actual_value,
                "confidence": r.confidence,
                "resolved": r.resolved,
                "evaluated_at": r.evaluated_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.post("/results/{result_id}/resolve")
async def resolve_validation_result(
    result_id: uuid.UUID,
    db: DBSession,
    current_user: VerifierUser,
) -> dict:
    vr = await db.get(ValidationResult, result_id)
    if not vr:
        raise HTTPException(status_code=404, detail="Validation result not found")
    vr.resolved = True
    vr.resolved_by = current_user.id
    await db.flush()
    return {"id": str(result_id), "resolved": True}


# ── Rules management ──────────────────────────────────────────────────────────

@router.get("/rules")
async def list_rules(
    *,
    db: DBSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> dict:
    q = select(ValidationRule).order_by(ValidationRule.rule_code)
    if category:
        q = q.where(ValidationRule.category == category)
    if is_active is not None:
        q = q.where(ValidationRule.is_active == is_active)
    result = await db.execute(q)
    rules = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "rule_code": r.rule_code,
                "rule_name": r.rule_name,
                "description": r.description,
                "severity": r.severity,
                "category": r.category,
                "is_active": r.is_active,
                "is_blocking": r.is_blocking,
                "config": r.config,
                "applies_to": r.applies_to,
            }
            for r in rules
        ],
        "total": len(rules),
        "built_in_codes": list(RULE_REGISTRY.keys()),
    }


@router.post("/rules", status_code=201)
async def create_rule(
    body: RuleCreate,
    db: DBSession,
    current_user: AdminUser,
) -> dict:
    existing = await db.execute(
        select(ValidationRule).where(ValidationRule.rule_code == body.rule_code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Rule '{body.rule_code}' already exists")

    rule = ValidationRule(**body.model_dump(), created_by=current_user.id, is_active=True)
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    await log_event("CREATE_RULE", current_user.id, "ValidationRule", rule.id, {"code": body.rule_code})
    return {"id": str(rule.id), "rule_code": rule.rule_code}


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: uuid.UUID,
    body: RuleUpdate,
    db: DBSession,
    current_user: AdminUser,
) -> dict:
    rule = await db.get(ValidationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(rule, k, v)
    await db.flush()
    await log_event("UPDATE_RULE", current_user.id, "ValidationRule", rule_id, {})
    return {"id": str(rule_id), "updated": True}


@router.delete("/rules/{rule_id}", status_code=204)
async def deactivate_rule(
    rule_id: uuid.UUID,
    db: DBSession,
    current_user: AdminUser,
) -> None:
    rule = await db.get(ValidationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.is_active = False
    await db.flush()


# ── System summary ─────────────────────────────────────────────────────────────

@router.get("/summary")
async def validation_summary(
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """System-wide validation health overview."""
    total_results = (await db.execute(select(func.count(ValidationResult.id)))).scalar() or 0
    failed_results = (await db.execute(
        select(func.count(ValidationResult.id)).where(ValidationResult.passed == False, ValidationResult.resolved == False)
    )).scalar() or 0
    error_results = (await db.execute(
        select(func.count(ValidationResult.id)).where(
            ValidationResult.passed == False,
            ValidationResult.severity == "ERROR",
            ValidationResult.resolved == False,
        )
    )).scalar() or 0
    records_with_errors = (await db.execute(
        select(func.count(func.distinct(ValidationResult.land_record_id))).where(
            ValidationResult.passed == False, ValidationResult.resolved == False
        )
    )).scalar() or 0

    return {
        "total_evaluations": total_results,
        "open_failures": failed_results,
        "open_errors": error_results,
        "records_with_issues": records_with_errors,
        "active_rules": (await db.execute(
            select(func.count(ValidationRule.id)).where(ValidationRule.is_active == True)
        )).scalar() or 0,
    }
