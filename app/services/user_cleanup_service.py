"""Service for permanently hard-deleting users and all associated reference records.

Unlike soft-deletion (which only marks `status=DELETED`), this service cascades
through all foreign key relationships in strict dependency order, clearing foreign
key pointers and deleting dependent records across every table before removing
the user accounts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Sequence

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.address import Address
from app.models.audit import AuditLog
from app.models.booking import (
    Booking,
    BookingOffer,
    BookingStatusHistory,
    BookingVisit,
    CarePlan,
    VisitTrackingPing,
)
from app.models.notification import Notification
from app.models.patient import PatientProfile
from app.models.payment import Payment, Payout
from app.models.professional import (
    ProfessionalAvailabilitySlot,
    ProfessionalDocument,
    ProfessionalProfile,
    ProfessionalSpecialization,
)
from app.models.review import Review
from app.models.service import ProfessionalService
from app.models.support import SupportTicket, SupportTicketMessage
from app.models.user import DeviceToken, OTPVerification, RefreshToken, User
from app.models.wallet import CouponRedemption, Wallet, WalletTransaction


@dataclass
class UserInfo:
    id: uuid.UUID
    email: str | None
    phone_number: str | None
    role: str
    full_name: str


@dataclass
class UserCleanupSummary:
    requested_identifiers: list[str] = field(default_factory=list)
    found_users: list[UserInfo] = field(default_factory=list)
    not_found_identifiers: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "requested_identifiers": self.requested_identifiers,
            "found_users": [
                {
                    "id": str(u.id),
                    "email": u.email,
                    "phone_number": u.phone_number,
                    "role": u.role,
                    "full_name": u.full_name,
                }
                for u in self.found_users
            ],
            "not_found_identifiers": self.not_found_identifiers,
            "counts": self.counts,
            "dry_run": self.dry_run,
        }


def parse_user_identifiers(identifiers: str | Sequence[str]) -> list[str]:
    """Parse a comma-separated string or sequence of identifiers into a cleaned list."""
    if isinstance(identifiers, str):
        raw_list = identifiers.split(",")
    else:
        raw_list = []
        for item in identifiers:
            raw_list.extend(item.split(","))

    cleaned: list[str] = []
    seen: set[str] = set()
    for token in raw_list:
        stripped = token.strip().strip("'\"")
        if stripped and stripped not in seen:
            seen.add(stripped)
            cleaned.append(stripped)
    return cleaned


class UserCleanupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def delete_users(
        self,
        identifiers: str | Sequence[str],
        *,
        dry_run: bool = False,
    ) -> UserCleanupSummary:
        """Purge the specified users and all their referencing data from every table.

        Parameters
        ----------
        identifiers:
            Comma-separated string or collection of emails / user UUIDs.
        dry_run:
            When True, runs the queries inside a transaction to validate constraints
            and calculate counts, but rolls back at the end without committing.
        """
        parsed = parse_user_identifiers(identifiers)
        summary = UserCleanupSummary(requested_identifiers=parsed, dry_run=dry_run)
        if not parsed:
            return summary

        uuids_to_lookup: list[uuid.UUID] = []
        emails_to_lookup: list[str] = []

        for item in parsed:
            try:
                uuids_to_lookup.append(uuid.UUID(item))
            except ValueError:
                emails_to_lookup.append(item.lower())

        conditions = []
        if uuids_to_lookup:
            conditions.append(User.id.in_(uuids_to_lookup))
        if emails_to_lookup:
            conditions.append(User.email.in_(emails_to_lookup))

        result = await self.session.execute(select(User).where(or_(*conditions)))
        users = result.scalars().all()

        found_uuids: set[str] = set()
        found_emails: set[str] = set()

        for u in users:
            found_uuids.add(str(u.id))
            if u.email:
                found_emails.add(u.email.lower())
            summary.found_users.append(
                UserInfo(
                    id=u.id,
                    email=u.email,
                    phone_number=u.phone_number,
                    role=u.role.value if hasattr(u.role, "value") else str(u.role),
                    full_name=u.full_name,
                )
            )

        for item in parsed:
            if item.lower() not in found_emails and item not in found_uuids:
                summary.not_found_identifiers.append(item)

        if not users:
            return summary

        user_ids = [u.id for u in users]
        user_id_strs = [str(u.id) for u in users]
        user_phones = [u.phone_number for u in users if u.phone_number]

        # -------------------------------------------------------------------------
        # Collect related IDs for cascade
        # -------------------------------------------------------------------------
        pro_profiles_res = await self.session.execute(
            select(ProfessionalProfile.id).where(ProfessionalProfile.user_id.in_(user_ids))
        )
        pro_profile_ids = [r[0] for r in pro_profiles_res.all()]

        patient_bookings_res = await self.session.execute(
            select(Booking.id).where(Booking.patient_id.in_(user_ids))
        )
        patient_booking_ids = [r[0] for r in patient_bookings_res.all()]

        care_plans_res = await self.session.execute(
            select(CarePlan.id).where(CarePlan.patient_id.in_(user_ids))
        )
        care_plan_ids = [r[0] for r in care_plans_res.all()]

        ticket_conditions = [SupportTicket.raised_by_id.in_(user_ids)]
        if patient_booking_ids:
            ticket_conditions.append(SupportTicket.booking_id.in_(patient_booking_ids))
        tickets_res = await self.session.execute(
            select(SupportTicket.id).where(or_(*ticket_conditions))
        )
        ticket_ids = [r[0] for r in tickets_res.all()]

        visit_ids: list[uuid.UUID] = []
        if patient_booking_ids:
            visits_res = await self.session.execute(
                select(BookingVisit.id).where(BookingVisit.booking_id.in_(patient_booking_ids))
            )
            visit_ids = [r[0] for r in visits_res.all()]

        wallets_res = await self.session.execute(
            select(Wallet.id).where(Wallet.user_id.in_(user_ids))
        )
        wallet_ids = [r[0] for r in wallets_res.all()]

        counts: dict[str, int] = {}

        # -------------------------------------------------------------------------
        # 1. Clear foreign key references pointing to target users/profiles
        # -------------------------------------------------------------------------
        res = await self.session.execute(
            update(User).where(User.referred_by_id.in_(user_ids)).values(referred_by_id=None)
        )
        if res.rowcount:
            counts["users.referred_by_id_cleared"] = res.rowcount

        res = await self.session.execute(
            update(ProfessionalDocument)
            .where(ProfessionalDocument.reviewed_by_id.in_(user_ids))
            .values(reviewed_by_id=None)
        )
        if res.rowcount:
            counts["professional_documents.reviewed_by_id_cleared"] = res.rowcount

        res = await self.session.execute(
            update(BookingStatusHistory)
            .where(BookingStatusHistory.changed_by_id.in_(user_ids))
            .values(changed_by_id=None)
        )
        if res.rowcount:
            counts["booking_status_history.changed_by_id_cleared"] = res.rowcount

        res = await self.session.execute(
            update(Booking).where(Booking.cancelled_by_id.in_(user_ids)).values(cancelled_by_id=None)
        )
        if res.rowcount:
            counts["bookings.cancelled_by_id_cleared"] = res.rowcount

        if pro_profile_ids:
            other_bookings_filter = [Booking.professional_id.in_(pro_profile_ids)]
            if patient_booking_ids:
                other_bookings_filter.append(~Booking.id.in_(patient_booking_ids))
            res = await self.session.execute(
                update(Booking).where(*other_bookings_filter).values(professional_id=None)
            )
            if res.rowcount:
                counts["other_bookings.professional_id_unassigned"] = res.rowcount

            other_plans_filter = [CarePlan.preferred_professional_id.in_(pro_profile_ids)]
            if care_plan_ids:
                other_plans_filter.append(~CarePlan.id.in_(care_plan_ids))
            res = await self.session.execute(
                update(CarePlan).where(*other_plans_filter).values(preferred_professional_id=None)
            )
            if res.rowcount:
                counts["other_care_plans.preferred_professional_id_cleared"] = res.rowcount

        other_tickets_filter = [SupportTicket.assigned_to_id.in_(user_ids)]
        if ticket_ids:
            other_tickets_filter.append(~SupportTicket.id.in_(ticket_ids))
        res = await self.session.execute(
            update(SupportTicket).where(*other_tickets_filter).values(assigned_to_id=None)
        )
        if res.rowcount:
            counts["other_support_tickets.assigned_to_id_cleared"] = res.rowcount

        if patient_booking_ids:
            res = await self.session.execute(
                update(WalletTransaction)
                .where(WalletTransaction.reference_booking_id.in_(patient_booking_ids))
                .values(reference_booking_id=None)
            )
            if res.rowcount:
                counts["wallet_transactions.reference_booking_id_cleared"] = res.rowcount

        res = await self.session.execute(
            update(AuditLog).where(AuditLog.actor_id.in_(user_ids)).values(actor_id=None)
        )
        if res.rowcount:
            counts["audit_logs.actor_id_cleared"] = res.rowcount

        await self.session.flush()

        # -------------------------------------------------------------------------
        # 2. Support tickets and messages
        # -------------------------------------------------------------------------
        msg_filter = [SupportTicketMessage.sender_id.in_(user_ids)]
        if ticket_ids:
            msg_filter.append(SupportTicketMessage.ticket_id.in_(ticket_ids))
        res = await self.session.execute(delete(SupportTicketMessage).where(or_(*msg_filter)))
        if res.rowcount:
            counts["support_ticket_messages"] = res.rowcount

        if ticket_ids:
            res = await self.session.execute(
                delete(SupportTicket).where(SupportTicket.id.in_(ticket_ids))
            )
            if res.rowcount:
                counts["support_tickets"] = res.rowcount

        await self.session.flush()

        # -------------------------------------------------------------------------
        # 3. Reviews
        # -------------------------------------------------------------------------
        rev_filter = [Review.reviewer_id.in_(user_ids), Review.reviewee_id.in_(user_ids)]
        if patient_booking_ids:
            rev_filter.append(Review.booking_id.in_(patient_booking_ids))
        res = await self.session.execute(delete(Review).where(or_(*rev_filter)))
        if res.rowcount:
            counts["reviews"] = res.rowcount

        # -------------------------------------------------------------------------
        # 4. Coupon redemptions
        # -------------------------------------------------------------------------
        redemp_filter = [CouponRedemption.user_id.in_(user_ids)]
        if patient_booking_ids:
            redemp_filter.append(CouponRedemption.booking_id.in_(patient_booking_ids))
        res = await self.session.execute(delete(CouponRedemption).where(or_(*redemp_filter)))
        if res.rowcount:
            counts["coupon_redemptions"] = res.rowcount

        # -------------------------------------------------------------------------
        # 5. Payments
        # -------------------------------------------------------------------------
        pay_filter = [Payment.user_id.in_(user_ids)]
        if patient_booking_ids:
            pay_filter.append(Payment.booking_id.in_(patient_booking_ids))
        res = await self.session.execute(delete(Payment).where(or_(*pay_filter)))
        if res.rowcount:
            counts["payments"] = res.rowcount

        # -------------------------------------------------------------------------
        # 6. Booking visits and tracking pings
        # -------------------------------------------------------------------------
        if visit_ids:
            res = await self.session.execute(
                delete(VisitTrackingPing).where(VisitTrackingPing.visit_id.in_(visit_ids))
            )
            if res.rowcount:
                counts["visit_tracking_pings"] = res.rowcount

        if patient_booking_ids:
            res = await self.session.execute(
                delete(BookingVisit).where(BookingVisit.booking_id.in_(patient_booking_ids))
            )
            if res.rowcount:
                counts["booking_visits"] = res.rowcount

        # -------------------------------------------------------------------------
        # 7. Booking status history & offers
        # -------------------------------------------------------------------------
        if patient_booking_ids:
            res = await self.session.execute(
                delete(BookingStatusHistory).where(
                    BookingStatusHistory.booking_id.in_(patient_booking_ids)
                )
            )
            if res.rowcount:
                counts["booking_status_history"] = res.rowcount

        offer_filter = []
        if patient_booking_ids:
            offer_filter.append(BookingOffer.booking_id.in_(patient_booking_ids))
        if pro_profile_ids:
            offer_filter.append(BookingOffer.professional_id.in_(pro_profile_ids))
        if offer_filter:
            res = await self.session.execute(delete(BookingOffer).where(or_(*offer_filter)))
            if res.rowcount:
                counts["booking_offers"] = res.rowcount

        await self.session.flush()

        # -------------------------------------------------------------------------
        # 8. Bookings
        # -------------------------------------------------------------------------
        if patient_booking_ids:
            res = await self.session.execute(
                delete(Booking).where(Booking.id.in_(patient_booking_ids))
            )
            if res.rowcount:
                counts["bookings"] = res.rowcount

        # -------------------------------------------------------------------------
        # 9. Care plans
        # -------------------------------------------------------------------------
        if care_plan_ids:
            res = await self.session.execute(
                delete(CarePlan).where(CarePlan.id.in_(care_plan_ids))
            )
            if res.rowcount:
                counts["care_plans"] = res.rowcount

        await self.session.flush()

        # -------------------------------------------------------------------------
        # 10. Addresses
        # -------------------------------------------------------------------------
        res = await self.session.execute(delete(Address).where(Address.user_id.in_(user_ids)))
        if res.rowcount:
            counts["addresses"] = res.rowcount

        # -------------------------------------------------------------------------
        # 11. Wallets & Wallet Transactions
        # -------------------------------------------------------------------------
        if wallet_ids:
            res = await self.session.execute(
                delete(WalletTransaction).where(WalletTransaction.wallet_id.in_(wallet_ids))
            )
            if res.rowcount:
                counts["wallet_transactions"] = res.rowcount

            res = await self.session.execute(delete(Wallet).where(Wallet.id.in_(wallet_ids)))
            if res.rowcount:
                counts["wallets"] = res.rowcount

        # -------------------------------------------------------------------------
        # 12. Professional Profiles and dependent records
        # -------------------------------------------------------------------------
        if pro_profile_ids:
            res = await self.session.execute(
                delete(Payout).where(Payout.professional_id.in_(pro_profile_ids))
            )
            if res.rowcount:
                counts["payouts"] = res.rowcount

            res = await self.session.execute(
                delete(ProfessionalDocument).where(
                    ProfessionalDocument.professional_id.in_(pro_profile_ids)
                )
            )
            if res.rowcount:
                counts["professional_documents"] = res.rowcount

            res = await self.session.execute(
                delete(ProfessionalSpecialization).where(
                    ProfessionalSpecialization.professional_id.in_(pro_profile_ids)
                )
            )
            if res.rowcount:
                counts["professional_specializations"] = res.rowcount

            res = await self.session.execute(
                delete(ProfessionalAvailabilitySlot).where(
                    ProfessionalAvailabilitySlot.professional_id.in_(pro_profile_ids)
                )
            )
            if res.rowcount:
                counts["professional_availability_slots"] = res.rowcount

            res = await self.session.execute(
                delete(ProfessionalService).where(
                    ProfessionalService.professional_id.in_(pro_profile_ids)
                )
            )
            if res.rowcount:
                counts["professional_services"] = res.rowcount

            res = await self.session.execute(
                delete(ProfessionalProfile).where(ProfessionalProfile.id.in_(pro_profile_ids))
            )
            if res.rowcount:
                counts["professional_profiles"] = res.rowcount

        # -------------------------------------------------------------------------
        # 13. Patient Profiles
        # -------------------------------------------------------------------------
        res = await self.session.execute(
            delete(PatientProfile).where(PatientProfile.user_id.in_(user_ids))
        )
        if res.rowcount:
            counts["patient_profiles"] = res.rowcount

        # -------------------------------------------------------------------------
        # 14. Notifications, Device Tokens, OTPs, Refresh Tokens
        # -------------------------------------------------------------------------
        res = await self.session.execute(
            delete(Notification).where(Notification.user_id.in_(user_ids))
        )
        if res.rowcount:
            counts["notifications"] = res.rowcount

        res = await self.session.execute(
            delete(DeviceToken).where(DeviceToken.user_id.in_(user_ids))
        )
        if res.rowcount:
            counts["device_tokens"] = res.rowcount

        res = await self.session.execute(
            delete(RefreshToken).where(RefreshToken.user_id.in_(user_ids))
        )
        if res.rowcount:
            counts["refresh_tokens"] = res.rowcount

        if user_phones:
            res = await self.session.execute(
                delete(OTPVerification).where(OTPVerification.phone_number.in_(user_phones))
            )
            if res.rowcount:
                counts["otp_verifications"] = res.rowcount

        # -------------------------------------------------------------------------
        # 15. Audit Logs for user entities
        # -------------------------------------------------------------------------
        res = await self.session.execute(
            delete(AuditLog).where(
                AuditLog.entity_type == "user", AuditLog.entity_id.in_(user_id_strs)
            )
        )
        if res.rowcount:
            counts["audit_logs (user entity)"] = res.rowcount

        await self.session.flush()

        # -------------------------------------------------------------------------
        # 16. Finally delete Users
        # -------------------------------------------------------------------------
        res = await self.session.execute(delete(User).where(User.id.in_(user_ids)))
        counts["users"] = res.rowcount

        if dry_run:
            await self.session.rollback()
        else:
            await self.session.commit()

        summary.counts = counts
        return summary

