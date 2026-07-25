"""Service catalogue: categories (e.g. Nursing Care), sellable services, professional pricing."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ProfessionalType
from app.db.base_class import Base, TimestampMixin, UUIDPKMixin
from app.db.types import pg_enum


class ServiceCategory(Base, UUIDPKMixin, TimestampMixin):
    """Top-level grouping shown on the app home screen, e.g. 'Nursing Care', 'Physiotherapy',
    'Elder Care', 'Mother & Baby Care', 'Lab Sample Collection'."""

    __tablename__ = "service_categories"

    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    services: Mapped[list["Service"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class Service(Base, UUIDPKMixin, TimestampMixin):
    """A sellable unit, e.g. 'ICU-trained Nurse — 12 hr shift', 'Physiotherapy session — 45 min'."""

    __tablename__ = "services"

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_categories.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_professional_type: Mapped[ProfessionalType] = mapped_column(
        pg_enum(ProfessionalType, "professional_type"), nullable=False
    )

    duration_minutes: Mapped[int] = mapped_column(nullable=False)
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_recurring_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_prescription: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    category: Mapped["ServiceCategory"] = relationship(back_populates="services")
    professional_services: Mapped[list["ProfessionalService"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )


class ProfessionalService(Base, UUIDPKMixin, TimestampMixin):
    """A professional opts into services they're qualified for; price_override lets senior/ICU
    nurses charge above the catalogue base_price."""

    __tablename__ = "professional_services"

    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("professional_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    price_override: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    professional: Mapped["ProfessionalProfile"] = relationship(back_populates="services")
    service: Mapped["Service"] = relationship(back_populates="professional_services")

    __table_args__ = (
        UniqueConstraint("professional_id", "service_id", name="uq_professional_service"),
    )
