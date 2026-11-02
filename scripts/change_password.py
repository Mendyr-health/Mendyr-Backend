"""Change an account's password by verifying its existing (current) password first.

Unlike reset_password.py (which generates a random password without needing the current one),
this script allows setting a chosen new password as long as the existing password is known
and verified. Works for all accounts (patients, professionals, admins, ops, super admins).

When changed, all active sessions (refresh tokens) are immediately revoked, requiring a
fresh login with the new password. The change is recorded in the activity audit log.

Usage:
    # Interactive (prompts securely for passwords without echoing):
    uv run python -m scripts.change_password --email user@example.com

    # Direct arguments / CI / scripted:
    uv run python -m scripts.change_password \\
        --email user@example.com \\
        --existing-password "CurrentPass123" \\
        --new-password "NewSecurePass456"

    # Environment variables (recommended in CI/GitHub Actions to avoid process listings):
    EMAIL="user@example.com" EXISTING_PASSWORD="..." NEW_PASSWORD="..." \\
        uv run python -m scripts.change_password

    # Dry-run mode (verifies account and current password, commits nothing):
    uv run python -m scripts.change_password --email user@example.com --dry-run
"""

import argparse
import asyncio
import getpass
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.constants import UserStatus
from app.core.security import hash_password, verify_password
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.services.audit_service import AuditService


def _read_passwords(
    arg_existing: str | None,
    arg_new: str | None,
) -> tuple[str, str]:
    """Read existing and new passwords from args, env vars, or interactive prompt."""
    existing_password = arg_existing or os.environ.get("EXISTING_PASSWORD")
    if not existing_password:
        if sys.stdin.isatty():
            existing_password = getpass.getpass("Existing password: ")
        else:
            raise SystemExit(
                "Missing existing password: provide via --existing-password, $EXISTING_PASSWORD, "
                "or run in an interactive terminal."
            )

    new_password = arg_new or os.environ.get("NEW_PASSWORD")
    if not new_password:
        if sys.stdin.isatty():
            new_password = getpass.getpass("New password: ")
            confirm = getpass.getpass("Confirm new password: ")
            if new_password != confirm:
                raise SystemExit("New passwords did not match.")
        else:
            raise SystemExit(
                "Missing new password: provide via --new-password, $NEW_PASSWORD, "
                "or run in an interactive terminal."
            )

    return existing_password, new_password


async def change_password(
    email: str,
    existing_password: str,
    new_password: str,
    *,
    dry_run: bool = False,
) -> bool:
    """Verify existing password and set new password for the specified email.

    Returns True on success, False on failure.
    """
    clean_email = email.strip().lower()

    if len(new_password) < 8:
        print("✗ New password must be at least 8 characters.")
        return False

    if existing_password == new_password:
        print("✗ New password cannot be the same as the existing password.")
        return False

    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        tokens = RefreshTokenRepository(session)
        audit = AuditService(session)

        stmt = select(User).where(func.lower(User.email) == clean_email)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if user is None or user.deleted_at is not None or user.status == UserStatus.DELETED:
            print(f"✗ No active account found for '{clean_email}'.")
            return False

        if not user.hashed_password or not verify_password(existing_password, user.hashed_password):
            print(f"✗ Incorrect existing password for '{clean_email}'.")
            return False

        if dry_run:
            print(
                f"Dry run — existing password verified for {clean_email} ({user.role.value}). "
                "No changes made."
            )
            await session.rollback()
            return True

        user.hashed_password = hash_password(new_password)
        await tokens.revoke_all_for_user(user.id, now=now)
        audit.log(
            actor_id=user.id,
            action="user.password_change",
            entity_type="user",
            entity_id=str(user.id),
            metadata={"via": "change_password script"},
        )
        await session.commit()

    print(f"✓ Password successfully changed for {clean_email} ({user.role.value}).")
    print("All previous sessions have been signed out; sign in with the new password immediately.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--email",
        default=os.environ.get("EMAIL"),
        help="Account email address (or set $EMAIL).",
    )
    parser.add_argument(
        "--existing-password",
        default=None,
        help="Current password (or set $EXISTING_PASSWORD, or leave blank to be prompted).",
    )
    parser.add_argument(
        "--new-password",
        default=None,
        help="New password to set (or set $NEW_PASSWORD, or leave blank to be prompted).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.environ.get("DRY_RUN", "").lower() in ("true", "1"),
        help="Verify the existing password without making any changes.",
    )

    args = parser.parse_args()

    email = args.email
    if not email:
        if sys.stdin.isatty():
            email = input("Account email: ").strip()
        else:
            raise SystemExit("No email provided. Use --email or set $EMAIL.")

    if not email:
        raise SystemExit("Email cannot be blank.")

    existing_password, new_password = _read_passwords(args.existing_password, args.new_password)

    success = asyncio.run(
        change_password(
            email=email,
            existing_password=existing_password,
            new_password=new_password,
            dry_run=args.dry_run,
        )
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

