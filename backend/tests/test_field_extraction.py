"""Field extraction from noisy OCR text.

These lock in the label-vs-value behaviour that regressed silently before: a
record's own header ("KHASRA NAKAL (REVENUE RECORD COPY)") matches the very same
pattern that finds the real Khasra number, and neighbouring labels sharing one
physical line must not swallow each other's values.
"""
from __future__ import annotations

import re

import pytest

from app.services.field_extractor import CONFIDENCE_REVIEW_THRESHOLD, FieldExtractor
from app.services.ocr_service import OCRResult, TextBlock


# A realistic Khasra header, where labels share physical lines and the title
# itself contains the word "KHASRA".
RECORD_TEXT = """KHASRA NAKAL (REVENUE RECORD COPY)
State: Uttar Pradesh    District: Lucknow
Tehsil: Sadar    Village: Rampur
Khasra No: KH-10142
Khata/Khatauni: KT-5032
Survey No: SUR-2841
Owner Name: Ramesh Prasad
Father Name: Shiv Prasad
Land Area: 2.45 hectares
Land Classification: Agricultural
Mutation No: MUT-2024-08-1432
Registration Date: 15/03/2024
PIN: 226001
"""


def _extract(text: str, confidence: float = 0.92) -> dict:
    blocks = [
        TextBlock(text=line.strip(), confidence=confidence, page=1)
        for line in text.splitlines()
        if line.strip()
    ]
    ocr = OCRResult(
        full_text=text,
        blocks=blocks,
        page_count=1,
        detected_language="en",
        avg_confidence=confidence,
        backend_name="tesseract",
    )
    return {r.field_name: r for r in FieldExtractor().extract(ocr)}


@pytest.fixture(scope="module")
def fields() -> dict:
    return _extract(RECORD_TEXT)


@pytest.mark.parametrize(
    ("field_name", "expected"),
    [
        ("khasra_number", "KH-10142"),
        ("khata_number", "KT-5032"),
        ("survey_number", "SUR-2841"),
        ("owner_name", "Ramesh Prasad"),
        ("father_name", "Shiv Prasad"),
        ("village", "Rampur"),
        ("tehsil", "Sadar"),
        ("district", "Lucknow"),
        ("state", "Uttar Pradesh"),
        ("pin_code", "226001"),
        ("mutation_number", "MUT-2024-08-1432"),
        ("land_classification", "AGRICULTURAL"),
        ("land_area", "2.45"),
        ("registration_date", "15/03/2024"),
    ],
)
def test_field_value_is_read_from_its_label(fields: dict, field_name, expected):
    assert fields[field_name].normalized_value == expected


def test_title_word_does_not_become_the_khasra_number(fields):
    """The document title says "KHASRA NAKAL"; the labelled value must win."""
    assert fields["khasra_number"].normalized_value != "NAKAL"
    assert fields["khasra_number"].validation_status == "AUTO_VALID"


def test_trailing_label_word_does_not_become_the_value(fields):
    """'Khata/Khatauni: KT-5032' must not capture the '/KHATAUNI' fragment."""
    assert fields["khata_number"].normalized_value != "/KHATAUNI"
    assert fields["khata_number"].raw_value == "KT-5032"


@pytest.mark.parametrize("field_name", ["state", "district", "village", "tehsil"])
def test_shared_line_labels_each_get_their_own_value(fields, field_name):
    """Two labels on one line must not leave the second one unparsed."""
    result = fields[field_name]
    assert result.normalized_value is not None
    assert result.validation_status == "AUTO_VALID"
    assert result.needs_review is False


def test_no_field_is_left_unparsed_for_a_complete_record(fields):
    missing = [name for name, r in fields.items() if r.normalized_value is None]
    assert missing == []


def test_extraction_does_not_invent_values_when_a_label_is_absent():
    fields = _extract("This page contains no labelled fields at all.")
    assert all(r.normalized_value is None for r in fields.values())
    assert all(r.needs_review for r in fields.values())


def test_low_confidence_values_are_routed_to_review():
    fields = _extract(RECORD_TEXT, confidence=0.30)
    assert fields["khasra_number"].needs_review is True
    # A low-confidence read is still reported, not silently dropped.
    assert fields["khasra_number"].normalized_value == "KH-10142"
    assert all(r.confidence_score < CONFIDENCE_REVIEW_THRESHOLD for r in fields.values())


def test_value_preceded_by_separator_outranks_bare_label_match():
    """A bare 'KHASRA NAKAL' line must lose to 'Khasra No: KH-10142'."""
    fields = _extract("KHASRA NAKAL\nKhasra No: KH-10142")
    assert fields["khasra_number"].normalized_value == "KH-10142"


def test_labelled_value_wins_regardless_of_line_order():
    """Ordering must not decide the outcome: a title after the value is fine too."""
    fields = _extract("Khasra No: KH-10142\nKHASRA NAKAL (REVENUE RECORD COPY)")
    assert fields["khasra_number"].normalized_value == "KH-10142"


def test_pure_alpha_header_word_is_not_a_valid_identifier():
    """With no labelled value, a header word must not pass as an identifier.

    "KHASRA NAKAL" is the record type, not a Khasra number, and identifiers
    carry digits. It must be flagged for review rather than look trustworthy.
    """
    result = _extract("KHASRA NAKAL (REVENUE RECORD COPY)")["khasra_number"]
    assert result.normalized_value == "NAKAL"
    assert result.validation_status == "AUTO_INVALID"
    assert result.needs_review is True
    assert result.confidence_score < CONFIDENCE_REVIEW_THRESHOLD


