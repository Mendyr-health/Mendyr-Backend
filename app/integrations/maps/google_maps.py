"""Google Maps helpers — address autocomplete/geocoding and ETA for the "en route" UI."""

import httpx

from app.core.config import settings

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


class GoogleMapsClient:
    async def geocode(self, address: str) -> tuple[float, float] | None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                GEOCODE_URL, params={"address": address, "key": settings.GOOGLE_MAPS_API_KEY}
            )
            data = response.json()
            results = data.get("results") or []
            if not results:
                return None
            location = results[0]["geometry"]["location"]
            return location["lat"], location["lng"]

    async def eta_seconds(
        self, origin: tuple[float, float], destination: tuple[float, float]
    ) -> int | None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                DISTANCE_MATRIX_URL,
                params={
                    "origins": f"{origin[0]},{origin[1]}",
                    "destinations": f"{destination[0]},{destination[1]}",
                    "key": settings.GOOGLE_MAPS_API_KEY,
                },
            )
            data = response.json()
            try:
                return data["rows"][0]["elements"][0]["duration"]["value"]
            except (KeyError, IndexError):
                return None
