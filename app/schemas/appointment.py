"""Nurse-facing appointment, care-note and earnings schemas — shaped to match the frontend's
`AppointmentPublic` / `CareNotePublic` / `EarningTransactionPublic` / `NurseEarningsSummary`
(mendyr-frontend/src/types/index.ts) exactly, field for field.
"""

import uuid
from datetime import datetime

from app.schemas.common import CamelModel


class AppointmentLocationOut(CamelModel):
    address: str
    city: str
    state: str | None = None
    distance_km: float | None = None


class VitalsIn(CamelModel):
    blood_pressure: str | None = None
    heart_rate: str | float | None = None
    temperature: str | float | None = None
    oxygen_saturation: str | float | None = None
    oxygen_level: str | float | None = None


class VitalsOut(VitalsIn):
    pass


class CareNoteIn(CamelModel):
    """Body of POST /appointments/{booking_id}/care-notes — logged mid-visit or at check-out."""

    notes: str
    vitals: VitalsIn | None = None
    medications_administered: list[str] | None = None


class CareNotePublic(CamelModel):
    id: str
    timestamp: str
    vitals: VitalsOut | None = None
    medications_administered: list[str] | None = None
    notes: str
    author_name: str


class AppointmentPublic(CamelModel):
    public_id: str
    patient_name: str
    patient_age: int | None = None
    patient_gender: str | None = None
    patient_avatar: str | None = None
    patient_phone: str | None = None
    service_name: str
    service_slug: str | None = None
    date: str
    time_slot: str
    duration_hours: float | None = None
    location: AppointmentLocationOut
    payout_amount: float
    status: str
    special_instructions: str | None = None
    medical_conditions: list[str] | None = None
    rejection_reason: str | None = None
    check_in_time: str | None = None
    check_out_time: str | None = None
    care_notes: list[CareNotePublic] | None = None
    created_at: str | None = None


class EarningTransactionPublic(CamelModel):
    id: str
    appointment_id: str | None = None
    patient_name: str
    service_name: str
    date: str
    amount: float
    status: str  # PAID | PROCESSING | PENDING
    payment_method: str | None = None


class NurseEarningsSummary(CamelModel):
    today_earnings: float
    week_earnings: float
    month_earnings: float
    total_earnings: float
    pending_payout: float
    completed_visits_count: int
    transactions: list[EarningTransactionPublic]


class NurseAvailabilityDayOut(CamelModel):
    day: str
    active: bool
    hours: str


class NurseAvailabilityOut(CamelModel):
    days: list[NurseAvailabilityDayOut]
    on_duty_now: bool
    availability_status: str


class NurseDocumentPublic(CamelModel):
    public_id: uuid.UUID
    type: str
    file_name: str
    file_url: str
    verified: bool
    created_at: datetime
