"""
Validation Engine — Configurable rule-based land record validator.

Architecture:
  - ValidationEngine is the orchestrator
  - Each rule is a function registered in RULE_REGISTRY
  - Rules are loaded from the validation_rules DB table (configurable at runtime)
  - Results are persisted in validation_results table

Rule categories:
  COMPLETENESS   — required fields present
  FORMAT         — field format / regex checks
  CONSISTENCY    — internal cross-field consistency
  CROSS_RECORD   — checks against other records in DB
  DUPLICATE      — duplicate detection
  CONFIDENCE     — OCR confidence thresholds
  GIS            — coordinate validity
  FINANCIAL      — amount reasonableness

Built-in rules (always run even if DB has no rule record):
  VR001 — Required fields completeness
  VR002 — Area range sanity (0.001–5000 ha)
  VR003 — Khasra number format
  VR004 — PIN code format
  VR005 — Land use vs area consistency (forest > 5 ha, etc.)
  VR006 — Owner name length
  VR007 — District / state pair consistency
  VR008 — Duplicate khasra in same district
  VR009 — Area vs registered area discrepancy >20%
  VR010 — Village / tehsil mismatch (cross-record)
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.land_record import LandRecord, LandUseType

log = logging.getLogger(__name__)

# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class RuleResult:
    rule_code: str
    passed: bool
    severity: str           # ERROR | WARNING | INFO
    message: str
    field_name: Optional[str] = None
    actual_value: Optional[str] = None
    expected_pattern: Optional[str] = None
    confidence: Optional[float] = None


@dataclass
class ValidationReport:
    record_id: uuid.UUID
    passed: bool            # True only if no ERROR-severity failures
    error_count: int
    warning_count: int
    info_count: int
    results: list[RuleResult] = field(default_factory=list)
    is_blocking: bool = False  # True if any blocking rule failed


# ── Rule function signature ───────────────────────────────────────────────────
# RuleFunc = async (record: LandRecord, db: AsyncSession, config: dict) -> RuleResult

RULE_REGISTRY: dict[str, Callable] = {}

def rule(code: str):
    """Decorator to register a rule function."""
    def _dec(fn: Callable) -> Callable:
        RULE_REGISTRY[code] = fn
        return fn
    return _dec


# ── Built-in rules ────────────────────────────────────────────────────────────

@rule("VR001")
async def check_required_fields(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """All required fields must be present and non-empty."""
    required = {
        "khasra_number": record.khasra_number,
        "owner_name":    record.owner_name,
        "district":      record.district,
        "state":         record.state,
        "village":       record.village,
        "tehsil":        record.tehsil,
        "area_hectares": record.area_hectares,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        return RuleResult("VR001", False, "ERROR",
                          f"Required fields missing: {', '.join(missing)}",
                          field_name=", ".join(missing))
    return RuleResult("VR001", True, "ERROR", "All required fields present")


@rule("VR002")
async def check_area_range(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """Area must be within configured bounds (default 0.001–5000 ha)."""
    min_area = config.get("min_area", 0.001)
    max_area = config.get("max_area", 5000.0)
    # `area_hectares` is a non-nullable column (Mapped[float], nullable=False),
    # so it is always populated on a persisted record.
    a = record.area_hectares
    if a <= 0:
        return RuleResult("VR002", False, "ERROR", "Area must be positive",
                          field_name="area_hectares", actual_value=str(a))
    if a < min_area:
        return RuleResult("VR002", False, "WARNING",
                          f"Area {a} ha is suspiciously small (min: {min_area} ha)",
                          field_name="area_hectares", actual_value=str(a),
                          expected_pattern=f">={min_area}")
    if a > max_area:
        return RuleResult("VR002", False, "ERROR",
                          f"Area {a} ha exceeds maximum allowed ({max_area} ha)",
                          field_name="area_hectares", actual_value=str(a),
                          expected_pattern=f"<={max_area}")
    return RuleResult("VR002", True, "ERROR", f"Area {a} ha is within bounds")


@rule("VR003")
async def check_khasra_format(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """Khasra number must match expected alphanumeric format."""
    pattern = config.get("pattern", r"^[A-Z0-9][A-Z0-9\-/]{1,30}$")
    val = (record.khasra_number or "").upper()
    if not re.match(pattern, val):
        return RuleResult("VR003", False, "WARNING",
                          f"Khasra number '{val}' does not match expected format",
                          field_name="khasra_number", actual_value=val, expected_pattern=pattern)
    return RuleResult("VR003", True, "WARNING", f"Khasra number format valid: {val}")


@rule("VR004")
async def check_pin_code(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """PIN code, if provided, must be 6 digits."""
    if not record.pin_code:
        return RuleResult("VR004", True, "INFO", "PIN code not provided (optional)")
    if not re.match(r"^\d{6}$", record.pin_code):
        return RuleResult("VR004", False, "WARNING",
                          f"PIN code '{record.pin_code}' must be exactly 6 digits",
                          field_name="pin_code", actual_value=record.pin_code,
                          expected_pattern=r"^\d{6}$")
    return RuleResult("VR004", True, "WARNING", f"PIN code {record.pin_code} valid")


@rule("VR005")
async def check_land_use_area_consistency(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """Check land-use vs area makes sense."""
    a = record.area_hectares or 0
    lu = record.land_use_type
    if lu == LandUseType.INDUSTRIAL and a < config.get("min_industrial_ha", 0.1):
        return RuleResult("VR005", False, "WARNING",
                          f"Industrial land use with area {a} ha seems very small",
                          field_name="area_hectares")
    if lu == LandUseType.FOREST and a < config.get("min_forest_ha", 1.0):
        return RuleResult("VR005", False, "INFO",
                          f"Forest classification with area {a} ha — please verify",
                          field_name="area_hectares")
    return RuleResult("VR005", True, "WARNING", "Land use / area combination is consistent")


@rule("VR006")
async def check_owner_name_quality(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """Owner name must be reasonable length and not contain numbers."""
    name = record.owner_name or ""
    min_len = config.get("min_name_len", 3)
    max_len = config.get("max_name_len", 200)
    if len(name) < min_len:
        return RuleResult("VR006", False, "ERROR",
                          f"Owner name too short ({len(name)} chars, min {min_len})",
                          field_name="owner_name", actual_value=name)
    if len(name) > max_len:
        return RuleResult("VR006", False, "WARNING",
                          f"Owner name unusually long ({len(name)} chars)",
                          field_name="owner_name", actual_value=name[:50])
    if re.search(r"\d{5,}", name):
        return RuleResult("VR006", False, "WARNING",
                          "Owner name contains suspicious numeric sequence",
                          field_name="owner_name", actual_value=name)
    return RuleResult("VR006", True, "ERROR", "Owner name quality check passed")


@rule("VR007")
async def check_location_consistency(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """State, district, tehsil should not be identical (copy-paste error)."""
    vals = [record.state, record.district, record.tehsil, record.village]
    non_null = [v for v in vals if v]
    if len(non_null) != len(set(v.lower() for v in non_null)):
        return RuleResult("VR007", False, "WARNING",
                          "Duplicate location values detected (state/district/tehsil/village should all differ)",
                          field_name="state, district, tehsil, village")
    return RuleResult("VR007", True, "WARNING", "Location fields are distinct")


@rule("VR008")
async def check_duplicate_khasra(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """Same khasra_number + district combination should not exist in another record."""
    q = select(func.count()).where(
        and_(
            LandRecord.khasra_number == record.khasra_number,
            LandRecord.district.ilike(record.district),
            LandRecord.id != record.id,
        )
    )
    count = (await db.execute(q)).scalar() or 0
    if count > 0:
        return RuleResult("VR008", False, "ERROR",
                          f"Khasra '{record.khasra_number}' in district '{record.district}' "
                          f"already exists in {count} other record(s)",
                          field_name="khasra_number", actual_value=record.khasra_number,
                          confidence=0.95)
    return RuleResult("VR008", True, "ERROR", "No duplicate khasra found in same district")


@rule("VR009")
async def check_area_consistency_across_records(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """
    If another record with same khasra exists, check area deviation.
    (Covers mutation scenarios where area changes >20% without split/merge.)
    """
    tolerance = config.get("area_tolerance_pct", 20.0)
    q = select(LandRecord.area_hectares).where(
        and_(
            LandRecord.khasra_number == record.khasra_number,
            LandRecord.id != record.id,
        )
    ).limit(1)
    existing_area = (await db.execute(q)).scalar_one_or_none()
    if existing_area is None:
        return RuleResult("VR009", True, "WARNING", "No existing record for area comparison")
    if record.area_hectares and existing_area:
        deviation_pct = abs(record.area_hectares - existing_area) / existing_area * 100
        if deviation_pct > tolerance:
            return RuleResult("VR009", False, "WARNING",
                              f"Area {record.area_hectares} ha deviates {deviation_pct:.1f}% "
                              f"from existing record ({existing_area} ha) — tolerance: {tolerance}%",
                              field_name="area_hectares",
                              actual_value=str(record.area_hectares))
    return RuleResult("VR009", True, "WARNING", "Area consistent with existing records")


@rule("VR010")
async def check_village_tehsil_state(record: LandRecord, db: AsyncSession, config: dict) -> RuleResult:
    """Village must have appeared with same tehsil in existing records."""
    if not record.village or not record.tehsil:
        return RuleResult("VR010", True, "INFO", "Village or tehsil not provided — skip cross-check")
    q = select(func.count()).where(
        and_(
            LandRecord.village.ilike(record.village),
            ~LandRecord.tehsil.ilike(record.tehsil),
            LandRecord.id != record.id,
        )
    )
    conflict_count = (await db.execute(q)).scalar() or 0
    if conflict_count > 0:
        return RuleResult("VR010", False, "WARNING",
                          f"Village '{record.village}' has been associated with a different tehsil "
                          f"in {conflict_count} existing record(s). Expected tehsil: '{record.tehsil}'",
                          field_name="village, tehsil")
    return RuleResult("VR010", True, "WARNING", "Village/tehsil combination consistent")


# ── Engine ────────────────────────────────────────────────────────────────────

# Default rule configs (used when no DB config override exists)
DEFAULT_CONFIGS: dict[str, dict] = {
    "VR001": {},
    "VR002": {"min_area": 0.001, "max_area": 5000.0},
    "VR003": {"pattern": r"^[A-Z0-9][A-Z0-9\-/]{1,30}$"},
    "VR004": {},
    "VR005": {"min_industrial_ha": 0.1, "min_forest_ha": 1.0},
    "VR006": {"min_name_len": 3, "max_name_len": 200},
    "VR007": {},
    "VR008": {},
    "VR009": {"area_tolerance_pct": 20.0},
    "VR010": {},
}


class ValidationEngine:
    """
    Runs all active rules against a LandRecord and returns a ValidationReport.
    Rule configs can be overridden from the validation_rules DB table.
    """

    def __init__(self, db_rule_configs: dict[str, dict] | None = None):
        # Merge DB configs over defaults
        self.configs = {**DEFAULT_CONFIGS, **(db_rule_configs or {})}

    async def validate(
        self,
        record: LandRecord,
        db: AsyncSession,
        rule_codes: list[str] | None = None,
    ) -> ValidationReport:
        """
        Run all (or specified) rules. Returns a ValidationReport.
        Also persists results to validation_results table.
        """
        codes = rule_codes or list(RULE_REGISTRY.keys())
        results: list[RuleResult] = []

        for code in codes:
            fn = RULE_REGISTRY.get(code)
            if not fn:
                log.warning("Unknown rule code: %s", code)
                continue
            cfg = self.configs.get(code, {})
            try:
                result = await fn(record, db, cfg)
                results.append(result)
            except Exception as exc:
                log.error("Rule %s failed with exception: %s", code, exc)
                results.append(RuleResult(
                    code, False, "WARNING",
                    f"Rule evaluation error: {exc}",
                ))

        errors   = [r for r in results if not r.passed and r.severity == "ERROR"]
        warnings = [r for r in results if not r.passed and r.severity == "WARNING"]
        infos    = [r for r in results if r.severity == "INFO" and not r.passed]

        return ValidationReport(
            record_id=record.id,
            passed=len(errors) == 0,
            error_count=len(errors),
            warning_count=len(warnings),
            info_count=len(infos),
            results=results,
            is_blocking=len(errors) > 0,
        )

    async def persist_results(
        self,
        report: ValidationReport,
        db: AsyncSession,
        rule_id_map: dict[str, uuid.UUID],
    ) -> None:
        """
        Write/upsert ValidationResult rows to DB.
        rule_id_map: {rule_code: validation_rules.id}
        """
        from app.models.extended import ValidationResult
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        for r in report.results:
            rule_id = rule_id_map.get(r.rule_code)
            if not rule_id:
                continue
            # Upsert by (land_record_id, rule_id)
            stmt = pg_insert(ValidationResult).values(
                id=uuid.uuid4(),
                land_record_id=report.record_id,
                rule_id=rule_id,
                rule_code=r.rule_code,
                passed=r.passed,
                severity=r.severity,
                message=r.message,
                field_name=r.field_name,
                actual_value=r.actual_value,
                expected_pattern=r.expected_pattern,
                confidence=r.confidence,
            ).on_conflict_do_update(
                constraint="uq_validation_result",
                set_={
                    "passed": r.passed,
                    "message": r.message,
                    "actual_value": r.actual_value,
                    "evaluated_at": func.now(),
                }
            )
            await db.execute(stmt)
        await db.flush()
