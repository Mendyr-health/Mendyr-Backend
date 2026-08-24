"""Professional onboarding, KYC document review, availability status/location, service opt-in."""

import uuid
from datetime import UTC, datetime, timedelta

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import BookingStatus, VerificationStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.models.booking import Booking
from app.models.payment import Payout
from app.models.professional import (
    ProfessionalAvailabilitySlot,
    ProfessionalDocument,
    ProfessionalProfile,
    ProfessionalSpecialization,
)
from app.models.service import ProfessionalService as ProfessionalServiceOptIn
from app.models.user import User
from app.repositories.booking_repo import BookingRepository
from app.repositories.professional_repo import ProfessionalRepository
from app.schemas.appointment import EarningTransactionPublic, NurseEarningsSummary
from app.schemas.professional import (
    AvailabilitySlotIn,
    AvailabilityStatusUpdateIn,
    ProfessionalDocumentUploadIn,
    ProfessionalOnboardIn,
    ProfessionalReviewDecisionIn,
)


class ProfessionalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.professionals = ProfessionalRepository(session)
        self.bookings = BookingRepository(session)

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

    # ── Earnings (GET /professionals/me/earnings) ────────────────────────────

    async def get_earnings_summary(self, professional_id: uuid.UUID) -> NurseEarningsSummary:
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)

        month_bookings = await self.bookings.list_completed_for_professional_between(
            professional_id, start=month_start, end=now + timedelta(days=1)
        )
        today_earnings = sum(
            float(b.professional_payout_amount)
            for b in month_bookings
            if b.scheduled_start_at >= today_start
        )
        week_earnings = sum(
            float(b.professional_payout_amount)
            for b in month_bookings
            if b.scheduled_start_at >= week_start
        )
        month_earnings = sum(float(b.professional_payout_amount) for b in month_bookings)

        total_row = await self.session.execute(
            select(func.coalesce(func.sum(Booking.professional_payout_amount), 0)).where(
                Booking.professional_id == professional_id,
                Booking.status == BookingStatus.COMPLETED,
            )
        )
        total_earnings = float(total_row.scalar_one())

        paid_out_row = await self.session.execute(
            select(func.coalesce(func.sum(Payout.net_amount), 0)).where(
                Payout.professional_id == professional_id
            )
        )
        already_paid_out = float(paid_out_row.scalar_one())

        recent = sorted(month_bookings, key=lambda b: b.scheduled_start_at, reverse=True)[:20]
        patient_ids = {b.patient_id for b in recent}
        patients = {}
        if patient_ids:
            rows = await self.session.execute(select(User).where(User.id.in_(patient_ids)))
            patients = {u.id: u.full_name for u in rows.scalars().all()}

        return NurseEarningsSummary(
            today_earnings=today_earnings,
            week_earnings=week_earnings,
            month_earnings=month_earnings,
            total_earnings=total_earnings,
            pending_payout=max(total_earnings - already_paid_out, 0),
            completed_visits_count=len(month_bookings),
            transactions=[
                EarningTransactionPublic(
                    id=str(b.id),
                    appointment_id=str(b.id),
                    patient_name=patients.get(b.patient_id, "Unknown"),
                    service_name=b.service_name_snapshot,
                    date=b.scheduled_start_at.date().isoformat(),
                    amount=float(b.professional_payout_amount),
                    status="paid" if already_paid_out >= total_earnings else "processing",
                    payment_method=None,
                )
                for b in recent
            ],
        )
