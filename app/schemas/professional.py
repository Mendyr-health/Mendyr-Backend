import uuid
from datetime import datetime, time

from pydantic import BaseModel, Field, model_validator

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
    bio: str | None = Field(default=None, max_length=1000)
    license_number: str | None = Field(default=None, max_length=100)
    council_registration_number: str | None = Field(default=None, max_length=100)
    languages_spoken: list[str] | None = None
    specialization_ids: list[uuid.UUID] = Field(default_factory=list)
    # Where they travel from and how far they'll go — together these decide which patients'
    # requests they see.
    location: GeoPoint
    service_radius_km: float = Field(default=10, ge=1, le=50)
    # Empty means "every active service my profession can do".
    service_ids: list[uuid.UUID] = Field(default_factory=list)


class ProfessionalUpdateIn(BaseModel):
    """Partial update of the professional's own profile; omitted fields are left unchanged.
    `professional_type` is fixed after onboarding — their service opt-ins depend on it."""

    years_of_experience: int | None = Field(default=None, ge=0, le=60)
    bio: str | None = Field(default=None, max_length=1000)
    license_number: str | None = Field(default=None, max_length=100)
    council_registration_number: str | None = Field(default=None, max_length=100)
    languages_spoken: list[str] | None = None
    location: GeoPoint | None = None
    service_radius_km: float | None = Field(default=None, ge=1, le=50)
    is_accepting_bookings: bool | None = None


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
    """One weekly working window, in MARKET_TIMEZONE wall-clock time. A shift that crosses
    midnight is two slots: e.g. Mon 20:00–23:59 and Tue 00:00–08:00."""

    day_of_week: int = Field(..., ge=0, le=6)  # 0 = Monday ... 6 = Sunday
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _end_after_start(self) -> "AvailabilitySlotIn":
        if self.end_time <= self.start_time:
            raise ValueError(
                "end_time must be after start_time — split overnight shifts at midnight"
            )
        return self


class AvailabilitySlotRead(ORMModel):
    day_of_week: int
    start_time: time
    end_time: time


class AvailabilityStatusUpdateIn(BaseModel):
    availability_status: AvailabilityStatus
    location: GeoPoint | None = None


class ProfessionalRead(BaseModel):
    """The professional's own view of their profile. Built by
    `professional_service.to_professional_read`, since lat/lng come from a PostGIS point."""

    id: uuid.UUID
    professional_type: ProfessionalType
    years_of_experience: int
    bio: str | None
    license_number: str | None
    council_registration_number: str | None
    languages_spoken: list[str] | None
    verification_status: VerificationStatus
    rejection_reason: str | None
    availability_status: AvailabilityStatus
    is_accepting_bookings: bool
    latitude: float | None
    longitude: float | None
    service_radius_km: float
    average_rating: float
    total_ratings: int
    total_visits_completed: int
    created_at: datetime


class ProfessionalPublicRead(BaseModel):
    """What the patient app shows about a professional — no banking/KYC internals."""

    id: uuid.UUID
    full_name: str
    avatar_url: str | None
    professional_type: ProfessionalType
    years_of_experience: int
    average_rating: float
    total_ratings: int
    languages_spoken: list[str] | None


class NearbyProfessionalRead(ProfessionalPublicRead):
    """A professional appearing in the patient app's "nearby available nurses" browse list."""

    distance_km: float


class ProfessionalServiceRead(BaseModel):
    """One row of the professional's own view of the catalogue: which services they've opted
    into and what they charge for each (base price unless they've overridden it)."""

    service_id: uuid.UUID
    service_name: str
    category_name: str
    base_price: float
    price_override: float | None
    effective_price: float
    is_opted_in: bool


class ProfessionalServiceUpdateIn(BaseModel):
    """Opt into (or out of) a catalogue service and set a per-visit price for it. Omitting
    `price_override` (or setting it to null) charges the catalogue's `base_price` instead —
    e.g. for a senior/ICU nurse charging above the standard rate for the same service."""

    is_opted_in: bool = True
    price_override: float | None = Field(default=None, ge=0)
