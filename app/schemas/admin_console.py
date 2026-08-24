"""Admin-console-facing schemas for the Next.js admin portal (src/types/index.ts) — nurses,
patients, service catalogue CRUD, waitlist, contact inquiries, audit log, dashboard stats.

All camelCase (CamelModel/CamelORMModel), matching the frontend exactly. See
src/features/admin/use{Nurses,Patients,Services,Waitlist,Contacts}.ts and
src/types/index.ts (NurseProfilePublic, PatientProfilePublic, ServicePublic,
WaitlistEntryPublic, ContactInquiryPublic, AuditLogPublic, DashboardStats, SearchParams).
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.core.constants import (
    ContactInquiryStatus,
    PreferredContactMethod,
    ProfessionalType,
    UserRole,
    VerificationStatus,
)
from app.schemas.common import CamelModel

# ─── Shared: embedded user (mirrors UserPublic in src/types/index.ts) ────────


class UserMiniOut(CamelModel):
    public_id: uuid.UUID
    email: str | None
    phone: str | None
    full_name: str
    role: UserRole
    status: str
    email_verified: bool
    avatar_url: str | None
    last_login_at: datetime | None
    created_at: datetime


# ─── Nurse (ProfessionalProfile) ──────────────────────────────────────────


class NurseDocumentOut(CamelModel):
    public_id: uuid.UUID
    type: str
    file_name: str
    file_url: str
    verified: bool
    created_at: datetime


class NurseAdminOut(CamelModel):
    public_id: uuid.UUID
    user: UserMiniOut
    gender: str | None
    date_of_birth: datetime | None
    address: str | None
    city: str | None
    state: str | None
    experience: str | None
    qualifications: list[str]
    certifications: list[str]
    verification_status: VerificationStatus
    preferred_contact: PreferredContactMethod | None
    documents: list[NurseDocumentOut]
    created_at: datetime


class NurseVerificationActionIn(CamelModel):
    """Body for POST /admin/nurses/{publicId}/reject — rejection_reason is required by the
    underlying review flow (ProfessionalService.review_kyc); optional here so approve can
    reuse the same schema with an empty body."""

    rejection_reason: str | None = None


# ─── Patient ───────────────────────────────────────────────────────────────


class PatientAdminOut(CamelModel):
    public_id: uuid.UUID
    user: UserMiniOut
    address: str | None
    city: str | None
    state: str | None
    # GAP: PatientProfile has no registration/status column — derived from the linked User's
    # status (active/suspended/deleted) as the closest available proxy. See final report.
    registration_status: str
    created_at: datetime


# ─── Service catalogue ───────────────────────────────────────────────────


class ServiceAdminOut(CamelModel):
    public_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    # GAP: shortDesc/heroImage/icon/features/seoTitle/seoDescription don't exist as columns on
    # Service — derived (shortDesc) or left null/empty (the rest). See final report.
    short_desc: str | None
    hero_image: str | None
    icon: str | None
    features: list[str]
    pricing_range: str | None
    is_active: bool
    seo_title: str | None
    seo_description: str | None
    created_at: datetime


class ServiceCreateIn(CamelModel):
    category_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=200)
    description: str | None = None
    required_professional_type: ProfessionalType
    duration_minutes: int = Field(gt=0)
    base_price: float = Field(ge=0)
    is_recurring_eligible: bool = False
    requires_prescription: bool = False
    display_order: int = 0


class ServiceUpdateIn(CamelModel):
    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=200)
    slug: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    required_professional_type: ProfessionalType | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    base_price: float | None = Field(default=None, ge=0)
    is_recurring_eligible: bool | None = None
    requires_prescription: bool | None = None
    display_order: int | None = None
    is_active: bool | None = None


# ─── Waitlist ─────────────────────────────────────────────────────────────


class WaitlistAdminOut(CamelModel):
    public_id: uuid.UUID
    email: str
    name: str | None
    phone: str | None
    source: str | None
    notified: bool
    created_at: datetime


# ─── Contact inquiries ────────────────────────────────────────────────────


class ContactAdminOut(CamelModel):
    public_id: uuid.UUID
    name: str
    email: str
    phone: str | None
    subject: str
    message: str
    status: ContactInquiryStatus
    created_at: datetime


class ContactStatusUpdateIn(CamelModel):
    # GAP: the frontend UI (WebAdminContacts) offers NEW/READ/REPLIED/ARCHIVED, but the backend
    # ContactInquiryStatus enum (app/core/constants.py) is NEW/IN_PROGRESS/RESOLVED — the two
    # never migrated to the same vocabulary. Exposing the real backend enum here; see final report.
    status: ContactInquiryStatus


# ─── Audit log ────────────────────────────────────────────────────────────


class AuditLogOut(CamelModel):
    id: str
    actor_name: str | None
    actor_email: str | None
    action: str
    resource: str
    resource_id: str | None
    old_value: Any | None
    new_value: Any | None
    ip_address: str | None
    created_at: datetime


# ─── Dashboard stats ──────────────────────────────────────────────────────


class DashboardStatsOut(CamelModel):
    total_patients: int
    total_nurses: int
    pending_verifications: int
    waitlist_count: int
    new_contacts: int
    recent_activity: list[AuditLogOut]


# ─── Generic search ───────────────────────────────────────────────────────

SearchEntity = Literal["nurses", "patients", "services", "contacts", "waitlist"]

SearchResultItem = (
    NurseAdminOut | PatientAdminOut | ServiceAdminOut | ContactAdminOut | WaitlistAdminOut
)
