"""Seed a small, realistic demo dataset for presenting the prototype: one test patient with an
address, two nurses and a physiotherapist (onboarded, approved, accepting requests, opted into
their profession's services), all within travel range of the patient — so a booking made as
the patient shows up straight away in the professionals' request lists.

Run `python -m scripts.seed` first — this assumes the service catalogue already exists.

Usage:
    uv run python -m scripts.seed_demo_data

Idempotent — matched by email, safe to re-run (e.g. to re-seed after `delete_demo_data.py`).
Prints the login credentials for every account it creates or finds.
"""

import asyncio
from datetime import UTC, datetime, time

from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.core.constants import (
    AvailabilityStatus,
    Gender,
    ProfessionalType,
    UserRole,
    VerificationStatus,
)
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.address import Address
from app.models.professional import ProfessionalAvailabilitySlot, ProfessionalProfile
from app.models.service import ProfessionalService as ProfessionalServiceOptIn
from app.models.service import Service
from app.models.user import User
from app.services.wallet_service import WalletService

DEMO_PASSWORD = "Demo@12345"

# MG Road, Bangalore — patient's address. The professionals are seeded a few km away in
# different directions so `GET /professionals/nearby` returns them at different distances.
PATIENT_LOCATION = (12.9716, 77.5946)  # (lat, lng)
SERVICE_RADIUS_KM = 15
WEEKDAY_DAYTIME = [(day, time(7, 0), time(21, 0)) for day in range(6)]  # Mon-Sat 7am-9pm

# (email prefix, name, profession, lat, lng, weekly timings — None means "any time")
PROFESSIONALS = [
    ("nurse1", "Priya Sharma", ProfessionalType.NURSE, 12.9550, 77.6100, WEEKDAY_DAYTIME),
    ("nurse2", "Kavita Reddy", ProfessionalType.NURSE, 13.0100, 77.5600, None),
    ("physio1", "Rohan Mehta", ProfessionalType.PHYSIOTHERAPIST, 12.9352, 77.6245, None),
]

PATIENT = {
    "email": "asha.patel.demo@mendyr.app",
    "full_name": "Asha Patel",
    "phone_number": "+919800000000",
    "gender": Gender.FEMALE,
    "date_of_birth": datetime(1958, 3, 22, tzinfo=UTC),
}


def _point(lat: float, lng: float) -> WKTElement:
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


