import uuid

from sqlalchemy import select

from app.models.wallet import Wallet
from app.repositories.base import BaseRepository


class WalletRepository(BaseRepository[Wallet]):
    model = Wallet

    async def get_by_user_id(self, user_id: uuid.UUID) -> Wallet | None:
        result = await self.session.execute(select(Wallet).where(Wallet.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_user_id_for_update(self, user_id: uuid.UUID) -> Wallet | None:
        """Row-locked read — call inside a transaction before mutating balance to prevent races
        between two concurrent debits/credits on the same wallet."""
        result = await self.session.execute(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()
