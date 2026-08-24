"""Patient profile lookups (admin search/list) plus the patient-facing dashboard queries:
upcoming bookings, care plan progress, default address and a generic nearby-professionals
browse list (distinct from `ProfessionalRepository.find_nearby_candidates`, which is scoped
to one service + one professional type for booking dispatch — this one powers the patient
dashboard's unscoped "nearby care providers" section)."""

import uuid

from geoalchemy2.functions import ST_Distance, ST_DWithin
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.constants import AvailabilityStatus, BookingStatus, VerificationStatus
from app.models.address import Address
from app.models.booking import Booking, BookingVisit, CarePlan
from app.models.patient import PatientProfile
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.repositories.base import BaseRepository


class PatientRepository(BaseRepository[PatientProfile]):
    model = PatientProfile

    async def get_by_user_id(self, user_id: uuid.UUID) -> PatientProfile | None:
        result = await self.session.execute(
            select(PatientProfile).where(PatientProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def search(
        self, *, q: str | None, limit: int, offset: int
    ) -> tuple[list[PatientProfile], int]:
        stmt = select(PatientProfile).join(User, PatientProfile.user_id == User.id)
        count_stmt = select(func.count(PatientProfile.id)).join(
            User, PatientProfile.user_id == User.id
        )

        if q:
            like = f"%{q}%"
            search_filter = or_(
                User.full_name.ilike(like), User.email.ilike(like), User.phone_number.ilike(like)
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.options(selectinload(PatientProfile.user))
            .order_by(PatientProfile.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    # ── Patient-facing dashboard queries ────────────────────────────────

    async def get_default_address(self, user_id: uuid.UUID) -> Address | None:
        result = await self.session.execute(
            select(Address).where(Address.user_id == user_id, Address.is_default.is_(True))
        )
        address = result.scalar_one_or_none()
        if address is not None:
            return address
        # No address explicitly marked default yet — fall back to the earliest one added.
        result = await self.session.execute(
            select(Address)
            .where(Address.user_id == user_id)
            .order_by(Address.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_upcoming_bookings(
        self, patient_id: uuid.UUID, *, limit: int = 5
    ) -> list[tuple[Booking, str | None]]:
        """Bookings not yet completed/cancelled, soonest first, with the assigned
        professional's display name (None until a professional is matched)."""
        stmt = (
            select(Booking, User.full_name)
            .outerjoin(ProfessionalProfile, ProfessionalProfile.id == Booking.professional_id)
            .outerjoin(User, User.id == ProfessionalProfile.user_id)
            .where(
                Booking.patient_id == patient_id,
                Booking.status.not_in([BookingStatus.COMPLETED, BookingStatus.CANCELLED]),
            )
            .order_by(Booking.scheduled_start_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def get_active_care_plan(self, patient_id: uuid.UUID) -> CarePlan | None:
        result = await self.session.execute(
            select(CarePlan)
            .where(CarePlan.patient_id == patient_id, CarePlan.is_active.is_(True))
            .order_by(CarePlan.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_completed_bookings_for_plan(self, care_plan_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Booking)
            .where(Booking.care_plan_id == care_plan_id, Booking.status == BookingStatus.COMPLETED)
        )
        return int(result.scalar_one())

    async def get_latest_visit_vitals(self, patient_id: uuid.UUID) -> str | None:
        """Most recent recorded vitals JSON string across the patient's completed visits."""
        stmt = (
            select(BookingVisit.vitals_recorded)
            .join(Booking, Booking.id == BookingVisit.booking_id)
            .where(Booking.patient_id == patient_id, BookingVisit.vitals_recorded.is_not(None))
            .order_by(BookingVisit.checked_out_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_nearby_professionals(
        self, *, location_wkt: str, radius_meters: float, limit: int = 6
    ) -> list[tuple[ProfessionalProfile, float, str]]:
        """Ranked by distance ascending. Same APPROVED + ONLINE-ish + accepting-bookings
        filters as the booking-dispatch geo query, but not scoped to one service/type."""
        distance_col = ST_Distance(ProfessionalProfile.current_location, location_wkt).label(
            "distance_meters"
        )
        stmt = (
            select(ProfessionalProfile, distance_col, User.full_name)
            .join(User, User.id == ProfessionalProfile.user_id)
            .where(
                and_(
                    ProfessionalProfile.verification_status == VerificationStatus.APPROVED,
                    ProfessionalProfile.availability_status.in_(
                        [AvailabilityStatus.ONLINE, AvailabilityStatus.ON_VISIT]
                    ),
                    ProfessionalProfile.is_accepting_bookings.is_(True),
                    ProfessionalProfile.current_location.is_not(None),
                    ST_DWithin(ProfessionalProfile.current_location, location_wkt, radius_meters),
                )
            )
            .order_by(distance_col.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]
