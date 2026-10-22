from typing import Literal

from pydantic import BaseModel


class GeoLocationOut(BaseModel):
    latitude: float
    longitude: float
    label: str
    precision: Literal["pincode", "city"]


class GeoAddressOut(BaseModel):
    latitude: float
    longitude: float
    label: str
    area: str | None
    city: str | None
    state: str | None
    pincode: str | None
