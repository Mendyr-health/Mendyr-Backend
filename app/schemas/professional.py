import uuid
from datetime import datetime, time

from pydantic import BaseModel, Field

from app.core.constants import (
    AvailabilityStatus,
    DocumentType,
    ProfessionalType,
    VerificationStatus,
)
from app.schemas.common import GeoPoint, ORMModel


class ProfessionalOnboardIn(BaseModel):
    professional_type: ProfessionalType
    years_of_experience: int = Field(default=0, ge=0, le=60)
    bio: str | None = None
    license_number: str | None = None
    council_registration_number: str | None = None
    languages_spoken: list[str] | None = None
    specialization_ids: list[uuid.UUID] = Field(default_factory=list)
    service_ids: list[uuid.UUID] = Field(default_factory=list)


class ProfessionalDocumentUploadIn(BaseModel):
    document_type: DocumentType
    file_url: str


class ProfessionalDocumentRead(ORMModel):
    id: uuid.UUID
    document_type: DocumentType
    file_url: str
    verification_status: VerificationStatus
    rejection_reason: str | None


class ProfessionalReviewDecisionIn(BaseModel):
    """Used by ops/admin to approve/reject a professional's KYC."""

    approve: bool
    rejection_reason: str | None = None


class AvailabilitySlotIn(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: time
    end_time: time


class AvailabilityStatusUpdateIn(BaseModel):
    availability_status: AvailabilityStatus
    location: GeoPoint | None = None


class ProfessionalRead(ORMModel):
    id: uuid.UUID
    professional_type: ProfessionalType
    years_of_experience: int
    bio: str | None
    verification_status: VerificationStatus
    availability_status: AvailabilityStatus
    average_rating: float
    total_ratings: int
    total_visits_completed: int
    is_accepting_bookings: bool
    created_at: datetime


class ProfessionalPublicRead(BaseModel):
    """What the patient app shows about the assigned professional — no banking/KYC internals."""

    id: uuid.UUID
    full_name: str
    avatar_url: str | None
    professional_type: ProfessionalType
    years_of_experience: int
    average_rating: float
    total_ratings: int
    languages_spoken: list[str] | None
