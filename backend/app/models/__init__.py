"""
Model package.

Every model is re-exported here so that importing any single module registers the
whole set with SQLAlchemy's declarative registry. Several relationships are
declared as strings (e.g. ``LandRecord.documents = relationship("Document")``);
those can only be resolved once every referenced class has been imported, so
entry points such as the seeders should import from this package instead of
from individual model modules.
"""

from app.models.document import Document, DocumentStatus, DocumentType
from app.models.extended import (
    CoordinateType,
    GISCoordinate,
    LandRecordOwner,
    Mutation,
    MutationStatus,
    MutationType,
    Notification,
    NotificationType,
    Owner,
    OwnerType,
    Plot,
    PlotStatus,
    Registration,
    RegistrationType,
    RuleSeverity,
    SurveyDetail,
    SurveyType,
    ValidationResult,
    ValidationRule,
    VerificationAction,
    VerificationActionType,
)
from app.models.land_record import LandRecord, LandUseType, RecordStatus
from app.models.pipeline import (
    AnomalyType,
    DocumentLanguage,
    ExtractedField,
    FieldValidationStatus,
    PipelineAnomaly,
    ProcessingJob,
    ProcessingStatus,
    VerificationTask,
)
from app.models.user import RoleEnum, User, UserRole

__all__ = [
    "AnomalyType",
    "CoordinateType",
    "Document",
    "DocumentLanguage",
    "DocumentStatus",
    "DocumentType",
    "ExtractedField",
    "FieldValidationStatus",
    "GISCoordinate",
    "LandRecord",
    "LandRecordOwner",
    "LandUseType",
    "Mutation",
    "MutationStatus",
    "MutationType",
    "Notification",
    "NotificationType",
    "Owner",
    "OwnerType",
    "PipelineAnomaly",
    "Plot",
    "PlotStatus",
    "ProcessingJob",
    "ProcessingStatus",
    "RecordStatus",
    "Registration",
    "RegistrationType",
    "RoleEnum",
    "RuleSeverity",
    "SurveyDetail",
    "SurveyType",
    "User",
    "UserRole",
    "ValidationResult",
    "ValidationRule",
    "VerificationAction",
    "VerificationActionType",
    "VerificationTask",
]
