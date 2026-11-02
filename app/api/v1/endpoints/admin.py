"""Internal ops/admin operations for the config portal: professional verification, users,
bookings, catalogue, dashboard analytics and the activity log. Nothing under this router is
reachable by patient/professional accounts — reads need ops or admin, writes that change
policy or catalogue need admin (super admin)."""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import BookingStatus, ProfessionalType, UserRole, UserStatus
from app.core.constants import VerificationStatus as VStatus
from app.core.permissions import require_admin, require_ops_or_admin
from app.db.session import get_db
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.schemas.admin import (
    AdminActivity,
    AdminBookingDetail,
    AdminBookingListItem,
    AdminCancelIn,
    AdminPage,
    AdminProfessionalDetail,
    AdminProfessionalListItem,
    AdminUserListItem,
    UserStatusIn,
    VerificationStats,
)
from app.schemas.admin_analytics import DashboardOverviewOut
from app.schemas.common import MessageResponse
from app.schemas.document import DocumentReviewIn
from app.schemas.professional import ProfessionalRead, ProfessionalReviewDecisionIn
from app.schemas.service import (
    CategoryAdminRead,
    CategoryWriteIn,
    ServiceAdminRead,
    ServiceWriteIn,
)
from app.services.admin_analytics_service import AdminAnalyticsService
from app.services.admin_service import AdminService
from app.services.catalog_service import CatalogService
from app.services.document_service import DocumentService
from app.services.professional_service import ProfessionalService, to_professional_read

router = APIRouter(prefix="/admin", tags=["admin"])

PageNo = Query(default=1, ge=1)
PageSize = Query(default=20, ge=1, le=100)


# ── Verification ────────────────────────────────────────────────────────


