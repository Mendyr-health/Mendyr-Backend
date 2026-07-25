import uuid

from pydantic import BaseModel, Field

from app.schemas.common import GeoPoint, ORMModel


class AddressCreateIn(BaseModel):
    label: str = Field(default="home", max_length=30)
    line1: str
    line2: str | None = None
    landmark: str | None = None
    city: str
    state: str
    pincode: str
    location: GeoPoint
    is_default: bool = False
    contact_name: str | None = None
    contact_phone: str | None = None
    instructions_for_professional: str | None = None


class AddressUpdateIn(BaseModel):
    label: str | None = None
    line1: str | None = None
    line2: str | None = None
    landmark: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    location: GeoPoint | None = None
    is_default: bool | None = None
    instructions_for_professional: str | None = None


class AddressRead(ORMModel):
    id: uuid.UUID
    label: str
    line1: str
    line2: str | None
    landmark: str | None
    city: str
    state: str
    pincode: str
    is_default: bool
    latitude: float
    longitude: float
