"""Inbound provider webhooks. No user auth — authenticity comes from the provider's signature."""
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.common import MessageResponse
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/razorpay", response_model=MessageResponse)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    body = await request.body()
    await PaymentService(db).handle_webhook(payload=body, signature=x_razorpay_signature)
    return MessageResponse(message="ok")
