"""Address <-> coordinates lookups for the web app's address and service-area forms.
Logged-in only: each call spends from a shared, rate-limited free geocoding quota."""
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, Request

from app.api.v1.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.geo import GeoAddressOut, GeoLocationOut
from app.services.geocoding_service import GeocodingService

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get("/locate", response_model=GeoLocationOut)
@limiter.limit("20/minute")
async def locate(
    request: Request,
    pincode: str = Query(..., pattern=r"^[1-9]\d{5}$"),
    city: str | None = Query(default=None, max_length=100),
    state: str | None = Query(default=None, max_length=100),
    current_user: User = Depends(get_current_user),
) -> GeoLocationOut:
    """Coordinates for an Indian pincode, falling back to the city when OpenStreetMap doesn't
    know the pincode (`precision` says which one matched)."""
    location = await GeocodingService().locate(pincode=pincode, city=city, state=state)
    if location is None:
        raise NotFoundError(
            "We couldn't find that pincode on the map. Check it, or use your current location."
        )
    return GeoLocationOut(**asdict(location))


@router.get("/reverse", response_model=GeoAddressOut)
@limiter.limit("20/minute")
async def reverse(
    request: Request,
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    current_user: User = Depends(get_current_user),
) -> GeoAddressOut:
    """Area/city/state/pincode for a device location, to prefill an address form."""
    address = await GeocodingService().reverse(latitude, longitude)
    if address is None:
        raise NotFoundError("We couldn't look up an address for your location. Please fill it in.")
    return GeoAddressOut(**asdict(address))
