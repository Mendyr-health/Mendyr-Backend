"""Internal ops/admin operations: professional KYC review and payout triggers."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import VerificationStatus
from app.core.permissions import require_ops_or_admin
from app.db.session import get_db
from app.models.professional import ProfessionalProfile
from app.models.user import User
from app.schemas.professional import ProfessionalRead, ProfessionalReviewDecisionIn
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
