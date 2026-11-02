"""The patient's own medical documents — prescriptions, lab reports, referrals. Upload is two
steps (get an upload URL, PUT the file, then record it); a document can be attached to an
upcoming booking so the assigned professional can see it during the visit."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_patient
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.document import (
    MedicalDocumentAttachIn,
    MedicalDocumentIn,
    MedicalDocumentOut,
    UploadUrlIn,
    UploadUrlOut,
)
from app.services.document_service import DocumentService
from app.services.storage_service import StorageService, medical_folder

router = APIRouter(prefix="/medical-documents", tags=["medical documents"])


@router.post("/upload-url", response_model=UploadUrlOut)
async def get_upload_url(
    payload: UploadUrlIn, current_user: User = Depends(require_patient)
) -> dict:
    """A presigned PUT URL for one file (PDF or photo, size-checked)."""
    return StorageService().presign_upload(
        folder=medical_folder(current_user.id),
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
    )


@router.get("", response_model=list[MedicalDocumentOut])
async def list_documents(
    booking_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> list[MedicalDocumentOut]:
    """Newest first, with short-lived view links; filter to one booking with `booking_id`."""
    service = DocumentService(db)
    docs = await service.list_medical(current_user.id, booking_id=booking_id)
    return [service.medical_out(d) for d in docs]


@router.post("", response_model=MedicalDocumentOut, status_code=201)
async def add_document(
    payload: MedicalDocumentIn,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> MedicalDocumentOut:
    service = DocumentService(db)
    return service.medical_out(await service.add_medical(current_user.id, payload))


@router.patch("/{document_id}", response_model=MedicalDocumentOut)
async def attach_document(
    document_id: uuid.UUID,
    payload: MedicalDocumentAttachIn,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> MedicalDocumentOut:
    """Attach to an upcoming booking of yours, or detach with `booking_id: null`."""
    service = DocumentService(db)
    doc = await service.attach_medical(document_id, current_user.id, payload.booking_id)
    return service.medical_out(doc)


@router.delete("/{document_id}", response_model=MessageResponse)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Deletes the record and the file itself."""
    await DocumentService(db).delete_medical(document_id, current_user.id)
    return MessageResponse(message="Document deleted.")
