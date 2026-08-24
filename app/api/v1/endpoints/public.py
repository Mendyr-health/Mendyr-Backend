"""Unauthenticated public-site endpoints: landing-page waitlist signup and the Contact Us
form. See src/app/(public)/page.tsx and src/app/(public)/contact/page.tsx — deliberately
mounted with no auth dependency at all.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.contact import ContactInquiry
from app.models.waitlist import WaitlistEntry
from app.schemas.common import ApiResponse, MessageResponse
from app.schemas.public import ContactSubmitIn, WaitlistSignupIn

router = APIRouter(tags=["public"])


@router.post("/waitlist", response_model=ApiResponse[MessageResponse])
async def join_waitlist(
    payload: WaitlistSignupIn, db: AsyncSession = Depends(get_db)
) -> ApiResponse[MessageResponse]:
    existing = (
        await db.execute(select(WaitlistEntry).where(WaitlistEntry.email == payload.email))
    ).scalar_one_or_none()
    if existing is not None:
        # Idempotent re-submission (e.g. the user hits the landing page form twice) — refresh
        # the source rather than erroring on the unique email constraint.
        existing.source = payload.source or existing.source
    else:
        db.add(WaitlistEntry(email=payload.email, source=payload.source))
    return ApiResponse.ok(MessageResponse(message="You're on the list!"))


@router.post("/contacts", response_model=ApiResponse[MessageResponse])
async def submit_contact_inquiry(
    payload: ContactSubmitIn, db: AsyncSession = Depends(get_db)
) -> ApiResponse[MessageResponse]:
    db.add(
        ContactInquiry(
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            subject=payload.subject,
            message=payload.message,
        )
    )
    return ApiResponse.ok(MessageResponse(message="Thanks for reaching out — we'll be in touch."))
