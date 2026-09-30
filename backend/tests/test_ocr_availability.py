"""OCR availability diagnostics.

The failure these lock down is a real one: the API was started with a global
interpreter that had FastAPI but not `pytesseract`, while the binary sat
installed on the machine. The old code reported that as "Tesseract not found",
which sent debugging in the wrong direction.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from app.services import ocr_service
from app.services.ocr_service import (
    OCRBackendUnavailable,
    TesseractBackend,
    _resolve_tesseract_cmd,
    ocr_diagnostics,
)


def test_diagnostics_report_the_running_interpreter():
    info = ocr_diagnostics()
    assert info["python"] == sys.executable
    assert info["python_version"] == sys.version.split()[0]


def test_diagnostics_never_execute_the_binary_when_a_package_is_missing():
    """Avoids a pointless subprocess call on a broken environment."""
    with patch.object(ocr_service, "_missing_python_packages",
                      return_value=["pytesseract"]):
        with patch.object(ocr_service, "_resolve_tesseract_cmd",
                          return_value=r"C:\fake\tesseract.exe"):
            with patch("pytesseract.get_tesseract_version") as version:
                info = ocr_diagnostics()
    assert info["missing_python_packages"] == ["pytesseract"]
    assert info["tesseract_version"] is None
    version.assert_not_called()


def test_missing_package_is_reported_as_unavailable():
    with patch.object(ocr_service, "_missing_python_packages",
                      return_value=["pytesseract"]):
        assert TesseractBackend().is_available() is False


def test_missing_binary_is_reported_as_unavailable():
    with patch.object(ocr_service, "_missing_python_packages", return_value=[]):
        with patch.object(ocr_service, "_resolve_tesseract_cmd", return_value=None):
            assert TesseractBackend().is_available() is False


def test_unrunnable_binary_is_reported_as_unavailable():
    """Found on disk but failing to execute is not 'available'."""
    with patch.object(ocr_service, "_missing_python_packages", return_value=[]):
        with patch.object(ocr_service, "_resolve_tesseract_cmd",
                          return_value=r"C:\fake\tesseract.exe"):
            with patch("pytesseract.get_tesseract_version",
                       side_effect=OSError("not a valid Win32 application")):
                assert TesseractBackend().is_available() is False


def test_healthy_environment_is_available():
    info = ocr_diagnostics()
    if info["missing_python_packages"] or not info["tesseract_cmd"]:
        pytest.skip("tesseract stack not installed in this interpreter")
    assert TesseractBackend().is_available() is True


def test_stale_tesseract_cmd_falls_back_to_auto_detection():
    """A TESSERACT_CMD left over from another machine must not mask a good install."""
    from app.config import settings

    with patch.object(settings, "tesseract_cmd", r"C:\does\not\exist\tesseract.exe"):
        resolved = _resolve_tesseract_cmd()
    if ocr_diagnostics()["tesseract_cmd"] is None:
        pytest.skip("no tesseract install to fall back to")
    assert resolved is not None
    assert resolved != r"C:\does\not\exist\tesseract.exe"
    assert os.path.isfile(resolved)


def test_existing_tesseract_cmd_is_honoured():
    from app.config import settings

    fake = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if not os.path.isfile(fake):
        pytest.skip("standard windows install not present")
    with patch.object(settings, "tesseract_cmd", fake):
        assert _resolve_tesseract_cmd() == fake


def test_error_message_names_the_actual_cause():
    """The message must not blame a missing install when a package is missing."""
    with patch.object(TesseractBackend, "is_available", return_value=False):
        with patch.object(ocr_service, "_missing_python_packages",
                          return_value=["pytesseract"]):
            with patch.object(ocr_service, "_resolve_tesseract_cmd",
                              return_value=r"C:\fake\tesseract.exe"):
                with pytest.raises(OCRBackendUnavailable) as excinfo:
                    ocr_service.get_ocr_backend("tesseract")

    message = str(excinfo.value)
    assert "pytesseract" in message
    assert sys.executable in message
    # It must not claim the binary is absent when it was found.
    assert "binary not found" not in message


def test_error_message_lists_searched_paths_when_binary_is_absent():
    with patch.object(TesseractBackend, "is_available", return_value=False):
        with patch.object(ocr_service, "_missing_python_packages", return_value=[]):
            with patch.object(ocr_service, "_resolve_tesseract_cmd", return_value=None):
                with pytest.raises(OCRBackendUnavailable) as excinfo:
                    ocr_service.get_ocr_backend("tesseract")

    message = str(excinfo.value)
    assert "binary not found" in message
    assert "Program Files" in message


def test_error_message_never_suggests_mock_fallback():
    with patch.object(TesseractBackend, "is_available", return_value=False):
        with patch.object(ocr_service, "_missing_python_packages",
                          return_value=["pytesseract"]):
            with patch.object(ocr_service, "_resolve_tesseract_cmd", return_value=None):
                with pytest.raises(OCRBackendUnavailable) as excinfo:
                    ocr_service.get_ocr_backend("tesseract")

    message = str(excinfo.value).lower()
    # The exception must not tell an operator to switch on mock OCR, which is
    # reserved for tests and would store synthetic text as a real scan.
    assert "ocr_backend=mock" not in message
    assert "mock ocr is not used as a fallback" in message
