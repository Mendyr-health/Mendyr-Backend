"""Professional self-service: onboarding, profile and service area, weekly timings, services,
KYC document upload. Also the patient-facing "professionals near this address" endpoint."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends
from geoalchemy2.shape import to_shape
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_professional
from app.core.config_registry import BookingRules
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import require_patient, require_professional
from app.db.session import get_db
from app.models.address import Address
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.repositories.professional_repo import ProfessionalRepository
from app.schemas.common import MessageResponse
from app.schemas.document import (
    ProfessionalDocumentIn,
    ProfessionalDocumentOut,
    UploadUrlIn,
    UploadUrlOut,
)
from app.schemas.professional import (
    AvailabilitySlotIn,
    AvailabilitySlotRead,
    AvailabilityStatusUpdateIn,
    NearbyProfessionalRead,
    ProfessionalOnboardIn,
    ProfessionalRead,
    ProfessionalServiceRead,
    ProfessionalServiceUpdateIn,
    ProfessionalUpdateIn,
)
from app.services.catalog_service import CatalogService
from app.services.config_service import ConfigService
from app.services.document_service import DocumentService
from app.services.professional_service import ProfessionalService, to_professional_read
from app.services.storage_service import StorageService, kyc_folder

router = APIRouter(prefix="/professionals", tags=["professionals"])


@router.post("/onboard", response_model=ProfessionalRead)
async def onboard(
    payload: ProfessionalOnboardIn,
    current_user: User = Depends(require_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalRead:
    profile = await ProfessionalService(db).onboard(current_user.id, payload)
    return to_professional_read(profile)


@router.get("/me", response_model=ProfessionalRead)
async def get_my_profile(
    professional: ProfessionalProfile = Depends(get_current_professional),
) -> ProfessionalRead:
    return to_professional_read(professional)


@router.patch("/me", response_model=ProfessionalRead)
async def update_my_profile(
    payload: ProfessionalUpdateIn,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalRead:
    """Edit profile details, service area, or the "accepting requests" switch."""
    profile = await ProfessionalService(db).update_profile(professional, payload)
    return to_professional_read(profile)


@router.post("/me/documents/upload-url", response_model=UploadUrlOut)
async def get_document_upload_url(
    payload: UploadUrlIn, professional: ProfessionalProfile = Depends(get_current_professional)
) -> dict:
    """A presigned PUT URL for one KYC file (PDF or photo, size-checked). Upload the bytes
    there with the returned headers, then record it with `POST /me/documents`."""
    return StorageService().presign_upload(
        folder=kyc_folder(professional.id),
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
    )


@router.get("/me/documents", response_model=list[ProfessionalDocumentOut])
async def list_my_documents(
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> list[ProfessionalDocumentOut]:
    """Uploaded KYC documents with their review status and short-lived view links."""
    service = DocumentService(db)
    return [service.professional_out(d) for d in await service.list_professional(professional.id)]


@router.post("/me/documents", response_model=ProfessionalDocumentOut, status_code=201)
async def add_document(
    payload: ProfessionalDocumentIn,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalDocumentOut:
    """Record an uploaded file. Replaces a pending/rejected document of the same type."""
    service = DocumentService(db)
    return service.professional_out(await service.add_professional(professional, payload))


@router.delete("/me/documents/{document_id}", response_model=MessageResponse)
async def delete_document(
    document_id: uuid.UUID,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Remove a pending or rejected document (verified ones stay — ask support)."""
    await DocumentService(db).delete_own_professional(document_id, professional)
    return MessageResponse(message="Document removed.")


@router.get("/me/availability/slots", response_model=list[AvailabilitySlotRead])
async def get_availability_slots(
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> list[AvailabilitySlotRead]:
    """The weekly timings, Monday first. Empty means "available any time"."""
    slots = await ProfessionalService(db).list_availability_slots(professional.id)
    return [AvailabilitySlotRead.model_validate(slot) for slot in slots]


@router.put("/me/availability/slots", response_model=MessageResponse)
async def set_availability_slots(
    slots: list[AvailabilitySlotIn],
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Replaces the whole weekly schedule."""
    await ProfessionalService(db).set_availability_slots(professional.id, slots)
    return MessageResponse(message="Availability schedule updated.")


@router.patch("/me/availability/status", response_model=ProfessionalRead)
async def update_availability_status(
    payload: AvailabilityStatusUpdateIn,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalRead:
    profile = await ProfessionalService(db).update_availability_status(professional.id, payload)
    return to_professional_read(profile)


@router.get("/me/services", response_model=list[ProfessionalServiceRead])
async def list_my_services(
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> list[ProfessionalServiceRead]:
    """Every catalogue service this professional's type qualifies for, showing whether
    they've opted in and what they charge — the "set your price" screen reads this."""
    return await ProfessionalService(db).list_my_services(professional.id)


@router.put("/me/services/{service_id}", response_model=ProfessionalServiceRead)
async def set_service_pricing(
    service_id: uuid.UUID,
    payload: ProfessionalServiceUpdateIn,
    professional: ProfessionalProfile = Depends(get_current_professional),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalServiceRead:
    service = ProfessionalService(db)
    await service.set_service_pricing(professional.id, service_id, payload)
    updated = await service.list_my_services(professional.id)
    match = next((row for row in updated if row.service_id == service_id), None)
    if match is None:
        raise NotFoundError("Service not found.")
    return match


@router.get("/nearby", response_model=list[NearbyProfessionalRead])
async def find_nearby_professionals(
    service_id: uuid.UUID,
    address_id: uuid.UUID,
    scheduled_at: AwareDatetime | None = None,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> list[NearbyProfessionalRead]:
    """Professionals whose service area covers one of the patient's saved addresses and who
    do the given service — and, with `scheduled_at`, are free at that time. The booking
    screen shows this as "N professionals available near you" before booking."""
    address = await db.get(Address, address_id)
    if address is None:
        raise NotFoundError("Address not found.")
    if address.user_id != current_user.id:
        raise ForbiddenError("This address does not belong to you.")

    catalogue_service = await CatalogService(db).get_service(service_id)
    rules = await ConfigService(db).typed("booking.rules", BookingRules)
    candidates = await ProfessionalRepository(db).find_nearby_candidates(
        service_id=service_id,
        professional_type=catalogue_service.required_professional_type,
        location_wkt=to_shape(address.location).wkt,
        at=scheduled_at,
        duration=timedelta(minutes=catalogue_service.duration_minutes),
        travel_buffer=timedelta(minutes=rules.travel_buffer_minutes),
    )
    return [
        NearbyProfessionalRead(
            id=professional.id,
            full_name=professional.user.full_name,
            avatar_url=professional.user.avatar_url,
            professional_type=professional.professional_type,
            years_of_experience=professional.years_of_experience,
            average_rating=float(professional.average_rating),
            total_ratings=professional.total_ratings,
            languages_spoken=professional.languages_spoken,
            distance_km=round(distance_meters / 1000, 1),
        )
        for professional, distance_meters in candidates
    ]
