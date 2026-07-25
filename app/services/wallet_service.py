"""Patient wallet ledger — every balance change is an immutable WalletTransaction row."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import WalletTxnReason, WalletTxnType
from app.core.exceptions import ValidationAppError
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.wallet_repo import WalletRepository


class WalletService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.wallets = WalletRepository(session)

    async def get_or_create_wallet(self, user_id: uuid.UUID) -> Wallet:
        wallet = await self.wallets.get_by_user_id(user_id)
        if wallet is None:
            wallet = Wallet(user_id=user_id, balance=0)
            self.wallets.add(wallet)
            await self.session.flush()
        return wallet

    async def credit(
        self,
        user_id: uuid.UUID,
        *,
        amount: float,
        reason: WalletTxnReason,
        reference_booking_id: uuid.UUID | None = None,
        description: str | None = None,
    ) -> Wallet:
        wallet = await self.wallets.get_by_user_id_for_update(
            user_id
        ) or await self.get_or_create_wallet(user_id)
        wallet.balance = float(wallet.balance) + amount
        self.session.add(
            WalletTransaction(
                wallet_id=wallet.id,
                txn_type=WalletTxnType.CREDIT,
                reason=reason,
                amount=amount,
                balance_after=wallet.balance,
                reference_booking_id=reference_booking_id,
                description=description,
                created_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return wallet

    async def debit(
        self,
        user_id: uuid.UUID,
        *,
        amount: float,
        reason: WalletTxnReason,
        reference_booking_id: uuid.UUID | None = None,
        description: str | None = None,
    ) -> Wallet:
        wallet = await self.wallets.get_by_user_id_for_update(user_id)
        if wallet is None or float(wallet.balance) < amount:
            raise ValidationAppError("Insufficient wallet balance.")

        wallet.balance = float(wallet.balance) - amount
        self.session.add(
            WalletTransaction(
                wallet_id=wallet.id,
                txn_type=WalletTxnType.DEBIT,
                reason=reason,
                amount=amount,
                balance_after=wallet.balance,
                reference_booking_id=reference_booking_id,
                description=description,
                created_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return wallet
