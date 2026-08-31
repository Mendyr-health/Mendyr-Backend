"""Internal ops/admin operations: professional KYC review, payout triggers, dashboard
analytics. Nothing under this router is reachable by patient/professional accounts — see
`require_ops_or_admin` — and none of it ships in the patient/nurse mobile apps; this is the
internal ops dashboard's API surface."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import VerificationStatus
from app.core.permissions import require_ops_or_admin
from app.db.session import get_db
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.schemas.admin_analytics import DashboardOverviewOut
from app.schemas.professional import ProfessionalRead, ProfessionalReviewDecisionIn
from app.services.admin_analytics_service import AdminAnalyticsService
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
    view. `city`/`state` filter the patient counts and location breakdown; `date_from`/
    `date_to` filter the signup counts and set the trend window (defaults to the last 14
    days). Booking counts are always all-time and unfiltered."""
    return await AdminAnalyticsService(db).get_overview(
        city=city, state=state, date_from=date_from, date_to=date_to
    )
