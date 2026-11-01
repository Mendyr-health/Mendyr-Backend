"""Admin dashboard analytics: registration counts, verification/booking-status breakdowns,
signup trend, and patient location breakdown. Read-only, all counts computed on demand —
fine at this scale, revisit with materialized views if the tables get large.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import BookingStatus, UserRole, VerificationStatus
from app.models.address import Address
from app.models.booking import Booking, BookingStatusHistory
from app.models.professional import ProfessionalProfile
from app.models.review import Review
from app.models.user import User
from app.schemas.admin_analytics import (
    BusinessKpis,
    DailyBookings,
    DailySignups,
    DashboardOverviewOut,
    LocationBreakdown,
)

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
            kpis=await self._kpis(bookings_by_status, professionals_by_status),
        )

    async def _kpis(
        self, bookings_by_status: dict[str, int], professionals_by_status: dict[str, int]
    ) -> BusinessKpis:
        now = datetime.now(UTC)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        gmv, revenue = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(Booking.total_amount), 0),
                    func.coalesce(func.sum(Booking.platform_fee), 0),
                ).where(Booking.status == BookingStatus.COMPLETED)
            )
        ).one()
        bookings_today = (
            await self.session.execute(
                select(func.count(Booking.id)).where(Booking.created_at >= today)
            )
        ).scalar_one()

        filled = sum(
            bookings_by_status.get(s.value, 0)
            for s in (
                BookingStatus.ASSIGNED,
                BookingStatus.CONFIRMED,
                BookingStatus.EN_ROUTE,
                BookingStatus.IN_PROGRESS,
                BookingStatus.COMPLETED,
                BookingStatus.NO_SHOW,
            )
        )
        failed = bookings_by_status.get(BookingStatus.FAILED.value, 0)
        cancelled = bookings_by_status.get(BookingStatus.CANCELLED.value, 0)
        total = sum(bookings_by_status.values())

        # Minutes from the request to its first ASSIGNED, over the last 30 days.
        first_assigned = (
            select(
                BookingStatusHistory.booking_id,
                func.min(BookingStatusHistory.created_at).label("assigned_at"),
            )
            .where(BookingStatusHistory.to_status == BookingStatus.ASSIGNED)
            .group_by(BookingStatusHistory.booking_id)
            .subquery()
        )
        avg_assign = (
            await self.session.execute(
                select(
                    func.avg(
                        func.extract("epoch", first_assigned.c.assigned_at - Booking.created_at)
                    )
                )
                .join(first_assigned, first_assigned.c.booking_id == Booking.id)
                .where(Booking.created_at >= now - timedelta(days=30))
            )
        ).scalar_one()
        avg_rating = (await self.session.execute(select(func.avg(Review.rating)))).scalar_one()

        day = func.date(Booking.created_at)
        rows = await self.session.execute(
            select(day, Booking.status, func.count(Booking.id))
            .where(Booking.created_at >= today - timedelta(days=13))
            .group_by(day, Booking.status)
        )
        per_day: dict[date, dict[str, int]] = {}
        for d, status, n in rows.all():
            bucket = per_day.setdefault(d, {"created": 0, "completed": 0, "cancelled": 0})
            bucket["created"] += n
            if status == BookingStatus.COMPLETED:
                bucket["completed"] += n
            elif status in (BookingStatus.CANCELLED, BookingStatus.FAILED):
                bucket["cancelled"] += n
        days = [(today - timedelta(days=13 - i)).date() for i in range(14)]
        empty = {"created": 0, "completed": 0, "cancelled": 0}

        return BusinessKpis(
            gmv_completed=float(gmv),
            platform_revenue=float(revenue),
            bookings_today=bookings_today,
            active_visits=bookings_by_status.get(BookingStatus.EN_ROUTE.value, 0)
            + bookings_by_status.get(BookingStatus.IN_PROGRESS.value, 0),
            fill_rate_pct=round(100 * filled / (filled + failed + cancelled), 1)
            if filled + failed + cancelled
            else None,
            cancellation_rate_pct=round(100 * cancelled / total, 1) if total else None,
            avg_minutes_to_assign=round(float(avg_assign) / 60, 1) if avg_assign else None,
            pending_verifications=professionals_by_status.get(VerificationStatus.PENDING.value, 0)
            + professionals_by_status.get(VerificationStatus.IN_REVIEW.value, 0),
            average_rating=round(float(avg_rating), 2) if avg_rating else None,
            daily_bookings=[DailyBookings(day=d, **per_day.get(d, empty)) for d in days],
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

    async def _top_locations(self, city: str | None, state: str | None) -> list[LocationBreakdown]:
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
