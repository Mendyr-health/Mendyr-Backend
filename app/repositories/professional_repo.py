"""Professional lookups, including the geospatial "who can serve this address" query."""

import uuid
from datetime import datetime

from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_GeogFromText
from sqlalchemy import (
    DateTime,
    Time,
    and_,
    bindparam,
    cast,
    exists,
    extract,
    func,
    or_,
    select,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.core.constants import ProfessionalType, VerificationStatus
from app.models.professional import ProfessionalAvailabilitySlot, ProfessionalProfile
from app.models.service import ProfessionalService as ProfessionalServiceOptIn
from app.models.service import Service, ServiceCategory
from app.repositories.base import BaseRepository


def available_at(
    professional_id: ColumnElement[uuid.UUID] | uuid.UUID,
    starts_at: ColumnElement[datetime],
) -> ColumnElement[bool]:
    """SQL condition: `starts_at` falls inside one of the professional's weekly timings.

    Timings are wall-clock times in MARKET_TIMEZONE, so the (UTC) start is converted first.
    Only the start has to fit — a 12-hour nursing shift would otherwise never match a typical
    evening slot. A professional who hasn't set any timings counts as available any time,
    so a new signup sees requests before they've visited the timings screen.
    """
    slot = ProfessionalAvailabilitySlot
    local_start = func.timezone(settings.MARKET_TIMEZONE, starts_at)
    owns_slot = and_(slot.professional_id == professional_id, slot.is_active.is_(True))
    return or_(
        ~exists().where(owns_slot),
        exists().where(
            owns_slot,
            slot.day_of_week == extract("isodow", local_start) - 1,  # isodow: Monday = 1
            slot.start_time <= cast(local_start, Time),
            slot.end_time > cast(local_start, Time),
        ),
    )


def utc_param(name: str, value: datetime) -> ColumnElement[datetime]:
    """A timestamptz bind parameter. The explicit cast matters: Postgres can't otherwise tell
    which `timezone(text, ...)` overload a bare parameter is meant for."""
    return cast(bindparam(name, value), DateTime(timezone=True))


class ProfessionalRepository(BaseRepository[ProfessionalProfile]):
    model = ProfessionalProfile

    async def get_by_user_id(self, user_id: uuid.UUID) -> ProfessionalProfile | None:
        result = await self.session.execute(
            select(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_availability_slots(
        self, professional_id: uuid.UUID
    ) -> list[ProfessionalAvailabilitySlot]:
        result = await self.session.execute(
            select(ProfessionalAvailabilitySlot)
            .where(
                ProfessionalAvailabilitySlot.professional_id == professional_id,
                ProfessionalAvailabilitySlot.is_active.is_(True),
            )
            .order_by(
                ProfessionalAvailabilitySlot.day_of_week, ProfessionalAvailabilitySlot.start_time
            )
        )
        return list(result.scalars().all())

    async def list_catalogue_with_pricing(
        self, professional_id: uuid.UUID, professional_type: ProfessionalType
    ) -> list[tuple[Service, ServiceCategory, ProfessionalServiceOptIn | None]]:
        """Every active catalogue service this professional's type qualifies for, alongside
        their own opt-in row if one exists (None means they haven't opted in yet)."""
        stmt = (
            select(Service, ServiceCategory, ProfessionalServiceOptIn)
            .join(ServiceCategory, ServiceCategory.id == Service.category_id)
            .outerjoin(
                ProfessionalServiceOptIn,
                and_(
                    ProfessionalServiceOptIn.service_id == Service.id,
                    ProfessionalServiceOptIn.professional_id == professional_id,
                ),
            )
            .where(
                Service.required_professional_type == professional_type,
                Service.is_active.is_(True),
            )
            .order_by(ServiceCategory.display_order, Service.display_order)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def get_service_optin(
        self, professional_id: uuid.UUID, service_id: uuid.UUID
    ) -> ProfessionalServiceOptIn | None:
        result = await self.session.execute(
            select(ProfessionalServiceOptIn).where(
                ProfessionalServiceOptIn.professional_id == professional_id,
                ProfessionalServiceOptIn.service_id == service_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_nearby_candidates(
        self,
        *,
        service_id: uuid.UUID,
        professional_type: ProfessionalType,
        location_wkt: str,
        at: datetime | None = None,
        limit: int = 20,
    ) -> list[tuple[ProfessionalProfile, float]]:
        """Professionals who could take a booking for `service_id` at `location`, nearest
        first. The mirror image of `BookingRepository.open_requests_query` — keep the two in
        step. Candidates must be:
        - APPROVED and accepting bookings
        - qualified for the service (opted into it)
        - close enough: the location is inside their own travel radius
        - free then, when `at` is given (see `available_at`)
        """
        # location_wkt is a plain string ("POINT(lng lat)") — PostGIS has no ST_Distance
        # overload for (geography, varchar), so it must be cast explicitly rather than left
        # for the driver to send as a bare VARCHAR bind param.
        location = ST_GeogFromText(location_wkt)
        distance_col = ST_Distance(ProfessionalProfile.current_location, location).label(
            "distance_meters"
        )

        conditions = [
            ProfessionalServiceOptIn.service_id == service_id,
            ProfessionalServiceOptIn.is_active.is_(True),
            ProfessionalProfile.professional_type == professional_type,
            ProfessionalProfile.verification_status == VerificationStatus.APPROVED,
            ProfessionalProfile.is_accepting_bookings.is_(True),
            ProfessionalProfile.current_location.is_not(None),
            ST_DWithin(
                ProfessionalProfile.current_location,
                location,
                ProfessionalProfile.base_service_radius_km * 1000,
            ),
        ]
        if at is not None:
            conditions.append(available_at(ProfessionalProfile.id, utc_param("at", at)))

        stmt = (
            select(ProfessionalProfile, distance_col)
            .options(selectinload(ProfessionalProfile.user))
            .join(
                ProfessionalServiceOptIn,
                ProfessionalServiceOptIn.professional_id == ProfessionalProfile.id,
            )
            .where(and_(*conditions))
            .order_by(distance_col.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
