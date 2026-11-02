"""Operations for the config portal: the professional verification queue, user management,
booking oversight and the activity log. Read paths are one or two queries per screen, not
one per row."""

import json
import statistics
import uuid
from datetime import UTC, datetime, timedelta

from geoalchemy2.shape import to_shape
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config_registry import VerificationConfig
from app.core.constants import (
    ADMIN_ROLES,
    BookingStatus,
    ProfessionalType,
    UserRole,
    UserStatus,
    VerificationStatus,
)
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.models.address import Address
from app.models.audit import AuditLog
from app.models.booking import Booking, BookingStatusHistory, BookingVisit
from app.models.professional import (
    ProfessionalAvailabilitySlot,
    ProfessionalDocument,
    ProfessionalProfile,
)
from app.models.review import Review
from app.models.service import ProfessionalService as ProfessionalServiceOptIn
from app.models.service import Service
from app.models.user import User
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.schemas.admin import (
    AdminActivity,
    AdminBookingDetail,
    AdminBookingListItem,
    AdminDocument,
    AdminPage,
    AdminProfessionalDetail,
    AdminProfessionalListItem,
    AdminSlot,
    AdminUserListItem,
    UserStatusIn,
    VerificationStats,
)
from app.schemas.booking import StatusEvent
from app.services.audit_service import AuditService
from app.services.booking_service import BookingService
from app.services.config_service import ConfigService
from app.services.document_service import DocumentService
from app.services.notification_service import NotificationService


def _like(q: str) -> str:
    return f"%{q.strip()}%"


