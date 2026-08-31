"""Professional self-service: onboarding, KYC document upload, availability, pricing.
Also the patient-facing "nearby available nurses" browse endpoint."""
import uuid

from fastapi import APIRouter, Depends, Query
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import require_patient, require_professional
from app.db.session import get_db
from app.models.address import Address
from app.models.user import User
from app.repositories.professional_repo import ProfessionalRepository
from app.schemas.common import MessageResponse
from app.schemas.professional import (
    AvailabilitySlotIn,
    AvailabilityStatusUpdateIn,
    NearbyProfessionalRead,
    ProfessionalDocumentRead,
    ProfessionalDocumentUploadIn,
    ProfessionalOnboardIn,
    ProfessionalRead,
    ProfessionalServiceRead,
    ProfessionalServiceUpdateIn,
)
from app.services.catalog_service import CatalogService
from app.services.professional_service import ProfessionalService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/professionals", tags=["professionals"])


@router.post("/onboard", response_model=ProfessionalRead)
async def onboard(
    payload: ProfessionalOnboardIn,
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalRead:
    return await ProfessionalService(db).onboard(current_user.id, payload)


@router.get("/me", response_model=ProfessionalRead)
async def get_my_profile(
    current_user: User = Depends(require_professional), db: AsyncSession = Depends(get_db)
) -> ProfessionalRead:
    return await ProfessionalService(db).get_owned_profile(current_user.id)


@router.post("/me/documents/upload-url")
async def get_document_upload_url(
    filename: str, content_type: str, current_user: User = Depends(require_professional)
) -> dict:
    """Returns a presigned S3 PUT URL; the app uploads bytes directly, then calls
    POST /professionals/me/documents with the returned `file_url` to record it."""
    profile_id = current_user.id  # object key namespaced by user id is sufficient pre-onboarding
    return StorageService().presign_kyc_upload(
        professional_id=str(profile_id), filename=filename, content_type=content_type
    )


@router.post("/me/documents", response_model=ProfessionalDocumentRead)
async def upload_document(
    payload: ProfessionalDocumentUploadIn,
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalDocumentRead:
    service = ProfessionalService(db)
    profile = await service.get_owned_profile(current_user.id)
    return await service.upload_document(profile.id, payload)


@router.put("/me/availability/slots", response_model=MessageResponse)
async def set_availability_slots(
    slots: list[AvailabilitySlotIn],
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    service = ProfessionalService(db)
    profile = await service.get_owned_profile(current_user.id)
    await service.set_availability_slots(profile.id, slots)
    return MessageResponse(message="Availability schedule updated.")


@router.patch("/me/availability/status", response_model=ProfessionalRead)
async def update_availability_status(
    payload: AvailabilityStatusUpdateIn,
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalRead:
    service = ProfessionalService(db)
    profile = await service.get_owned_profile(current_user.id)
    return await service.update_availability_status(profile.id, payload)


@router.get("/me/services", response_model=list[ProfessionalServiceRead])
async def list_my_services(
    current_user: User = Depends(require_professional), db: AsyncSession = Depends(get_db)
) -> list[ProfessionalServiceRead]:
    """Every catalogue service this professional's type qualifies for, showing whether
    they've opted in and what they charge — the "set your price" screen reads this."""
    service = ProfessionalService(db)
    profile = await service.get_owned_profile(current_user.id)
    return await service.list_my_services(profile.id)


@router.put("/me/services/{service_id}", response_model=ProfessionalServiceRead)
async def set_service_pricing(
    service_id: uuid.UUID,
    payload: ProfessionalServiceUpdateIn,
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalServiceRead:
    service = ProfessionalService(db)
    profile = await service.get_owned_profile(current_user.id)
    await service.set_service_pricing(profile.id, service_id, payload)
    updated = await service.list_my_services(profile.id)
    match = next((row for row in updated if row.service_id == service_id), None)
    if match is None:
        raise NotFoundError("Service not found.")
    return match


@router.get("/nearby", response_model=list[NearbyProfessionalRead])
async def find_nearby_professionals(
    service_id: uuid.UUID,
    address_id: uuid.UUID,
    radius_km: float = Query(
        default=settings.DEFAULT_SEARCH_RADIUS_KM, gt=0, le=settings.MAX_SEARCH_RADIUS_KM
    ),
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> list[NearbyProfessionalRead]:
    """Available, verified nurses/professionals near one of the patient's saved addresses,
    qualified for the given service — what the dashboard's "nearby care providers" list and
    "book a service" flow show before a booking is actually created."""
    address = await db.get(Address, address_id)
    if address is None:
        raise NotFoundError("Address not found.")
    if address.user_id != current_user.id:
        raise ForbiddenError("This address does not belong to you.")

    catalogue_service = await CatalogService(db).get_service(service_id)
    location_wkt = to_shape(address.location).wkt

    candidates = await ProfessionalRepository(db).find_nearby_candidates(
        service_id=service_id,
        professional_type=catalogue_service.required_professional_type,
        location_wkt=location_wkt,
        radius_meters=radius_km * 1000,
        limit=20,
    )
    return [
        NearbyProfessionalRead(
            id=professional.id,
            full_name=professional.user.full_name,
            avatar_url=professional.user.avatar_url,
            professional_type=professional.professional_type,
            years_of_experience=professional.years_of_experience,
            average_rating=professional.average_rating,
            total_ratings=professional.total_ratings,
            languages_spoken=professional.languages_spoken,
            distance_km=round(distance_meters / 1000, 2),
        )
        for professional, distance_meters in candidates
    ]
