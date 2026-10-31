"""Booking lifecycle. Patient side: quote, create, list, get, cancel. Professional side: open
requests near them, accept, release, and their assigned bookings (visit progress lives in
`visits.py`). See `booking_service` for how matching works."""
import base64
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_professional, get_current_user, pagination_params
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.permissions import require_patient
from app.db.session import get_db
from app.models.address import Address
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.repositories.booking_repo import BookingRepository
from app.schemas.booking import (
    BookingCancelIn,
    BookingCreateIn,
    BookingListItem,
    BookingQuoteIn,
    BookingQuoteOut,
    BookingRead,
    BookingRequestRead,
    ProfessionalBookingRead,
)
from app.schemas.common import PaginationParams
from app.services.booking_service import (
    BookingService,
    to_professional_read,
    to_request_read,
)
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


@router.post("/prescriptions/upload")
async def upload_prescription(
    file: UploadFile = File(...),
    current_user: User = Depends(require_patient),
) -> dict:
    """Upload prescription image or PDF document. Returns file_url to attach to booking."""
    content_type = file.content_type or "application/octet-stream"
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    allowed = {"jpg", "jpeg", "png", "webp", "pdf", "heic", "heif"}
    if ext not in allowed and not content_type.startswith(("image/", "application/pdf")):
        raise ValidationAppError("Allowed formats are JPG, PNG, WEBP, and PDF.")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise ValidationAppError("File size cannot exceed 10MB.")

    # Upload to S3 if configured
    if settings.S3_BUCKET and settings.AWS_ACCESS_KEY_ID:
        try:
            from app.services.storage_service import StorageService

            s3 = StorageService().s3
            key = s3.build_object_key(
                folder=f"prescriptions/{current_user.id}", filename=file.filename or f"rx.{ext}"
            )
            s3._client.put_object(
                Bucket=settings.S3_BUCKET,
                Key=key,
                Body=contents,
                ContentType=content_type,
            )
            file_url = (
                s3.presign_download(key)
                if not settings.S3_ENDPOINT_URL
                else s3.public_url(key)
            )
            return {"file_url": file_url, "filename": file.filename}
        except Exception:
            pass

    # Resilient fallback: base64 Data URL format works everywhere
    b64 = base64.b64encode(contents).decode("utf-8")
    data_url = f"data:{content_type};base64,{b64}"
    return {"file_url": data_url, "filename": file.filename}


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

    booking_service = BookingService(db)
    booking = await booking_service.create_booking(
        patient_id=current_user.id, service=service, address=address, payload=payload
    )
    return await booking_service.patient_view(booking.id)


@router.get("", response_model=list[BookingListItem])
async def list_my_bookings(
    current_user: User = Depends(require_patient),
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
) -> list[BookingListItem]:
    rows = await BookingRepository(db).list_for_patient(
        current_user.id, limit=pagination.page_size, offset=pagination.offset
    )
    items = []
    for booking, professional_name in rows:
        item = BookingListItem.model_validate(booking)
        item.professional_name = professional_name
        items.append(item)
    return items


# ── Professional side. Declared before `/{booking_id}` routes on purpose: FastAPI matches in
# order, and "professional" would otherwise be parsed (and rejected) as a booking id.


@router.get("/professional/requests", response_model=list[BookingRequestRead])
async def list_open_requests(
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> list[BookingRequestRead]:
    """Open bookings this professional can accept: their profession and services, inside
    their travel radius, starting within their weekly timings. Soonest first."""
    rows = await BookingService(db).list_open_requests(professional)
    return [to_request_read(row) for row in rows]


@router.get("/professional/mine", response_model=list[ProfessionalBookingRead])
async def list_professional_bookings(
    professional: ProfessionalProfile = Depends(get_current_professional),
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
) -> list[ProfessionalBookingRead]:
    rows = await BookingRepository(db).list_for_professional(
        professional.id, limit=pagination.page_size, offset=pagination.offset
    )
    return [to_professional_read(row) for row in rows]


@router.get("/professional/{booking_id}", response_model=ProfessionalBookingRead)
async def get_professional_booking(
    booking_id: uuid.UUID,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalBookingRead:
    return await BookingService(db).professional_view(booking_id, professional)


@router.post("/{booking_id}/accept", response_model=ProfessionalBookingRead)
async def accept_request(
    booking_id: uuid.UUID,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalBookingRead:
    """First to accept gets the booking; anyone after that gets a 409."""
    booking_service = BookingService(db)
    await booking_service.accept(booking_id, professional)
    return await booking_service.professional_view(booking_id, professional)


@router.post("/{booking_id}/release", response_model=ProfessionalBookingRead)
async def release_booking(
    booking_id: uuid.UUID,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalBookingRead:
    """Hand an accepted booking back ("can't make it") — it reopens for other professionals.
    Returns the booking as it was just before release, since it's no longer theirs."""
    booking_service = BookingService(db)
    view = await booking_service.professional_view(booking_id, professional)
    booking = await booking_service.release(booking_id, professional)
    view.status = booking.status
    return view


# ── Patient side, by id.


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingRead:
    booking_service = BookingService(db)
    await booking_service.get_owned_booking(booking_id, patient_id=current_user.id)
    return await booking_service.patient_view(booking_id)


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
        # No-op unless the booking was paid online (not part of the prototype flow).
        await PaymentService(db).refund(booking, amount=refundable)
    return await booking_service.patient_view(booking_id)
