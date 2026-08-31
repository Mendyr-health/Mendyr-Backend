"""Professional onboarding, KYC document review, availability status/location, service opt-in."""

import uuid
from datetime import UTC, datetime

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import VerificationStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.professional import (
    ProfessionalAvailabilitySlot,
    ProfessionalDocument,
    ProfessionalProfile,
    ProfessionalSpecialization,
)
from app.models.service import ProfessionalService as ProfessionalServiceOptIn
from app.models.service import Service
from app.repositories.professional_repo import ProfessionalRepository
from app.schemas.professional import (
    AvailabilitySlotIn,
    AvailabilityStatusUpdateIn,
    ProfessionalDocumentUploadIn,
    ProfessionalOnboardIn,
    ProfessionalReviewDecisionIn,
    ProfessionalServiceRead,
    ProfessionalServiceUpdateIn,
)


class ProfessionalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.professionals = ProfessionalRepository(session)

    async def onboard(
        self, user_id: uuid.UUID, payload: ProfessionalOnboardIn
    ) -> ProfessionalProfile:
        existing = await self.professionals.get_by_user_id(user_id)
        if existing is not None:
            raise ConflictError("Professional profile already exists for this user.")

        profile = ProfessionalProfile(
            user_id=user_id,
            professional_type=payload.professional_type,
            years_of_experience=payload.years_of_experience,
            bio=payload.bio,
            license_number=payload.license_number,
            council_registration_number=payload.council_registration_number,
            languages_spoken=payload.languages_spoken,
            verification_status=VerificationStatus.PENDING,
        )
        self.professionals.add(profile)
        await self.session.flush()

        for spec_id in payload.specialization_ids:
            self.session.add(
                ProfessionalSpecialization(professional_id=profile.id, specialization_id=spec_id)
            )
        for service_id in payload.service_ids:
            self.session.add(
                ProfessionalServiceOptIn(professional_id=profile.id, service_id=service_id)
            )
        await self.session.flush()
        return profile

    async def get_owned_profile(self, user_id: uuid.UUID) -> ProfessionalProfile:
        profile = await self.professionals.get_by_user_id(user_id)
        if profile is None:
            raise NotFoundError("Professional profile not found. Complete onboarding first.")
        return profile

    async def upload_document(
        self, professional_id: uuid.UUID, payload: ProfessionalDocumentUploadIn
    ) -> ProfessionalDocument:
        document = ProfessionalDocument(
            professional_id=professional_id,
            document_type=payload.document_type,
            file_url=payload.file_url,
            verification_status=VerificationStatus.PENDING,
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def review_kyc(
        self,
        professional_id: uuid.UUID,
        decision: ProfessionalReviewDecisionIn,
        *,
        reviewer_id: uuid.UUID,
    ) -> ProfessionalProfile:
        profile = await self.professionals.get(professional_id)
        if profile is None:
            raise NotFoundError("Professional not found.")

        if decision.approve:
            profile.verification_status = VerificationStatus.APPROVED
            profile.verified_at = datetime.now(UTC)
            profile.rejection_reason = None
        else:
            if not decision.rejection_reason:
                raise ValidationAppError("rejection_reason is required when rejecting.")
            profile.verification_status = VerificationStatus.REJECTED
            profile.rejection_reason = decision.rejection_reason

        await self.session.flush()
        return profile

    async def set_availability_slots(
        self, professional_id: uuid.UUID, slots: list[AvailabilitySlotIn]
    ) -> list[ProfessionalAvailabilitySlot]:
        # Replace-all semantics keep the weekly schedule endpoint idempotent and simple for the app.
        result = await self.session.execute(
            select(ProfessionalAvailabilitySlot).where(
                ProfessionalAvailabilitySlot.professional_id == professional_id
            )
        )
        for existing in result.scalars().all():
            await self.session.delete(existing)
        await self.session.flush()

        created = []
        for slot in slots:
            row = ProfessionalAvailabilitySlot(
                professional_id=professional_id,
                day_of_week=slot.day_of_week,
                start_time=slot.start_time,
                end_time=slot.end_time,
            )
            self.session.add(row)
            created.append(row)
        await self.session.flush()
        return created

    async def list_my_services(self, professional_id: uuid.UUID) -> list[ProfessionalServiceRead]:
        profile = await self.professionals.get(professional_id)
        if profile is None:
            raise NotFoundError("Professional not found.")

        rows = await self.professionals.list_catalogue_with_pricing(
            professional_id, profile.professional_type
        )
        return [
            ProfessionalServiceRead(
                service_id=service.id,
                service_name=service.name,
                category_name=category.name,
                base_price=float(service.base_price),
                price_override=float(optin.price_override)
                if optin and optin.price_override is not None
                else None,
                effective_price=float(
                    optin.price_override
                    if optin and optin.price_override is not None
                    else service.base_price
                ),
                is_opted_in=optin is not None and optin.is_active,
            )
            for service, category, optin in rows
        ]

    async def set_service_pricing(
        self,
        professional_id: uuid.UUID,
        service_id: uuid.UUID,
        payload: ProfessionalServiceUpdateIn,
    ) -> ProfessionalServiceOptIn:
        profile = await self.professionals.get(professional_id)
        if profile is None:
            raise NotFoundError("Professional not found.")

        service = await self.session.get(Service, service_id)
        if service is None or not service.is_active:
            raise NotFoundError("Service not found.")
        if service.required_professional_type != profile.professional_type:
            raise ValidationAppError(
                f"This service requires a {service.required_professional_type.value}, "
                f"not a {profile.professional_type.value}."
            )

        optin = await self.professionals.get_service_optin(professional_id, service_id)
        if optin is None:
            optin = ProfessionalServiceOptIn(professional_id=professional_id, service_id=service_id)
            self.session.add(optin)

        optin.is_active = payload.is_opted_in
        optin.price_override = payload.price_override
        await self.session.flush()
        return optin

    async def update_availability_status(
        self, professional_id: uuid.UUID, payload: AvailabilityStatusUpdateIn
    ) -> ProfessionalProfile:
        profile = await self.professionals.get(professional_id)
        if profile is None:
            raise NotFoundError("Professional not found.")

        profile.availability_status = payload.availability_status
        if payload.location is not None:
            profile.current_location = WKTElement(
                f"POINT({payload.location.longitude} {payload.location.latitude})", srid=4326
            )
            profile.location_updated_at = datetime.now(UTC)

        await self.session.flush()
        return profile
