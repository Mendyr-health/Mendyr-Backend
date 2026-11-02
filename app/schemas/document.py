"""Upload/view shapes for professional KYC documents and patient medical documents."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.constants import DocumentType, VerificationStatus

MedicalDocumentType = Literal["prescription", "lab_report", "referral", "other"]


class UploadUrlIn(BaseModel):
    content_type: str = Field(..., max_length=100)
    size_bytes: int = Field(..., gt=0)


class UploadUrlOut(BaseModel):
    """PUT the file to `upload_url` with exactly `headers`, then record `file_key`."""

    upload_url: str
    file_key: str
    method: str
    headers: dict[str, str]
    expires_in: int


class ProfessionalDocumentIn(BaseModel):
    document_type: DocumentType
    file_key: str = Field(..., max_length=500)


class ProfessionalDocumentOut(BaseModel):
    id: uuid.UUID
    document_type: DocumentType
    verification_status: VerificationStatus
    rejection_reason: str | None
    content_type: str | None
    # Short-lived (minutes) — request the list again rather than storing it.
    view_url: str
    reviewed_at: datetime | None
    created_at: datetime


class DocumentReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]
    rejection_reason: str | None = Field(default=None, max_length=500)


class MedicalDocumentIn(BaseModel):
    document_type: MedicalDocumentType = "prescription"
    file_key: str = Field(..., max_length=500)
    title: str | None = Field(default=None, max_length=150)
    booking_id: uuid.UUID | None = None


class MedicalDocumentAttachIn(BaseModel):
    """Attach to one of your bookings, or detach with null."""

    booking_id: uuid.UUID | None


class MedicalDocumentOut(BaseModel):
    id: uuid.UUID
    document_type: MedicalDocumentType
    title: str | None
    booking_id: uuid.UUID | None
    content_type: str
    size_bytes: int
    view_url: str
    created_at: datetime
