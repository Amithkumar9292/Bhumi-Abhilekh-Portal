"""
Canonical document-processing pipeline stages.

The upload request only ever creates a job in ``QUEUED``. Everything below runs
inside a background worker, and every stage transition is committed to
PostgreSQL immediately so that ``GET /documents/{id}/status`` can report real
progress rather than a guess.

Stage order::

    QUEUED
      -> FILE_VALIDATION
      -> IMAGE_QUALITY
      -> PREPROCESSING
      -> OCR
      -> LANGUAGE_DETECTION
      -> FIELD_EXTRACTION
      -> CLASSIFICATION
      -> CONFIDENCE_SCORING
      -> VALIDATION
      -> DUPLICATE_CHECK
      -> ANOMALY_CHECK
      -> VERIFICATION_REQUIRED | COMPLETED

``ProcessingStatus`` (the persisted job status) and :class:`PipelineStage` (the
canonical stage vocabulary) are kept separate on purpose: several stages share a
coarse status value, and the status endpoint needs to report both the coarse
lifecycle (``processing``) and the precise stage (``OCR``).
"""
from __future__ import annotations

from enum import Enum

from app.models.pipeline import ProcessingStatus


class PipelineStage(str, Enum):
    """Canonical, human-readable stage names exposed by the status API."""

    QUEUED = "QUEUED"
    FILE_VALIDATION = "FILE_VALIDATION"
    IMAGE_QUALITY = "IMAGE_QUALITY"
    PREPROCESSING = "PREPROCESSING"
    OCR = "OCR"
    LANGUAGE_DETECTION = "LANGUAGE_DETECTION"
    FIELD_EXTRACTION = "FIELD_EXTRACTION"
    CLASSIFICATION = "CLASSIFICATION"
    CONFIDENCE_SCORING = "CONFIDENCE_SCORING"
    VALIDATION = "VALIDATION"
    DUPLICATE_CHECK = "DUPLICATE_CHECK"
    ANOMALY_CHECK = "ANOMALY_CHECK"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobState(str, Enum):
    """Coarse lifecycle reported as ``status`` by the status endpoints."""

    QUEUED = "queued"
    PROCESSING = "processing"
    VERIFICATION_REQUIRED = "verification_required"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationStatus(str, Enum):
    """Whether extracted fields still need a human decision."""

    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"


# Progress percentage at the *start* of each stage. The terminal stages are
# pinned to 100 so the progress bar can never stall at 99%.
STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.QUEUED,
    PipelineStage.FILE_VALIDATION,
    PipelineStage.IMAGE_QUALITY,
    PipelineStage.PREPROCESSING,
    PipelineStage.OCR,
    PipelineStage.LANGUAGE_DETECTION,
    PipelineStage.FIELD_EXTRACTION,
    PipelineStage.CLASSIFICATION,
    PipelineStage.CONFIDENCE_SCORING,
    PipelineStage.VALIDATION,
    PipelineStage.DUPLICATE_CHECK,
    PipelineStage.ANOMALY_CHECK,
    PipelineStage.VERIFICATION_REQUIRED,
    PipelineStage.COMPLETED,
)

STAGE_START_PROGRESS: dict[PipelineStage, int] = {
    PipelineStage.QUEUED: 0,
    PipelineStage.FILE_VALIDATION: 2,
    PipelineStage.IMAGE_QUALITY: 8,
    PipelineStage.PREPROCESSING: 14,
    PipelineStage.OCR: 20,
    PipelineStage.LANGUAGE_DETECTION: 45,
    PipelineStage.FIELD_EXTRACTION: 50,
    PipelineStage.CLASSIFICATION: 65,
    PipelineStage.CONFIDENCE_SCORING: 70,
    PipelineStage.VALIDATION: 75,
    PipelineStage.DUPLICATE_CHECK: 82,
    PipelineStage.ANOMALY_CHECK: 88,
    PipelineStage.VERIFICATION_REQUIRED: 94,
    PipelineStage.COMPLETED: 100,
    PipelineStage.FAILED: 100,
}

# Short, user-facing progress messages shown while a stage is running.
STAGE_MESSAGES: dict[PipelineStage, str] = {
    PipelineStage.QUEUED: "Upload accepted. Waiting for a processing worker…",
    PipelineStage.FILE_VALIDATION: "Validating the uploaded file…",
    PipelineStage.IMAGE_QUALITY: "Analysing image quality (sharpness, contrast)…",
    PipelineStage.PREPROCESSING: "Preprocessing the scan (deskew, denoise, binarize)…",
    PipelineStage.OCR: "Running OCR — extracting text from the document…",
    PipelineStage.LANGUAGE_DETECTION: "Detecting the document language…",
    PipelineStage.FIELD_EXTRACTION: "Extracting land-record fields…",
    PipelineStage.CLASSIFICATION: "Classifying the document type…",
    PipelineStage.CONFIDENCE_SCORING: "Scoring extraction confidence…",
    PipelineStage.VALIDATION: "Validating extracted values…",
    PipelineStage.DUPLICATE_CHECK: "Checking for duplicate land records…",
    PipelineStage.ANOMALY_CHECK: "Running anomaly detection…",
    PipelineStage.VERIFICATION_REQUIRED: "Routing low-confidence fields to verification…",
    PipelineStage.COMPLETED: "Processing complete.",
    PipelineStage.FAILED: "Processing failed.",
}

