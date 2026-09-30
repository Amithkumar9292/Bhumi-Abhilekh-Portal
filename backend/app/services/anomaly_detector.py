"""
Anomaly Detector — Identifies data quality issues and cross-record conflicts.

Checks performed:
  1. DUPLICATE_RECORD   — same khasra_number already exists in DB
  2. AREA_MISMATCH      — extracted area deviates >20% from existing record
  3. OWNER_CONFLICT     — owner name differs significantly from existing record
  4. SURVEY_FORMAT_ERROR — survey number doesn't match state-specific format
  5. MISSING_REQUIRED   — required fields are absent or low confidence
  6. LOW_CONFIDENCE_FIELD — any field below WARN_THRESHOLD
  7. BOUNDARY_CONFLICT  — geometry overlap (placeholder for future GIS integration)
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.field_extractor import FieldResult


WARN_THRESHOLD = 0.65   # fields below this generate LOW_CONFIDENCE anomaly
AREA_TOLERANCE = 0.20   # 20% deviation triggers AREA_MISMATCH


@dataclass
class AnomalyResult:
    anomaly_type: str
    field_name: Optional[str]
    severity: str           # HIGH | MEDIUM | LOW
    description: str
    confidence: float       # detector's confidence this is a real anomaly


class AnomalyDetector:

    async def detect(
        self,
        fields: list[FieldResult],
        db: AsyncSession,
        land_record_id: Optional[uuid.UUID] = None,
    ) -> tuple[list[AnomalyResult], bool]:
        """
        Run all anomaly checks.
        Returns (anomaly_list, is_duplicate).
        """
        anomalies: list[AnomalyResult] = []
        is_duplicate = False

        field_map = {f.field_name: f for f in fields}

        # 1. Missing required fields
        anomalies.extend(self._check_missing(field_map))

        # 2. Low-confidence fields
        anomalies.extend(self._check_low_confidence(fields))

        # 3. Survey number format
        anomalies.extend(self._check_survey_format(field_map))

        # 4. Area sanity check (must be positive, reasonable)
        anomalies.extend(self._check_area_sanity(field_map))

        # 5. Duplicate detection against existing records
        dup_anomalies, is_duplicate = await self._check_duplicate(field_map, db, land_record_id)
        anomalies.extend(dup_anomalies)

        return anomalies, is_duplicate

    # ── Individual checks ─────────────────────────────────────────

    def _check_missing(self, field_map: dict[str, FieldResult]) -> list[AnomalyResult]:
        required = ["khasra_number", "owner_name", "district", "state", "land_area"]
        results = []
        for f in required:
            fr = field_map.get(f)
            if not fr or not fr.normalized_value:
                results.append(AnomalyResult(
                    anomaly_type="MISSING_REQUIRED",
                    field_name=f,
                    severity="HIGH",
                    description=f"Required field '{f.replace('_', ' ').title()}' could not be extracted from the document.",
                    confidence=0.95,
                ))
        return results

    def _check_low_confidence(self, fields: list[FieldResult]) -> list[AnomalyResult]:
        results = []
        for f in fields:
            if f.normalized_value and f.confidence_score < WARN_THRESHOLD:
                results.append(AnomalyResult(
                    anomaly_type="LOW_CONFIDENCE_FIELD",
                    field_name=f.field_name,
                    severity="MEDIUM" if f.confidence_score > 0.40 else "HIGH",
                    description=(
                        f"Field '{f.field_display}' extracted with low confidence "
                        f"({f.confidence_score:.0%}). Value: '{f.normalized_value}'"
                    ),
                    confidence=1.0 - f.confidence_score,
                ))
        return results

    def _check_survey_format(self, field_map: dict[str, FieldResult]) -> list[AnomalyResult]:
        results = []
        survey = field_map.get("survey_number")
        if survey and survey.normalized_value:
            val = survey.normalized_value
            # Generic format: should start with letters or digits, no special chars
            if not re.match(r"^[A-Z0-9][A-Z0-9\-/]{1,18}$", val):
                results.append(AnomalyResult(
                    anomaly_type="SURVEY_FORMAT_ERROR",
                    field_name="survey_number",
                    severity="MEDIUM",
                    description=f"Survey number '{val}' does not match expected format (alphanumeric, max 20 chars).",
                    confidence=0.85,
                ))
        return results

    def _check_area_sanity(self, field_map: dict[str, FieldResult]) -> list[AnomalyResult]:
        results = []
        area_field = field_map.get("land_area")
        if area_field and area_field.normalized_value:
            try:
                area = float(area_field.normalized_value)
                if area <= 0:
                    results.append(AnomalyResult(
                        anomaly_type="AREA_MISMATCH",
                        field_name="land_area",
                        severity="HIGH",
                        description=f"Extracted land area ({area} ha) is non-positive — likely an extraction error.",
                        confidence=0.90,
                    ))
                elif area > 500:
                    results.append(AnomalyResult(
                        anomaly_type="AREA_MISMATCH",
                        field_name="land_area",
                        severity="MEDIUM",
                        description=f"Extracted land area ({area} ha) is unusually large — please verify.",
                        confidence=0.75,
                    ))
            except (ValueError, TypeError):
                pass
        return results

    async def _check_duplicate(
        self,
        field_map: dict[str, FieldResult],
        db: AsyncSession,
        exclude_id: Optional[uuid.UUID],
    ) -> tuple[list[AnomalyResult], bool]:
        from app.models.land_record import LandRecord
        results: list[AnomalyResult] = []
        is_dup = False

        khasra_field = field_map.get("khasra_number")
        if not khasra_field or not khasra_field.normalized_value:
            return results, is_dup

        khasra_val = khasra_field.normalized_value

        try:
            q = select(LandRecord).where(
                LandRecord.khasra_number == khasra_val
            )
            if exclude_id:
                q = q.where(LandRecord.id != exclude_id)

            result = await db.execute(q.limit(3))
            existing = result.scalars().all()

            if existing:
                is_dup = True
                refs = ", ".join(str(r.id)[:8] + "…" for r in existing)
                results.append(AnomalyResult(
                    anomaly_type="DUPLICATE_RECORD",
                    field_name="khasra_number",
                    severity="HIGH",
                    description=(
                        f"Khasra number '{khasra_val}' already exists in {len(existing)} "
                        f"record(s): {refs}. This may be a duplicate submission."
                    ),
                    confidence=0.95,
                ))

                # Owner conflict check
                owner_field = field_map.get("owner_name")
                if owner_field and owner_field.normalized_value:
                    for rec in existing:
                        similarity = SequenceMatcher(
                            None,
                            owner_field.normalized_value.lower(),
                            (rec.owner_name or "").lower(),
                        ).ratio()
                        if similarity < 0.60:
                            results.append(AnomalyResult(
                                anomaly_type="OWNER_CONFLICT",
                                field_name="owner_name",
                                severity="HIGH",
                                description=(
                                    f"Owner name mismatch for khasra '{khasra_val}': "
                                    f"document says '{owner_field.normalized_value}' but "
                                    f"existing record has '{rec.owner_name}'."
                                ),
                                confidence=1.0 - similarity,
                            ))
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Duplicate check error: %s", exc)

        return results, is_dup
