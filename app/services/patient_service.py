"""Patient dashboard, profile and settings — assembles data across bookings, care plans,
addresses and a nearest-professional geo browse for the patient-facing portal.

Grounded in src/features/patient/dashboardData.ts (mock data explicitly marked "replace
... when the patient endpoints are available") and the profile/settings pages under
src/components/web/patient/ + src/components/mobile/patient/.
"""

import json
import uuid

from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.core.constants import AvailabilityStatus
from app.models.patient import PatientProfile
from app.models.user import User
from app.repositories.patient_repo import PatientRepository
from app.schemas.patient import (
    AppointmentSummaryOut,
    CarePlanProgressOut,
    EmergencyContactOut,
    HealthReadingOut,
    NearbyProviderOut,
    PatientDashboardOut,
    PatientProfileOut,
    PatientProfileUpdateIn,
    PatientSettingsOut,
    PatientSettingsUpdateIn,
)

_AVAILABILITY_LABELS = {
    AvailabilityStatus.ONLINE: "Available now",
    AvailabilityStatus.ON_VISIT: "On a visit",
    AvailabilityStatus.BREAK: "On break",
    AvailabilityStatus.OFFLINE: "Offline",
}

_ROLE_LABELS = {
    "nurse": "Nurse",
    "doctor": "Doctor",
    "physiotherapist": "Physiotherapist",
    "caretaker": "Caretaker",
    "lab_technician": "Lab Technician",
    "baby_care_specialist": "Baby Care Specialist",
}

_DEFAULT_CARE_PLAN_TITLE = "Recovery care plan"

# (candidate JSON keys, display label, unit) — covers both snake_case and the frontend's
# camelCase spelling of the nurse-side VitalsIn/VitalsOut fields (app/schemas/appointment.py).
_KNOWN_VITALS: list[tuple[tuple[str, ...], str, str | None]] = [
    (("blood_pressure", "bloodPressure"), "Blood pressure", "mmHg"),
    (("heart_rate", "heartRate"), "Heart rate", "bpm"),
    (("temperature",), "Temperature", "°F"),
    (
        ("oxygen_saturation", "oxygenSaturation", "oxygen_level", "oxygenLevel"),
        "Oxygen saturation",
        "%",
    ),
]


