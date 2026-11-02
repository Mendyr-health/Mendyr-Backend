"""Professional KYC documents and patient medical documents: record an upload, list with
fresh view links, delete, attach to a booking, and admin review.

Who sees what:
- a professional's KYC documents — that professional and admin/ops
- a patient's medical documents — that patient, admin/ops, and the professional assigned to
  a booking the document is attached to, only while that visit is live (not once it's
  cancelled or finished — the same rule as contact details, see `PrivacyConfig`)
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import COMMITTED_STATUSES, BookingStatus, VerificationStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.booking import Booking
from app.models.medical_document import MedicalDocument
from app.models.professional import ProfessionalDocument, ProfessionalProfile
from app.schemas.document import (
    DocumentReviewIn,
    MedicalDocumentIn,
    MedicalDocumentOut,
    ProfessionalDocumentIn,
    ProfessionalDocumentOut,
)
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.storage_service import (
    ALLOWED_CONTENT_TYPES,
    StorageService,
    kyc_folder,
    medical_folder,
)

_EXT_TO_TYPE = {ext: ctype for ctype, ext in ALLOWED_CONTENT_TYPES.items()}
# A document can be attached to a booking until the visit is over.
ATTACHABLE_STATUSES = frozenset({BookingStatus.SEARCHING, *COMMITTED_STATUSES})


def _content_type_of(key: str) -> str | None:
    return _EXT_TO_TYPE.get(key.rsplit(".", 1)[-1].lower())


class DocumentService:
    def __init__(self, session: AsyncSession, storage: StorageService | None = None) -> None:
        self.session = session
        self.storage = storage or StorageService()
        self.audit = AuditService(session)

    # ── Professional KYC ────────────────────────────────────────────────

    def professional_out(self, doc: ProfessionalDocument) -> ProfessionalDocumentOut:
        return ProfessionalDocumentOut(
            id=doc.id,
            document_type=doc.document_type,
            verification_status=doc.verification_status,
            rejection_reason=doc.rejection_reason,
            content_type=_content_type_of(doc.file_url),
            view_url=self.storage.view_url(doc.file_url),
            reviewed_at=doc.reviewed_at,
            created_at=doc.created_at,
        )

    async def list_professional(self, professional_id: uuid.UUID) -> list[ProfessionalDocument]:
        result = await self.session.execute(
            select(ProfessionalDocument)
            .where(ProfessionalDocument.professional_id == professional_id)
            .order_by(ProfessionalDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_professional(
        self, professional: ProfessionalProfile, payload: ProfessionalDocumentIn
    ) -> ProfessionalDocument:
        """Record an uploaded KYC file. A newer upload of the same type replaces a pending or
        rejected one (the re-upload flow); an approved one stays until an admin removes it."""
        self.storage.verify_upload(payload.file_key, folder=kyc_folder(professional.id))
        for existing in await self.list_professional(professional.id):
            if (
                existing.document_type == payload.document_type
                and existing.verification_status != VerificationStatus.APPROVED
            ):
                await self._delete_professional_row(existing)
        doc = ProfessionalDocument(
            professional_id=professional.id,
            document_type=payload.document_type,
            file_url=payload.file_key,
            verification_status=VerificationStatus.PENDING,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def _get_professional_doc(
        self, document_id: uuid.UUID, professional_id: uuid.UUID
    ) -> ProfessionalDocument:
        doc = await self.session.get(ProfessionalDocument, document_id)
        if doc is None or doc.professional_id != professional_id:
            raise NotFoundError("Document not found.")
        return doc

    async def _delete_professional_row(self, doc: ProfessionalDocument) -> None:
        self.storage.delete(doc.file_url)
        await self.session.delete(doc)
        await self.session.flush()

    async def delete_own_professional(
        self, document_id: uuid.UUID, professional: ProfessionalProfile
    ) -> None:
        doc = await self._get_professional_doc(document_id, professional.id)
        if doc.verification_status == VerificationStatus.APPROVED:
            raise ConflictError(
                "Verified documents can't be removed — contact support to replace one."
            )
        await self._delete_professional_row(doc)

    async def admin_delete_professional(
        self, document_id: uuid.UUID, professional_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        doc = await self._get_professional_doc(document_id, professional_id)
        self.audit.log(
            actor_id=actor_id,
            action="document.delete",
            entity_type="professional",
            entity_id=str(professional_id),
            metadata={"document_type": doc.document_type.value},
        )
        await self._delete_professional_row(doc)

    async def review_professional(
        self,
        document_id: uuid.UUID,
        professional_id: uuid.UUID,
        payload: DocumentReviewIn,
        *,
        actor_id: uuid.UUID,
    ) -> ProfessionalDocument:
        doc = await self._get_professional_doc(document_id, professional_id)
        if payload.decision == "rejected" and not payload.rejection_reason:
            raise ValidationAppError("rejection_reason is required when rejecting.")
        doc.verification_status = VerificationStatus(payload.decision)
        doc.rejection_reason = payload.rejection_reason if payload.decision == "rejected" else None
        doc.reviewed_by_id = actor_id
        doc.reviewed_at = datetime.now(UTC)
        self.audit.log(
            actor_id=actor_id,
            action=f"document.{payload.decision}",
            entity_type="professional",
            entity_id=str(professional_id),
            metadata={
                "document_type": doc.document_type.value,
                "reason": payload.rejection_reason,
            },
        )
        if payload.decision == "rejected":
            profile = await self.session.get(ProfessionalProfile, professional_id)
            if profile is not None:
                label = doc.document_type.value.replace("_", " ")
                await NotificationService(self.session).push_to_user(
                    profile.user_id,
                    title="Please re-upload a document",
                    body=f"Your {label} wasn't accepted: {payload.rejection_reason}",
                    data={"template_key": "document_rejected", "document_id": str(doc.id)},
                )
        await self.session.flush()
        return doc

    # ── Patient medical documents ───────────────────────────────────────

    def medical_out(self, doc: MedicalDocument) -> MedicalDocumentOut:
        return MedicalDocumentOut(
            id=doc.id,
            document_type=doc.document_type,  # type: ignore[arg-type]
            title=doc.title,
            booking_id=doc.booking_id,
            content_type=doc.content_type,
            size_bytes=doc.size_bytes,
            view_url=self.storage.view_url(doc.file_key),
            created_at=doc.created_at,
        )

    async def list_medical(
        self, user_id: uuid.UUID, *, booking_id: uuid.UUID | None = None
    ) -> list[MedicalDocument]:
        stmt = select(MedicalDocument).where(MedicalDocument.user_id == user_id)
        if booking_id is not None:
            stmt = stmt.where(MedicalDocument.booking_id == booking_id)
        result = await self.session.execute(stmt.order_by(MedicalDocument.created_at.desc()))
        return list(result.scalars().all())

    async def for_booking(self, booking_id: uuid.UUID) -> list[MedicalDocument]:
        result = await self.session.execute(
            select(MedicalDocument)
            .where(MedicalDocument.booking_id == booking_id)
            .order_by(MedicalDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def for_bookings(self, booking_ids: list[uuid.UUID]) -> dict[uuid.UUID, list]:
        """Documents per booking for a list view, in one query."""
        if not booking_ids:
            return {}
        result = await self.session.execute(
            select(MedicalDocument)
            .where(MedicalDocument.booking_id.in_(booking_ids))
            .order_by(MedicalDocument.created_at.desc())
        )
        grouped: dict[uuid.UUID, list] = {}
        for doc in result.scalars().all():
            grouped.setdefault(doc.booking_id, []).append(doc)
        return grouped

    async def _attachable_booking(self, booking_id: uuid.UUID, user_id: uuid.UUID) -> Booking:
        booking = await self.session.get(Booking, booking_id)
        if booking is None or booking.patient_id != user_id:
            raise NotFoundError("Booking not found.")
        if booking.status not in ATTACHABLE_STATUSES:
            raise ValidationAppError("Documents can only be added to an upcoming visit.")
        return booking

    async def add_medical(self, user_id: uuid.UUID, payload: MedicalDocumentIn) -> MedicalDocument:
        meta = self.storage.verify_upload(payload.file_key, folder=medical_folder(user_id))
        if payload.booking_id is not None:
            await self._attachable_booking(payload.booking_id, user_id)
        doc = MedicalDocument(
            user_id=user_id,
            booking_id=payload.booking_id,
            document_type=payload.document_type,
            title=payload.title,
            file_key=payload.file_key,
            content_type=meta.get("content_type") or _content_type_of(payload.file_key) or "",
            size_bytes=int(meta.get("size") or 0),
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def _own_medical(self, document_id: uuid.UUID, user_id: uuid.UUID) -> MedicalDocument:
        doc = await self.session.get(MedicalDocument, document_id)
        if doc is None or doc.user_id != user_id:
            raise NotFoundError("Document not found.")
        return doc

    async def attach_medical(
        self, document_id: uuid.UUID, user_id: uuid.UUID, booking_id: uuid.UUID | None
    ) -> MedicalDocument:
        doc = await self._own_medical(document_id, user_id)
        if booking_id is not None:
            await self._attachable_booking(booking_id, user_id)
        doc.booking_id = booking_id
        await self.session.flush()
        return doc

    async def attach_many(
        self, document_ids: list[uuid.UUID], *, user_id: uuid.UUID, booking_id: uuid.UUID
    ) -> None:
        """Attach documents picked during booking. All must be the patient's own."""
        for document_id in dict.fromkeys(document_ids):
            doc = await self._own_medical(document_id, user_id)
            doc.booking_id = booking_id
        await self.session.flush()

    async def delete_medical(self, document_id: uuid.UUID, user_id: uuid.UUID) -> None:
        doc = await self._own_medical(document_id, user_id)
        self.storage.delete(doc.file_key)
        await self.session.delete(doc)
        await self.session.flush()

    async def has_prescription(self, document_ids: list[uuid.UUID], user_id: uuid.UUID) -> bool:
        if not document_ids:
            return False
        result = await self.session.execute(
            select(MedicalDocument.id).where(
                MedicalDocument.id.in_(document_ids),
                MedicalDocument.user_id == user_id,
                MedicalDocument.document_type == "prescription",
            )
        )
        return result.first() is not None
