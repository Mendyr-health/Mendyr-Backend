"""Professional lookups, including the geospatial nearest-candidate query used by matching."""

import uuid

from geoalchemy2.functions import ST_Distance, ST_DWithin
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.constants import AvailabilityStatus, ProfessionalType, VerificationStatus
from app.models.professional import ProfessionalProfile
from app.models.service import ProfessionalService
from app.models.user import User
from app.repositories.base import BaseRepository


class ProfessionalRepository(BaseRepository[ProfessionalProfile]):
    model = ProfessionalProfile

    async def get_by_user_id(self, user_id: uuid.UUID) -> ProfessionalProfile | None:
        result = await self.session.execute(
            select(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_with_relations(self, professional_id: uuid.UUID) -> ProfessionalProfile | None:
        """Loaded with `user` and `documents` — used by the admin console, which always needs
        both to render a nurse row/detail view."""
        result = await self.session.execute(
            select(ProfessionalProfile)
            .where(ProfessionalProfile.id == professional_id)
            .options(
                selectinload(ProfessionalProfile.user),
                selectinload(ProfessionalProfile.documents),
            )
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        q: str | None,
        verification_status: VerificationStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ProfessionalProfile], int]:
        stmt = select(ProfessionalProfile).join(User, ProfessionalProfile.user_id == User.id)
        count_stmt = select(func.count(ProfessionalProfile.id)).join(
            User, ProfessionalProfile.user_id == User.id
        )

        if verification_status is not None:
            stmt = stmt.where(ProfessionalProfile.verification_status == verification_status)
            count_stmt = count_stmt.where(
                ProfessionalProfile.verification_status == verification_status
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
            stmt.options(
                selectinload(ProfessionalProfile.user), selectinload(ProfessionalProfile.documents)
            )
            .order_by(ProfessionalProfile.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def count_pending(self) -> int:
        result = await self.session.execute(
            select(func.count(ProfessionalProfile.id)).where(
                ProfessionalProfile.verification_status.in_(
                    [VerificationStatus.PENDING, VerificationStatus.IN_REVIEW]
                )
            )
        )
        return result.scalar_one()

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count(ProfessionalProfile.id)))
        return result.scalar_one()

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
