"""Reset the password of one or more accounts — patients, professionals, admins, ops. Super
admin accounts are never touched (a super admin changes their own password).

Each account gets its own new random password, printed once, and every session it had is
signed out (refresh tokens revoked; the 30-minute access token is the only thing that
outlives it). Each reset is recorded in the activity log.

Usage:
    uv run python -m scripts.reset_password --users "a@x.com, b@y.com" [--dry-run]

Passwords are generated, never passed in: a password typed into a command or a workflow
input ends up in shell history or the run's input record.
"""

import argparse
import asyncio
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.constants import UserRole, UserStatus
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.services.audit_service import AuditService

# No look-alikes (0/O, 1/l/I) — these get read out over the phone or copied from a log.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def generate_password() -> str:
    """e.g. `Kp7w-x2Qm-9fHt` — 12 random characters (~70 bits) in readable groups."""
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3))


def parse_emails(raw: str) -> list[str]:
    seen: dict[str, None] = {}
    for part in raw.replace("\n", ",").replace(";", ",").split(","):
        email = part.strip().lower()
        if email:
            seen[email] = None
    return list(seen)


async def reset(emails: list[str], *, dry_run: bool) -> int:
    """Returns how many accounts couldn't be reset."""
    results: list[tuple[str, str]] = []
    failed = 0
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        tokens = RefreshTokenRepository(session)
        audit = AuditService(session)
        for email in emails:
            user = (
                await session.execute(select(User).where(func.lower(User.email) == email))
            ).scalar_one_or_none()
            if user is None or user.deleted_at is not None or user.status == UserStatus.DELETED:
                results.append((email, "✗ no such account"))
                failed += 1
                continue
            if user.role == UserRole.SUPER_ADMIN:
                results.append((email, "✗ skipped — super admin passwords can't be reset here"))
                failed += 1
                continue
            if dry_run:
                results.append((email, f"would reset ({user.role.value})"))
                continue
            password = generate_password()
            user.hashed_password = hash_password(password)
            await tokens.revoke_all_for_user(user.id, now=now)
            audit.log(
                actor_id=None,
                action="user.password_reset",
                entity_type="user",
                entity_id=str(user.id),
                metadata={"via": "reset_password script"},
            )
            results.append((email, f"✓ {user.role.value:<12} new password: {password}"))
        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    width = max((len(e) for e, _ in results), default=0)
    print("Dry run — nothing changed.\n" if dry_run else "Passwords reset:\n")
    for email, outcome in results:
        print(f"  {email:<{width}}  {outcome}")
    if not dry_run and failed < len(results):
        print(
            "\nShare each password privately. Every session of these accounts has been signed"
            " out; they can sign in with the new password straight away."
        )
    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--users", required=True, help="Emails separated by commas, semicolons or new lines."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    emails = parse_emails(args.users)
    if not emails:
        raise SystemExit("No emails given.")
    failed = asyncio.run(reset(emails, dry_run=args.dry_run))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
