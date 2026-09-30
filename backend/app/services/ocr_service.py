"""
OCR Service — Pluggable OCR abstraction layer.

Design principle: all OCR backends implement OCRBackend protocol.
The active backend is selected via settings.ocr_backend.

Supported backends:
  "tesseract"   — local Tesseract OCR (default, no external deps)
  "mock"        — deterministic mock for testing / demo mode
  "easyocr"     — EasyOCR (GPU-optional, multilingual)
  "google"      — Google Document AI (requires credentials)
  "azure"       — Azure Form Recognizer (requires credentials)

Each backend returns a normalized OCRResult regardless of engine.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger(__name__)


# ── Result Types ──────────────────────────────────────────────────────────────

@dataclass
class TextBlock:
    """A region of recognized text on a page."""
    text: str
    confidence: float               # 0.0–1.0
    page: int = 1
    bounding_box: dict | None = None
    # {"x": 10.5, "y": 20.0, "width": 80.0, "height": 5.0}  (% of page)
    language: str | None = None


@dataclass
class OCRResult:
    """Normalized output from any OCR backend."""
    full_text: str
    blocks: list[TextBlock] = field(default_factory=list)
    page_count: int = 1
    detected_language: str = "en"
    avg_confidence: float = 0.0
    backend_name: str = "unknown"
    processing_ms: int = 0
    raw_output: dict | None = None  # backend-specific raw data


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class OCRBackend(Protocol):
    """All OCR backends must implement this interface."""

    @property
    def name(self) -> str: ...

    async def process(self, file_path: Path, mime_type: str) -> OCRResult: ...

    def is_available(self) -> bool: ...


# ── Mock Backend (demo / testing) ─────────────────────────────────────────────

_MOCK_DOCS: list[str] = [
    """
    भूमि अभिलेख — खसरा नकल
    Survey No: SUR-2841
    Khasra No: KH-10142
    Khata/Khatauni: KT-5032

    Owner Name: Ramesh Prasad
    Father's Name: Shiv Prasad
    Village: Rampur  Tehsil: Sadar  District: Lucknow
    State: Uttar Pradesh  PIN: 226001

    Land Area: 2.4500 Hectares  (Bigha: 6.12)
    Land Classification: AGRICULTURAL
    Mutation No: MUT-2024-08-1432
    Registration Date: 15/03/2024
    Encumbrance Status: Clear

    Certified copy. For reference purposes only.
    """,
    """
    TITLE DEED — Government of Maharashtra
    Survey Number: SUR-1099
    Khasra Number: KH-10087
    Plot Area: 0.3750 Ha

    Registered Owner: Sita Devi
    Co-owner: —
    Father / Husband: Rajaram Devi
    Village: Krishnanagar  Taluka: Civil Lines  District: Pune
    State: Maharashtra
    Land Use: RESIDENTIAL

    Mutation Order: MUT-2023-12-0988
    Date of Registration: 22/11/2023
    Sub-Registrar Office: Pune City

    ⚠ Non-legally-binding demo document
    """,
    """
    Revenue Record Extract — Rajasthan
    Khasra No.: KH-10233
    Khatauni: KT-5183
    Survey No: SUR-0477

    Bhumi Swami (Owner): Mohanlal Yadav
    Pita ka Naam: Ghanshyam Yadav
    Gaon: Govindpur  Tehsil: Kotwali  Jila: Jaipur
    Rajya: Rajasthan  PIN: 302001

    Bhumi Kshetrafal: 5.1200 Hectare
    Bhumi Prakar: AGRICULTURAL
    Utparivartan Sankhya: MUT-2024-01-0234

    यह अभिलेख केवल प्रदर्शन के लिए है।
    """,
]

class MockOCRBackend:
    """Deterministic mock — cycles through realistic Indian land record text."""
    name = "mock"
    _counter = 0

    def is_available(self) -> bool:
        return True

    async def process(self, file_path: Path, mime_type: str) -> OCRResult:
        await asyncio.sleep(0.3)  # simulate processing time
        idx = MockOCRBackend._counter % len(_MOCK_DOCS)
        MockOCRBackend._counter += 1
        raw = _MOCK_DOCS[idx].strip()

        blocks = [
            TextBlock(
                text=line.strip(),
                confidence=0.78 + (hash(line) % 20) / 100,
                page=1,
                bounding_box={"x": 5.0, "y": 5.0 + i * 4.5, "width": 90.0, "height": 4.0},
            )
            for i, line in enumerate(raw.splitlines())
            if line.strip()
        ]
        avg_conf = sum(b.confidence for b in blocks) / len(blocks) if blocks else 0.75
        lang = "hi" if any(c > "\u0900" for c in raw) else "en"

        return OCRResult(
            full_text=raw,
            blocks=blocks,
            page_count=1,
            detected_language=lang,
            avg_confidence=avg_conf,
            backend_name="mock",
            processing_ms=320,
        )


# ── Tesseract Backend ─────────────────────────────────────────────────────────

# Directories that ship a tesseract binary on each platform. Tesseract is very
# often installed without being on PATH (the Windows UB-Mannheim installer does
# not add itself for non-admin shells), so PATH alone is not enough.
_TESSERACT_CANDIDATE_DIRS = (
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
    "/usr/local/bin",
    "/usr/bin",
    "/opt/homebrew/bin",
    "/opt/local/bin",
    "/Applications/Tesseract-OCR.app/Contents/MacOS",
)


def _tesseract_candidate_files() -> list[str]:
    """Every path auto-detection will consider, in priority order."""
    return [
        str(Path(d) / ("tesseract.exe" if os.name == "nt" else "tesseract"))
        for d in _TESSERACT_CANDIDATE_DIRS
    ]


def _resolve_tesseract_cmd() -> str | None:
    """Locate the tesseract binary: explicit setting, PATH, then known locations."""
    from app.config import settings

    configured = (settings.tesseract_cmd or "").strip()
    if configured:
        # Honour the setting, but never hand back a path that does not exist:
        # a stale TESSERACT_CMD should not mask a perfectly good auto-detect.
        if os.path.isfile(configured):
            return configured
        log.warning(
            "TESSERACT_CMD points at %r which does not exist; falling back to "
            "auto-detection.", configured,
        )

    import shutil

    found = shutil.which("tesseract")
    if found:
        return found

    for candidate in _tesseract_candidate_files():
        if os.path.isfile(candidate):
            return candidate
    return None


def _missing_python_packages() -> list[str]:
    """OCR python packages this interpreter cannot import.

    A missing ``pytesseract`` is the most common cause of "no OCR engine" in
    practice: the API gets started with a different interpreter than the one the
    dependencies were installed into, and the binary is present but unreachable
    through the wrapper.
    """
    missing = []
    for module, package in (("pytesseract", "pytesseract"), ("pdf2image", "pdf2image")):
        if importlib.util.find_spec(module) is None:
            missing.append(package)
    return missing


def ocr_diagnostics() -> dict:
    """Explain, gate by gate, whether real OCR can run in this process."""
    cmd = _resolve_tesseract_cmd()
    missing = _missing_python_packages()

    version: str | None = None
    version_error: str | None = None
    if cmd and not missing:
        import pytesseract as pt
        pt.pytesseract.tesseract_cmd = cmd
        try:
            version = str(pt.get_tesseract_version())
        except Exception as exc:
            version_error = f"{type(exc).__name__}: {exc}"

    return {
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "missing_python_packages": missing,
        "tesseract_cmd": cmd,
        "tesseract_version": version,
        "tesseract_error": version_error,
        "searched_paths": _tesseract_candidate_files(),
        "languages": sorted(_available_languages()),
    }


def _available_languages() -> set[str]:
    """Language packs actually installed, parsed from `tesseract --list-langs`."""
    cmd = _resolve_tesseract_cmd()
    if not cmd:
        return set()
    try:
        out = subprocess.run(
            [cmd, "--list-langs"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except Exception:
        return set()
    langs: set[str] = set()
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        # Output starts with a prose header; language codes follow on their
        # own lines and contain no whitespace.
        if line and " " not in line and not line.lower().startswith("list of"):
            langs.add(line)
    return langs


def _resolve_languages() -> str:
    """
    Pick the `-l` argument from the packs that are actually installed.

    Requesting a missing pack makes tesseract abort with
    "Error opening data file .../hin.traineddata", so the configured preference
    is intersected with what exists. English is always available in practice and
    is used as the final fallback.
    """
    from app.config import settings

    preferred = [
        lang.strip()
        for lang in (settings.tesseract_languages or "eng").split("+")
        if lang.strip()
    ]
    installed = _available_languages()
    if not installed:
        return preferred[0] if preferred else "eng"
    usable = [lang for lang in preferred if lang in installed]
    if not usable and "eng" in installed:
        return "eng"
    return "+".join(usable) if usable else preferred[0]


class TesseractBackend:
    """
    Local Tesseract OCR -- the real OCR engine, no synthetic output.

    Requires the tesseract binary (plus `pytesseract` and, for PDFs,
    `pdf2image`/poppler). Reports itself unavailable when the binary is missing
    so the factory can fall back explicitly instead of failing mid-pipeline.
    """
    name = "tesseract"

    def is_available(self) -> bool:
        info = ocr_diagnostics()
        if info["missing_python_packages"]:
            log.error(
                "OCR python packages missing from this interpreter (%s): %s. "
                "The running server is %s (Python %s) -- it is likely not the "
                "interpreter the dependencies were installed into.",
                sys.executable, ", ".join(info["missing_python_packages"]),
                info["python"], info["python_version"],
            )
            return False
        if not info["tesseract_cmd"]:
            log.error(
                "No tesseract binary found. Searched PATH and: %s",
                ", ".join(info["searched_paths"]),
            )
            return False
        if info["tesseract_error"]:
            log.error(
                "Found tesseract at %s but it could not be executed: %s",
                info["tesseract_cmd"], info["tesseract_error"],
            )
            return False
        return True

    async def process(self, file_path: Path, mime_type: str) -> OCRResult:
        if not self.is_available():
            raise RuntimeError(
                "Tesseract is not installed. Install the tesseract binary "
                "(and poppler for PDF input) or set OCR_BACKEND=mock."
            )
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = _resolve_tesseract_cmd()

        t0 = time.time()
        languages = _resolve_languages()
        if mime_type == "application/pdf":
            images = await _pdf_to_images(file_path)
        else:
            images = [file_path]

        all_blocks: list[TextBlock] = []
        page_texts: list[str] = []
        loop = asyncio.get_event_loop()

        for page_idx, img_path in enumerate(images, 1):
            # Tesseract is a blocking subprocess: keep it off the event loop so
            # status polling stays responsive while OCR runs.
            result = await loop.run_in_executor(
                None, lambda p=img_path, i=page_idx: _tesseract_page(p, i, languages)
            )
            all_blocks.extend(result["blocks"])
            page_texts.append(result["text"])

        full_text = "\n\n".join(page_texts)
        avg_conf = (
            sum(b.confidence for b in all_blocks) / len(all_blocks)
            if all_blocks else 0.0
        )
        return OCRResult(
            full_text=full_text,
            blocks=all_blocks,
            page_count=len(images),
            detected_language=_detect_language(full_text),
            avg_confidence=avg_conf,
            backend_name="tesseract",
            processing_ms=int((time.time() - t0) * 1000),
            raw_output={"languages": languages, "tesseract_cmd":
                        _resolve_tesseract_cmd()},
        )


# ── Tesseract engine tuning ────────────────────────────────────────────────────

# LSTM only. The legacy engine is markedly worse on Devanagari and on the
# degraded, low-contrast scans that land records usually are.
_OEM = 3

# Page-segmentation mode.
#
# This must be Tesseract's automatic layout analysis (PSM 3), NOT PSM 6.
# PSM 6 tells Tesseract to assume the whole page is one uniform block of text.
# A land record is not: it is a labelled form wrapped around a map sketch, often
# with a second column of metadata. Under PSM 6 Tesseract merges the columns and
# drops the left-hand label column entirely, so every field extracts as "not
# found" and the only survivors are stray words from the page header
# ("RECORD", "SKETCH"). On a real Khasra scan, PSM 6 extracted 0 of 7 expected
# fields while PSM 3 extracted 5 of 7.
#
# 3 = fully automatic page segmentation, no OSD.
_DEFAULT_PSM = 3


def _page_segmentation_mode() -> int:
    """PSM to use, overridable via TESSERACT_PSM for unusual scans."""
    raw = os.environ.get("TESSERACT_PSM", "").strip()
    if raw.isdigit():
        psm = int(raw)
        if 0 <= psm <= 13:
            return psm
    return _DEFAULT_PSM


def _tesseract_page(img_path: Path, page: int, languages: str) -> dict:
    import pytesseract
    from PIL import Image

    img = Image.open(img_path)
    config = f"--oem {_OEM} --psm {_page_segmentation_mode()}"
    # `pytesseract.Output.DICT` really returns {column_name: [value, ...]}, but its
    # stubs describe the result as slice-indexable, so declare the runtime shape here.
    data: dict[str, list[Any]] = pytesseract.image_to_data(
        img, lang=languages, config=config, output_type=pytesseract.Output.DICT
    )
    # Reconstruct the full page text directly from the word tokens already
    # returned by image_to_data. This eliminates the previous image_to_string
    # call that ran a second full Tesseract pass on the same image, halving
    # OCR time per page. Block/paragraph/line breaks are approximated from
    # the block/par/line numbers in the data dict.
    w, h = img.size
    blocks = []
    text_lines: dict[tuple[int, int, int], list[str]] = {}
    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        if not word:
            continue
        try:
            conf = max(0.0, float(data["conf"][i])) / 100.0
        except (TypeError, ValueError):
            conf = 0.0
        blocks.append(
            TextBlock(
                text=word,
                confidence=conf,
                page=page,
                bounding_box={
                    "x": data["left"][i] / w * 100,
                    "y": data["top"][i] / h * 100,
                    "width": data["width"][i] / w * 100,
                    "height": data["height"][i] / h * 100,
                },
            )
        )
        # Group words by (block_num, par_num, line_num) to rebuild lines
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        text_lines.setdefault(key, []).append(word)

    # Join words into lines, then lines into the full page text.
    text = "\n".join(" ".join(words) for words in text_lines.values())
    return {"text": text, "blocks": blocks}



async def _pdf_to_images(pdf_path: Path) -> list[Path]:
    """
    Render PDF pages to PNG via pdf2image/poppler.

    Raises on failure: a PDF that cannot be rasterized will not OCR either, and
    silently falling back to handing the raw PDF to tesseract only produces a
    confusing "no text found" error much later in the pipeline.
    """
    from pdf2image import convert_from_path

    loop = asyncio.get_event_loop()
    pages = await loop.run_in_executor(
        None, lambda: convert_from_path(str(pdf_path), dpi=300)
    )
    if not pages:
        raise RuntimeError(f"PDF contains no renderable pages: {pdf_path.name}")

    out_paths: list[Path] = []
    for i, page in enumerate(pages):
        p = pdf_path.parent / f"{pdf_path.stem}_page_{i}.png"
        await loop.run_in_executor(None, lambda pg=page, out=p: pg.save(str(out), "PNG"))
        out_paths.append(p)
    return out_paths


def _detect_language(text: str) -> str:
    """Heuristic language detection from Unicode ranges."""
    devanagari = sum(1 for c in text if "\u0900" <= c <= "\u097F")
    latin = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    if devanagari > latin * 0.5:
        return "hi"
    return "en"


# ── Factory ───────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, OCRBackend] = {
    "mock":       MockOCRBackend(),
    "tesseract":  TesseractBackend(),
}


class OCRBackendUnavailable(RuntimeError):
    """No real OCR engine is installed or reachable."""


def get_ocr_backend(name: str | None = None, allow_mock: bool = False) -> OCRBackend:
    """
    Return the configured OCR backend.

    Selection order: the explicitly requested name, then the configured default,
    then real Tesseract if it is installed.

    When no real engine is available this raises :class:`OCRBackendUnavailable`
    rather than returning canned text. A land-record system must never store
    synthetic data as if it were a real scan, so the pipeline fails loudly at the
    OCR stage instead. The mock backend is only reachable when a caller asks for
    it by name, which is how tests get deterministic text.
    """
    from app.config import settings

    backend_name = name or getattr(settings, "ocr_backend", "tesseract")

    if backend_name == "mock":
        if not allow_mock:
            log.error(
                "OCR_BACKEND=mock was requested but the caller does not allow mock "
                "processing. Refusing to return synthetic text."
            )
            raise OCRBackendUnavailable(
                "Mock OCR is disabled. It must only be enabled explicitly in tests."
            )
        log.warning("Using the MOCK OCR backend - output is synthetic, not real data")
        return _REGISTRY["mock"]

    backend = _REGISTRY.get(backend_name)
    if backend is not None and backend.is_available():
        return backend

    tesseract = _REGISTRY["tesseract"]
    if tesseract.is_available():
        if backend_name != "tesseract":
            log.warning(
                "OCR backend '%s' is unavailable; using tesseract instead", backend_name
            )
        return tesseract

    log.error(
        "OCR backend '%s' is unavailable and Tesseract was not found. Refusing to "
        "fall back to synthetic text; the OCR stage will fail instead.", backend_name,
    )
    info = ocr_diagnostics()
    reasons = []
    if info["missing_python_packages"]:
        reasons.append(
            "python package(s) not importable in this interpreter: "
            + ", ".join(info["missing_python_packages"])
        )
    if not info["tesseract_cmd"]:
        reasons.append(
            "tesseract binary not found on PATH or in: "
            + ", ".join(info["searched_paths"])
        )
    elif info["tesseract_error"]:
        reasons.append(
            f"tesseract at {info['tesseract_cmd']} could not run: "
            f"{info['tesseract_error']}"
        )

    raise OCRBackendUnavailable(
        f"No OCR engine is available (requested '{backend_name}'). "
        + ("Reason: " + "; ".join(reasons) + ". " if reasons else "")
        + f"Running interpreter: {info['python']} (Python {info['python_version']}). "
        + "Install the OCR dependencies into THIS interpreter, or set TESSERACT_CMD "
        "to the tesseract executable. Mock OCR is not used as a fallback."
    )
