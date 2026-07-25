"""Patient service addresses — geocoded so matching can run nearest-professional lookups."""

import uuid

from geoalchemy2 import Geography
from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPKMixin


class Address(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "addresses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    label: Mapped[str] = mapped_column(String(30), nullable=False)  # home | work | other
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    landmark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    pincode: Mapped[str] = mapped_column(String(10), nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="IN", nullable=False)

    # SRID 4326 (WGS84) geography point — enables ST_DWithin radius search from matching.
    location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )

    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(15), nullable=True)
    instructions_for_professional: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped["User"] = relationship(back_populates="addresses")

    __table_args__ = (Index("ix_addresses_location", "location", postgresql_using="gist"),)
