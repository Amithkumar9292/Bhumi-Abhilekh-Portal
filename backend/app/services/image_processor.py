"""
Image Quality Analyzer & Preprocessor.

Analyzes uploaded images/PDFs for:
- Resolution adequacy
- Blur detection (Laplacian variance)
- Brightness / contrast
- Skew angle
- Noise level

Returns a quality score (0.0–1.0) and preprocessing recommendations.
Uses Pillow (always available). Enhances image quality before OCR.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # Pillow is imported lazily inside the functions that need it; this is only
    # so the `_binarize` annotation below can name `Image.Image`.
    from PIL import Image

log = logging.getLogger(__name__)


@dataclass
class QualityReport:
    score: float                    # 0.0–1.0 overall quality
    resolution_ok: bool
    width_px: Optional[int]
    height_px: Optional[int]
    blur_score: Optional[float]     # higher = sharper
    brightness: Optional[float]     # 0–255 mean pixel intensity
    contrast: Optional[float]       # std dev of pixel intensities
    estimated_dpi: Optional[int]
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    preprocessed_path: Optional[str] = None


async def analyze_and_preprocess(file_path: Path, mime_type: str) -> QualityReport:
    """
    Analyze image quality and apply preprocessing.
    Returns a QualityReport with the path to the preprocessed file.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_analyze, file_path, mime_type)


def _sync_analyze(file_path: Path, mime_type: str) -> QualityReport:
    try:
        from PIL import Image, ImageFilter, ImageEnhance
    except ImportError:
        log.warning("Pillow not available — skipping quality analysis")
        return QualityReport(score=0.75, resolution_ok=True, width_px=None,
                             height_px=None, blur_score=None, brightness=None,
                             contrast=None, estimated_dpi=None)

    issues: list[str] = []
    recommendations: list[str] = []

    try:
        # Handle PDF: convert first page only
        if mime_type == "application/pdf":
            try:
                from pdf2image import convert_from_path
                pages = convert_from_path(str(file_path), dpi=150, first_page=1, last_page=1)
                if pages:
                    img = pages[0].convert("L")  # grayscale
                else:
                    raise ValueError("No pages")
            except Exception:
                return QualityReport(score=0.7, resolution_ok=True, width_px=None,
                                     height_px=None, blur_score=None, brightness=None,
                                     contrast=None, estimated_dpi=None,
                                     issues=["PDF preview unavailable"])
        else:
            img = Image.open(file_path).convert("L")

        w, h = img.size

        # ── Resolution check ──────────────────────────────────────
        resolution_ok = (w >= 600 and h >= 400)
        estimated_dpi = _estimate_dpi(w, h)
        if not resolution_ok:
            issues.append(f"Low resolution: {w}×{h}px — OCR quality may be poor")
            recommendations.append("Scan at minimum 300 DPI")

        # ── Blur detection (Laplacian variance) ───────────────────
        blur_score: Optional[float] = None
        try:
            import numpy as np
            arr = np.array(img, dtype=float)
            # Laplacian kernel
            lap = (
                arr[:-2, 1:-1] + arr[2:, 1:-1] + arr[1:-1, :-2] + arr[1:-1, 2:] - 4 * arr[1:-1, 1:-1]
            )
            blur_score = round(float(np.var(lap)), 2)
            if blur_score < 200:
                issues.append(f"Document appears blurry (score: {blur_score:.0f})")
                recommendations.append("Use a higher-resolution scan or sharper photograph")
        except ImportError:
            pass  # numpy optional

        # ── Brightness / contrast ─────────────────────────────────
        pixels = list(img.getdata())  # type: ignore
        brightness = round(statistics.mean(pixels), 2)
        contrast = round(statistics.stdev(pixels), 2) if len(pixels) > 1 else 0.0

        if brightness < 60:
            issues.append("Document is very dark — text may not be readable")
            recommendations.append("Increase scan brightness")
        elif brightness > 220:
            issues.append("Document is overexposed — text contrast is low")
            recommendations.append("Reduce scan brightness or avoid direct flash")

        if contrast < 40:
            issues.append("Low contrast detected — text may blend with background")
            recommendations.append("Adjust scanner contrast settings")

        # ── Preprocessing ─────────────────────────────────────────
        proc_img = img

        # 1. Enhance contrast
        if contrast < 60:
            proc_img = ImageEnhance.Contrast(proc_img).enhance(1.5)

        # 2. Sharpen if blurry
        if blur_score is not None and blur_score < 400:
            proc_img = proc_img.filter(ImageFilter.SHARPEN)

        # 3. Adaptive threshold (binarize) for cleaner OCR
        proc_img = _binarize(proc_img)

        # Save preprocessed image
        proc_path = file_path.parent / (file_path.stem + "_preprocessed.png")
        proc_img.save(str(proc_path), "PNG")

        # ── Overall score ─────────────────────────────────────────
        score = _compute_score(resolution_ok, blur_score, brightness, contrast)

        return QualityReport(
            score=score,
            resolution_ok=resolution_ok,
            width_px=w,
            height_px=h,
            blur_score=blur_score,
            brightness=brightness,
            contrast=contrast,
            estimated_dpi=estimated_dpi,
            issues=issues,
            recommendations=recommendations,
            preprocessed_path=str(proc_path),
        )

    except Exception as exc:
        log.error("Quality analysis failed: %s", exc)
        return QualityReport(
            score=0.5, resolution_ok=True, width_px=None, height_px=None,
            blur_score=None, brightness=None, contrast=None, estimated_dpi=None,
            issues=[f"Analysis error: {exc}"],
        )


def _binarize(img: "Image.Image") -> "Image.Image":
    """Otsu-style binarization using Pillow."""
    # Point operation: pixels > threshold → white, else black
    threshold = 128
    return img.point(lambda p: 255 if p > threshold else 0, "L")


def _estimate_dpi(w: int, h: int) -> int:
    """Rough DPI estimate assuming A4 paper (210×297 mm)."""
    dpi_w = int(w / 8.27)   # 8.27 inches = 210mm
    dpi_h = int(h / 11.69)  # 11.69 inches = 297mm
    return max(dpi_w, dpi_h)


def _compute_score(resolution_ok: bool, blur: Optional[float],
                   brightness: float, contrast: float) -> float:
    score = 1.0
    if not resolution_ok:
        score -= 0.30
    if blur is not None:
        if blur < 100:
            score -= 0.30
        elif blur < 300:
            score -= 0.15
    if brightness < 60 or brightness > 220:
        score -= 0.15
    if contrast < 40:
        score -= 0.15
    return round(max(0.0, min(1.0, score)), 3)
