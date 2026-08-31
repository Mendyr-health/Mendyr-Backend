"""Create or promote an admin user — the only supported way to provision `role=admin` accounts.

`POST /auth/register` only ever creates `patient`/`professional` accounts (enforced in
`app/schemas/auth.py`); `admin`/`ops` accounts are deliberately unreachable through any public
API, so they can only come from someone with direct database access running this script.

Usage:
    # Promote an existing user (created via normal signup) to admin:
    uv run python -m scripts.create_admin promote --email you@example.com

    # Bootstrap a brand-new admin account (e.g. the very first admin on a fresh DB):
    uv run python -m scripts.create_admin create \\
        --email you@example.com --phone +919876500000 --full-name "Jane Doe"

Password: set $ADMIN_PASSWORD before running, or leave it unset to be prompted interactively
(hidden input). Never pass it as a `--password` flag — it would end up in shell history and
process listings.
"""
import argparse
import asyncio
import getpass
import json
import os
import secrets
import string
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.constants import UserRole, UserStatus
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.user import User

REFERRAL_ALPHABET = string.ascii_uppercase + string.digits


def _generate_referral_code() -> str:
    return "".join(secrets.choice(REFERRAL_ALPHABET) for _ in range(8))


def _read_password() -> str:
    password = os.environ.get("ADMIN_PASSWORD")
    if password:
        return password

    password = getpass.getpass("Password: ")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords did not match.")
    return password


async def promote(email: str) -> None:
    email = email.strip().lower()
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"No user found with email {email!r} — use `create` to bootstrap one.")
        if user.role is UserRole.ADMIN:
            print(f"{email} is already an admin. Nothing to do.")
            return

        previous_role = user.role.value
        user.role = UserRole.ADMIN
        session.add(
            AuditLog(
                actor_id=None,
                action="user.promoted_to_admin",
                entity_type="user",
                entity_id=str(user.id),
                metadata_json=json.dumps({"previous_role": previous_role}),
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    print(f"Promoted {email} (was {previous_role}) to admin.")


async def create(*, email: str, phone_number: str, full_name: str) -> None:
    email = email.strip().lower()
    password = _read_password()

    async with AsyncSessionLocal() as session:
        if (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none() is not None:
            raise SystemExit(f"A user with email {email!r} already exists — use `promote` instead.")
        if (
            await session.execute(select(User).where(User.phone_number == phone_number))
        ).scalar_one_or_none() is not None:
            raise SystemExit(f"A user with phone number {phone_number!r} already exists.")

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            phone_number=phone_number,
            referral_code=_generate_referral_code(),
            last_login_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()
        session.add(
            AuditLog(
                actor_id=None,
                action="user.created_as_admin",
                entity_type="user",
                entity_id=str(user.id),
                metadata_json=None,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    print(f"Created admin user {email}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    promote_parser = subparsers.add_parser("promote", help="Promote an existing user to admin.")
    promote_parser.add_argument("--email", required=True)

    create_parser = subparsers.add_parser("create", help="Create a brand-new admin user.")
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--phone", required=True, dest="phone_number")
    create_parser.add_argument("--full-name", required=True, dest="full_name")

    args = parser.parse_args()

    if args.command == "promote":
        asyncio.run(promote(args.email))
    else:
        asyncio.run(
            create(email=args.email, phone_number=args.phone_number, full_name=args.full_name)
        )


if __name__ == "__main__":
    main()
