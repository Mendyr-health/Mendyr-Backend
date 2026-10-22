"""Unit tests for user deletion / cleanup parsing and service logic."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.user import User
from app.services.user_cleanup_service import (
    UserCleanupService,
    parse_user_identifiers,
)


def test_parse_user_identifiers_handles_various_formats():
    # Comma-separated string with mixed spacing and quotes
    input_str = "user1@example.com, 'user2@example.com', \"user3@example.com\",  , user1@example.com "
    result = parse_user_identifiers(input_str)
    assert result == ["user1@example.com", "user2@example.com", "user3@example.com"]


def test_parse_user_identifiers_handles_sequence():
    seq = ["a@b.com, c@d.com", "e@f.com", "a@b.com"]
    result = parse_user_identifiers(seq)
    assert result == ["a@b.com", "c@d.com", "e@f.com"]


def test_parse_user_identifiers_empty():
    assert parse_user_identifiers("") == []
    assert parse_user_identifiers(["", "  "]) == []


@pytest.mark.asyncio
async def test_cleanup_service_identifies_missing_and_found_users():
    found_id = uuid.uuid4()
    mock_user = MagicMock(spec=User)
    mock_user.id = found_id
    mock_user.email = "found@example.com"
    mock_user.phone_number = "+919876543210"
    mock_user.role = MagicMock()
    mock_user.role.value = "patient"
    mock_user.full_name = "Found Patient"

    session = AsyncMock()

    # When querying for users
    mock_users_res = MagicMock()
    mock_users_res.scalars.return_value.all.return_value = [mock_user]

    # When querying for pro profiles, bookings, care plans, tickets, visits, wallets
    empty_res = MagicMock()
    empty_res.all.return_value = []

    # Execution mock return values in order:
    # 1. users
    # 2. pro_profiles
    # 3. patient_bookings
    # 4. care_plans
    # 5. tickets
    # 6. wallets
    # 7. updates and deletes
    exec_count = 0

    async def mock_execute(stmt, *args, **kwargs):
        nonlocal exec_count
        exec_count += 1
        if exec_count == 1:
            return mock_users_res
        elif exec_count in (2, 3, 4, 5, 6):
            return empty_res
        row_mock = MagicMock()
        row_mock.rowcount = 1
        return row_mock

    session.execute.side_effect = mock_execute

    service = UserCleanupService(session)
    summary = await service.delete_users("found@example.com, notfound@example.com", dry_run=True)

    assert len(summary.found_users) == 1
    assert summary.found_users[0].id == found_id
    assert summary.found_users[0].email == "found@example.com"
    assert summary.not_found_identifiers == ["notfound@example.com"]
    assert summary.dry_run is True
    session.rollback.assert_awaited_once()

