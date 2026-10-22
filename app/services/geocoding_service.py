"""Turns what people type (a pincode, a city) into the coordinates matching runs on, and a
device's location back into address fields for "use my current location".

Matching needs a point for every patient address and every professional's service area, but
nobody knows their latitude — so the web app geocodes the pincode here before saving.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from app.integrations.maps.nominatim import NominatimClient

_CACHE_LIMIT = 2000


@dataclass(frozen=True)
class GeoLocation:
    latitude: float
    longitude: float
    label: str
    # "pincode" when the pincode itself was found; "city" when only the city was — coarse
    # enough that the app should suggest using the device location instead.
    precision: Literal["pincode", "city"]


@dataclass(frozen=True)
class GeoAddress:
    latitude: float
    longitude: float
    label: str
    area: str | None
    city: str | None
    state: str | None
    pincode: str | None


def _first(address: dict[str, Any], *keys: str) -> str | None:
    return next((address[k] for k in keys if address.get(k)), None)


def _parts(result: dict[str, Any]) -> dict[str, str | None]:
    address = result.get("address") or {}
    postcode = re.sub(r"\D", "", address.get("postcode") or "")
    return {
        "area": _first(address, "suburb", "neighbourhood", "quarter", "residential", "road"),
        "city": _first(
            address, "city", "town", "village", "municipality", "city_district", "state_district"
        ),
        "state": address.get("state"),
        "pincode": postcode if len(postcode) == 6 else None,
    }


def _label(result: dict[str, Any]) -> str:
    parts = _parts(result)
    place = ", ".join(p for p in (parts["area"], parts["city"], parts["state"]) if p)
    if place and parts["pincode"]:
        return f"{place} {parts['pincode']}"
    return place or str(result.get("display_name", ""))


class GeocodingService:
    # Process-wide memo: the same pincodes and cities come up constantly, and the free
    # geocoder only allows ~1 request/second.
    _cache: ClassVar[dict[tuple[Any, ...], Any]] = {}

    def __init__(self) -> None:
        self.client = NominatimClient()

    def _remember(self, key: tuple[Any, ...], value: Any) -> None:
        if len(self._cache) >= _CACHE_LIMIT:
            self._cache.clear()
        self._cache[key] = value

    async def locate(
        self, *, pincode: str, city: str | None = None, state: str | None = None
    ) -> GeoLocation | None:
        key = ("locate", pincode, (city or "").strip().lower(), (state or "").strip().lower())
        if key in self._cache:
            return self._cache[key]

        precision: Literal["pincode", "city"] = "pincode"
        result = await self.client.search(postalcode=pincode)
        if result is None and city:
            await asyncio.sleep(1)  # Nominatim's 1 request/second policy
            result = await self.client.search(q=", ".join(p for p in (city, state) if p))
            precision = "city"
        if result is None:
            return None

        location = GeoLocation(
            latitude=float(result["lat"]),
            longitude=float(result["lon"]),
            label=_label(result),
            precision=precision,
        )
        self._remember(key, location)
        return location

    async def reverse(self, latitude: float, longitude: float) -> GeoAddress | None:
        key = ("reverse", round(latitude, 4), round(longitude, 4))
        if key in self._cache:
            return self._cache[key]

        result = await self.client.reverse(latitude, longitude)
        if result is None:
            return None
        address = GeoAddress(
            latitude=latitude, longitude=longitude, label=_label(result), **_parts(result)
        )
        self._remember(key, address)
        return address