async def _get_or_create_user(
    session, *, email, full_name, phone_number, role, gender, date_of_birth
) -> User:
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        # Backfill only what's actually missing, so re-running repairs accounts seeded before
        # this field existed (they'd otherwise be bounced into onboarding on every login)
        # without overwriting anything a demo run has since edited through the app.
        if existing.date_of_birth is None:
            existing.date_of_birth = date_of_birth
        return existing

    user = User(
        email=email,
        hashed_password=hash_password(DEMO_PASSWORD),
        full_name=full_name,
        phone_number=phone_number,
        role=role,
        gender=gender,
        # Set so these accounts read as fully onboarded: the app sends anyone missing a date
        # of birth through the "tell us about yourself" step on login, which would otherwise
        # be the first thing a demo hits.
        date_of_birth=date_of_birth,
        phone_verified=True,
        email_verified=True,
        referral_code=email.split("@")[0].upper()[:12],
        last_login_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    return user


async def _ensure_address(
    session, user: User, *, line1: str, city: str, state: str, pincode: str, lat: float, lng: float
) -> None:
    """Give `user` a default home address at (lat, lng), unless they already have one."""
    existing = (
        await session.execute(select(Address).where(Address.user_id == user.id).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        Address(
            user_id=user.id,
            label="home",
            line1=line1,
            city=city,
            state=state,
            pincode=pincode,
            country="IN",
            location=_point(lat, lng),
            is_default=True,
            contact_name=user.full_name,
            contact_phone=user.phone_number,
        )
    )


async def _ensure_professional(
    session,
    user: User,
    *,
    kind: ProfessionalType,
    years_of_experience: int,
    languages: list[str],
    lat: float,
    lng: float,
    timings: list[tuple[int, time, time]] | None,
    services: list[Service],
) -> ProfessionalProfile:
    """Make `user` an approved, online professional at (lat, lng), opted into every catalogue
    service for their profession. An existing profile is kept as-is (a demo run may have
    edited it through the app); only missing service opt-ins are added."""
    profile = (
        await session.execute(
            select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = ProfessionalProfile(
            user_id=user.id,
            professional_type=kind,
            years_of_experience=years_of_experience,
            bio=f"{user.full_name} is a registered {kind.value.replace('_', ' ')} with "
            f"{years_of_experience} years of home-care experience.",
            languages_spoken=languages,
            verification_status=VerificationStatus.APPROVED,
            verified_at=datetime.now(UTC),
            availability_status=AvailabilityStatus.ONLINE,
            current_location=_point(lat, lng),
            location_updated_at=datetime.now(UTC),
            base_service_radius_km=SERVICE_RADIUS_KM,
            is_accepting_bookings=True,
        )
        session.add(profile)
        await session.flush()
        for day, start, end in timings or []:
            session.add(
                ProfessionalAvailabilitySlot(
                    professional_id=profile.id,
                    day_of_week=day,
                    start_time=start,
                    end_time=end,
                )
            )

    for service in [s for s in services if s.required_professional_type == kind]:
        optin = (
            await session.execute(
                select(ProfessionalServiceOptIn).where(
                    ProfessionalServiceOptIn.professional_id == profile.id,
                    ProfessionalServiceOptIn.service_id == service.id,
                )
            )
        ).scalar_one_or_none()
        if optin is None:
            # No price_override: bookings are priced from the catalogue for now.
            session.add(
                ProfessionalServiceOptIn(
                    professional_id=profile.id, service_id=service.id, is_active=True
                )
            )
    return profile


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        # ── Patient ──────────────────────────────────────────────────────
        patient = await _get_or_create_user(
            session,
            email=PATIENT["email"],
            full_name=PATIENT["full_name"],
            phone_number=PATIENT["phone_number"],
            role=UserRole.PATIENT,
            gender=PATIENT["gender"],
            date_of_birth=PATIENT["date_of_birth"],
        )
        await WalletService(session).get_or_create_wallet(patient.id)

        lat, lng = PATIENT_LOCATION
        await _ensure_address(
            session,
            patient,
            line1="221B, MG Road",
            city="Bengaluru",
            state="Karnataka",
            pincode="560001",
            lat=lat,
            lng=lng,
        )

        # ── Professionals ────────────────────────────────────────────────
        services = (await session.execute(select(Service))).scalars().all()
        if not services:
            print(
                "WARNING: no services found — run `uv run python -m scripts.seed` first, "
                "then re-run this script to opt the professionals into services."
            )

        credentials = [(PATIENT["email"], DEMO_PASSWORD, "patient")]

        for idx, (prefix, name, kind, lat, lng, timings) in enumerate(PROFESSIONALS, start=1):
            email = f"{prefix}.demo@mendyr.app"
            pro_user = await _get_or_create_user(
                session,
                email=email,
                full_name=name,
                phone_number=f"+91980000{idx:04d}",
                role=UserRole.PROFESSIONAL,
                gender=Gender.MALE if kind == ProfessionalType.PHYSIOTHERAPIST else Gender.FEMALE,
                # Professionals must be adults; a fixed date keeps the seed deterministic.
                date_of_birth=datetime(1990, 6, 15, tzinfo=UTC),
            )
            await WalletService(session).get_or_create_wallet(pro_user.id)

            await _ensure_professional(
                session,
                pro_user,
                kind=kind,
                years_of_experience=3 + idx,
                languages=["English", "Hindi", "Kannada"],
                lat=lat,
                lng=lng,
                timings=timings,
                services=services,
            )

            credentials.append((email, DEMO_PASSWORD, kind.value))

        await session.commit()

    print("\nDemo accounts ready:\n")
    for email, password, role in credentials:
        print(f"  [{role:15}] {email}  /  {password}")
    print(
        "\nThe professionals are approved, accepting requests within 15 km, and opted into "
        "their profession's services. The patient has a default address near MG Road, "
        "Bengaluru — a booking made there shows up in their request lists."
    )


if __name__ == "__main__":
    asyncio.run(seed())
