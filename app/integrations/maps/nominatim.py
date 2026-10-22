"""OpenStreetMap Nominatim — free address <-> coordinates lookups for the prototype.

Usage policy (https://operations.osmfoundation.org/policies/nominatim/): at most ~1 request
per second, an identifying User-Agent, and OpenStreetMap attribution wherever results are
shown. Swap for a paid geocoder (see google_maps.py) before real traffic.
"""

from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class NominatimClient:
    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        headers = {"User-Agent": settings.NOMINATIM_USER_AGENT, "Accept-Language": "en"}
        try:
            async with httpx.AsyncClient(timeout=8, headers=headers) as client:
                response = await client.get(
                    f"{settings.NOMINATIM_URL}{path}", params={**params, "format": "jsonv2"}
                )
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("nominatim_request_failed", path=path, error=str(exc))
            return None

    async def search(self, **params: str) -> dict[str, Any] | None:
        """First match in India for a free-form (`q=`) or structured (`postalcode=`) query."""
        data = await self._get(
            "/search", {**params, "countrycodes": "in", "limit": 1, "addressdetails": 1}
        )
        return data[0] if isinstance(data, list) and data else None

    async def reverse(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        data = await self._get(
            "/reverse", {"lat": latitude, "lon": longitude, "addressdetails": 1, "zoom": 18}
        )
        return data if isinstance(data, dict) and "error" not in data else None
