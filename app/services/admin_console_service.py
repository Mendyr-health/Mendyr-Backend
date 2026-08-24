"""Admin console orchestration: generic entity search, dashboard stats, nurse verification
actions, waitlist notify, contact status updates. Backs the Next.js admin portal
(src/features/admin/use{Nurses,Patients,Services,Waitlist,Contacts}.ts) — every method here
returns the camelCase schemas in app.schemas.admin_console, ready to hand back via ApiResponse.
"""

import json
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ContactInquiryStatus, VerificationStatus
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.audit import AuditLog
from app.models.contact import ContactInquiry
from app.models.patient import PatientProfile
from app.models.professional import ProfessionalDocument, ProfessionalProfile
from app.models.service import Service
from app.models.user import User
from app.models.waitlist import WaitlistEntry
from app.repositories.contact_repo import ContactRepository
from app.repositories.patient_repo import PatientRepository
from app.repositories.professional_repo import ProfessionalRepository
from app.repositories.waitlist_repo import WaitlistRepository
from app.schemas.admin_console import (
    AuditLogOut,
    ContactAdminOut,
    DashboardStatsOut,
    NurseAdminOut,
    NurseDocumentOut,
    PatientAdminOut,
    SearchEntity,
    SearchResultItem,
    ServiceAdminOut,
    UserMiniOut,
    WaitlistAdminOut,
)
from app.schemas.professional import ProfessionalReviewDecisionIn
from app.services.catalog_service import CatalogService
from app.services.professional_service import ProfessionalService


