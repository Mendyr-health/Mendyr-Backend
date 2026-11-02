"""Rules added for the premium upgrade: no clashing requests, contact details withdrawn after
a cancellation, gender preference, the visit PIN, stale-request expiry, config validation,
the admin verification queue, and the access fixes."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.constants import Gender, UserRole
from app.db.session import AsyncSessionLocal
from app.models.booking import Booking
from app.models.user import User
from app.services import booking_service
from tests.conftest import set_config
from tests.integration.test_booking_flow import (
    INDIRANAGAR,
    _book,
    _data,
    _next_ist,
    _nurse,
    _patient_with_address,
    _register,
    _request_ids,
)

pytestmark = pytest.mark.asyncio


async def _set_user(headers: dict, **values) -> None:
    """Patch the user behind `headers` directly (role/gender aren't self-service)."""
    from app.core.security import decode_token

    user_id = uuid.UUID(decode_token(headers["Authorization"].removeprefix("Bearer "))["sub"])
    async with AsyncSessionLocal() as session:
        await session.execute(update(User).where(User.id == user_id).values(**values))
        await session.commit()


async def _admin(client) -> dict:
    headers = await _register(client, "patient", "Ops Admin")
    await _set_user(headers, role=UserRole.SUPER_ADMIN)
    return headers


@pytest.fixture(autouse=True)
async def _auto_approve():
    await set_config("verification", {"auto_approve": True})
    yield
    await set_config("verification", {"auto_approve": False})
    await set_config("app.features", {})


async def test_professional_doesnt_see_requests_that_clash_with_an_accepted_visit(
    client, nursing_service_id
):
    patient, address_id = await _patient_with_address(client)
    nurse = await _nurse(client, "Clash Nurse", INDIRANAGAR)
    day = _next_ist(2, 10)
    first = await _book(client, patient, address_id, nursing_service_id, day)
    _data(await client.post(f"/api/v1/bookings/{first['id']}/accept", headers=nurse))

    overlapping = await _book(
        client, patient, address_id, nursing_service_id, day + timedelta(minutes=30)
    )
    # Ends at 11:00; the default 30-minute travel buffer blocks 11:00–11:30 too.
    inside_buffer = await _book(
        client, patient, address_id, nursing_service_id, day + timedelta(minutes=80)
    )
    later = await _book(client, patient, address_id, nursing_service_id, day + timedelta(hours=3))

    visible = await _request_ids(client, nurse)
    assert overlapping["id"] not in visible
    assert inside_buffer["id"] not in visible
    assert later["id"] in visible

    response = await client.post(f"/api/v1/bookings/{overlapping['id']}/accept", headers=nurse)
    assert response.status_code == 403

    def nearby_at(when: datetime):
        return client.get(
            "/api/v1/professionals/nearby",
            headers=patient,
            params={
                "service_id": nursing_service_id,
                "address_id": address_id,
                "scheduled_at": when.isoformat(),
            },
        )

    busy = {p["full_name"] for p in _data(await nearby_at(day + timedelta(minutes=30)))}
    free = {p["full_name"] for p in _data(await nearby_at(day + timedelta(hours=3)))}
    assert "Clash Nurse" not in busy
    assert "Clash Nurse" in free


async def test_contact_details_are_hidden_after_cancellation(client, nursing_service_id):
    patient, address_id = await _patient_with_address(client)
    nurse = await _nurse(client, "Privacy Nurse", INDIRANAGAR)
    booking = await _book(client, patient, address_id, nursing_service_id, _next_ist(3, 11))
    _data(await client.post(f"/api/v1/bookings/{booking['id']}/accept", headers=nurse))

    live = _data(await client.get(f"/api/v1/bookings/{booking['id']}", headers=patient))
    assert live["professional"]["phone_number"]
    assert live["contact_hidden"] is False

    _data(
        await client.post(
            f"/api/v1/bookings/{booking['id']}/cancel", headers=patient, json={"reason": "Other"}
        )
    )
    as_patient = _data(await client.get(f"/api/v1/bookings/{booking['id']}", headers=patient))
    assert as_patient["contact_hidden"] is True
    assert as_patient["professional"]["phone_number"] is None
    assert as_patient["professional"]["user_ref"].startswith("MU-")
    assert as_patient["cancelled_by"] == "patient"
    assert [e["status"] for e in as_patient["timeline"]] == ["searching", "assigned", "cancelled"]

    as_nurse = _data(
        await client.get(f"/api/v1/bookings/professional/{booking['id']}", headers=nurse)
    )
    assert as_nurse["contact_hidden"] is True
    assert as_nurse["patient_phone"] is None
    assert as_nurse["latitude"] is None and as_nurse["longitude"] is None
    assert "221B" not in as_nurse["address"]
    assert as_nurse["patient_ref"].startswith("MU-")
    assert as_nurse["cancelled_by"] == "patient"


async def test_gender_preference_limits_who_sees_the_request(client, nursing_service_id):
    patient, address_id = await _patient_with_address(client)
    female = await _nurse(client, "Female Nurse", INDIRANAGAR)
    male = await _nurse(client, "Male Nurse", INDIRANAGAR)
    await _set_user(female, gender=Gender.FEMALE)
    await _set_user(male, gender=Gender.MALE)

    response = await client.post(
        "/api/v1/bookings",
        headers=patient,
        json={
            "service_id": nursing_service_id,
            "address_id": address_id,
            "scheduled_start_at": _next_ist(4, 9).isoformat(),
            "preferred_gender": "female",
        },
    )
    booking = _data(response)
    assert booking["preferred_gender"] == "female"
    assert booking["id"] in await _request_ids(client, female)
    assert booking["id"] not in await _request_ids(client, male)


async def test_visit_pin_is_required_when_the_flag_is_on(client, nursing_service_id):
    await set_config("app.features", {"visit_otp": True})
    patient, address_id = await _patient_with_address(client)
    nurse = await _nurse(client, "Pin Nurse", INDIRANAGAR)
    starts = datetime.now(UTC) + timedelta(minutes=90)
    booking = await _book(client, patient, address_id, nursing_service_id, starts)
    accepted = _data(await client.post(f"/api/v1/bookings/{booking['id']}/accept", headers=nurse))
    assert accepted["requires_visit_pin"] is True

    pin = _data(await client.get(f"/api/v1/bookings/{booking['id']}", headers=patient))["visit_pin"]
    assert pin and len(pin) == 4

    wrong = "0000" if pin != "0000" else "1111"
    response = await client.post(
        f"/api/v1/bookings/{booking['id']}/check-in", headers=nurse, json={"visit_pin": wrong}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "visit_pin_invalid"

    started = _data(
        await client.post(
            f"/api/v1/bookings/{booking['id']}/check-in", headers=nurse, json={"visit_pin": pin}
        )
    )
    assert started["status"] == "in_progress"
    # Once started the PIN is no longer shown to the patient.
    after = _data(await client.get(f"/api/v1/bookings/{booking['id']}", headers=patient))
    assert after["visit_pin"] is None


async def test_unaccepted_requests_expire_once_their_time_has_passed(client, nursing_service_id):
    patient, address_id = await _patient_with_address(client)
    booking = await _book(client, patient, address_id, nursing_service_id, _next_ist(1, 15))
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Booking)
            .where(Booking.id == uuid.UUID(booking["id"]))
            .values(scheduled_start_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await session.commit()
    booking_service._last_stale_sweep = 0.0

    listed = _data(await client.get("/api/v1/bookings", headers=patient))
    assert next(b for b in listed if b["id"] == booking["id"])["status"] == "failed"
    inbox = _data(await client.get("/api/v1/notifications", headers=patient))
    assert inbox["unread_count"] >= 1
    assert any("couldn't find" in (n["title"] or "") for n in inbox["items"])


async def test_config_bundle_defaults_validation_and_access(client):
    patient = await _register(client, "patient", "Config Reader")
    admin = await _admin(client)

    bundle = _data(await client.get("/api/v1/configs/app?role=patient&platform=android"))
    configs = bundle["configs"]
    assert configs["booking.rules"]["slot_step_minutes"] == 30
    assert configs["app.theme"]["primary"].startswith("#")
    assert "pricing" not in configs and "privacy" not in configs  # backend-only keys

    denied = await client.put(
        "/api/v1/configs/by-key/app.theme", headers=patient, json={"value": {}}
    )
    assert denied.status_code == 403
    assert (await client.get("/api/v1/configs", headers=patient)).status_code == 403

    bad = await client.put(
        "/api/v1/configs/by-key/app.theme", headers=admin, json={"value": {"primary": "blue"}}
    )
    assert bad.status_code == 422

    saved = _data(
        await client.put(
            "/api/v1/configs/by-key/app.theme",
            headers=admin,
            json={"value": {"primary": "#0A7D5A"}},
        )
    )
    assert saved["value"]["primary"] == "#0A7D5A"
    assert saved["value"]["radius"] == 16  # filled from the default
    refreshed = _data(await client.get("/api/v1/configs/app"))
    assert refreshed["configs"]["app.theme"]["primary"] == "#0A7D5A"
    assert refreshed["version"] != bundle["version"]

    registry = _data(await client.get("/api/v1/configs/registry", headers=admin))
    theme = next(e for e in registry if e["key"] == "app.theme")
    assert theme["is_overridden"] is True and "properties" in theme["schema"]

    activity = _data(await client.get("/api/v1/admin/activity?entity_type=config", headers=admin))
    assert any(a["entity_id"] == "app.theme" for a in activity)
    await client.delete(f"/api/v1/configs/{saved['id']}", headers=admin)


async def test_super_admin_verifies_a_pending_professional(client, nursing_service_id):
    await set_config("verification", {"auto_approve": False})
    admin = await _admin(client)
    nurse = await _nurse(client, "Queued Nurse", INDIRANAGAR)
    me = _data(await client.get("/api/v1/professionals/me", headers=nurse))
    assert me["verification_status"] == "pending"

    stats = _data(await client.get("/api/v1/admin/professionals/stats", headers=admin))
    assert stats["by_status"]["pending"] >= 1 and stats["auto_approve"] is False

    queue = _data(
        await client.get("/api/v1/admin/professionals?status=pending&q=Queued", headers=admin)
    )
    assert queue["total"] >= 1
    item = queue["items"][0]

    missing_reason = await client.post(
        f"/api/v1/admin/professionals/{item['id']}/review",
        headers=admin,
        json={"decision": "rejected"},
    )
    assert missing_reason.status_code == 422

    detail = _data(
        await client.post(
            f"/api/v1/admin/professionals/{item['id']}/review",
            headers=admin,
            json={"decision": "approved", "note": "Council certificate checked"},
        )
    )
    assert detail["verification_status"] == "approved"
    assert detail["history"][0]["action"] == "professional.approved"
    inbox = _data(await client.get("/api/v1/notifications", headers=nurse))
    assert inbox["items"][0]["title"] == "You're verified!"


async def test_suspension_takes_effect_immediately(client):
    admin = await _admin(client)
    patient = await _register(client, "patient", "Soon Suspended")
    assert (await client.get("/api/v1/auth/me", headers=patient)).status_code == 200
    users = _data(await client.get("/api/v1/admin/users?q=Soon%20Suspended", headers=admin))
    user_id = users["items"][0]["id"]

    _data(
        await client.patch(
            f"/api/v1/admin/users/{user_id}/status",
            headers=admin,
            json={"status": "suspended", "reason": "Abusive behaviour"},
        )
    )
    assert (await client.get("/api/v1/auth/me", headers=patient)).status_code == 401


async def test_saved_queries_and_tickets_are_not_open_to_everyone(client):
    patient = await _register(client, "patient", "Curious Patient")
    other = await _register(client, "patient", "Other Patient")
    assert (await client.get("/api/v1/analytics/anything/data", headers=patient)).status_code == 403

    ticket = _data(
        await client.post(
            "/api/v1/support/tickets",
            headers=other,
            json={"subject": "Refund", "category": "billing", "initial_message": "Hi"},
        )
    )
    response = await client.post(
        f"/api/v1/support/tickets/{ticket['id']}/messages",
        headers=patient,
        json={"message": "Hijack"},
    )
    assert response.status_code == 403


async def test_saving_an_existing_config_and_query_again_works(client):
    admin = await _admin(client)
    for value in ({"hindi": False}, {"hindi": True}, {"hindi": True, "prescription_upload": True}):
        saved = _data(
            await client.put(
                "/api/v1/configs/by-key/app.features", headers=admin, json={"value": value}
            )
        )
        assert saved["value"]["hindi"] == value["hindi"]
    toggled = _data(await client.patch(f"/api/v1/configs/{saved['id']}/toggle", headers=admin))
    assert toggled["is_active"] is False and toggled["updated_at"]
    await client.delete(f"/api/v1/configs/{saved['id']}", headers=admin)

    query = _data(
        await client.post(
            "/api/v1/analytics",
            headers=admin,
            json={"name": f"q_{uuid.uuid4().hex[:6]}", "query": "SELECT 1 AS one"},
        )
    )
    edited = await client.patch(
        f"/api/v1/analytics/{query['id']}", headers=admin, json={"batch_size": 10}
    )
    assert edited.status_code == 200, edited.text
