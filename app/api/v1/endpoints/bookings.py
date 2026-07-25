"""Patient booking lifecycle: quote, create, list, get, cancel. Professional-side listing too."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, pagination_params
from app.core.exceptions import NotFoundError
from app.core.permissions import require_patient, require_professional
from app.db.session import get_db
from app.models.address import Address
from app.models.user import User
from app.repositories.booking_repo import BookingRepository
from app.repositories.professional_repo import ProfessionalRepository
from app.schemas.booking import (
    BookingCancelIn,
    BookingCreateIn,
    BookingListItem,
    BookingQuoteIn,
    BookingQuoteOut,
    BookingRead,
)
from app.schemas.common import PaginationParams
from app.services.booking_service import BookingService
from app.services.catalog_service import CatalogService
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/quote", response_model=BookingQuoteOut)
async def quote_booking(
    payload: BookingQuoteIn,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> BookingQuoteOut:
    service = await CatalogService(db).get_service(payload.service_id)
    breakdown = await BookingService(db).quote(service=service, coupon_code=payload.coupon_code)
    return BookingQuoteOut(**breakdown.__dict__)


@router.post("", response_model=BookingRead)
async def create_booking(
    payload: BookingCreateIn,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    service = await CatalogService(db).get_service(payload.service_id)

    address = await db.get(Address, payload.address_id)
    if address is None:
        raise NotFoundError("Address not found.")

    return await BookingService(db).create_booking(
        patient_id=current_user.id, service=service, address=address, payload=payload
    )


@router.get("", response_model=list[BookingListItem])
async def list_my_bookings(
    current_user: User = Depends(require_patient),
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await BookingRepository(db).list_for_patient(
        current_user.id, limit=pagination.page_size, offset=pagination.offset
    )


@router.get("/professional/mine", response_model=list[BookingListItem])
async def list_professional_bookings(
    current_user: User = Depends(require_professional),
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
) -> list:
    profile = await ProfessionalRepository(db).get_by_user_id(current_user.id)
    if profile is None:
        return []
    return await BookingRepository(db).list_for_professional(
        profile.id, limit=pagination.page_size, offset=pagination.offset
    )


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    return await BookingService(db).get_owned_booking(booking_id, patient_id=current_user.id)


@router.post("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: uuid.UUID,
    payload: BookingCancelIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    booking_service = BookingService(db)
    booking = await booking_service.get_owned_booking(booking_id, patient_id=current_user.id)
    booking = await booking_service.cancel(
        booking, cancelled_by_id=current_user.id, reason=payload.reason
    )

    refundable = float(booking.total_amount) - float(booking.cancellation_fee_amount)
    if refundable > 0:
        await PaymentService(db).refund(booking, amount=refundable)
    return booking