class PatientService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PatientRepository(session)

    # ── Dashboard ─────────────────────────────────────────────────────

    async def get_dashboard(self, user: User) -> PatientDashboardOut:
        profile = await self.repo.get_by_user_id(user.id)

        return PatientDashboardOut(
            upcoming_appointments=await self._get_upcoming_appointments(user.id),
            nearby_providers=await self._get_nearby_providers(user.id),
            care_plan=await self._get_care_plan_progress(user.id),
            health_summary=await self._get_health_summary(user.id),
            emergency_contact=_build_emergency_contact(profile),
        )

    async def _get_upcoming_appointments(
        self, patient_id: uuid.UUID
    ) -> list[AppointmentSummaryOut]:
        rows = await self.repo.list_upcoming_bookings(patient_id)
        return [
            AppointmentSummaryOut(
                id=booking.id,
                service=booking.service_name_snapshot,
                clinician=clinician_name,
                scheduled_start_at=booking.scheduled_start_at,
                scheduled_end_at=booking.scheduled_end_at,
                status=booking.status,
                address=booking.address_snapshot,
            )
            for booking, clinician_name in rows
        ]

    async def _get_nearby_providers(self, patient_id: uuid.UUID) -> list[NearbyProviderOut]:
        address = await self.repo.get_default_address(patient_id)
        if address is None:
            # Patient hasn't added a geocoded Address yet — nothing to search from.
            return []

        point = to_shape(address.location)
        location_wkt = f"POINT({point.x} {point.y})"
        radius_meters = app_settings.DEFAULT_SEARCH_RADIUS_KM * 1000

        rows = await self.repo.find_nearby_professionals(
            location_wkt=location_wkt, radius_meters=radius_meters
        )
        providers = []
        for professional, distance_meters, full_name in rows:
            role = _ROLE_LABELS.get(
                professional.professional_type.value, professional.professional_type.value.title()
            )
            specialty = f"{role} · {professional.years_of_experience} yrs exp."
            providers.append(
                NearbyProviderOut(
                    id=professional.id,
                    name=full_name,
                    role=role,
                    specialty=specialty,
                    distance_km=round(distance_meters / 1000, 1),
                    rating=float(professional.average_rating),
                    availability=_AVAILABILITY_LABELS.get(
                        professional.availability_status, "Unavailable"
                    ),
                )
            )
        return providers

    async def _get_care_plan_progress(self, patient_id: uuid.UUID) -> CarePlanProgressOut | None:
        plan = await self.repo.get_active_care_plan(patient_id)
        if plan is None:
            return None
        completed = await self.repo.count_completed_bookings_for_plan(plan.id)
        return CarePlanProgressOut(
            id=plan.id,
            # CarePlan has no dedicated `title` column — `notes` is the closest existing
            # field; falls back to a generic label when the plan was created without one.
            title=plan.notes or _DEFAULT_CARE_PLAN_TITLE,
            completed=completed,
            total=plan.total_visits,
            next_step=None,
        )

    async def _get_health_summary(self, patient_id: uuid.UUID) -> list[HealthReadingOut]:
        # Cross-domain note: `BookingVisit.vitals_recorded` is a free-form JSON *string*
        # column (see app/models/booking.py), written by the nurse-side visit-checkout flow
        # (app/services/visit_service.py / app/schemas/appointment.py's VitalsIn — at the
        # time this was written that flow was mid-change and not yet persisting vitals at
        # all, so the exact JSON shape it will end up writing is unconfirmed). This parses
        # defensively: known vitals field names (in either snake_case or the frontend's
        # camelCase) get a friendly label + unit, and anything else falls back to a raw
        # label/value pair so nothing is silently dropped once that flow lands.
        raw = await self.repo.get_latest_visit_vitals(patient_id)
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(data, dict):
            return []

        readings: list[HealthReadingOut] = []
        seen_keys: set[str] = set()
        for keys, label, unit in _KNOWN_VITALS:
            for key in keys:
                if key in data and data[key] not in (None, ""):
                    readings.append(HealthReadingOut(label=label, value=str(data[key]), unit=unit))
                    seen_keys.add(key)
                    break

        for key, value in data.items():
            if key in seen_keys or value in (None, ""):
                continue
            if isinstance(value, dict):
                readings.append(
                    HealthReadingOut(
                        label=key, value=str(value.get("value", "")), unit=value.get("unit")
                    )
                )
            else:
                readings.append(HealthReadingOut(label=key, value=str(value), unit=None))
        return readings

    # ── Profile ───────────────────────────────────────────────────────

    async def get_profile(self, user: User) -> PatientProfileOut:
        profile = await self._get_or_create_profile(user)
        return _to_profile_out(user, profile)

    async def update_profile(
        self, user: User, payload: PatientProfileUpdateIn
    ) -> PatientProfileOut:
        profile = await self._get_or_create_profile(user)
        data = payload.model_dump(exclude_unset=True)
        full_name = data.pop("full_name", None)
        if full_name is not None:
            user.full_name = full_name
        for field, value in data.items():
            setattr(profile, field, value)
        await self.session.flush()
        return _to_profile_out(user, profile)

    # ── Settings ──────────────────────────────────────────────────────
    # WebPatientSettings.tsx / MobilePatientSettings.tsx currently only render local
    # (unpersisted) notification checkboxes plus a change-password form (handled by
    # existing auth endpoints) and a static support contact — none of that reads/writes
    # a backend today. The one genuinely persisted "preference" already on the model is
    # PatientProfile.preferred_language, so settings here covers that plus the account
    # identity fields (name/email/phone) also shown on the profile page.

    async def get_settings(self, user: User) -> PatientSettingsOut:
        profile = await self._get_or_create_profile(user)
        return _to_settings_out(user, profile)

    async def update_settings(
        self, user: User, payload: PatientSettingsUpdateIn
    ) -> PatientSettingsOut:
        profile = await self._get_or_create_profile(user)
        data = payload.model_dump(exclude_unset=True)
        if data.get("full_name") is not None:
            user.full_name = data["full_name"]
        if data.get("email") is not None:
            user.email = data["email"]
        if "preferred_language" in data:
            profile.preferred_language = data["preferred_language"]
        await self.session.flush()
        return _to_settings_out(user, profile)

    async def _get_or_create_profile(self, user: User) -> PatientProfile:
        profile = await self.repo.get_by_user_id(user.id)
        if profile is None:
            # Defensive fallback only — AuthService.register always creates one for
            # role=PATIENT. Guards against pre-existing rows created before that changed.
            profile = PatientProfile(user_id=user.id)
            self.session.add(profile)
            await self.session.flush()
        return profile


def _build_emergency_contact(profile: PatientProfile | None) -> EmergencyContactOut | None:
    if profile is None or not profile.emergency_contact_phone:
        return None
    return EmergencyContactOut(
        name=profile.emergency_contact_name or "Emergency contact",
        relationship=profile.emergency_contact_relationship,
        phone=profile.emergency_contact_phone,
    )


def _to_profile_out(user: User, profile: PatientProfile) -> PatientProfileOut:
    return PatientProfileOut(
        public_id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone_number,
        avatar_url=user.avatar_url,
        address_line=profile.address_line,
        city=profile.city,
        state=profile.state,
        known_conditions=profile.known_conditions,
        allergies=profile.allergies,
        current_medications=profile.current_medications,
        emergency_contact_name=profile.emergency_contact_name,
        emergency_contact_phone=profile.emergency_contact_phone,
        emergency_contact_relationship=profile.emergency_contact_relationship,
        preferred_language=profile.preferred_language,
        notes=profile.notes,
        date_of_birth=profile.date_of_birth,
        created_at=profile.created_at,
    )


def _to_settings_out(user: User, profile: PatientProfile) -> PatientSettingsOut:
    return PatientSettingsOut(
        full_name=user.full_name,
        email=user.email,
        phone=user.phone_number,
        preferred_language=profile.preferred_language,
    )
