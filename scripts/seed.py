"""Seed reference data: service categories, services and specializations.

Run with: `python -m scripts.seed` (after `alembic upgrade head`).
Idempotent — safe to re-run; existing rows (matched by slug/name) are left untouched.
"""
import asyncio

from sqlalchemy import select

from app.core.constants import ProfessionalType
from app.db.session import AsyncSessionLocal
from app.models.professional import Specialization
from app.models.service import Service, ServiceCategory

CATEGORIES = [
    {"name": "Nursing Care", "slug": "nursing-care", "display_order": 1},
    {"name": "Physiotherapy", "slug": "physiotherapy", "display_order": 2},
    {"name": "Elder Care", "slug": "elder-care", "display_order": 3},
    {"name": "Mother & Baby Care", "slug": "mother-baby-care", "display_order": 4},
    {"name": "Lab Sample Collection", "slug": "lab-sample-collection", "display_order": 5},
]

SERVICES = [
    {
        "category_slug": "nursing-care",
        "name": "General Nursing — 12 hr shift",
        "slug": "general-nursing-12hr",
        "required_professional_type": ProfessionalType.NURSE,
        "duration_minutes": 720,
        "base_price": 1800,
    },
    {
        "category_slug": "nursing-care",
        "name": "ICU-Trained Nursing — 12 hr shift",
        "slug": "icu-nursing-12hr",
        "required_professional_type": ProfessionalType.NURSE,
        "duration_minutes": 720,
        "base_price": 2600,
    },
    {
        "category_slug": "physiotherapy",
        "name": "Physiotherapy Session",
        "slug": "physiotherapy-session",
        "required_professional_type": ProfessionalType.PHYSIOTHERAPIST,
        "duration_minutes": 45,
        "base_price": 700,
    },
    {
        "category_slug": "elder-care",
        "name": "Elder Care Attendant — 8 hr shift",
        "slug": "elder-care-8hr",
        "required_professional_type": ProfessionalType.CARETAKER,
        "duration_minutes": 480,
        "base_price": 1200,
    },
    {
        "category_slug": "mother-baby-care",
        "name": "New-Mother & Baby Care — 8 hr shift",
        "slug": "mother-baby-care-8hr",
        "required_professional_type": ProfessionalType.BABY_CARE_SPECIALIST,
        "duration_minutes": 480,
        "base_price": 1400,
    },
    {
        "category_slug": "lab-sample-collection",
        "name": "At-Home Lab Sample Collection",
        "slug": "lab-sample-collection-visit",
        "required_professional_type": ProfessionalType.LAB_TECHNICIAN,
        "duration_minutes": 20,
        "base_price": 200,
    },
]

SPECIALIZATIONS = [
    "ICU Care",
    "Wound Dressing",
    "Post-Operative Care",
    "Diabetic Care",
    "Palliative Care",
    "Ventilator Support",
    "Ryles Tube / Catheter Care",
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        category_ids: dict[str, object] = {}
        for cat in CATEGORIES:
            existing = (
                await session.execute(select(ServiceCategory).where(ServiceCategory.slug == cat["slug"]))
            ).scalar_one_or_none()
            if existing is None:
                existing = ServiceCategory(**cat)
                session.add(existing)
                await session.flush()
            category_ids[cat["slug"]] = existing.id

        for svc in SERVICES:
            existing = (
                await session.execute(select(Service).where(Service.slug == svc["slug"]))
            ).scalar_one_or_none()
            if existing is None:
                data = {k: v for k, v in svc.items() if k != "category_slug"}
                data["category_id"] = category_ids[svc["category_slug"]]
                session.add(Service(**data))

        for name in SPECIALIZATIONS:
            existing = (
                await session.execute(select(Specialization).where(Specialization.name == name))
            ).scalar_one_or_none()
            if existing is None:
                session.add(Specialization(name=name))

        await session.commit()
    print(f"Seeded {len(CATEGORIES)} categories, {len(SERVICES)} services, "
          f"{len(SPECIALIZATIONS)} specializations.")


if __name__ == "__main__":
    asyncio.run(seed())
