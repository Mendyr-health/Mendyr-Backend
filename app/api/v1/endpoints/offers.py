"""Professional-side dispatch offers: accept/reject a booking offered by the matching engine."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.permissions import require_professional
from app.db.session import get_db
from app.models.user import User
from app.repositories.professional_repo import ProfessionalRepository
from app.schemas.booking import BookingRead, OfferRespondIn
from app.services.matching_service import MatchingService

router = APIRouter(prefix="/offers", tags=["offers"])


@router.post("/{booking_id}/respond", response_model=BookingRead)
async def respond_to_offer(
    booking_id: uuid.UUID,
    payload: OfferRespondIn,
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    profile = await ProfessionalRepository(db).get_by_user_id(current_user.id)
    if profile is None:
        raise NotFoundError("Complete professional onboarding first.")

    return await MatchingService(db).respond_to_offer(
        booking_id=booking_id, professional_id=profile.id, accept=payload.accept
    )
