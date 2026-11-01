import uuid
from datetime import datetime, timedelta

from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_GeogFromText
from geoalchemy2.shape import to_shape
from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import aliased

from app.core.constants import BookingStatus, Gender
from app.models.address import Address
from app.models.booking import Booking, BookingStatusHistory, BookingVisit
from app.models.professional import ProfessionalProfile
from app.models.review import Review
from app.models.service import ProfessionalService as ProfessionalServiceOptIn
from app.models.user import User
from app.repositories.base import BaseRepository
from app.repositories.professional_repo import available_at, utc_param

# Row shapes the presenters in `booking_service` consume — one query per list, not one per row.
PatientBookingRow = tuple[Booking, ProfessionalProfile | None, User | None, BookingVisit | None]
ProfessionalBookingRow = tuple[Booking, User, Address | None, BookingVisit | None]
OpenRequestRow = tuple[Booking, Address | None, float]

# A professional holding a booking in one of these is busy for its time window.
COMMITTED_STATUSES = (
    BookingStatus.ASSIGNED,
    BookingStatus.CONFIRMED,
    BookingStatus.EN_ROUTE,
    BookingStatus.IN_PROGRESS,
)


def busy_during(
    professional_id: uuid.UUID, booking: type[Booking] | Booking, buffer: timedelta
) -> object:
    """SQL condition: the professional already has a committed visit overlapping `booking`'s
    window, padded by `buffer` on both sides for travel between homes."""
    other = aliased(Booking)
    return exists().where(
        other.professional_id == professional_id,
        other.status.in_(COMMITTED_STATUSES),
        other.id != booking.id,
        other.scheduled_start_at < booking.scheduled_end_at + buffer,
        other.scheduled_end_at + buffer > booking.scheduled_start_at,
    )


