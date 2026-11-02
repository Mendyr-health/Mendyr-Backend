import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.core.constants import BookingStatus, BookingType
from app.schemas.common import ORMModel
from app.schemas.document import MedicalDocumentOut
from app.schemas.professional import ProfessionalPublicRead


class BookingCreateIn(BaseModel):
    service_id: uuid.UUID
    address_id: uuid.UUID
    # Must carry a UTC offset — a naive time is ambiguous for a visit happening in India
    # but possibly booked from abroad (e.g. a child booking care for a parent).
    scheduled_start_at: AwareDatetime
    patient_notes: str | None = Field(default=None, max_length=1000)
    coupon_code: str | None = None
    # Care-plan fields — only used when booking_type=CARE_PLAN:
    booking_type: BookingType = BookingType.ONE_TIME
    total_visits: int | None = Field(default=None, ge=1, le=90)
    visits_per_day: int = Field(default=1, ge=1, le=4)
    preferred_professional_id: uuid.UUID | None = None
    # Only professionals of this gender see the request (feature flag `gender_preference`).
    preferred_gender: Literal["female", "male"] | None = None
    # The patient's own uploaded medical documents to share with the professional.
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class BookingQuoteIn(BaseModel):
    """Price preview shown before the patient confirms — no rows written yet."""

    service_id: uuid.UUID
    # Not used by pricing yet (no distance-based fares) — optional so the price can be shown
    # before the patient has picked an address.
    address_id: uuid.UUID | None = None
    coupon_code: str | None = None


class BookingQuoteOut(BaseModel):
    base_price: float
    discount_amount: float
    platform_fee: float
    tax_amount: float
    total_amount: float


class BookingCancelIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class AssignedProfessionalRead(ProfessionalPublicRead):
    """The professional assigned to a patient's booking. Includes their phone number while
    the visit is live — the two need to coordinate directly and there's no call masking. Once
    the booking is cancelled (or a while after it's done) the number is withheld and only
    `user_ref` is shown; see `PrivacyConfig`."""

    phone_number: str | None
    user_ref: str
    is_verified: bool
    gender: str


class StatusEvent(BaseModel):
    """One step of a booking's timeline, oldest first."""

    status: BookingStatus
    at: datetime
    note: str | None = None


class BookingRead(ORMModel):
    """The patient's view of one of their bookings."""

    id: uuid.UUID
    booking_code: str
    status: BookingStatus
    booking_type: BookingType
    service_id: uuid.UUID
    service_name_snapshot: str
    address_snapshot: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    base_price: float
    discount_amount: float
    platform_fee: float
    tax_amount: float
    total_amount: float
    patient_notes: str | None = None
    cancellation_reason: str | None = None
    cancellation_fee_amount: float = 0
    cancelled_by: Literal["patient", "professional", "admin", "system"] | None = None
    professional: AssignedProfessionalRead | None = None
    # The professional's notes and vitals from check-out, shown once the visit is done.
    visit_summary_notes: str | None = None
    vitals_recorded: str | None = None
    review_rating: int | None = None
    # Read out to the professional at the door to start the visit (flag `visit_otp`).
    # Only present while the visit is upcoming.
    visit_pin: str | None = None
    preferred_gender: str | None = None
    en_route_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    contact_hidden: bool = False
    timeline: list[StatusEvent] = Field(default_factory=list)
    documents: list[MedicalDocumentOut] = Field(default_factory=list)
    created_at: datetime


class BookingListItem(ORMModel):
    id: uuid.UUID
    booking_code: str
    status: BookingStatus
    service_name_snapshot: str
    scheduled_start_at: datetime
    total_amount: float
    professional_name: str | None = None


class BookingRequestRead(BaseModel):
    """An open booking the calling professional may accept. Shows only the area, not the
    street address or the patient's identity — those are revealed once they accept."""

    id: uuid.UUID
    booking_code: str
    service_id: uuid.UUID
    service_name: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    area: str
    distance_km: float
    # What the professional takes home (base price minus platform commission).
    earning_amount: float
    patient_notes: str | None
    preferred_gender: str | None = None
    # A prescription/report is attached; visible once accepted.
    has_documents: bool = False
    created_at: datetime


class ProfessionalBookingRead(BaseModel):
    """A booking assigned to the calling professional — everything needed to do the visit.

    When `contact_hidden` is true (cancelled, or a while after completion — see
    `PrivacyConfig`) the phone, exact address and coordinates are withheld: `address` is just
    the area and the patient is identified by `patient_ref`."""

    id: uuid.UUID
    booking_code: str
    status: BookingStatus
    service_name: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    address: str
    landmark: str | None
    instructions: str | None
    latitude: float | None
    longitude: float | None
    patient_name: str
    patient_phone: str | None
    patient_ref: str
    patient_notes: str | None
    earning_amount: float
    en_route_at: datetime | None = None
    started_at: datetime | None
    completed_at: datetime | None
    visit_summary_notes: str | None
    vitals_recorded: str | None = None
    cancellation_reason: str | None = None
    cancelled_by: Literal["patient", "professional", "admin", "system"] | None = None
    # True when check-in must include the patient's visit PIN.
    requires_visit_pin: bool = False
    contact_hidden: bool = False
    # The patient's attached prescriptions/reports — only while the visit is live.
    documents: list[MedicalDocumentOut] = Field(default_factory=list)
    created_at: datetime


class VisitCheckInIn(BaseModel):
    # Only required (and checked against the address) when VISIT_GEOFENCE_ENABLED is on.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    # The patient's visit PIN — required when the `visit_otp` feature flag is on.
    visit_pin: str | None = Field(default=None, min_length=4, max_length=4)


class VisitCheckOutIn(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    visit_summary_notes: str | None = Field(default=None, max_length=4000)
    vitals_recorded: str | None = Field(default=None, max_length=2000)
    proof_of_visit_photo_url: str | None = None
