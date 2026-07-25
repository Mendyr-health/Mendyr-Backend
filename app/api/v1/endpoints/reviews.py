"""Post-visit ratings — a patient reviewing the professional who served a completed booking."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_patient
from app.db.session import get_db
from app.models.user import User
from app.schemas.review import ReviewCreateIn, ReviewRead
from app.services.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewRead)
async def create_review(
    payload: ReviewCreateIn,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> ReviewRead:
    return await ReviewService(db).create_review(reviewer_id=current_user.id, payload=payload)