class BookingRepository(BaseRepository[Booking]):
    model = Booking

    async def get_by_code(self, booking_code: str) -> Booking | None:
        result = await self.session.execute(
            select(Booking).where(Booking.booking_code == booking_code)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, booking_id: uuid.UUID) -> Booking | None:
        """Row-locked read: concurrent accepts of the same request serialize here, so the
        second one sees the first's ASSIGNED status instead of double-booking."""
        result = await self.session.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_for_patient(
        self, patient_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[tuple[Booking, str | None]]:
        """Newest-scheduled first, each paired with the assigned professional's name."""
        result = await self.session.execute(
            select(Booking, User.full_name)
            .outerjoin(ProfessionalProfile, ProfessionalProfile.id == Booking.professional_id)
            .outerjoin(User, User.id == ProfessionalProfile.user_id)
            .where(Booking.patient_id == patient_id)
            .order_by(Booking.scheduled_start_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_patient_row(self, booking_id: uuid.UUID) -> PatientBookingRow | None:
        professional_user = aliased(User)
        result = await self.session.execute(
            select(Booking, ProfessionalProfile, professional_user, BookingVisit)
            .outerjoin(ProfessionalProfile, ProfessionalProfile.id == Booking.professional_id)
            .outerjoin(professional_user, professional_user.id == ProfessionalProfile.user_id)
            .outerjoin(BookingVisit, BookingVisit.booking_id == Booking.id)
            .where(Booking.id == booking_id)
        )
        row = result.one_or_none()
        return (row[0], row[1], row[2], row[3]) if row else None

    async def list_status_history(self, booking_id: uuid.UUID) -> list[BookingStatusHistory]:
        result = await self.session.execute(
            select(BookingStatusHistory)
            .where(BookingStatusHistory.booking_id == booking_id)
            .order_by(BookingStatusHistory.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_stale_searching(self, *, now: datetime, limit: int = 200) -> list[Booking]:
        """Requests nobody accepted before their start time — they can't happen any more."""
        result = await self.session.execute(
            select(Booking)
            .where(Booking.status == BookingStatus.SEARCHING, Booking.scheduled_start_at < now)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_review_rating(self, booking_id: uuid.UUID) -> int | None:
        result = await self.session.execute(
            select(Review.rating).where(Review.booking_id == booking_id)
        )
        return result.scalar_one_or_none()

    def _professional_rows_query(self, professional_id: uuid.UUID) -> Select:
        return (
            select(Booking, User, Address, BookingVisit)
            .join(User, User.id == Booking.patient_id)
            .outerjoin(Address, Address.id == Booking.address_id)
            .outerjoin(BookingVisit, BookingVisit.booking_id == Booking.id)
            .where(Booking.professional_id == professional_id)
        )

    async def list_for_professional(
        self, professional_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[ProfessionalBookingRow]:
        result = await self.session.execute(
            self._professional_rows_query(professional_id)
            .order_by(Booking.scheduled_start_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def get_professional_row(
        self, booking_id: uuid.UUID, professional_id: uuid.UUID
    ) -> ProfessionalBookingRow | None:
        result = await self.session.execute(
            self._professional_rows_query(professional_id).where(Booking.id == booking_id)
        )
        row = result.one_or_none()
        return (row[0], row[1], row[2], row[3]) if row else None

    def open_requests_query(
        self,
        professional: ProfessionalProfile,
        *,
        now: datetime,
        gender: Gender,
        travel_buffer: timedelta,
    ) -> Select:
        """Bookings still looking for a professional that `professional` may accept — the
        mirror image of `ProfessionalRepository.find_nearby_candidates`:
        - still SEARCHING and not yet started
        - for their profession, and a service they've opted into
        - inside their own travel radius
        - starting inside their weekly timings (see `available_at`)
        - not clashing with a visit they've already taken (plus `travel_buffer` either side)
        - no gender preference, or one matching theirs
        Whether the professional is approved/accepting is checked by the caller, once,
        rather than per row. Requires `professional.current_location` to be set.
        """
        preferred_gender = Booking.extended_attributes["preferred_gender"].astext
        location = ST_GeogFromText(to_shape(professional.current_location).wkt)
        opted_in = exists().where(
            ProfessionalServiceOptIn.professional_id == professional.id,
            ProfessionalServiceOptIn.service_id == Booking.service_id,
            ProfessionalServiceOptIn.is_active.is_(True),
        )
        return (
            select(
                Booking,
                Address,
                ST_Distance(Booking.service_location, location).label("distance_meters"),
            )
            .outerjoin(Address, Address.id == Booking.address_id)
            .where(
                Booking.status == BookingStatus.SEARCHING,
                Booking.scheduled_start_at > utc_param("now", now),
                Booking.required_professional_type == professional.professional_type,
                opted_in,
                ST_DWithin(
                    Booking.service_location,
                    location,
                    float(professional.base_service_radius_km) * 1000,
                ),
                available_at(professional.id, Booking.scheduled_start_at),
                ~busy_during(professional.id, Booking, travel_buffer),
                or_(preferred_gender.is_(None), preferred_gender == gender.value),
            )
        )

    async def list_open_requests(
        self,
        professional: ProfessionalProfile,
        *,
        now: datetime,
        gender: Gender,
        travel_buffer: timedelta,
        limit: int = 50,
    ) -> list[OpenRequestRow]:
        result = await self.session.execute(
            self.open_requests_query(
                professional, now=now, gender=gender, travel_buffer=travel_buffer
            )
            .order_by(Booking.scheduled_start_at.asc())
            .limit(limit)
        )
        return [(row[0], row[1], float(row[2])) for row in result.all()]

    async def is_open_request_for(
        self,
        booking_id: uuid.UUID,
        professional: ProfessionalProfile,
        *,
        now: datetime,
        gender: Gender,
        travel_buffer: timedelta,
    ) -> bool:
        result = await self.session.execute(
            self.open_requests_query(
                professional, now=now, gender=gender, travel_buffer=travel_buffer
            ).where(Booking.id == booking_id)
        )
        return result.first() is not None
