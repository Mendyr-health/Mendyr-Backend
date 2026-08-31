"""Admin dashboard analytics: registration counts, verification/booking-status breakdowns,
signup trend, and patient location breakdown. Read-only, all counts computed on demand —
fine at this scale, revisit with materialized views if the tables get large.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import BookingStatus, UserRole, VerificationStatus
from app.models.address import Address
from app.models.booking import Booking
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.schemas.admin_analytics import DailySignups, DashboardOverviewOut, LocationBreakdown

DEFAULT_TREND_DAYS = 14
TOP_LOCATIONS_LIMIT = 10


class AdminAnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_overview(
        self,
        *,
        city: str | None = None,
        state: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> DashboardOverviewOut:
        """`city`/`state` scope the patient counts and location breakdown (professionals have
        no city/state on file — see the schema docstring). `date_from`/`date_to` scope the
        signup counts and the signup trend; omitted, the trend defaults to the last 14 days
        and the counts are all-time."""
        patient_filters = [User.role == UserRole.PATIENT]
        professional_filters = [User.role == UserRole.PROFESSIONAL]
        if date_from is not None:
            patient_filters.append(User.created_at >= date_from)
            professional_filters.append(User.created_at >= date_from)
        if date_to is not None:
            # date_to is inclusive of the whole day.
            upper = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)
            patient_filters.append(User.created_at <= upper)
            professional_filters.append(User.created_at <= upper)

        patient_query = select(func.count(User.id)).where(*patient_filters)
        if city or state:
            patient_query = patient_query.where(
                User.id.in_(select(Address.user_id).where(*self._location_filters(city, state)))
            )

        total_patients = (await self.session.execute(patient_query)).scalar_one()
        total_professionals = (
            await self.session.execute(select(func.count(User.id)).where(*professional_filters))
        ).scalar_one()

        professionals_by_status = await self._professionals_by_verification_status()
        total_bookings, bookings_by_status = await self._booking_counts()
        daily_signups = await self._daily_signups(date_from, date_to)
        top_locations = await self._top_locations(city, state)

        return DashboardOverviewOut(
            total_patients=total_patients,
            total_professionals=total_professionals,
            professionals_by_verification_status=professionals_by_status,
            total_bookings=total_bookings,
            bookings_by_status=bookings_by_status,
            daily_signups=daily_signups,
            top_locations=top_locations,
        )

    @staticmethod
    def _location_filters(city: str | None, state: str | None) -> list:
        filters = []
        if city:
            filters.append(func.lower(Address.city) == city.lower())
        if state:
            filters.append(func.lower(Address.state) == state.lower())
        return filters

    async def _professionals_by_verification_status(self) -> dict[str, int]:
        result = await self.session.execute(
            select(
                ProfessionalProfile.verification_status, func.count(ProfessionalProfile.id)
            ).group_by(ProfessionalProfile.verification_status)
        )
        counts = {status.value: 0 for status in VerificationStatus}
        for status, count in result.all():
            counts[status.value] = count
        return counts

    async def _booking_counts(self) -> tuple[int, dict[str, int]]:
        result = await self.session.execute(
            select(Booking.status, func.count(Booking.id)).group_by(Booking.status)
        )
        counts = {status.value: 0 for status in BookingStatus}
        total = 0
        for status, count in result.all():
            counts[status.value] = count
            total += count
        return total, counts

    async def _daily_signups(
        self, date_from: date | None, date_to: date | None
    ) -> list[DailySignups]:
        end = date_to or datetime.now(UTC).date()
        start = date_from or (end - timedelta(days=DEFAULT_TREND_DAYS - 1))

        day_col = func.date(User.created_at).label("signup_date")
        result = await self.session.execute(
            select(day_col, User.role, func.count(User.id))
            .where(
                User.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                User.created_at <= datetime.combine(end, datetime.max.time(), tzinfo=UTC),
                User.role.in_([UserRole.PATIENT, UserRole.PROFESSIONAL]),
            )
            .group_by(day_col, User.role)
        )
        by_day: dict[date, dict[str, int]] = {}
        for signup_date, role, count in result.all():
            bucket = by_day.setdefault(signup_date, {"patients": 0, "professionals": 0})
            bucket["patients" if role == UserRole.PATIENT else "professionals"] += count

        days = []
        cursor = start
        while cursor <= end:
            counts = by_day.get(cursor, {"patients": 0, "professionals": 0})
            days.append(DailySignups(signup_date=cursor, **counts))
            cursor += timedelta(days=1)
        return days

    async def _top_locations(
        self, city: str | None, state: str | None
    ) -> list[LocationBreakdown]:
        stmt = (
            select(Address.city, Address.state, func.count(func.distinct(Address.user_id)))
            .join(User, User.id == Address.user_id)
            .where(User.role == UserRole.PATIENT, *self._location_filters(city, state))
            .group_by(Address.city, Address.state)
            .order_by(func.count(func.distinct(Address.user_id)).desc())
            .limit(TOP_LOCATIONS_LIMIT)
        )
        result = await self.session.execute(stmt)
        return [
            LocationBreakdown(city=row_city, state=row_state, patient_count=count)
            for row_city, row_state, count in result.all()
        ]
