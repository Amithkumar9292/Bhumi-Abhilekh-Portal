"""
Field Extractor — Extracts structured land record fields from raw OCR text.

Design: two-pass extraction
  Pass 1: Regex patterns with named groups (fast, deterministic)
  Pass 2: Positional context patterns (handles noisy OCR output)

Every field gets:
  - raw_value (exactly as found)
  - normalized_value (cleaned/standardized)
  - confidence_score (0.0–1.0)
  - source_page (from OCR block)
  - bounding_box (from OCR block if available)
  - validation_status (AUTO_VALID / AUTO_INVALID / NOT_VALIDATED)
  - needs_review (True if confidence < threshold)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional

from app.services.ocr_service import OCRResult, TextBlock


# ── Field definitions ─────────────────────────────────────────────────────────

@dataclass
class FieldResult:
    field_name: str
    field_display: str
    raw_value: Optional[str]
    normalized_value: Optional[str]
    confidence_score: float
    ocr_confidence: Optional[float]
    extraction_method: str          # "regex" | "context" | "heuristic"
    source_page: Optional[int]
    bounding_box: Optional[dict]
    validation_status: str          # "AUTO_VALID" | "AUTO_INVALID" | "NOT_VALIDATED"
    validation_rule: Optional[str]
    validation_message: Optional[str]
    needs_review: bool


CONFIDENCE_REVIEW_THRESHOLD = 0.60   # below this → human review required
CONFIDENCE_REJECT_THRESHOLD = 0.30   # below this → field marked invalid


# ── Regex patterns for Indian land records ────────────────────────────────────
# Each pattern is (field_name, display_name, regex, normalizer_fn)

def _clean(s: str) -> str:
    """Normalize whitespace and Unicode."""
    s = unicodedata.normalize("NFKC", s)
    return " ".join(s.split()).strip()

def _upper(s: str) -> str:
    return _clean(s).upper()

def _title(s: str) -> str:
    return _clean(s).title()

def _digits_only(s: str) -> str:
    return re.sub(r"[^\d.]", "", s)


# Characters that introduce a field's value, e.g. "Khasra No: KH-10142".
_VALUE_SEPARATORS = ":：—–-"

# Labels that can follow a free-text value on the same physical line, as in
# "State: Uttar Pradesh    District: Lucknow". Without this boundary the value
# pattern runs into the next label and the field is reported as not found.
_NEXT_LABEL = (
    r"(?:\s+(?:state|rajya|district|dist|jila|tehsil|taluka|taluk|village|"
    r"gaon|gram|pin|postal|khasra|khata|survey|owner|father|mother|husband|"
    r"land|area|plot|mutation|registration|classification|use|type)\b|\n|$)"
)


_PATTERNS: list[tuple[str, str, str, Callable[[str], str], str]] = [
    # (field_name, display, regex_pattern, normalizer, validation_regex)
    #
    # Identifier patterns require the value to *start* with an alphanumeric
    # character. Without that, "Khata/Khatauni: KT-5032" matches "Khata" and
    # captures "/KHATAUNI" -- the label's own trailing word instead of the value.
    (
        "khasra_number", "Khasra Number",
        r"(?:khasra\s*(?:(?:number|num|nkl|no)\b)?\.?\s*[:—\-]?\s*)([A-Z0-9][A-Z0-9\-/]*)",
        _upper, r"^(?=.*\d)[A-Z0-9\-/]{3,20}$",
    ),
    (
        "khata_number", "Khata / Khatauni Number",
        r"(?:khata(?:uni)?\s*(?:(?:number|num|no)\b)?\.?\s*[:—\-]?\s*)([A-Z0-9][A-Z0-9\-/]*)",
        _upper, r"^(?=.*\d)[A-Z0-9\-/]{2,20}$",
    ),
    (
        "survey_number", "Survey Number",
        r"(?:survey\s*(?:(?:number|num|no)\b)?\.?\s*[:—\-]?\s*)([A-Z0-9][A-Z0-9\-/]*)",
        _upper, r"^(?=.*\d)[A-Z0-9\-/]{3,20}$",
    ),
    (
        "owner_name", "Owner Name",
        r"(?:owner\s*name|bhumi\s*swami|registered\s*owner|owner)\s*[:—\-]\s*"
        r"([A-Za-z\s\u0900-\u097F]+?)" + _NEXT_LABEL,
        _title, r"^[\w\s\u0900-\u097F]{3,80}$",
    ),
    (
        "father_name", "Father / Husband Name",
        r"(?:father(?:'s)?\s*name|pita\s*ka\s*naam|father\s*/\s*husband(?:\s*name)?)\s*[:—\-]\s*"
        r"([A-Za-z\s\u0900-\u097F]+?)" + _NEXT_LABEL,
        _title, r"^[\w\s\u0900-\u097F]{3,80}$",
    ),
    (
        "land_area", "Land Area (Hectares)",
        r"(?:land\s*area|area|bhumi\s*kshetrafal|plot\s*area)\s*(?:\([^)]*\))?\s*[:—\-]\s*([\d,]+\.?\d*)\s*(?:hectare|ha|hect)?",
        _digits_only, r"^\d+\.?\d{0,4}$",
    ),
    (
        "village", "Village",
        r"(?:village|gaon|gram)\s*[:—\-]?\s*([A-Za-z\s\u0900-\u097F]+?)" + _NEXT_LABEL,
        _title, r"^[\w\s\u0900-\u097F]{2,50}$",
    ),
    (
        "tehsil", "Tehsil / Taluka",
        r"(?:tehsil|taluka|taluk)\s*[:—\-]?\s*([A-Za-z\s\u0900-\u097F]+?)" + _NEXT_LABEL,
        _title, r"^[\w\s\u0900-\u097F]{2,50}$",
    ),
    (
        "district", "District",
        r"(?:district|dist|jila)\s*[:—\-]?\s*([A-Za-z\s\u0900-\u097F]+?)" + _NEXT_LABEL,
        _title, r"^[\w\s\u0900-\u097F]{2,50}$",
    ),
    (
        "state", "State",
        r"(?:state|rajya)\s*[:—\-]?\s*([A-Za-z\s\u0900-\u097F]+?)" + _NEXT_LABEL,
        _title, r"^[\w\s\u0900-\u097F]{3,40}$",
    ),
    (
        "pin_code", "PIN Code",
        r"(?:pin\s*(?:code)?|postal)\s*[:—\-]?\s*(\d{6})",
        str, r"^\d{6}$",
    ),
    (
        "land_classification", "Land Classification",
        r"(?:land\s*(?:classification|use|type|prakar)|bhumi\s*prakar)\s*[:—\-]\s*(AGRICULTURAL|DRY\s*LAND|WET\s*LAND|FALLOW|ORCHARD|PLANTATION|GRASSLAND|PASTURE|RESIDENTIAL|COMMERCIAL|INDUSTRIAL|FOREST|WASTELAND|WASTE\s*LAND|MINING|QUARRY|BAMBOO|SUGARCANE|TOBACCO|TRUST|GRAM\s*PANCHAYAT|GOVERNMENT|GOVT)",
        _upper, r"^(AGRICULTURAL|DRY\s*LAND|WET\s*LAND|FALLOW|ORCHARD|PLANTATION|GRASSLAND|PASTURE|RESIDENTIAL|COMMERCIAL|INDUSTRIAL|FOREST|WASTELAND|WASTE\s*LAND|MINING|QUARRY|BAMBOO|SUGARCANE|TOBACCO|TRUST|GRAM\s*PANCHAYAT|GOVERNMENT|GOVT)$",
    ),
    (
        "mutation_number", "Mutation Number",
        r"(?:mutation\s*(?:(?:number|num|order|no)\b)?|utparivartan\s*sankhya)\s*[:—\-]\s*([A-Z0-9\-/]+)",
        _upper, r"^(?=.*\d)[A-Z0-9\-/]{5,30}$",
    ),
    (
        "registration_date", "Registration Date",
        r"(?:registration\s*date|date\s*of\s*registration)\s*[:—\-]\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        str, r"^\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}$",
    ),
]


# ── Block search helpers ──────────────────────────────────────────────────────

def _find_block_for_match(value: str, blocks: list[TextBlock]) -> Optional[TextBlock]:
    """Find the OCR block closest to the extracted value."""
    for blk in blocks:
        if value.lower()[:6] in blk.text.lower():
            return blk
    return None


def _pick_match(pattern: str, text: str) -> Optional[re.Match]:
    """Choose the best match for a field instead of simply the first one.

    A record's own header ("KHASRA NAKAL (REVENUE RECORD COPY)") matches the very
    same pattern that finds the field's real value ("Khasra No: KH-10142"), and
    `re.search` would take the header and report the title word as a Khasra
    number. A value introduced by a separator outranks one that merely trails the
    label word, and an earlier match outranks a later one.
    """
    best: Optional[re.Match] = None
    best_rank: Optional[tuple[bool, int]] = None

    for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
        preceding = text[max(0, match.start(1) - 4):match.start(1)].rstrip()
        separated = bool(preceding) and preceding[-1] in _VALUE_SEPARATORS
        rank = (separated, -match.start())
        if best_rank is None or rank > best_rank:
            best, best_rank = match, rank

    return best


# ── Core extractor ────────────────────────────────────────────────────────────

class FieldExtractor:
    """
    Extracts all defined fields from an OCRResult.
    Returns a list of FieldResult, one per defined field.
    """

    def __init__(self, confidence_review_threshold: float = CONFIDENCE_REVIEW_THRESHOLD):
        self.review_threshold = confidence_review_threshold

    def extract(self, ocr: OCRResult) -> list[FieldResult]:
        text = ocr.full_text
        results: list[FieldResult] = []

        for field_name, display, pattern, normalizer, validation in _PATTERNS:
            result = self._extract_field(
                field_name, display, pattern, normalizer,
                validation, text, ocr.blocks, ocr.avg_confidence,
            )
            results.append(result)

        return results

    def _extract_field(
        self,
        field_name: str,
        display: str,
        pattern: str,
        normalizer: Callable[[str], str],
        validation_regex: str,
        text: str,
        blocks: list[TextBlock],
        base_confidence: float,
    ) -> FieldResult:

        # Attempt regex match (case-insensitive)
        match = _pick_match(pattern, text)

        if not match:
            # No match → low confidence, needs review
            return FieldResult(
                field_name=field_name,
                field_display=display,
                raw_value=None,
                normalized_value=None,
                confidence_score=0.0,
                ocr_confidence=None,
                extraction_method="regex",
                source_page=None,
                bounding_box=None,
                validation_status="AUTO_INVALID",
                validation_rule="required_field",
                validation_message=f"Field '{display}' not found in document",
                needs_review=True,
            )

        raw = match.group(1).strip()
        try:
            normalized = normalizer(raw)
        except Exception:
            normalized = raw.strip()

        # Confidence: base OCR confidence * pattern match quality
        ocr_conf = base_confidence
        match_confidence = min(1.0, 0.60 + len(raw) * 0.02)  # longer match = higher conf
        conf = round(ocr_conf * match_confidence, 3)

        # Find OCR block for source location
        blk = _find_block_for_match(raw, blocks)
        source_page = blk.page if blk else None
        bounding_box = blk.bounding_box if blk else None
        ocr_confidence = blk.confidence if blk else None

        # Validate extracted value
        valid = bool(re.match(validation_regex, normalized or ""))
        if valid:
            val_status = "AUTO_VALID"
            val_msg = None
        else:
            val_status = "AUTO_INVALID"
            val_msg = f"Value '{normalized}' failed validation rule"
            conf = max(0.0, conf - 0.2)  # penalize confidence

        needs_review = (conf < self.review_threshold) or (val_status == "AUTO_INVALID")

        return FieldResult(
            field_name=field_name,
            field_display=display,
            raw_value=raw,
            normalized_value=normalized,
            confidence_score=conf,
            ocr_confidence=ocr_confidence,
            extraction_method="regex",
            source_page=source_page,
            bounding_box=bounding_box,
            validation_status=val_status,
            # The persisted rule column is String(128) and is meant to name the
            # rule, like the "required_field" code above -- not to carry the
            # pattern. Storing the regex overflowed the column as soon as a
            # pattern grew past 128 characters (the land-classification
            # vocabulary), and PostgreSQL then failed the whole field write,
            # failing the job. Keep it a short code.
            validation_rule=f"regex:{field_name}",
            validation_message=val_msg,
            needs_review=needs_review,
        )