def _user_mini_out(user: User) -> UserMiniOut:
    return UserMiniOut(
        public_id=user.id,
        email=user.email,
        phone=user.phone_number,
        full_name=user.full_name,
        role=user.role,
        status=user.status.value,
        email_verified=user.email_verified,
        avatar_url=user.avatar_url,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _nurse_document_out(document: ProfessionalDocument) -> NurseDocumentOut:
    return NurseDocumentOut(
        public_id=document.id,
        type=document.document_type.value,
        file_name=os.path.basename(document.file_url),
        file_url=document.file_url,
        verified=document.verification_status == VerificationStatus.APPROVED,
        created_at=document.created_at,
    )


def nurse_admin_out(profile: ProfessionalProfile) -> NurseAdminOut:
    return NurseAdminOut(
        public_id=profile.id,
        user=_user_mini_out(profile.user),
        gender=profile.user.gender.value,
        date_of_birth=profile.user.date_of_birth,
        address=profile.address_line,
        city=profile.city,
        state=profile.state,
        experience=profile.experience_description,
        qualifications=_split_csv(profile.qualifications),
        certifications=_split_csv(profile.certifications),
        verification_status=profile.verification_status,
        preferred_contact=profile.preferred_contact,
        documents=[_nurse_document_out(doc) for doc in profile.documents],
        created_at=profile.created_at,
    )


def patient_admin_out(profile: PatientProfile) -> PatientAdminOut:
    return PatientAdminOut(
        public_id=profile.id,
        user=_user_mini_out(profile.user),
        address=profile.address_line,
        city=profile.city,
        state=profile.state,
        registration_status=profile.user.status.value,
        created_at=profile.created_at,
    )


def service_admin_out(service: Service) -> ServiceAdminOut:
    short_desc = (
        (service.description[:120] + "…")
        if service.description and len(service.description) > 120
        else service.description
    )
    return ServiceAdminOut(
        public_id=service.id,
        name=service.name,
        slug=service.slug,
        description=service.description,
        short_desc=short_desc,
        hero_image=None,
        icon=None,
        features=[],
        pricing_range=f"₹{service.base_price:.0f}",
        is_active=service.is_active,
        seo_title=None,
        seo_description=None,
        created_at=service.created_at,
    )


def waitlist_admin_out(entry: WaitlistEntry) -> WaitlistAdminOut:
    return WaitlistAdminOut(
        public_id=entry.id,
        email=entry.email,
        name=entry.name,
        phone=entry.phone,
        source=entry.source,
        notified=entry.notified,
        created_at=entry.created_at,
    )


def contact_admin_out(inquiry: ContactInquiry) -> ContactAdminOut:
    return ContactAdminOut(
        public_id=inquiry.id,
        name=inquiry.name,
        email=inquiry.email,
        phone=inquiry.phone,
        subject=inquiry.subject,
        message=inquiry.message,
        status=inquiry.status,
        created_at=inquiry.created_at,
    )


class AdminConsoleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.professionals = ProfessionalRepository(session)
        self.patients = PatientRepository(session)
        self.waitlist = WaitlistRepository(session)
        self.contacts = ContactRepository(session)
        self.catalog = CatalogService(session)

    # ── Generic search (GET /api/v1/search?entity=...) ─────────────────────────────

    async def search(
        self,
        *,
        entity: SearchEntity,
        q: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[SearchResultItem], int]:
        if entity == "nurses":
            verification_status = VerificationStatus(status) if status else None
            nurse_profiles, total = await self.professionals.search(
                q=q, verification_status=verification_status, limit=limit, offset=offset
            )
            return [nurse_admin_out(p) for p in nurse_profiles], total

        if entity == "patients":
            patient_profiles, total = await self.patients.search(q=q, limit=limit, offset=offset)
            return [patient_admin_out(p) for p in patient_profiles], total

        if entity == "services":
            services, total = await self.catalog.search_services(q=q, limit=limit, offset=offset)
            return [service_admin_out(s) for s in services], total

        if entity == "waitlist":
            entries, total = await self.waitlist.search(q=q, limit=limit, offset=offset)
            return [waitlist_admin_out(e) for e in entries], total

        if entity == "contacts":
            contact_status = ContactInquiryStatus(status) if status else None
            inquiries, total = await self.contacts.search(
                q=q, status=contact_status, limit=limit, offset=offset
            )
            return [contact_admin_out(c) for c in inquiries], total

        raise ValidationAppError(f"Unsupported search entity: {entity}")

    # ── Nurse verification (delegates to the existing KYC review flow) ─────────────

    async def review_nurse(
        self,
        professional_id: uuid.UUID,
        *,
        approve: bool,
        rejection_reason: str | None,
        reviewer_id: uuid.UUID,
    ) -> NurseAdminOut:
        decision = ProfessionalReviewDecisionIn(approve=approve, rejection_reason=rejection_reason)
        await ProfessionalService(self.session).review_kyc(
            professional_id, decision, reviewer_id=reviewer_id
        )
        profile = await self.professionals.get_with_relations(professional_id)
        if profile is None:
            raise NotFoundError("Professional not found.")

        self.session.add(
            AuditLog(
                actor_id=reviewer_id,
                action="nurse.approve" if approve else "nurse.reject",
                entity_type="professional_profile",
                entity_id=str(professional_id),
                metadata_json=json.dumps(
                    {"new_value": {"verificationStatus": profile.verification_status.value}}
                ),
                created_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return nurse_admin_out(profile)

    # ── Waitlist ─────────────────────────────────────────────────────────────────

    async def mark_waitlist_notified(self, waitlist_id: uuid.UUID) -> WaitlistAdminOut:
        entry = await self.waitlist.get(waitlist_id)
        if entry is None:
            raise NotFoundError("Waitlist entry not found.")
        entry.notified = True
        await self.session.flush()
        return waitlist_admin_out(entry)

    # ── Contact inquiries ────────────────────────────────────────────────────────

    async def update_contact_status(
        self, contact_id: uuid.UUID, status: ContactInquiryStatus
    ) -> ContactAdminOut:
        inquiry = await self.contacts.get(contact_id)
        if inquiry is None:
            raise NotFoundError("Contact inquiry not found.")
        inquiry.status = status
        await self.session.flush()
        return contact_admin_out(inquiry)

    # ── Dashboard stats ──────────────────────────────────────────────────────────

    async def get_dashboard_stats(self, *, recent_activity_limit: int = 10) -> DashboardStatsOut:
        total_patients = (
            await self.session.execute(select(func.count(PatientProfile.id)))
        ).scalar_one()
        total_nurses = await self.professionals.count_all()
        pending_verifications = await self.professionals.count_pending()
        waitlist_count = await self.waitlist.count_all()
        new_contacts = await self.contacts.count_by_status(ContactInquiryStatus.NEW)

        result = await self.session.execute(
            select(AuditLog, User.full_name, User.email)
            .outerjoin(User, User.id == AuditLog.actor_id)
            .order_by(AuditLog.created_at.desc())
            .limit(recent_activity_limit)
        )
        recent_activity = [
            _audit_log_out(log, actor_name, actor_email)
            for log, actor_name, actor_email in result.all()
        ]

        return DashboardStatsOut(
            total_patients=total_patients,
            total_nurses=total_nurses,
            pending_verifications=pending_verifications,
            waitlist_count=waitlist_count,
            new_contacts=new_contacts,
            recent_activity=recent_activity,
        )


def _audit_log_out(log: AuditLog, actor_name: str | None, actor_email: str | None) -> AuditLogOut:
    # GAP: AuditLog stores a single `metadata_json` blob rather than discrete old/new value
    # columns. When it was written as {"old_value": ..., "new_value": ...} we split it back
    # out; otherwise the whole blob is surfaced as newValue. See final report.
    old_value = None
    new_value = None
    if log.metadata_json:
        try:
            parsed = json.loads(log.metadata_json)
        except (TypeError, ValueError):
            parsed = log.metadata_json
        if isinstance(parsed, dict) and ("old_value" in parsed or "new_value" in parsed):
            old_value = parsed.get("old_value")
            new_value = parsed.get("new_value")
        else:
            new_value = parsed

    return AuditLogOut(
        id=str(log.id),
        actor_name=actor_name,
        actor_email=actor_email,
        action=log.action,
        resource=log.entity_type,
        resource_id=log.entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=log.ip_address,
        created_at=log.created_at,
    )
