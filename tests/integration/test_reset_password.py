"""The reset-password script: new password works, old one and old sessions don't, super
admins are never touched."""

import re
import uuid

import pytest

from app.core.constants import UserRole
from scripts.reset_password import ALPHABET, generate_password, parse_emails, reset
from tests.integration.test_booking_flow import NATIVE, _data
from tests.integration.test_premium_rules import _set_user

pytestmark = pytest.mark.asyncio


async def _account(client, name: str) -> tuple[str, dict, str]:
    suffix = uuid.uuid4().hex[:8]
    email = f"reset-{suffix}@example.com"
    body = _data(
        await client.post(
            "/api/v1/auth/register",
            headers=NATIVE,
            json={
                "email": email,
                "password": "OldPassword@1",
                "full_name": name,
                "phone_number": f"+9197{int(suffix, 16) % 10**8:08d}",
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


def test_generated_passwords_are_readable_and_strong():
    password = generate_password()
    assert re.fullmatch(r"[A-Za-z2-9]{4}-[A-Za-z2-9]{4}-[A-Za-z2-9]{4}", password)
    assert not set(password.replace("-", "")) - set(ALPHABET)
    assert parse_emails("A@x.com; b@y.com,\n a@x.com ") == ["a@x.com", "b@y.com"]


async def test_reset_signs_out_and_skips_super_admins(client, capsys):
    patient, _, refresh = await _account(client, "Reset Patient")
    ops, ops_headers, _ = await _account(client, "Reset Ops")
    await _set_user(ops_headers, role=UserRole.OPS)
    boss, boss_headers, _ = await _account(client, "Reset Boss")
    await _set_user(boss_headers, role=UserRole.SUPER_ADMIN)

    failed = await reset([patient, ops, boss, "nobody@example.com"], dry_run=False)
    out = capsys.readouterr().out
    assert failed == 2
    assert "super admin passwords can't be reset" in out and "no such account" in out
    passwords = dict(re.findall(r"(\S+@example\.com)\s+✓\s+\w+\s+new password: (\S+)", out))
    assert set(passwords) == {patient, ops}

    assert await _login(client, patient, "OldPassword@1") == 401
    assert await _login(client, patient, passwords[patient]) == 200
    assert await _login(client, ops, passwords[ops]) == 200
    assert await _login(client, boss, "OldPassword@1") == 200  # untouched

    stale = await client.post(
        "/api/v1/auth/token/refresh", headers=NATIVE, json={"refresh_token": refresh}
    )
    assert stale.status_code == 401


async def test_dry_run_changes_nothing(client, capsys):
    patient, _, _ = await _account(client, "Dry Run Patient")
    assert await reset([patient], dry_run=True) == 0
    assert "would reset" in capsys.readouterr().out
    assert await _login(client, patient, "OldPassword@1") == 200
