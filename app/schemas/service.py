import uuid

from pydantic import BaseModel

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


class ProfessionalServiceOptInIn(BaseModel):
    service_id: uuid.UUID
    price_override: float | None = None
