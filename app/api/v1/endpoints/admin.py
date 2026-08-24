"""Internal ops/admin operations: professional KYC review and payout triggers (legacy
ops-facing routes below), plus the Next.js admin-console-facing routes (nurse
verification actions, dashboard stats, waitlist/contact admin actions) — see
src/features/admin/useNurses.ts, src/components/web/admin/WebAdminDashboard.tsx,
src/components/web/admin/waitlist/WebAdminWaitlist.tsx,
src/components/web/admin/contacts/WebAdminContacts.tsx.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import VerificationStatus
from app.core.permissions import require_admin, require_ops_or_admin
from app.db.session import get_db
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.schemas.admin_console import (
    ContactAdminOut,
    ContactStatusUpdateIn,
    DashboardStatsOut,
    NurseAdminOut,
    NurseVerificationActionIn,
    WaitlistAdminOut,
)
from app.schemas.common import ApiResponse
from app.schemas.professional import ProfessionalRead, ProfessionalReviewDecisionIn
from app.services.admin_console_service import AdminConsoleService
from app.services.professional_service import ProfessionalService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/professionals/pending", response_model=list[ProfessionalRead])
async def list_pending_professionals(
    current_user: User = Depends(require_ops_or_admin), db: AsyncSession = Depends(get_db)
) -> list:
    result = await db.execute(
        select(ProfessionalProfile).where(
            ProfessionalProfile.verification_status.in_(
                [VerificationStatus.PENDING, VerificationStatus.IN_REVIEW]
            )
        )
    )
    return list(result.scalars().all())


@router.post("/professionals/{professional_id}/review", response_model=ProfessionalRead)
async def review_professional(
    professional_id: uuid.UUID,
    decision: ProfessionalReviewDecisionIn,
    current_user: User = Depends(require_ops_or_admin),
    db: AsyncSession = Depends(get_db),
) -> ProfessionalRead:
    return await ProfessionalService(db).review_kyc(
        professional_id, decision, reviewer_id=current_user.id
    )


# ─── Admin-console routes (Next.js admin portal) ──────────────────────────────


@router.post("/nurses/{professional_id}/approve", response_model=ApiResponse[NurseAdminOut])
async def approve_nurse(
    professional_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[NurseAdminOut]:
    nurse = await AdminConsoleService(db).review_nurse(
        professional_id, approve=True, rejection_reason=None, reviewer_id=current_user.id
    )
    return ApiResponse.ok(nurse)


@router.post("/nurses/{professional_id}/reject", response_model=ApiResponse[NurseAdminOut])
async def reject_nurse(
    professional_id: uuid.UUID,
    payload: NurseVerificationActionIn = NurseVerificationActionIn(),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[NurseAdminOut]:
    nurse = await AdminConsoleService(db).review_nurse(
        professional_id,
        approve=False,
        rejection_reason=payload.rejection_reason,
        reviewer_id=current_user.id,
    )
    return ApiResponse.ok(nurse)


@router.get("/dashboard", response_model=ApiResponse[DashboardStatsOut])
async def get_dashboard_stats(
    current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> ApiResponse[DashboardStatsOut]:
    stats = await AdminConsoleService(db).get_dashboard_stats()
    return ApiResponse.ok(stats)


@router.post("/waitlist/{waitlist_id}/notify", response_model=ApiResponse[WaitlistAdminOut])
async def mark_waitlist_entry_notified(
    waitlist_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WaitlistAdminOut]:
    entry = await AdminConsoleService(db).mark_waitlist_notified(waitlist_id)
    return ApiResponse.ok(entry)


@router.patch("/contacts/{contact_id}/status", response_model=ApiResponse[ContactAdminOut])
async def update_contact_inquiry_status(
    contact_id: uuid.UUID,
    payload: ContactStatusUpdateIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ContactAdminOut]:
    contact = await AdminConsoleService(db).update_contact_status(contact_id, payload.status)
    return ApiResponse.ok(contact)
