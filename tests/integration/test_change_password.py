"""The change-password job and endpoint: verifies existing password, updates to new password,
revokes previous sessions, rejects incorrect existing passwords or identical new passwords."""

import uuid

import pytest

from scripts.change_password import change_password
from tests.integration.test_booking_flow import NATIVE, _data

pytestmark = pytest.mark.asyncio


async def _account(client, name: str, password: str = "OldPassword@1") -> tuple[str, dict, str]:
    suffix = uuid.uuid4().hex[:8]
    email = f"change-pwd-{suffix}@example.com"
    body = _data(
        await client.post(
            "/api/v1/auth/register",
            headers=NATIVE,
            json={
                "email": email,
                "password": password,
                "full_name": name,
                "phone_number": f"+9196{int(suffix, 16) % 10**8:08d}",
                "role": "patient",
            },
        )
    )
    headers = {"Authorization": f"Bearer {body['access_token']}", **NATIVE}
    return email, headers, body["refresh_token"]


async def _login(client, email: str, password: str) -> int:
    response = await client.post(
        "/api/v1/auth/login", headers=NATIVE, json={"email": email, "password": password}
    )
    return response.status_code


async def test_change_password_success(client):
    email, _, refresh = await _account(client, "Change Pass User", "CurrentSecret123")

    ok = await change_password(
        email=email,
        existing_password="CurrentSecret123",
        new_password="NewSecretPass456",
        dry_run=False,
    )
    assert ok is True

    # Old password no longer works
    assert await _login(client, email, "CurrentSecret123") == 401

    # New password works
    assert await _login(client, email, "NewSecretPass456") == 200

    # Old refresh token is revoked
    stale = await client.post(
        "/api/v1/auth/token/refresh", headers=NATIVE, json={"refresh_token": refresh}
    )
    assert stale.status_code == 401


async def test_change_password_wrong_existing_password(client):
    email, _, _ = await _account(client, "Wrong Pass User", "CorrectOldPass1")

    ok = await change_password(
        email=email,
        existing_password="IncorrectOldPass!",
        new_password="NewSecretPass456",
        dry_run=False,
    )
    assert ok is False

    # Old password still intact
    assert await _login(client, email, "CorrectOldPass1") == 200
    assert await _login(client, email, "NewSecretPass456") == 401


async def test_change_password_same_password_rejected(client):
    email, _, _ = await _account(client, "Same Pass User", "SamePass1234")

    ok = await change_password(
        email=email,
        existing_password="SamePass1234",
        new_password="SamePass1234",
        dry_run=False,
    )
    assert ok is False
    assert await _login(client, email, "SamePass1234") == 200


async def test_change_password_too_short_rejected(client):
    email, _, _ = await _account(client, "Short Pass User", "ValidOldPass1")

    ok = await change_password(
        email=email,
        existing_password="ValidOldPass1",
        new_password="short",
        dry_run=False,
    )
    assert ok is False
    assert await _login(client, email, "ValidOldPass1") == 200


async def test_change_password_dry_run(client):
    email, _, _ = await _account(client, "Dry Run User", "CurrentSecret123")

    ok = await change_password(
        email=email,
        existing_password="CurrentSecret123",
        new_password="NewSecretPass456",
        dry_run=True,
    )
    assert ok is True

    # Password was not actually changed
    assert await _login(client, email, "CurrentSecret123") == 200
    assert await _login(client, email, "NewSecretPass456") == 401


async def test_change_password_api_endpoint(client):
    email, headers, refresh = await _account(client, "API Change User", "ApiOldPassword1")

    # Wrong current password fails with 401
    bad_res = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "WrongPassword99", "new_password": "NewApiPassword2"},
    )
    assert bad_res.status_code == 401

    # Same password fails with 422
    same_res = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "ApiOldPassword1", "new_password": "ApiOldPassword1"},
    )
    assert same_res.status_code == 422

    # Correct current password succeeds with 200
    res = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "ApiOldPassword1", "new_password": "NewApiPassword2"},
    )
    assert res.status_code == 200

    # Old password fails, new password succeeds
    assert await _login(client, email, "ApiOldPassword1") == 401
    assert await _login(client, email, "NewApiPassword2") == 200

    # Prior refresh token revoked
    stale = await client.post(
        "/api/v1/auth/token/refresh", headers=NATIVE, json={"refresh_token": refresh}
    )
    assert stale.status_code == 401

