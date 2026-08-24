"""Patient-facing dashboard, profile and settings schemas — camelCase for the Next.js
frontend. Grounded in:
  - src/features/patient/dashboardData.ts (dashboard shape: appointments, nearbyProviders,
    carePlan, healthSummary, emergencyContact — mock data explicitly marked for replacement)
  - src/types/index.ts PatientProfilePublic / UserPublic / AppointmentPublic (naming
    conventions, e.g. `distanceKm` on a location block)
  - src/components/web/patient/WebPatientProfile.tsx + WebPatientSettings.tsx (profile/
    settings fields actually rendered/edited)
"""

import uuid
from datetime import datetime

from pydantic import Field

from app.core.constants import BookingStatus
from app.schemas.common import CamelModel


class AppointmentSummaryOut(CamelModel):
    id: uuid.UUID
    service: str
    clinician: str | None
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    status: BookingStatus
    address: str


class NearbyProviderOut(CamelModel):
    id: uuid.UUID
    name: str
    role: str
    specialty: str
    distance_km: float
    rating: float
    availability: str


class CarePlanProgressOut(CamelModel):
    id: uuid.UUID
    title: str
    completed: int
    total: int
    next_step: str | None = None


class HealthReadingOut(CamelModel):
    label: str
    value: str
    unit: str | None = None


class EmergencyContactOut(CamelModel):
    name: str
    relationship: str | None = None
    phone: str


class PatientDashboardOut(CamelModel):
    upcoming_appointments: list[AppointmentSummaryOut] = Field(default_factory=list)
    nearby_providers: list[NearbyProviderOut] = Field(default_factory=list)
    care_plan: CarePlanProgressOut | None = None
    health_summary: list[HealthReadingOut] = Field(default_factory=list)
    emergency_contact: EmergencyContactOut | None = None


class PatientProfileOut(CamelModel):
    public_id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    avatar_url: str | None
    address_line: str | None
    city: str | None
    state: str | None
    known_conditions: list[str] | None
    allergies: list[str] | None
    current_medications: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    emergency_contact_relationship: str | None
    preferred_language: str | None
    notes: str | None
    date_of_birth: datetime | None
    created_at: datetime


class PatientProfileUpdateIn(CamelModel):
    full_name: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    known_conditions: list[str] | None = None
    allergies: list[str] | None = None
    current_medications: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relationship: str | None = None
    preferred_language: str | None = None
    notes: str | None = None
    date_of_birth: datetime | None = None


class PatientSettingsOut(CamelModel):
    full_name: str
    email: str | None
    phone: str | None
    preferred_language: str | None


class PatientSettingsUpdateIn(CamelModel):
    full_name: str | None = None
    email: str | None = None
    preferred_language: str | None = None
