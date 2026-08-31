"""Professional lookups, including the geospatial nearest-candidate query used by matching."""

import uuid

from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_GeogFromText
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.core.constants import AvailabilityStatus, ProfessionalType, VerificationStatus
from app.models.professional import ProfessionalProfile
from app.models.service import ProfessionalService as ProfessionalServiceOptIn
from app.models.service import Service, ServiceCategory
from app.repositories.base import BaseRepository


class ProfessionalRepository(BaseRepository[ProfessionalProfile]):
    model = ProfessionalProfile

    async def get_by_user_id(self, user_id: uuid.UUID) -> ProfessionalProfile | None:
        result = await self.session.execute(
            select(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

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
        radius_meters: float,
        exclude_ids: set[uuid.UUID] | None = None,
        limit: int = 10,
    ) -> list[tuple[ProfessionalProfile, float]]:
        """Ranked by distance ascending. Candidates must be:
        - APPROVED + currently ONLINE + accepting bookings
        - qualified for the requested service (opted into ProfessionalService)
        - within `radius_meters` of the service location (PostGIS ST_DWithin, uses a GiST index)
        """
        # location_wkt is a plain string ("POINT(lng lat)") — PostGIS has no ST_Distance
        # overload for (geography, varchar), so it must be cast explicitly rather than left
        # for the driver to send as a bare VARCHAR bind param.
        location = ST_GeogFromText(location_wkt)
        distance_col = ST_Distance(ProfessionalProfile.current_location, location).label(
            "distance_meters"
        )

        stmt = (
            select(ProfessionalProfile, distance_col)
            .options(selectinload(ProfessionalProfile.user))
            .join(
                ProfessionalServiceOptIn,
                ProfessionalServiceOptIn.professional_id == ProfessionalProfile.id,
            )
            .where(
                and_(
                    ProfessionalServiceOptIn.service_id == service_id,
                    ProfessionalServiceOptIn.is_active.is_(True),
                    ProfessionalProfile.professional_type == professional_type,
                    ProfessionalProfile.verification_status == VerificationStatus.APPROVED,
                    ProfessionalProfile.availability_status == AvailabilityStatus.ONLINE,
                    ProfessionalProfile.is_accepting_bookings.is_(True),
                    ProfessionalProfile.current_location.is_not(None),
                    ST_DWithin(ProfessionalProfile.current_location, location, radius_meters),
                )
            )
            .order_by(distance_col.asc())
            .limit(limit)
        )
        if exclude_ids:
            stmt = stmt.where(ProfessionalProfile.id.not_in(exclude_ids))

        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
