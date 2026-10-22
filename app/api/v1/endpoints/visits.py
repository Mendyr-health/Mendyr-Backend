"""Professional-side visit progress: en-route (optional), check-in to start the visit,
check-out to complete it."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_professional
from app.db.session import get_db
from app.models.professional import ProfessionalProfile
from app.schemas.booking import ProfessionalBookingRead, VisitCheckInIn, VisitCheckOutIn
from app.services.booking_service import BookingService
from app.services.visit_service import VisitService

router = APIRouter(prefix="/bookings", tags=["visits"])


@router.post("/{booking_id}/en-route", response_model=ProfessionalBookingRead)
async def mark_en_route(
    booking_id: uuid.UUID,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalBookingRead:
    await VisitService(db).mark_en_route(booking_id, professional.id)
    return await BookingService(db).professional_view(booking_id, professional)


@router.post("/{booking_id}/check-in", response_model=ProfessionalBookingRead)
async def check_in(
    booking_id: uuid.UUID,
    payload: VisitCheckInIn | None = None,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalBookingRead:
    await VisitService(db).check_in(booking_id, professional.id, payload or VisitCheckInIn())
    return await BookingService(db).professional_view(booking_id, professional)


@router.post("/{booking_id}/check-out", response_model=ProfessionalBookingRead)
async def check_out(
    booking_id: uuid.UUID,
    payload: VisitCheckOutIn | None = None,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalBookingRead:
    await VisitService(db).check_out(booking_id, professional.id, payload or VisitCheckOutIn())
    return await BookingService(db).professional_view(booking_id, professional)