@router.get("/professionals", response_model=AdminPage[AdminProfessionalListItem])
async def list_professionals(
    status: VStatus | None = Query(default=None),
    professional_type: ProfessionalType | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    page: int = PageNo,
    page_size: int = PageSize,
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminPage[AdminProfessionalListItem]:
    """Every professional, filterable by verification status, type and a name/phone/email/
    registration-number search. Pending/in-review lists come oldest first (the queue)."""
    return await AdminService(db).list_professionals(
        status=status, professional_type=professional_type, q=q, page=page, page_size=page_size
    )


@router.get("/professionals/stats", response_model=VerificationStats)
async def verification_stats(
    current_user: User = Depends(require_ops_or_admin), db: AsyncSession = Depends(get_db)
) -> VerificationStats:
    """Onboarded / in queue / approved / rejected counts, per type, plus a 30-day trend."""
    return await AdminService(db).verification_stats()


@router.get("/professionals/pending", response_model=list[ProfessionalRead])
async def list_pending_professionals(
    current_user: User = Depends(require_ops_or_admin), db: AsyncSession = Depends(get_db)
) -> list[ProfessionalRead]:
    """Kept for older portal builds — prefer `GET /admin/professionals?status=pending`."""
    result = await db.execute(
        select(ProfessionalProfile).where(
            ProfessionalProfile.verification_status.in_([VStatus.PENDING, VStatus.IN_REVIEW])
        )
    )
    return [to_professional_read(profile) for profile in result.scalars().all()]


@router.get("/professionals/{professional_id}", response_model=AdminProfessionalDetail)
async def get_professional(
    professional_id: uuid.UUID,
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminProfessionalDetail:
    return await AdminService(db).get_professional(professional_id)


@router.post("/professionals/{professional_id}/review", response_model=AdminProfessionalDetail)
async def review_professional(
    professional_id: uuid.UUID,
    decision: ProfessionalReviewDecisionIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminProfessionalDetail:
    """Approve, reject (with a reason the professional sees) or mark in review. Super admins
    only; the professional is notified and the decision is logged."""
    await ProfessionalService(db).review_kyc(professional_id, decision, reviewer_id=current_user.id)
    return await AdminService(db).get_professional(professional_id)


@router.post(
    "/professionals/{professional_id}/documents/{document_id}/review",
    response_model=AdminProfessionalDetail,
)
async def review_document(
    professional_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: DocumentReviewIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminProfessionalDetail:
    """Approve or reject one document (a rejection asks the professional to re-upload)."""
    await DocumentService(db).review_professional(
        document_id, professional_id, payload, actor_id=current_user.id
    )
    return await AdminService(db).get_professional(professional_id)


@router.delete(
    "/professionals/{professional_id}/documents/{document_id}",
    response_model=AdminProfessionalDetail,
)
async def delete_document(
    professional_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminProfessionalDetail:
    """Remove a document and its file (e.g. an approved one that has to be replaced)."""
    await DocumentService(db).admin_delete_professional(
        document_id, professional_id, actor_id=current_user.id
    )
    return await AdminService(db).get_professional(professional_id)


# ── Users ───────────────────────────────────────────────────────────────


@router.get("/users", response_model=AdminPage[AdminUserListItem])
async def list_users(
    role: UserRole | None = Query(default=None),
    status: UserStatus | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    page: int = PageNo,
    page_size: int = PageSize,
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminPage[AdminUserListItem]:
    return await AdminService(db).list_users(
        role=role, status=status, q=q, page=page, page_size=page_size
    )


@router.patch("/users/{user_id}/status", response_model=MessageResponse)
async def set_user_status(
    user_id: uuid.UUID,
    payload: UserStatusIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Suspend (signs them out everywhere) or reactivate an account."""
    user = await AdminService(db).set_user_status(user_id, payload, actor=current_user)
    return MessageResponse(message=f"{user.full_name} is now {user.status.value}.")


# ── Bookings ────────────────────────────────────────────────────────────


@router.get("/bookings", response_model=AdminPage[AdminBookingListItem])
async def list_bookings(
    status: BookingStatus | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = PageNo,
    page_size: int = PageSize,
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminPage[AdminBookingListItem]:
    return await AdminService(db).list_bookings(
        status=status, q=q, date_from=date_from, date_to=date_to, page=page, page_size=page_size
    )


@router.get("/bookings/{booking_id}", response_model=AdminBookingDetail)
async def get_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminBookingDetail:
    return await AdminService(db).get_booking(booking_id)


@router.post("/bookings/{booking_id}/cancel", response_model=AdminBookingDetail)
async def cancel_booking(
    booking_id: uuid.UUID,
    payload: AdminCancelIn,
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminBookingDetail:
    """Cancel on the patient's behalf (no fee); both sides are notified."""
    service = AdminService(db)
    await service.cancel_booking(booking_id, payload.reason, actor=current_user)
    return await service.get_booking(booking_id)


@router.post("/bookings/{booking_id}/reopen", response_model=AdminBookingDetail)
async def reopen_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminBookingDetail:
    """Unassign the professional and put the request back on the board."""
    service = AdminService(db)
    await service.reopen_booking(booking_id, actor=current_user)
    return await service.get_booking(booking_id)


# ── Catalogue ───────────────────────────────────────────────────────────


@router.get("/catalog/categories", response_model=list[CategoryAdminRead])
async def list_categories(
    current_user: User = Depends(require_ops_or_admin), db: AsyncSession = Depends(get_db)
) -> list:
    return await CatalogService(db).list_categories(include_inactive=True)


@router.post("/catalog/categories", response_model=CategoryAdminRead, status_code=201)
async def create_category(
    payload: CategoryWriteIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):  # type: ignore[no-untyped-def]
    return await CatalogService(db).save_category(
        payload, category_id=None, actor_id=current_user.id
    )


@router.put("/catalog/categories/{category_id}", response_model=CategoryAdminRead)
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryWriteIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):  # type: ignore[no-untyped-def]
    return await CatalogService(db).save_category(
        payload, category_id=category_id, actor_id=current_user.id
    )


@router.get("/catalog/services", response_model=list[ServiceAdminRead])
async def list_services(
    current_user: User = Depends(require_ops_or_admin), db: AsyncSession = Depends(get_db)
) -> list[ServiceAdminRead]:
    return await CatalogService(db).admin_list_services()


@router.post("/catalog/services", response_model=ServiceAdminRead, status_code=201)
async def create_service(
    payload: ServiceWriteIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ServiceAdminRead:
    return await CatalogService(db).save_service(payload, service_id=None, actor_id=current_user.id)


@router.put("/catalog/services/{service_id}", response_model=ServiceAdminRead)
async def update_service(
    service_id: uuid.UUID,
    payload: ServiceWriteIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ServiceAdminRead:
    return await CatalogService(db).save_service(
        payload, service_id=service_id, actor_id=current_user.id
    )


# ── Dashboard & activity ────────────────────────────────────────────────


@router.get("/dashboard", response_model=DashboardOverviewOut)
async def get_dashboard_overview(
    city: str | None = Query(default=None),
    state: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> DashboardOverviewOut:
    """Registration counts, professional-verification and booking-status breakdowns, a
    signup trend, and a patient location breakdown — the internal ops dashboard's summary
    view — plus business KPIs (GMV, fill rate, cancellation rate). `city`/`state` filter the
    patient counts and location breakdown; `date_from`/`date_to` filter the signup counts and
    set the trend window (defaults to the last 14 days)."""
    return await AdminAnalyticsService(db).get_overview(
        city=city, state=state, date_from=date_from, date_to=date_to
    )


@router.get("/activity", response_model=list[AdminActivity])
async def list_activity(
    entity_type: str | None = Query(default=None, max_length=50),
    entity_id: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminActivity]:
    """Who did what, newest first — config changes, approvals, suspensions, cancellations."""
    return await AdminService(db).activity(
        entity_type=entity_type, entity_id=entity_id, limit=limit, offset=offset
    )
