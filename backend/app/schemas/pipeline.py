"""
Pipeline Schemas — Pydantic models for API request/response.
"""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float
    page: int = 1


class ExtractedFieldOut(BaseModel):
    id: uuid.UUID
    field_name: str
    field_display: Optional[str]
    raw_value: Optional[str]
    normalized_value: Optional[str]
    confidence_score: float
    ocr_confidence: Optional[float]
    extraction_method: Optional[str]
    source_page: Optional[int]
    bounding_box: Optional[dict]
    validation_status: str
    validation_message: Optional[str]
    needs_review: bool
    verified_by: Optional[uuid.UUID]
    verified_value: Optional[str]
    verified_at: Optional[datetime]

    class Config:
        from_attributes = True


class AnomalyOut(BaseModel):
    id: uuid.UUID
    anomaly_type: str
    field_name: Optional[str]
    severity: str
    description: str
    confidence: float
    resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AnomalyFeedItem(AnomalyOut):
    """One anomaly plus the document and land record it was found in."""
    job_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    document_type: str
    land_record_id: Optional[uuid.UUID] = None
    khasra_number: Optional[str] = None
    village: Optional[str] = None
    district: Optional[str] = None
    confidence_pct: int = 0
    resolved_by: Optional[uuid.UUID] = None


class AnomalyFeedOut(BaseModel):
    items: list[AnomalyFeedItem]
    total: int
    page: int
    page_size: int
    pages: int


class VerificationTaskOut(BaseModel):
    id: uuid.UUID
    field_id: uuid.UUID
    status: str
    priority: str
    context_snippet: Optional[str]
    resolution_notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ProcessingJobOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    land_record_id: Optional[uuid.UUID]
    status: str
    current_stage: Optional[str]
    progress_pct: int
    detected_language: Optional[str]
    page_count: Optional[int]
    image_quality_score: Optional[float]
    overall_confidence: Optional[float]
    needs_human_review: bool
    has_anomalies: bool
    is_duplicate: bool
    duplicate_of_id: Optional[uuid.UUID]
    error_message: Optional[str]
    stage_timings: Optional[dict]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    extracted_fields: list[ExtractedFieldOut] = []
    anomalies: list[AnomalyOut] = []
    verification_tasks: list[VerificationTaskOut] = []

    class Config:
        from_attributes = True


class FieldVerificationIn(BaseModel):
    verified_value: str = Field(..., description="Corrected value from the verifier")
    notes: Optional[str] = None


class JobTriggerIn(BaseModel):
    document_id: uuid.UUID
    land_record_id: Optional[uuid.UUID] = None
    priority: str = "NORMAL"  # LOW | NORMAL | HIGH
