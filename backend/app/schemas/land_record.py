"""Land Record Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.land_record import LandUseType, RecordStatus


class LandRecordBase(BaseModel):
    khasra_number: str = Field(..., min_length=1, max_length=64)
    khatauni_number: str | None = None
    survey_number: str | None = None

    state: str = Field(..., min_length=2, max_length=64)
    district: str = Field(..., min_length=2, max_length=128)
    tehsil: str = Field(..., min_length=2, max_length=128)
    village: str = Field(..., min_length=2, max_length=128)
    pin_code: str | None = None

    area_hectares: float = Field(..., gt=0)
    land_use_type: LandUseType

    owner_name: str = Field(..., min_length=2, max_length=255)
    father_name: str | None = None
    address: str | None = None
    aadhaar_last4: str | None = Field(None, min_length=4, max_length=4, pattern=r"^\d{4}$")

    geometry: dict | None = None


class LandRecordCreate(LandRecordBase):
    pass


class LandRecordUpdate(BaseModel):
    khatauni_number: str | None = None
    survey_number: str | None = None
    area_hectares: float | None = Field(None, gt=0)
    land_use_type: LandUseType | None = None
    owner_name: str | None = None
    father_name: str | None = None
    address: str | None = None
    geometry: dict | None = None


class VerifyRequest(BaseModel):
    approved: bool
    rejection_reason: str | None = None


class LandRecordResponse(LandRecordBase):
    id: UUID
    status: RecordStatus
    rejection_reason: str | None = None
    created_by: UUID | None
    verified_by: UUID | None
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LandRecordListItem(BaseModel):
    """Lighter version for list views."""
    id: UUID
    khasra_number: str
    owner_name: str
    district: str
    village: str
    area_hectares: float
    land_use_type: LandUseType
    status: RecordStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