async def _paged(session: AsyncSession, stmt: Select, page: int, page_size: int) -> tuple:
    total = (
        await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
    ).scalar_one()
    rows = (await session.execute(stmt.limit(page_size).offset((page - 1) * page_size))).all()
    return rows, total


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    # ── Professionals ───────────────────────────────────────────────────

    def _professional_query(self) -> Select:
        docs = (
            select(func.count(ProfessionalDocument.id))
            .where(ProfessionalDocument.professional_id == ProfessionalProfile.id)
            .correlate(ProfessionalProfile)
            .scalar_subquery()
        )
        return select(ProfessionalProfile, User, docs.label("documents_count")).join(
            User, User.id == ProfessionalProfile.user_id
        )

    @staticmethod
    def _professional_item(
        profile: ProfessionalProfile, user: User, documents_count: int
    ) -> AdminProfessionalListItem:
        return AdminProfessionalListItem(
            id=profile.id,
            user_id=user.id,
            full_name=user.full_name,
            phone_number=user.phone_number,
            email=user.email,
            gender=user.gender.value,
            avatar_url=user.avatar_url,
            professional_type=profile.professional_type,
            years_of_experience=profile.years_of_experience,
            license_number=profile.license_number,
            council_registration_number=profile.council_registration_number,
            verification_status=profile.verification_status,
            rejection_reason=profile.rejection_reason,
            verified_at=profile.verified_at,
            is_accepting_bookings=profile.is_accepting_bookings,
            user_status=user.status,
            city=(profile.extended_attributes or {}).get("city"),
            average_rating=float(profile.average_rating),
            total_ratings=profile.total_ratings,
            total_visits_completed=profile.total_visits_completed,
            documents_count=documents_count,
            created_at=profile.created_at,
        )

    async def list_professionals(
        self,
        *,
        status: VerificationStatus | None,
        professional_type: ProfessionalType | None,
        q: str | None,
        page: int,
        page_size: int,
    ) -> AdminPage[AdminProfessionalListItem]:
        stmt = self._professional_query()
        if status is not None:
            stmt = stmt.where(ProfessionalProfile.verification_status == status)
        if professional_type is not None:
            stmt = stmt.where(ProfessionalProfile.professional_type == professional_type)
        if q:
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(_like(q)),
                    User.phone_number.ilike(_like(q)),
                    User.email.ilike(_like(q)),
                    ProfessionalProfile.council_registration_number.ilike(_like(q)),
                )
            )
        # The queue is worked oldest-first; everything else newest-first.
        queue = status in (VerificationStatus.PENDING, VerificationStatus.IN_REVIEW)
        stmt = stmt.order_by(
            ProfessionalProfile.created_at.asc() if queue else ProfessionalProfile.created_at.desc()
        )
        rows, total = await _paged(self.session, stmt, page, page_size)
        return AdminPage(
            items=[self._professional_item(p, u, n) for p, u, n in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_professional(self, professional_id: uuid.UUID) -> AdminProfessionalDetail:
        row = (
            await self.session.execute(
                self._professional_query().where(ProfessionalProfile.id == professional_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Professional not found.")
        profile, user, documents_count = row

        documents = (
            (
                await self.session.execute(
                    select(ProfessionalDocument)
                    .where(ProfessionalDocument.professional_id == profile.id)
                    .order_by(ProfessionalDocument.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        services = (
            await self.session.execute(
                select(Service.name)
                .join(ProfessionalServiceOptIn, ProfessionalServiceOptIn.service_id == Service.id)
                .where(
                    ProfessionalServiceOptIn.professional_id == profile.id,
                    ProfessionalServiceOptIn.is_active.is_(True),
                )
                .order_by(Service.name)
            )
        ).scalars()
        slots = (
            (
                await self.session.execute(
                    select(ProfessionalAvailabilitySlot)
                    .where(
                        ProfessionalAvailabilitySlot.professional_id == profile.id,
                        ProfessionalAvailabilitySlot.is_active.is_(True),
                    )
                    .order_by(
                        ProfessionalAvailabilitySlot.day_of_week,
                        ProfessionalAvailabilitySlot.start_time,
                    )
                )
            )
            .scalars()
            .all()
        )
        booking_counts = await self.session.execute(
            select(Booking.status, func.count(Booking.id))
            .where(Booking.professional_id == profile.id)
            .group_by(Booking.status)
        )
        point = to_shape(profile.current_location) if profile.current_location else None
        item = self._professional_item(profile, user, documents_count)
        return AdminProfessionalDetail(
            **item.model_dump(),
            bio=profile.bio,
            languages_spoken=profile.languages_spoken,
            service_radius_km=float(profile.base_service_radius_km),
            latitude=point.y if point else None,
            longitude=point.x if point else None,
            documents=[
                AdminDocument(**DocumentService(self.session).professional_out(d).model_dump())
                for d in documents
            ],
            services=list(services),
            availability=[
                AdminSlot(day_of_week=s.day_of_week, start_time=s.start_time, end_time=s.end_time)
                for s in slots
            ],
            bookings_by_status={status.value: n for status, n in booking_counts.all()},
            history=await self.activity(entity_type="professional", entity_id=str(profile.id)),
        )

    async def verification_stats(self) -> VerificationStats:
        now = datetime.now(UTC)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = (
            await self.session.execute(
                select(
                    ProfessionalProfile.professional_type,
                    ProfessionalProfile.verification_status,
                    func.count(ProfessionalProfile.id),
                ).group_by(
                    ProfessionalProfile.professional_type, ProfessionalProfile.verification_status
                )
            )
        ).all()
        by_status = {s.value: 0 for s in VerificationStatus}
        by_type: dict[str, dict[str, int]] = {}
        for ptype, status, n in rows:
            by_status[status.value] += n
            by_type.setdefault(ptype.value, {s.value: 0 for s in VerificationStatus})[
                status.value
            ] = n

        async def onboarded_since(since: datetime) -> int:
            return (
                await self.session.execute(
                    select(func.count(ProfessionalProfile.id)).where(
                        ProfessionalProfile.created_at >= since
                    )
                )
            ).scalar_one()

        async def decided_since(action: str, since: datetime) -> int:
            return (
                await self.session.execute(
                    select(func.count(AuditLog.id)).where(
                        AuditLog.action == action, AuditLog.created_at >= since
                    )
                )
            ).scalar_one()

        approvals = (
            await self.session.execute(
                select(ProfessionalProfile.created_at, ProfessionalProfile.verified_at).where(
                    ProfessionalProfile.verification_status == VerificationStatus.APPROVED,
                    ProfessionalProfile.verified_at >= now - timedelta(days=30),
                )
            )
        ).all()
        hours = [
            (verified - created).total_seconds() / 3600
            for created, verified in approvals
            if verified and created and verified >= created
        ]
        oldest_pending = (
            await self.session.execute(
                select(func.min(ProfessionalProfile.created_at)).where(
                    ProfessionalProfile.verification_status.in_(
                        [VerificationStatus.PENDING, VerificationStatus.IN_REVIEW]
                    )
                )
            )
        ).scalar_one()

        day = func.date(ProfessionalProfile.created_at)
        daily_rows = await self.session.execute(
            select(day, func.count(ProfessionalProfile.id))
            .where(ProfessionalProfile.created_at >= today - timedelta(days=29))
            .group_by(day)
        )
        per_day = dict(daily_rows.all())
        daily = [
            {"date": d.isoformat(), "onboarded": per_day.get(d, 0)}
            for d in ((today - timedelta(days=29 - i)).date() for i in range(30))
        ]
        verification = await ConfigService(self.session).typed("verification", VerificationConfig)
        return VerificationStats(
            total=sum(by_status.values()),
            by_status=by_status,
            by_type=by_type,
            onboarded_today=await onboarded_since(today),
            onboarded_7d=await onboarded_since(now - timedelta(days=7)),
            onboarded_30d=await onboarded_since(now - timedelta(days=30)),
            approved_7d=await decided_since("professional.approved", now - timedelta(days=7)),
            rejected_7d=await decided_since("professional.rejected", now - timedelta(days=7)),
            median_hours_to_approve=round(statistics.median(hours), 1) if hours else None,
            oldest_pending_at=oldest_pending,
            auto_approve=verification.auto_approve,
            daily=daily,
        )

    # ── Users ───────────────────────────────────────────────────────────

    async def list_users(
        self,
        *,
        role: UserRole | None,
        status: UserStatus | None,
        q: str | None,
        page: int,
        page_size: int,
    ) -> AdminPage[AdminUserListItem]:
        bookings = (
            select(func.count(Booking.id))
            .where(Booking.patient_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )
        stmt = select(User, bookings).where(User.deleted_at.is_(None))
        if role is not None:
            stmt = stmt.where(User.role == role)
        if status is not None:
            stmt = stmt.where(User.status == status)
        if q:
            stmt = stmt.where(
                or_(
                    User.full_name.ilike(_like(q)),
                    User.phone_number.ilike(_like(q)),
                    User.email.ilike(_like(q)),
                )
            )
        rows, total = await _paged(
            self.session, stmt.order_by(User.created_at.desc()), page, page_size
        )
        return AdminPage(
            items=[
                AdminUserListItem(
                    id=u.id,
                    full_name=u.full_name,
                    phone_number=u.phone_number,
                    email=u.email,
                    role=u.role,
                    status=u.status,
                    gender=u.gender.value,
                    created_at=u.created_at,
                    last_login_at=u.last_login_at,
                    bookings_count=n,
                )
                for u, n in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def set_user_status(
        self, user_id: uuid.UUID, payload: UserStatusIn, *, actor: User
    ) -> User:
        if user_id == actor.id:
            raise ValidationAppError("You can't change your own account status.")
        user = await self.session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise NotFoundError("User not found.")
        if user.role in ADMIN_ROLES and actor.role != UserRole.SUPER_ADMIN:
            raise ForbiddenError("Only a super admin can suspend another admin.")
        before = user.status
        user.status = UserStatus(payload.status)
        if user.status == UserStatus.SUSPENDED:
            # Their access token is rejected on the next request (see get_current_user);
            # revoking refresh tokens stops them signing straight back in.
            await RefreshTokenRepository(self.session).revoke_all_for_user(
                user.id, now=datetime.now(UTC)
            )
            profile = (
                await self.session.execute(
                    select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id)
                )
            ).scalar_one_or_none()
            if profile is not None:
                profile.is_accepting_bookings = False
        self.audit.log(
            actor_id=actor.id,
            action=f"user.{payload.status}",
            entity_type="user",
            entity_id=str(user.id),
            metadata={"from": before.value, "reason": payload.reason},
        )
        await self.session.flush()
        return user

    # ── Bookings ────────────────────────────────────────────────────────

    def _booking_query(self) -> tuple[Select, type[User]]:
        patient = aliased(User)
        pro_user = aliased(User)
        return (
            select(Booking, patient, pro_user, Address)
            .join(patient, patient.id == Booking.patient_id)
            .outerjoin(ProfessionalProfile, ProfessionalProfile.id == Booking.professional_id)
            .outerjoin(pro_user, pro_user.id == ProfessionalProfile.user_id)
            .outerjoin(Address, Address.id == Booking.address_id)
        ), patient

    @staticmethod
    def _booking_item(
        booking: Booking, patient: User, pro_user: User | None, address: Address | None
    ) -> AdminBookingListItem:
        return AdminBookingListItem(
            id=booking.id,
            booking_code=booking.booking_code,
            status=booking.status,
            service_name=booking.service_name_snapshot,
            scheduled_start_at=booking.scheduled_start_at,
            total_amount=float(booking.total_amount),
            patient_name=patient.full_name,
            patient_phone=patient.phone_number,
            professional_name=pro_user.full_name if pro_user else None,
            city=address.city if address else None,
            created_at=booking.created_at,
        )

    async def list_bookings(
        self,
        *,
        status: BookingStatus | None,
        q: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        page: int,
        page_size: int,
    ) -> AdminPage[AdminBookingListItem]:
        stmt, patient = self._booking_query()
        if status is not None:
            stmt = stmt.where(Booking.status == status)
        if q:
            stmt = stmt.where(
                or_(
                    Booking.booking_code.ilike(_like(q)),
                    patient.full_name.ilike(_like(q)),
                    patient.phone_number.ilike(_like(q)),
                    Booking.service_name_snapshot.ilike(_like(q)),
                )
            )
        if date_from is not None:
            stmt = stmt.where(Booking.scheduled_start_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Booking.scheduled_start_at <= date_to)
        rows, total = await _paged(
            self.session, stmt.order_by(Booking.scheduled_start_at.desc()), page, page_size
        )
        return AdminPage(
            items=[self._booking_item(*row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_booking(self, booking_id: uuid.UUID) -> AdminBookingDetail:
        stmt, _ = self._booking_query()
        row = (await self.session.execute(stmt.where(Booking.id == booking_id))).one_or_none()
        if row is None:
            raise NotFoundError("Booking not found.")
        booking, patient, pro_user, address = row
        visit = (
            await self.session.execute(
                select(BookingVisit).where(BookingVisit.booking_id == booking.id)
            )
        ).scalar_one_or_none()
        history = (
            (
                await self.session.execute(
                    select(BookingStatusHistory)
                    .where(BookingStatusHistory.booking_id == booking.id)
                    .order_by(BookingStatusHistory.created_at)
                )
            )
            .scalars()
            .all()
        )
        rating = (
            await self.session.execute(select(Review.rating).where(Review.booking_id == booking.id))
        ).scalar_one_or_none()
        item = self._booking_item(booking, patient, pro_user, address)
        docs = DocumentService(self.session)
        return AdminBookingDetail(
            **item.model_dump(),
            address=booking.address_snapshot,
            patient_id=patient.id,
            professional_id=booking.professional_id,
            professional_phone=pro_user.phone_number if pro_user else None,
            base_price=float(booking.base_price),
            discount_amount=float(booking.discount_amount),
            platform_fee=float(booking.platform_fee),
            tax_amount=float(booking.tax_amount),
            professional_payout_amount=float(booking.professional_payout_amount),
            patient_notes=booking.patient_notes,
            cancellation_reason=booking.cancellation_reason,
            cancellation_fee_amount=float(booking.cancellation_fee_amount),
            preferred_gender=(booking.extended_attributes or {}).get("preferred_gender"),
            visit_summary_notes=visit.visit_summary_notes if visit else None,
            vitals_recorded=visit.vitals_recorded if visit else None,
            review_rating=rating,
            timeline=[
                StatusEvent(status=h.to_status, at=h.created_at, note=h.reason) for h in history
            ],
            documents=[docs.medical_out(d) for d in await docs.for_booking(booking.id)],
        )

    async def cancel_booking(self, booking_id: uuid.UUID, reason: str, *, actor: User) -> None:
        bookings = BookingService(self.session)
        booking = await bookings.bookings.get_for_update(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        await bookings.cancel(booking, cancelled_by_id=actor.id, reason=reason)
        # An ops cancellation isn't the patient's fault: no fee.
        booking.cancellation_fee_amount = 0
        notifications = NotificationService(self.session)
        await notifications.notify_booking_status(
            booking,
            title="Your booking was cancelled",
            body=f"Our team cancelled your {booking.service_name_snapshot} visit: {reason}",
        )
        if booking.professional_id is not None:
            profile = await self.session.get(ProfessionalProfile, booking.professional_id)
            if profile is not None:
                await notifications.push_to_user(
                    profile.user_id,
                    title="Visit cancelled",
                    body=f"{booking.booking_code} was cancelled by Mendyr support.",
                    data={"template_key": "booking_cancelled", "booking_id": str(booking.id)},
                )
        self.audit.log(
            actor_id=actor.id,
            action="booking.cancel",
            entity_type="booking",
            entity_id=str(booking.id),
            metadata={"reason": reason},
        )

    async def reopen_booking(self, booking_id: uuid.UUID, *, actor: User) -> None:
        """Take a booking off its assigned professional and put it back on the board."""
        bookings = BookingService(self.session)
        booking = await bookings.bookings.get_for_update(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found.")
        if booking.status not in (BookingStatus.ASSIGNED, BookingStatus.CONFIRMED):
            raise ValidationAppError("Only an assigned visit that hasn't started can be reopened.")
        booking.professional_id = None
        await bookings.transition_status(
            booking, BookingStatus.SEARCHING, reason="Reopened by support", changed_by_id=actor.id
        )
        self.audit.log(
            actor_id=actor.id,
            action="booking.reopen",
            entity_type="booking",
            entity_id=str(booking.id),
        )

    # ── Activity ────────────────────────────────────────────────────────

    async def activity(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdminActivity]:
        stmt = (
            select(AuditLog, User.full_name)
            .outerjoin(User, User.id == AuditLog.actor_id)
            .order_by(AuditLog.created_at.desc())
        )
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        rows = (await self.session.execute(stmt.limit(limit).offset(offset))).all()
        return [
            AdminActivity(
                id=log.id,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                actor_name=name,
                metadata=json.loads(log.metadata_json) if log.metadata_json else None,
                created_at=log.created_at,
            )
            for log, name in rows
        ]
