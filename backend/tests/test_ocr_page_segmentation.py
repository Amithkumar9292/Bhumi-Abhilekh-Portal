"""Tesseract engine configuration.

The default page-segmentation mode is load-bearing, not a tuning detail.
PSM 6 tells Tesseract the whole page is one uniform block of text. Land records
are labelled forms wrapped around a map sketch, often with a second column of
metadata, so PSM 6 merges the columns and drops the label column: on a real
survey scan it read 0 of 13 expected fields and returned 0.55 average
confidence, against 13 of 13 and 0.88 under automatic layout analysis (PSM 3).
"""
from __future__ import annotations

import os

import pytest

from app.services.ocr_service import _DEFAULT_PSM, _page_segmentation_mode


def test_default_is_automatic_page_segmentation():
    """Automatic layout analysis (PSM 3) must be the default, not PSM 6."""
    assert _DEFAULT_PSM == 3
    assert _page_segmentation_mode() == 3


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("6", 6),
        ("4", 4),
        (" 11 ", 11),
        ("13", 13),
    ],
)
def test_valid_psm_override_is_honoured(monkeypatch, raw, expected):
    monkeypatch.setenv("TESSERACT_PSM", raw)
    assert _page_segmentation_mode() == expected


@pytest.mark.parametrize("raw", ["", "   ", "auto", "three", "14", "-1", "3.5"])
def test_unusable_psm_override_falls_back_to_the_default(monkeypatch, raw):
    """A bad override must not be passed through to the Tesseract CLI."""
    monkeypatch.setenv("TESSERACT_PSM", raw)
    assert _page_segmentation_mode() == _DEFAULT_PSM


def test_psm_override_is_absent_by_default(monkeypatch):
    monkeypatch.delenv("TESSERACT_PSM", raising=False)
    assert _page_segmentation_mode() == _DEFAULT_PSM
    assert os.environ.get("TESSERACT_PSM") is None
