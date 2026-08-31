"""Admin-curated, read-only named queries — see app/services/query_info_service.py for how
`query` is validated (SELECT-only) and executed."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base, TimestampMixin, UUIDPKMixin


class QueryInfo(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "query_info"

    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    # Default and max page size when this query is run — caps how many rows a single call
    # can return, so a stored query can't be used to pull an entire huge table in one request.
    batch_size: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
