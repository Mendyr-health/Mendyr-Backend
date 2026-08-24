"""Unauthenticated public-site schemas: landing-page waitlist signup and the Contact Us
form (src/app/(public)/page.tsx and src/app/(public)/contact/page.tsx).
"""

from app.schemas.common import CamelModel


class WaitlistSignupIn(CamelModel):
    email: str
    source: str | None = None


class ContactSubmitIn(CamelModel):
    name: str
    email: str
    phone: str | None = None
    subject: str
    message: str
