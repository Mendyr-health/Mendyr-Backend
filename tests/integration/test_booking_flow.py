"""The prototype's core flow over HTTP: a patient books a visit, the professionals it suits
see it as a request, the first to accept gets it, and the visit is started, completed and
rated. Uses Bearer tokens (native-client mode) so no cookies leak between users."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio

from app.core.constants import ProfessionalType
from app.db.session import AsyncSessionLocal
from app.models.service import Service, ServiceCategory

IST = ZoneInfo("Asia/Kolkata")
NATIVE = {"X-Client-Platform": "android"}

MG_ROAD = {"latitude": 12.9716, "longitude": 77.5946}
INDIRANAGAR = {"latitude": 12.9784, "longitude": 77.6408}  # ~5 km from MG Road
MYSURU = {"latitude": 12.2958, "longitude": 76.6394}  # ~140 km away


def _data(response):
    body = response.json()
    assert body["success"], body
    return body["data"]


def _next_ist(weekday: int, hour: int) -> datetime:
    """The next `weekday` (0 = Monday) at `hour`:00 India time, at least a day away."""
    now = datetime.now(IST)
    days_ahead = (weekday - now.weekday()) % 7 or 7
    return (now + timedelta(days=days_ahead)).replace(hour=hour, minute=0, second=0, microsecond=0)


@pytest_asyncio.fixture(scope="module")
async def nursing_service_id() -> str:
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        category = ServiceCategory(name=f"Nursing {suffix}", slug=f"nursing-{suffix}")
        session.add(category)
        await session.flush()
        service = Service(
            category_id=category.id,
            name="General Nursing Visit",
            slug=f"general-nursing-{suffix}",
            required_professional_type=ProfessionalType.NURSE,
            duration_minutes=60,
            base_price=1000,
        )
        session.add(service)
        await session.commit()
        return str(service.id)


async def _register(client, role: str, name: str) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/v1/auth/register",
        headers=NATIVE,
        json={
            "email": f"{role}-{suffix}@example.com",
            "password": "Password@123",
            "full_name": name,
            "phone_number": f"+9198{int(suffix, 16) % 10**8:08d}",
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {_data(response)['access_token']}", **NATIVE}


async def _patient_with_address(client, name: str = "Asha Patel"):
    headers = await _register(client, "patient", name)
    address = _data(
        await client.post(
            "/api/v1/addresses",
            headers=headers,
            json={
                "label": "home",
                "line1": "221B, Sunrise Apartments",
                "line2": "MG Road",
                "city": "Bengaluru",
                "state": "Karnataka",
                "pincode": "560001",
                "location": MG_ROAD,
                "is_default": True,
            },
        )
    )
    return headers, address["id"]


async def _nurse(client, name: str, location: dict, slots: list[dict] | None = None):
    headers = await _register(client, "professional", name)
    _data(
        await client.post(
            "/api/v1/professionals/onboard",
            headers=headers,
            json={
                "professional_type": "nurse",
                "years_of_experience": 4,
                "location": location,
                "service_radius_km": 10,
            },
        )
    )
    if slots is not None:
        _data(
            await client.put(
                "/api/v1/professionals/me/availability/slots", headers=headers, json=slots
            )
        )
    return headers


async def _book(client, headers, address_id, service_id, starts_at: datetime) -> dict:
    return _data(
        await client.post(
            "/api/v1/bookings",
            headers=headers,
            json={
                "service_id": service_id,
                "address_id": address_id,
                "scheduled_start_at": starts_at.isoformat(),
                "patient_notes": "Dressing change for my father after knee surgery.",
            },
        )
    )


async def _request_ids(client, headers) -> set[str]:
    return {
        r["id"]
        for r in _data(await client.get("/api/v1/bookings/professional/requests", headers=headers))
    }


@pytest.mark.asyncio
async def test_requests_reach_only_suitable_professionals_and_first_accept_wins(
    client, nursing_service_id
):
    patient, address_id = await _patient_with_address(client)
    monday_9_to_6 = [{"day_of_week": 0, "start_time": "09:00", "end_time": "18:00"}]
    nearby = await _nurse(client, "Priya Sharma", INDIRANAGAR, monday_9_to_6)
    anytime = await _nurse(client, "Kavita Reddy", INDIRANAGAR)  # no timings = any time
    far_away = await _nurse(client, "Meera Iyer", MYSURU)
    evenings_only = await _nurse(
        client,
        "Sunita Rao",
        INDIRANAGAR,
        [{"day_of_week": 0, "start_time": "19:00", "end_time": "23:00"}],
    )

    quote = _data(
        await client.post(
            "/api/v1/bookings/quote", headers=patient, json={"service_id": nursing_service_id}
        )
    )
    assert quote["total_amount"] == pytest.approx(1180)  # base + 18% GST

    monday_10am = _next_ist(0, 10)
    available = _data(
        await client.get(
            "/api/v1/professionals/nearby",
            headers=patient,
            params={
                "service_id": nursing_service_id,
                "address_id": address_id,
                "scheduled_at": monday_10am.isoformat(),
            },
        )
    )
    assert {p["full_name"] for p in available} == {"Priya Sharma", "Kavita Reddy"}

    booking = await _book(client, patient, address_id, nursing_service_id, monday_10am)
    assert booking["status"] == "searching"
    assert booking["professional"] is None

    assert booking["id"] in await _request_ids(client, nearby)
    assert booking["id"] in await _request_ids(client, anytime)
    assert booking["id"] not in await _request_ids(client, far_away)
    assert booking["id"] not in await _request_ids(client, evenings_only)

    request = next(
        r
        for r in _data(await client.get("/api/v1/bookings/professional/requests", headers=nearby))
        if r["id"] == booking["id"]
    )
    assert "221B" not in request["area"]  # street address stays hidden until accepted
    assert request["earning_amount"] == pytest.approx(800)  # base minus 20% commission
    assert 3 < request["distance_km"] < 7

    outside_timings = await client.post(
        f"/api/v1/bookings/{booking['id']}/accept", headers=evenings_only
    )
    assert outside_timings.status_code == 403

    accepted = _data(await client.post(f"/api/v1/bookings/{booking['id']}/accept", headers=nearby))
    assert accepted["status"] == "assigned"
    assert accepted["address"].startswith("221B, Sunrise Apartments")
    assert accepted["patient_name"] == "Asha Patel"

    too_late = await client.post(f"/api/v1/bookings/{booking['id']}/accept", headers=anytime)
    assert too_late.status_code == 409
    assert booking["id"] not in await _request_ids(client, anytime)

    patient_view = _data(await client.get(f"/api/v1/bookings/{booking['id']}", headers=patient))
    assert patient_view["status"] == "assigned"
    assert patient_view["professional"]["full_name"] == "Priya Sharma"
    assert patient_view["professional"]["phone_number"].startswith("+91")

    mine = _data(await client.get("/api/v1/bookings/professional/mine", headers=nearby))
    assert [b["id"] for b in mine] == [booking["id"]]


@pytest.mark.asyncio
async def test_visit_lifecycle_release_start_complete_and_review(client, nursing_service_id):
    patient, address_id = await _patient_with_address(client)
    nurse = await _nurse(client, "Anita Das", INDIRANAGAR)
    soon = datetime.now(IST) + timedelta(minutes=90)
    booking = await _book(client, patient, address_id, nursing_service_id, soon)
    path = f"/api/v1/bookings/{booking['id']}"

    _data(await client.post(f"{path}/accept", headers=nurse))
    released = _data(await client.post(f"{path}/release", headers=nurse))
    assert released["status"] == "searching"
    reopened = _data(await client.get(path, headers=patient))
    assert reopened["status"] == "searching"
    assert reopened["professional"] is None
    assert booking["id"] in await _request_ids(client, nurse)

    _data(await client.post(f"{path}/accept", headers=nurse))
    complete_too_early = await client.post(f"{path}/check-out", headers=nurse, json={})
    assert complete_too_early.status_code == 422

    started = _data(await client.post(f"{path}/check-in", headers=nurse))
    assert started["status"] == "in_progress"
    assert started["started_at"] is not None

    cancel_after_start = await client.post(
        f"{path}/cancel", headers=patient, json={"reason": "Changed my mind"}
    )
    assert cancel_after_start.status_code == 422

    completed = _data(
        await client.post(
            f"{path}/check-out",
            headers=nurse,
            json={
                "visit_summary_notes": "Wound clean, dressing changed.",
                "vitals_recorded": "BP 120/80",
            },
        )
    )
    assert completed["status"] == "completed"
    assert (
        _data(await client.get("/api/v1/professionals/me", headers=nurse))["total_visits_completed"]
        == 1
    )

    _data(
        await client.post(
            "/api/v1/reviews", headers=patient, json={"booking_id": booking["id"], "rating": 5}
        )
    )
    final = _data(await client.get(path, headers=patient))
    assert final["visit_summary_notes"] == "Wound clean, dressing changed."
    assert final["review_rating"] == 5


@pytest.mark.asyncio
async def test_visits_cannot_be_started_long_before_they_are_due(client, nursing_service_id):
    patient, address_id = await _patient_with_address(client)
    nurse = await _nurse(client, "Rekha Nair", INDIRANAGAR)
    booking = await _book(client, patient, address_id, nursing_service_id, _next_ist(2, 11))
    _data(await client.post(f"/api/v1/bookings/{booking['id']}/accept", headers=nurse))

    response = await client.post(f"/api/v1/bookings/{booking['id']}/check-in", headers=nurse)
    assert response.status_code == 422
    assert "2 hours" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_cancelled_requests_leave_the_board(client, nursing_service_id):
    patient, address_id = await _patient_with_address(client)
    nurse = await _nurse(client, "Lata Menon", INDIRANAGAR)
    booking = await _book(client, patient, address_id, nursing_service_id, _next_ist(4, 15))
    assert booking["id"] in await _request_ids(client, nurse)

    cancelled = _data(
        await client.post(
            f"/api/v1/bookings/{booking['id']}/cancel",
            headers=patient,
            json={"reason": "Not needed"},
        )
    )
    assert cancelled["status"] == "cancelled"
    assert booking["id"] not in await _request_ids(client, nurse)

    in_use = await client.delete(f"/api/v1/addresses/{address_id}", headers=patient)
    assert in_use.status_code == 409


@pytest.mark.asyncio
async def test_bookings_need_a_timezone_and_a_future_time(client, nursing_service_id):
    patient, address_id = await _patient_with_address(client)
    naive = await client.post(
        "/api/v1/bookings",
        headers=patient,
        json={
            "service_id": nursing_service_id,
            "address_id": address_id,
            "scheduled_start_at": "2030-01-01T10:00:00",
        },
    )
    assert naive.status_code == 422
    assert naive.json()["error"]["message"].startswith("scheduled_start_at:")

    past = await client.post(
        "/api/v1/bookings",
        headers=patient,
        json={
            "service_id": nursing_service_id,
            "address_id": address_id,
            "scheduled_start_at": (datetime.now(IST) - timedelta(hours=1)).isoformat(),
        },
    )
    assert past.status_code == 422


@pytest.mark.asyncio
async def test_browser_session_refreshes_and_logs_out_via_cookies(client):
    suffix = uuid.uuid4().hex[:8]
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"web-{suffix}@example.com",
            "password": "Password@123",
            "full_name": "Web User",
            "phone_number": f"+9197{int(suffix, 16) % 10**8:08d}",
        },
    )
    assert registered.status_code == 201
    assert client.cookies.get("refresh_token")

    refreshed = await client.post("/api/v1/auth/token/refresh")  # no body: cookie only
    assert refreshed.status_code == 200, refreshed.text
    assert _data(await client.get("/api/v1/auth/me"))["full_name"] == "Web User"

    client.cookies.delete("access_token")  # as if it had expired
    logged_out = await client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200
    assert "refresh_token=" in logged_out.headers.get("set-cookie", "")
