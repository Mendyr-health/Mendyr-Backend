"""Shapes for the config portal's operations screens: verification queue, users, bookings,
activity log."""

import uuid
from datetime import datetime, time
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from app.core.constants import (
    BookingStatus,
    DocumentType,
    ProfessionalType,
    UserRole,
    UserStatus,
    VerificationStatus,
)
from app.schemas.booking import StatusEvent
from app.schemas.document import MedicalDocumentOut

T = TypeVar("T")


class AdminPage(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ── Professionals / verification ────────────────────────────────────────


class AdminProfessionalListItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    phone_number: str
    email: str | None
    gender: str
    avatar_url: str | None
    professional_type: ProfessionalType
    years_of_experience: int
    license_number: str | None
    council_registration_number: str | None
    verification_status: VerificationStatus
    rejection_reason: str | None
    verified_at: datetime | None
    is_accepting_bookings: bool
    user_status: UserStatus
    city: str | None
    average_rating: float
    total_ratings: int
    total_visits_completed: int
    documents_count: int
    created_at: datetime


class AdminDocument(BaseModel):
    id: uuid.UUID
    document_type: DocumentType
    verification_status: VerificationStatus
    rejection_reason: str | None
    content_type: str | None
    # Short-lived link to the private file — fetch the detail again rather than storing it.
    view_url: str
    reviewed_at: datetime | None
    created_at: datetime


class AdminSlot(BaseModel):
    day_of_week: int
    start_time: time
    end_time: time


class AdminActivity(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str
    actor_name: str | None
    metadata: dict | None
    created_at: datetime


class AdminProfessionalDetail(AdminProfessionalListItem):
    bio: str | None
    languages_spoken: list[str] | None
    service_radius_km: float
    latitude: float | None
    longitude: float | None
    documents: list[AdminDocument]
    services: list[str]
    availability: list[AdminSlot]
    bookings_by_status: dict[str, int]
    history: list[AdminActivity]


class VerificationStats(BaseModel):
    """Headline numbers for the verification queue."""

    total: int
    by_status: dict[str, int]
    by_type: dict[str, dict[str, int]]
    onboarded_today: int
    onboarded_7d: int
    onboarded_30d: int
    approved_7d: int
    rejected_7d: int
    # Median hours from signup to approval over the last 30 days.
    median_hours_to_approve: float | None
    oldest_pending_at: datetime | None
    auto_approve: bool
    daily: list[dict]


# ── Users ───────────────────────────────────────────────────────────────


class AdminUserListItem(BaseModel):
    id: uuid.UUID
    full_name: str
    phone_number: str
    email: str | None
    role: UserRole
    status: UserStatus
    gender: str
    created_at: datetime
    last_login_at: datetime | None
    bookings_count: int


class UserStatusIn(BaseModel):
    status: Literal["active", "suspended"]
    reason: str | None = Field(default=None, max_length=300)


# ── Bookings ────────────────────────────────────────────────────────────


class AdminBookingListItem(BaseModel):
    id: uuid.UUID
    booking_code: str
    status: BookingStatus
    service_name: str
    scheduled_start_at: datetime
    total_amount: float
    patient_name: str
    patient_phone: str
    professional_name: str | None
    city: str | None
    created_at: datetime


class AdminBookingDetail(AdminBookingListItem):
    address: str
    patient_id: uuid.UUID
    professional_id: uuid.UUID | None
    professional_phone: str | None
    base_price: float
    discount_amount: float
    platform_fee: float
    tax_amount: float
    professional_payout_amount: float
    patient_notes: str | None
    cancellation_reason: str | None
    cancellation_fee_amount: float
    preferred_gender: str | None
    visit_summary_notes: str | None
    vitals_recorded: str | None
    review_rating: int | None
    timeline: list[StatusEvent]
    documents: list[MedicalDocumentOut] = []


class AdminCancelIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
