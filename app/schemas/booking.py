import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import BookingStatus, BookingType
from app.schemas.common import ORMModel
from app.schemas.professional import ProfessionalPublicRead


class BookingCreateIn(BaseModel):
    service_id: uuid.UUID
    address_id: uuid.UUID
    scheduled_start_at: datetime
    patient_notes: str | None = None
    coupon_code: str | None = None
    # Care-plan fields — only used when booking_type=CARE_PLAN:
    booking_type: BookingType = BookingType.ONE_TIME
    total_visits: int | None = Field(default=None, ge=1, le=90)
    visits_per_day: int = Field(default=1, ge=1, le=4)
    preferred_professional_id: uuid.UUID | None = None


class BookingQuoteIn(BaseModel):
    """Price preview shown before the patient confirms — no rows written yet."""

    service_id: uuid.UUID
    address_id: uuid.UUID
    coupon_code: str | None = None


class BookingQuoteOut(BaseModel):
    base_price: float
    discount_amount: float
    platform_fee: float
    tax_amount: float
    total_amount: float


class BookingCancelIn(BaseModel):
    reason: str


class BookingRead(ORMModel):
    id: uuid.UUID
    booking_code: str
    status: BookingStatus
    booking_type: BookingType
    service_name_snapshot: str
    address_snapshot: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    base_price: float
    discount_amount: float
    platform_fee: float
    tax_amount: float
    total_amount: float
    professional: ProfessionalPublicRead | None = None
    created_at: datetime


class BookingListItem(ORMModel):
    id: uuid.UUID
    booking_code: str
    status: BookingStatus
    service_name_snapshot: str
    scheduled_start_at: datetime
    total_amount: float


class OfferRespondIn(BaseModel):
    accept: bool


class OfferRead(ORMModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    round_number: int
    distance_meters: int
    status: str
    expires_at: datetime


class VisitCheckInIn(BaseModel):
    latitude: float
    longitude: float


class VisitCheckOutIn(BaseModel):
    latitude: float
    longitude: float
    visit_summary_notes: str | None = None
    vitals_recorded: str | None = None
    proof_of_visit_photo_url: str | None = None