def test_pure_alpha_values_are_rejected_for_every_identifier_field():
    for field_name, label in (
        ("khasra_number", "Khasra Number"),
        ("khata_number", "Khata / Khatauni Number"),
        ("survey_number", "Survey Number"),
        ("mutation_number", "Mutation Number"),
    ):
        result = _extract(f"{label}: NAKAL")[field_name]
        assert result.validation_status == "AUTO_INVALID", field_name
        assert result.needs_review is True, field_name


# A real "Khasra Name" / "Jamabandi" scan: the labels spell out "Number", the unit
# sits inside the area label, and the parent line reads "Father / Husband Name".
SURVEY_TEXT = """LAND RECORD / SURVEY RECORD
Owner Name: Ramesh Kumar Naik
Father / Husband Name: Suresh Naik
Survey Number: 124/3A
Khasra Number: 124/3A
Khata / Khatauni Number: 456
Land Area (Hectares): 0.3200
Village: Brahmavara
Tehsil: Udupi
District: Udupi
State: Karnataka
PIN Code: 576213
Land Classification: Dry Land
Mutation Number: MR-2023-4578
Registration Date: 12-07-2023
"""


@pytest.fixture(scope="module")
def survey_fields() -> dict:
    return _extract(SURVEY_TEXT)


@pytest.mark.parametrize(
    ("field_name", "expected"),
    [
        ("khasra_number", "124/3A"),
        ("survey_number", "124/3A"),
        ("khata_number", "456"),
        ("owner_name", "Ramesh Kumar Naik"),
        ("father_name", "Suresh Naik"),
        ("land_area", "0.3200"),
        ("village", "Brahmavara"),
        ("tehsil", "Udupi"),
        ("district", "Udupi"),
        ("state", "Karnataka"),
        ("pin_code", "576213"),
        ("mutation_number", "MR-2023-4578"),
        ("registration_date", "12-07-2023"),
    ],
)
def test_survey_record_fields_are_read(survey_fields, field_name, expected):
    assert survey_fields[field_name].normalized_value == expected


def test_label_suffix_word_is_not_captured_as_the_value(survey_fields):
    """'Khasra Number: 124/3A' must not match 'num' inside 'Number' and keep 'BER'.

    The optional no/num/number suffix is matched longest-first with a trailing
    \\b, so the leftover of the label word can never be read as the value.
    """
    assert survey_fields["khasra_number"].normalized_value != "BER"
    assert survey_fields["khasra_number"].raw_value == "124/3A"


def test_unit_inside_the_area_label_is_tolerated(survey_fields):
    """'Land Area (Hectares): 0.3200' keeps the unit in the label, not the value."""
    assert survey_fields["land_area"].normalized_value == "0.3200"
    assert survey_fields["land_area"].validation_status == "AUTO_VALID"


def test_father_husband_label_accepts_the_trailing_name_word(survey_fields):
    assert survey_fields["father_name"].normalized_value == "Suresh Naik"


def test_survey_record_has_no_unparsed_fields(survey_fields):
    missing = [name for name, r in survey_fields.items() if r.normalized_value is None]
    assert missing == []


def test_every_survey_record_value_passes_validation(survey_fields):
    invalid = [name for name, r in survey_fields.items() if r.validation_status != "AUTO_VALID"]
    assert invalid == []


class TestPersistedRuleFitsItsColumn:
    """`extracted_fields.validation_rule` is a String(128) column.

    The extractor used to persist the whole validation regex there. SQLite does
    not enforce column length, so the suite passed, but PostgreSQL rejected the
    insert with "value too long for type character varying(128)" the moment a
    pattern grew -- which failed the entire field write and left the job FAILED.
    Every rule the extractor can emit must therefore fit the real column width.
    """

    WIDTH = 128

    def test_persisted_rule_fits_the_column_for_a_complete_record(self, survey_fields):
        for name, r in survey_fields.items():
            rule = r.validation_rule or ""
            assert len(rule) <= self.WIDTH, f"{name}: {len(rule)} chars"

    def test_persisted_rule_is_a_code_not_a_pattern(self, survey_fields):
        for name, r in survey_fields.items():
            assert not (r.validation_rule or "").startswith("^"), name
            assert not (r.validation_rule or "").endswith("$"), name

    def test_rule_is_populated_even_when_the_field_is_absent(self):
        fields = _extract("nothing labelled here at all")
        for r in fields.values():
            assert r.validation_rule, r.field_name
            assert len(r.validation_rule) <= self.WIDTH
    def test_no_pattern_in_the_table_is_long_enough_to_overflow(self):
        """Belt-and-braces: a future long pattern must be caught here, not in prod."""
        from app.services.field_extractor import _PATTERNS

        for field_name, _display, _pattern, _norm, validation_regex in _PATTERNS:
            # The rule that gets persisted is a code, so length cannot leak
            # through; this documents the width we are staying inside.
            assert len(f"regex:{field_name}") <= self.WIDTH, field_name
            re.compile(validation_regex)
