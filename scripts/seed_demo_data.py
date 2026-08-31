"""Seed a small, realistic demo dataset for presenting the prototype: one test patient, two
test nurses (onboarded, KYC-approved, online, with priced services), and an address near each
other so the "nearby available nurses" search has something real to show.

Run `python -m scripts.seed` first — this assumes the service catalogue already exists.

Usage:
    uv run python -m scripts.seed_demo_data

Idempotent — matched by email, safe to re-run (e.g. to re-seed after `delete_demo_data.py`).
Prints the login credentials for every account it creates or finds.
"""

import asyncio
from datetime import UTC, datetime

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
from app.models.professional import ProfessionalProfile
from app.models.service import ProfessionalService as ProfessionalServiceOptIn
from app.models.service import Service
from app.models.user import User
from app.services.wallet_service import WalletService

DEMO_PASSWORD = "Demo@12345"

# MG Road, Bangalore — patient's address. The two nurses are seeded a few km away in different
# directions so `GET /professionals/nearby` returns them at different distances.
PATIENT_LOCATION = (12.9716, 77.5946)  # (lat, lng)
NURSE_LOCATIONS = [
    ("Priya Sharma", 12.9550, 77.6100),  # ~2.5km away
    ("Kavita Reddy", 13.0100, 77.5600),  # ~8km away
]

PATIENT = {
    "email": "asha.patel.demo@mendyr.app",
    "full_name": "Asha Patel",
    "phone_number": "+919800000000",
    "gender": Gender.FEMALE,
}


def _point(lat: float, lng: float) -> WKTElement:
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


async def _get_or_create_user(session, *, email, full_name, phone_number, role, gender) -> User:
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(
        email=email,
        hashed_password=hash_password(DEMO_PASSWORD),
        full_name=full_name,
        phone_number=phone_number,
        role=role,
        gender=gender,
        phone_verified=True,
        email_verified=True,
        referral_code=email.split("@")[0].upper()[:12],
        last_login_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    return user


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
        )
        await WalletService(session).get_or_create_wallet(patient.id)

        existing_address = (
            await session.execute(select(Address).where(Address.user_id == patient.id))
        ).scalar_one_or_none()
        if existing_address is None:
            lat, lng = PATIENT_LOCATION
            session.add(
                Address(
                    user_id=patient.id,
                    label="home",
                    line1="221B, MG Road",
                    city="Bengaluru",
                    state="Karnataka",
                    pincode="560001",
                    country="IN",
                    location=_point(lat, lng),
                    is_default=True,
                    contact_name=patient.full_name,
                    contact_phone=patient.phone_number,
                )
            )

        # ── Nurses ───────────────────────────────────────────────────────
        services = (await session.execute(select(Service))).scalars().all()
        nurse_services = [
            s for s in services if s.required_professional_type == ProfessionalType.NURSE
        ]
        if not services:
            print(
                "WARNING: no services found — run `uv run python -m scripts.seed` first, "
                "then re-run this script to price the nurses' services."
            )

        credentials = [(PATIENT["email"], DEMO_PASSWORD, "patient")]

        for idx, (name, lat, lng) in enumerate(NURSE_LOCATIONS, start=1):
            email = f"nurse{idx}.demo@mendyr.app"
            nurse_user = await _get_or_create_user(
                session,
                email=email,
                full_name=name,
                phone_number=f"+91980000{idx:04d}",
                role=UserRole.PROFESSIONAL,
                gender=Gender.FEMALE,
            )
            await WalletService(session).get_or_create_wallet(nurse_user.id)

            profile = (
                await session.execute(
                    select(ProfessionalProfile).where(ProfessionalProfile.user_id == nurse_user.id)
                )
            ).scalar_one_or_none()
            if profile is None:
                profile = ProfessionalProfile(
                    user_id=nurse_user.id,
                    professional_type=ProfessionalType.NURSE,
                    years_of_experience=3 + idx,
                    bio=f"{name} is a registered nurse with {3 + idx} years of home-care "
                    "experience.",
                    verification_status=VerificationStatus.APPROVED,
                    verified_at=datetime.now(UTC),
                    availability_status=AvailabilityStatus.ONLINE,
                    current_location=_point(lat, lng),
                    location_updated_at=datetime.now(UTC),
                    is_accepting_bookings=True,
                )
                session.add(profile)
                await session.flush()

            for service in nurse_services:
                optin = (
                    await session.execute(
                        select(ProfessionalServiceOptIn).where(
                            ProfessionalServiceOptIn.professional_id == profile.id,
                            ProfessionalServiceOptIn.service_id == service.id,
                        )
                    )
                ).scalar_one_or_none()
                if optin is None:
                    # Second nurse charges a bit above catalogue rate, to show price_override.
                    override = float(service.base_price) * 1.15 if idx == 2 else None
                    session.add(
                        ProfessionalServiceOptIn(
                            professional_id=profile.id,
                            service_id=service.id,
                            price_override=override,
                            is_active=True,
                        )
                    )

            credentials.append((email, DEMO_PASSWORD, "nurse"))

        await session.commit()

    print("\nDemo accounts ready:\n")
    for email, password, role in credentials:
        print(f"  [{role:8}] {email}  /  {password}")
    print(
        "\nBoth nurses are ONLINE, KYC-approved, and opted into every nursing service in the "
        "catalogue. The patient has a default address near MG Road, Bengaluru — "
        "GET /api/v1/professionals/nearby with that address_id should return both."
    )


if __name__ == "__main__":
    asyncio.run(seed())