# Persisted job status for each stage. Several stages deliberately share a
# coarse status, which is why the stage name is stored separately.
STAGE_TO_PROCESSING_STATUS: dict[PipelineStage, ProcessingStatus] = {
    PipelineStage.QUEUED: ProcessingStatus.QUEUED,
    PipelineStage.FILE_VALIDATION: ProcessingStatus.VALIDATING,
    PipelineStage.IMAGE_QUALITY: ProcessingStatus.QUALITY_ANALYSIS,
    PipelineStage.PREPROCESSING: ProcessingStatus.PREPROCESSING,
    PipelineStage.OCR: ProcessingStatus.OCR_RUNNING,
    PipelineStage.LANGUAGE_DETECTION: ProcessingStatus.LANGUAGE_DETECTION,
    PipelineStage.FIELD_EXTRACTION: ProcessingStatus.EXTRACTING,
    PipelineStage.CLASSIFICATION: ProcessingStatus.CLASSIFYING,
    PipelineStage.CONFIDENCE_SCORING: ProcessingStatus.SCORING,
    PipelineStage.VALIDATION: ProcessingStatus.VALIDATING,
    PipelineStage.DUPLICATE_CHECK: ProcessingStatus.DEDUP_CHECK,
    PipelineStage.ANOMALY_CHECK: ProcessingStatus.ANOMALY_CHECK,
    PipelineStage.VERIFICATION_REQUIRED: ProcessingStatus.PENDING_REVIEW,
    PipelineStage.COMPLETED: ProcessingStatus.COMPLETED,
    PipelineStage.FAILED: ProcessingStatus.FAILED,
}

_TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.FAILED})
_REVIEW_STATES = frozenset({JobState.VERIFICATION_REQUIRED})

# Processing statuses that mean "work is still in flight".
IN_PROGRESS_STATUSES = frozenset(
    {
        ProcessingStatus.QUEUED,
        ProcessingStatus.VALIDATING,
        ProcessingStatus.QUALITY_ANALYSIS,
        ProcessingStatus.PREPROCESSING,
        ProcessingStatus.OCR_RUNNING,
        ProcessingStatus.LANGUAGE_DETECTION,
        ProcessingStatus.EXTRACTING,
        ProcessingStatus.CLASSIFYING,
        ProcessingStatus.SCORING,
        ProcessingStatus.DEDUP_CHECK,
        ProcessingStatus.ANOMALY_CHECK,
        ProcessingStatus.PENDING_REVIEW,
    }
)

TERMINAL_STATUSES = frozenset({ProcessingStatus.COMPLETED, ProcessingStatus.FAILED})

# Statuses whose automatic processing has finished, so the job can be re-queued.
# PENDING_REVIEW belongs here: the pipeline is done and only the extracted
# *fields* await a human, which does not make the OCR itself unrepeatable. A
# reviewer who sees every field empty needs to re-run the engine, and without
# this the only option is re-uploading the file as a new document.
RETRYABLE_STATUSES = frozenset(
    {
        ProcessingStatus.COMPLETED,
        ProcessingStatus.FAILED,
        ProcessingStatus.PENDING_REVIEW,
    }
)


def resolve_stage(status: ProcessingStatus | str | None) -> PipelineStage:
    """Map a persisted job status back onto its canonical stage."""
    if status is None:
        return PipelineStage.QUEUED
    if isinstance(status, PipelineStage):
        return status
    raw = status.value if isinstance(status, ProcessingStatus) else str(status)
    for stage, mapped in STAGE_TO_PROCESSING_STATUS.items():
        if mapped.value == raw:
            return stage
    try:
        return PipelineStage(raw)
    except ValueError:
        return PipelineStage.QUEUED


def state_for(status: ProcessingStatus | str | None) -> JobState:
    """Map a persisted job status onto the coarse lifecycle reported to clients."""
    if status is None:
        return JobState.QUEUED
    if isinstance(status, ProcessingStatus):
        raw = status
    else:
        try:
            raw = ProcessingStatus(str(status))
        except ValueError:
            return JobState.QUEUED
    if raw is ProcessingStatus.QUEUED:
        return JobState.QUEUED
    if raw is ProcessingStatus.FAILED:
        return JobState.FAILED
    if raw is ProcessingStatus.PENDING_REVIEW:
        return JobState.VERIFICATION_REQUIRED
    if raw in IN_PROGRESS_STATUSES:
        return JobState.PROCESSING
    if raw is ProcessingStatus.COMPLETED:
        return JobState.COMPLETED
    return JobState.PROCESSING


def is_terminal(state: JobState) -> bool:
    """True once no further automated work will happen (completed or failed)."""
    return state in _TERMINAL_STATES


def is_confirmable(state: JobState) -> bool:
    """
    True when a human may submit corrections for this job.

    A job awaiting verification is exactly the state confirmation is for, so
    ``verification_required`` counts as confirmable even though it is not
    terminal -- automatic processing is finished, the outcome is just not final.
    """
    return state in _TERMINAL_STATES or state in _REVIEW_STATES


def needs_verification(state: JobState) -> bool:
    return state in _REVIEW_STATES


def progress_for(stage: PipelineStage) -> int:
    return STAGE_START_PROGRESS.get(stage, 0)


def message_for(stage: PipelineStage) -> str:
    return STAGE_MESSAGES.get(stage, stage.value)
