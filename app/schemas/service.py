import uuid

from pydantic import BaseModel, Field

from app.core.config_registry import Faq
from app.core.constants import ProfessionalType
from app.schemas.common import ORMModel


class ServiceCategoryRead(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    icon_url: str | None


class ServiceRead(ORMModel):
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    required_professional_type: ProfessionalType
    duration_minutes: int
    base_price: float
    is_recurring_eligible: bool
    requires_prescription: bool
    # Presentation content and social proof — see `CatalogContent`.
    image_url: str | None = None
    tagline: str | None = None
    badge: str | None = None
    includes: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    faqs: list[Faq] = Field(default_factory=list)
    rating_avg: float | None = None
    rating_count: int = 0
    bookings_count: int = 0


class ProfessionalServiceOptInIn(BaseModel):
    service_id: uuid.UUID
    price_override: float | None = None


# ── Admin catalogue editing ─────────────────────────────────────────────


class CategoryAdminRead(ServiceCategoryRead):
    display_order: int
    is_active: bool


class CategoryWriteIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    icon_url: str | None = Field(default=None, max_length=500)
    display_order: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class ServiceAdminRead(ServiceRead):
    display_order: int
    is_active: bool


class ServiceWriteIn(BaseModel):
    category_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    required_professional_type: ProfessionalType
    duration_minutes: int = Field(..., ge=15, le=24 * 60)
    base_price: float = Field(..., ge=0)
    is_recurring_eligible: bool = False
    requires_prescription: bool = False
    display_order: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True
    image_url: str | None = Field(default=None, max_length=500)
    tagline: str | None = Field(default=None, max_length=120)
    badge: str | None = Field(default=None, max_length=24)
    includes: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    faqs: list[Faq] = Field(default_factory=list)
