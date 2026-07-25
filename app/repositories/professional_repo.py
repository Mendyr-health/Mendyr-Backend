"""Professional lookups, including the geospatial nearest-candidate query used by matching."""

import uuid

from geoalchemy2.functions import ST_Distance, ST_DWithin
from sqlalchemy import and_, select

from app.core.constants import AvailabilityStatus, ProfessionalType, VerificationStatus
from app.models.professional import ProfessionalProfile
from app.models.service import ProfessionalService
from app.repositories.base import BaseRepository


class ProfessionalRepository(BaseRepository[ProfessionalProfile]):
    model = ProfessionalProfile

    async def get_by_user_id(self, user_id: uuid.UUID) -> ProfessionalProfile | None:
        result = await self.session.execute(
            select(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id)
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
        distance_col = ST_Distance(ProfessionalProfile.current_location, location_wkt).label(
            "distance_meters"
        )

        stmt = (
            select(ProfessionalProfile, distance_col)
            .join(
                ProfessionalService, ProfessionalService.professional_id == ProfessionalProfile.id
            )
            .where(
                and_(
                    ProfessionalService.service_id == service_id,
                    ProfessionalService.is_active.is_(True),
                    ProfessionalProfile.professional_type == professional_type,
                    ProfessionalProfile.verification_status == VerificationStatus.APPROVED,
                    ProfessionalProfile.availability_status == AvailabilityStatus.ONLINE,
                    ProfessionalProfile.is_accepting_bookings.is_(True),
                    ProfessionalProfile.current_location.is_not(None),
                    ST_DWithin(ProfessionalProfile.current_location, location_wkt, radius_meters),
                )
            )
            .order_by(distance_col.asc())
            .limit(limit)
        )
        if exclude_ids:
            stmt = stmt.where(ProfessionalProfile.id.not_in(exclude_ids))

        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]
