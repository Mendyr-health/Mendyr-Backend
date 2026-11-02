"""Shared helpers for the test-account seed script (`seed_dummy_users.py`): idempotent
get-or-create for users, home addresses and approved professionals."""

from datetime import UTC, datetime, time

from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.core.constants import AvailabilityStatus, ProfessionalType, VerificationStatus
from app.core.security import hash_password
from app.models.address import Address
from app.models.professional import ProfessionalAvailabilitySlot, ProfessionalProfile
from app.models.service import ProfessionalService as ProfessionalServiceOptIn
from app.models.service import Service
from app.models.user import User

# Shared, public password for every seeded test account — never use them for real people.
DEMO_PASSWORD = "Demo@12345"
SERVICE_RADIUS_KM = 15


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
