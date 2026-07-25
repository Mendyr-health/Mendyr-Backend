"""Patient wallet balance and transaction history."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.wallet import WalletTransaction
from app.schemas.wallet import WalletRead, WalletTransactionRead
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", response_model=WalletRead)
async def get_wallet(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> WalletRead:
    wallet = await WalletService(db).get_or_create_wallet(current_user.id)
    return WalletRead.model_validate(wallet)


@router.get("/transactions", response_model=list[WalletTransactionRead])
async def list_transactions(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list:
    wallet = await WalletService(db).get_or_create_wallet(current_user.id)
    result = await db.execute(
        select(WalletTransaction)
        .where(WalletTransaction.wallet_id == wallet.id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())
