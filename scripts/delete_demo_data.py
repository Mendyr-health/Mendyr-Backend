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

from sqlalchemy import select

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

        for user in users:
            print(f"  deleting {user.email} ({user.role.value})")
            await session.delete(user)

        await session.commit()
    print(f"\nDeleted {len(users)} demo account(s) and everything cascaded from them.")


if __name__ == "__main__":
    asyncio.run(delete_demo_data())
