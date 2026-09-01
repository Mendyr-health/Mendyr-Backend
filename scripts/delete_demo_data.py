"""Permanently remove the accounts created by `seed_demo_data.py` — the demo patient and
nurses, matched by their `*.demo@mendyr.app` email suffix. Deliberately narrower than
`@mendyr.app` alone: real accounts already exist on that domain (e.g. `nik@mendyr.app`) that
this must never touch.

This is a hard DELETE, not the soft-delete `create_admin.py delete` does for real users:
these accounts are only ever pricing/onboarding/profile data (no bookings, payments, reviews,
or support tickets, none of which cascade), so a real delete is safe here specifically because
`seed_demo_data.py` never creates rows in those tables. Do not repurpose this script for
deleting a real user — see `create_admin.py`'s docstring for why that's unsafe.

Usage:
    uv run python -m scripts.delete_demo_data
"""

import asyncio

from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.models.user import User

DEMO_EMAIL_SUFFIX = ".demo@mendyr.app"


async def delete_demo_data() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email.like(f"%{DEMO_EMAIL_SUFFIX}")))
        users = result.scalars().all()
        if not users:
            print("No demo accounts found — nothing to delete.")
            return

        # `users.referred_by_id` is a self-referential FK, so an account that referred someone
        # cannot be deleted while that referral row still points at it. Two demo accounts in
        # one run collide on this by themselves: SQLAlchemy emits the deletes as a single
        # executemany, and the referrer can be removed before the account referred by them.
        # Clearing the links first also covers the case that matters more — a real, non-demo
        # user who signed up with a demo account's referral code, who must survive this with
        # their own row intact rather than being cascaded away with the referrer.
        cleared = await session.execute(
            update(User)
            .where(User.referred_by_id.in_([u.id for u in users]))
            .values(referred_by_id=None)
        )
        if cleared.rowcount:
            print(f"  cleared {cleared.rowcount} referral link(s) pointing at these accounts")
        await session.flush()

        for user in users:
            print(f"  deleting {user.email} ({user.role.value})")
            await session.delete(user)

        await session.commit()
    print(f"\nDeleted {len(users)} demo account(s) and everything cascaded from them.")


if __name__ == "__main__":
    asyncio.run(delete_demo_data())
