import uuid
from datetime import datetime

from app.core.constants import WalletTxnReason, WalletTxnType
from app.schemas.common import ORMModel


class WalletRead(ORMModel):
    id: uuid.UUID
    balance: float


class WalletTransactionRead(ORMModel):
    id: uuid.UUID
    txn_type: WalletTxnType
    reason: WalletTxnReason
    amount: float
    balance_after: float
    description: str | None
    created_at: datetime
