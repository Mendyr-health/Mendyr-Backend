"""Professional self-service: onboarding, KYC document upload, availability."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_professional
from app.db.session import get_db
from app.models.user import User
from app.schemas.appointment import NurseEarningsSummary
from app.schemas.common import ApiResponse, MessageResponse
from app.schemas.professional import (
    AvailabilitySlotIn,
    AvailabilityStatusUpdateIn,
    ProfessionalDocumentRead,
    ProfessionalDocumentUploadIn,
    ProfessionalOnboardIn,
    ProfessionalRead,
)
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


@router.get("/me/earnings", response_model=ApiResponse[NurseEarningsSummary])
async def get_my_earnings(
    current_user: User = Depends(require_professional), db: AsyncSession = Depends(get_db)
) -> ApiResponse[NurseEarningsSummary]:
    service = ProfessionalService(db)
    profile = await service.get_owned_profile(current_user.id)
    summary = await service.get_earnings_summary(profile.id)
    return ApiResponse.ok(summary)
