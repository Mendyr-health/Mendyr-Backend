"""Professional-side visit tracking: en-route, geofenced check-in, check-out."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.permissions import require_professional
from app.db.session import get_db
from app.models.user import User
from app.repositories.professional_repo import ProfessionalRepository
from app.schemas.booking import BookingRead, VisitCheckInIn, VisitCheckOutIn
from app.services.visit_service import VisitService

router = APIRouter(prefix="/bookings", tags=["visits"])


async def _get_professional_id(current_user: User, db: AsyncSession) -> uuid.UUID:
    profile = await ProfessionalRepository(db).get_by_user_id(current_user.id)
    if profile is None:
        raise NotFoundError("Complete professional onboarding first.")
    return profile.id


@router.post("/{booking_id}/en-route", response_model=BookingRead)
async def mark_en_route(
    booking_id: uuid.UUID,
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    professional_id = await _get_professional_id(current_user, db)
    return await VisitService(db).mark_en_route(booking_id, professional_id)


@router.post("/{booking_id}/check-in", response_model=BookingRead)
async def check_in(
    booking_id: uuid.UUID,
    payload: VisitCheckInIn,
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    professional_id = await _get_professional_id(current_user, db)
    return await VisitService(db).check_in(booking_id, professional_id, payload)


@router.post("/{booking_id}/check-out", response_model=BookingRead)
async def check_out(
    booking_id: uuid.UUID,
    payload: VisitCheckOutIn,
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    professional_id = await _get_professional_id(current_user, db)
    return await VisitService(db).check_out(booking_id, professional_id, payload)
