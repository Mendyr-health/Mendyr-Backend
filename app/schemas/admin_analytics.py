from datetime import date

from pydantic import BaseModel


class LocationBreakdown(BaseModel):
    city: str
    state: str
    patient_count: int


class DailySignups(BaseModel):
    signup_date: date
    patients: int
    professionals: int


class DashboardOverviewOut(BaseModel):
    total_patients: int
    total_professionals: int
    professionals_by_verification_status: dict[str, int]
    total_bookings: int
    bookings_by_status: dict[str, int]
    # Last 14 days by default, or the requested date_from/date_to range — see
    # AdminAnalyticsService.get_overview for how the window is chosen.
    daily_signups: list[DailySignups]
    # Location breakdown is patient-only: patients have a saved Address (city/state);
    # professionals only carry a live geo point (current_location, no city/state column),
    # so there's nothing to group them by without reverse-geocoding — out of scope here.
    top_locations: list[LocationBreakdown]
