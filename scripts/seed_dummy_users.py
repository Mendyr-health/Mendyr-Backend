"""Seed a larger set of dummy accounts for testing: 18 professionals (three of every profession)
and 12 patients, all around Bengaluru. Every patient has a default address and at least one
professional of each profession within the 15 km service radius, so a booking of any service
from any patient shows up in some professional's request list.

The professionals are approved, online, available any time, and opted into their profession's
catalogue services. Doctors are seeded too but get no requests until the catalogue has a
doctor service.

Run `python -m scripts.seed` first — this assumes the service catalogue already exists.

Usage:
    uv run python -m scripts.seed_dummy_users

Non-interactive and idempotent — matched by email, safe to re-run. Every account uses the
`*.dummy@mendyr.app` email suffix and the demo password, and the script prints all of them.
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.constants import Gender, ProfessionalType, UserRole
from app.db.session import AsyncSessionLocal
from app.models.service import Service
from app.services.wallet_service import WalletService
from scripts.seed_demo_data import (
    DEMO_PASSWORD,
    _ensure_address,
    _ensure_professional,
    _get_or_create_user,
)

EMAIL_SUFFIX = ".dummy@mendyr.app"
F, M = Gender.FEMALE, Gender.MALE
P = ProfessionalType

# Bengaluru localities used below: (lat, lng, pincode).
LOCALITIES = {
    # Professionals
    "Hebbal": (13.0358, 77.5970, "560024"),
    "Indiranagar": (12.9719, 77.6412, "560038"),
    "Jayanagar": (12.9250, 77.5938, "560041"),
    "Malleshwaram": (13.0031, 77.5643, "560003"),
    "Koramangala": (12.9352, 77.6245, "560034"),
    "JP Nagar": (12.9063, 77.5857, "560078"),
    "RT Nagar": (13.0213, 77.5960, "560032"),
    "Domlur": (12.9610, 77.6387, "560071"),
    "BTM Layout": (12.9166, 77.6101, "560076"),
    "Kalyan Nagar": (13.0280, 77.6400, "560043"),
    "Ulsoor": (12.9817, 77.6286, "560008"),
    "Bommanahalli": (12.9000, 77.6250, "560068"),
    "Sadashivanagar": (13.0068, 77.5813, "560080"),
    "HSR Layout": (12.9116, 77.6474, "560102"),
    "Basavanagudi": (12.9422, 77.5735, "560004"),
    "Frazer Town": (12.9986, 77.6170, "560005"),
    "Old Airport Road": (12.9600, 77.6500, "560017"),
    "Rajajinagar": (12.9910, 77.5525, "560010"),
    # Patients
    "Whitefield": (12.9698, 77.7500, "560066"),
    "Marathahalli": (12.9591, 77.6974, "560037"),
    "Electronic City": (12.8452, 77.6602, "560100"),
    "Yelahanka": (13.1005, 77.5963, "560064"),
    "Bellandur": (12.9304, 77.6784, "560103"),
    "Vijayanagar": (12.9719, 77.5329, "560040"),
    "Banaswadi": (13.0141, 77.6518, "560043"),
    "Yeshwanthpur": (13.0285, 77.5400, "560022"),
    "Shivajinagar": (12.9857, 77.6057, "560001"),
    "Sarjapur Road": (12.9100, 77.6870, "560035"),
    "RR Nagar": (12.9274, 77.5155, "560098"),
    "Cooke Town": (12.9980, 77.6280, "560005"),
}

# Per profession, one professional each in the north, centre-east and south of the city.
# (email prefix, name, gender, profession, locality)
PROFESSIONALS = [
    ("nurse01", "Ananya Iyer", F, P.NURSE, "Hebbal"),
    ("nurse02", "Meera Nair", F, P.NURSE, "Indiranagar"),
    ("nurse03", "Sunita Gowda", F, P.NURSE, "Jayanagar"),
    ("physio01", "Arjun Rao", M, P.PHYSIOTHERAPIST, "Malleshwaram"),
    ("physio02", "Neha Kulkarni", F, P.PHYSIOTHERAPIST, "Koramangala"),
    ("physio03", "Vikram Shetty", M, P.PHYSIOTHERAPIST, "JP Nagar"),
    ("caretaker01", "Ramesh Kumar", M, P.CARETAKER, "RT Nagar"),
    ("caretaker02", "Lakshmi Devi", F, P.CARETAKER, "Domlur"),
    ("caretaker03", "Suresh Babu", M, P.CARETAKER, "BTM Layout"),
    ("babycare01", "Fatima Sheikh", F, P.BABY_CARE_SPECIALIST, "Kalyan Nagar"),
    ("babycare02", "Pooja Hegde", F, P.BABY_CARE_SPECIALIST, "Ulsoor"),
    ("babycare03", "Divya Menon", F, P.BABY_CARE_SPECIALIST, "Bommanahalli"),
    ("labtech01", "Imran Khan", M, P.LAB_TECHNICIAN, "Sadashivanagar"),
    ("labtech02", "Kiran Patil", M, P.LAB_TECHNICIAN, "HSR Layout"),
    ("labtech03", "Shreya Joshi", F, P.LAB_TECHNICIAN, "Basavanagudi"),
    ("doctor01", "Dr. Rahul Verma", M, P.DOCTOR, "Frazer Town"),
    ("doctor02", "Dr. Kavya Reddy", F, P.DOCTOR, "Old Airport Road"),
    ("doctor03", "Dr. Sameer Desai", M, P.DOCTOR, "Rajajinagar"),
]

# (email prefix, name, gender, year of birth, street, locality)
PATIENTS = [
    ("patient01", "Gopal Krishnan", M, 1948, "14, ITPL Main Road", "Whitefield"),
    ("patient02", "Saroja Rao", F, 1952, "7, Outer Ring Road", "Marathahalli"),
    ("patient03", "Nikhil Agarwal", M, 1991, "102, Neeladri Road", "Electronic City"),
    ("patient04", "Kamala Murthy", F, 1945, "33, Bazaar Street", "Yelahanka"),
    ("patient05", "Ritu Sharma", F, 1994, "B-1204, Green Glen Layout", "Bellandur"),
    ("patient06", "Venkatesh Prasad", M, 1956, "88, 9th Main Road", "Vijayanagar"),
    ("patient07", "Ayesha Siddiqui", F, 1989, "21, Kammanahalli Main Road", "Banaswadi"),
    ("patient08", "Harish Chandra", M, 1950, "5, Tumkur Road", "Yeshwanthpur"),
    ("patient09", "Mary Thomas", F, 1960, "17, Infantry Road", "Shivajinagar"),
    ("patient10", "Sanjay Mishra", M, 1985, "C-305, Kaikondrahalli", "Sarjapur Road"),
    ("patient11", "Deepa Ramesh", F, 1992, "61, BEML Layout", "RR Nagar"),
    ("patient12", "Joseph D'Souza", M, 1942, "9, Wheeler Road", "Cooke Town"),
]


async def seed() -> None:
    credentials: list[tuple[str, str, str]] = []
    async with AsyncSessionLocal() as session:
        services = (await session.execute(select(Service))).scalars().all()
        if not services:
            print(
                "WARNING: no services found — run `uv run python -m scripts.seed` first, "
                "then re-run this script to opt the professionals into services."
            )

        for idx, (prefix, name, gender, kind, locality) in enumerate(PROFESSIONALS, 1):
            lat, lng, _ = LOCALITIES[locality]
            email = f"{prefix}{EMAIL_SUFFIX}"
            user = await _get_or_create_user(
                session,
                email=email,
                full_name=name,
                phone_number=f"+9197000010{idx:02d}",
                role=UserRole.PROFESSIONAL,
                gender=gender,
                date_of_birth=datetime(1980 + idx, 1 + idx % 12, 10, tzinfo=UTC),
            )
            await WalletService(session).get_or_create_wallet(user.id)
            await _ensure_professional(
                session,
                user,
                kind=kind,
                years_of_experience=2 + idx % 10,
                languages=["English", "Hindi", "Kannada"],
                lat=lat,
                lng=lng,
                timings=None,
                services=services,
            )
            credentials.append((email, kind.value, locality))

        for idx, (prefix, name, gender, born, street, locality) in enumerate(PATIENTS, 1):
            lat, lng, pincode = LOCALITIES[locality]
            email = f"{prefix}{EMAIL_SUFFIX}"
            user = await _get_or_create_user(
                session,
                email=email,
                full_name=name,
                phone_number=f"+9197000020{idx:02d}",
                role=UserRole.PATIENT,
                gender=gender,
                date_of_birth=datetime(born, 1 + idx % 12, 15, tzinfo=UTC),
            )
            await WalletService(session).get_or_create_wallet(user.id)
            await _ensure_address(
                session,
                user,
                line1=f"{street}, {locality}",
                city="Bengaluru",
                state="Karnataka",
                pincode=pincode,
                lat=lat,
                lng=lng,
            )
            credentials.append((email, "patient", locality))

        await session.commit()

    print(f"\nDummy accounts ready (password for all: {DEMO_PASSWORD}):\n")
    for email, role, locality in credentials:
        print(f"  [{role:20}] {email:32} {locality}")
    print(
        f"\n{len(PROFESSIONALS)} professionals (approved, online, any time, 15 km radius) and "
        f"{len(PATIENTS)} patients with a default address, all around Bengaluru."
    )


if __name__ == "__main__":
    asyncio.run(seed())
