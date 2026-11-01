"""Typed app config — the keys the admin portal edits and the apps/backend read.

Every entry lives in the generic `configs` table (key → JSONB). A key listed here gets:
- a Pydantic model, so a malformed value is rejected at write time rather than crashing an
  app at read time
- a default, so a fresh database (or a deleted row) still produces a complete bundle
- a `public` flag: public keys are served to the apps via `GET /configs/app`; private ones
  (pricing, verification policy, privacy rules) are read by the backend only.

Unknown keys are still allowed and stored as free-form JSON — the registry is additive.
Defaults that mirror an env setting read it, so the env value stays the fallback until an
admin overrides it in the portal.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.core.constants import BookingStatus, DocumentType

HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"
Role = Literal["patient", "professional"]
Platform = Literal["android", "ios", "web"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── Public (served to apps) ─────────────────────────────────────────────


class FeatureFlags(BaseModel):
    """On/off switches the apps check before showing a feature. Extra keys are allowed so a
    new flag can be rolled out from the portal before the backend knows about it."""

    model_config = ConfigDict(extra="allow")

    reviews: bool = True
    # The patient reads a 4-digit PIN to the professional, who enters it to start the
    # visit. Off by default: app builds older than this release can't send the PIN.
    visit_otp: bool = False
    sos: bool = True
    live_status: bool = True
    gender_preference: bool = True
    coupons: bool = False
    prescription_upload: bool = False
    chat: bool = False
    wallet: bool = False
    referrals: bool = False
    hindi: bool = True


class ThemeConfig(_Strict):
    primary: str = Field(default="#1262E2", pattern=HEX_COLOR)
    primary_dark: str = Field(default="#0F4ABF", pattern=HEX_COLOR)
    accent: str = Field(default="#0EA5A4", pattern=HEX_COLOR)
    success: str = Field(default="#16A34A", pattern=HEX_COLOR)
    warning: str = Field(default="#F59E0B", pattern=HEX_COLOR)
    danger: str = Field(default="#EF4444", pattern=HEX_COLOR)
    radius: int = Field(default=16, ge=0, le=32)


HomeSectionType = Literal[
    "banners", "categories", "book_again", "trust", "how_it_works", "offers", "support"
]


class HomeSection(_Strict):
    type: HomeSectionType
    enabled: bool = True
    title: str | None = Field(default=None, max_length=80)


def _default_home_sections() -> list[HomeSection]:
    return [
        HomeSection(type="banners"),
        HomeSection(type="categories", title="What do you need today?"),
        HomeSection(type="book_again", title="Book again"),
        HomeSection(type="trust"),
        HomeSection(type="how_it_works", title="How Mendyr works"),
        HomeSection(type="support"),
    ]


class HomeConfig(_Strict):
    sections: list[HomeSection] = Field(default_factory=_default_home_sections)

    @field_validator("sections")
    @classmethod
    def _unique_types(cls, sections: list[HomeSection]) -> list[HomeSection]:
        seen = [s.type for s in sections]
        if len(seen) != len(set(seen)):
            raise ValueError("Each home section can appear only once.")
        return sections


class Banner(_Strict):
    id: str = Field(..., min_length=1, max_length=40)
    title: str = Field(..., min_length=1, max_length=80)
    subtitle: str | None = Field(default=None, max_length=160)
    image_url: str | None = Field(default=None, max_length=500)
    cta_label: str | None = Field(default=None, max_length=30)
    # In-app route ("/service/<id>", "/book", "/support") or an https:// link.
    deeplink: str | None = Field(default=None, max_length=300)
    bg_color: str = Field(default="#1262E2", pattern=HEX_COLOR)
    text_color: str = Field(default="#FFFFFF", pattern=HEX_COLOR)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    roles: list[Role] = Field(default_factory=lambda: ["patient"])
    platforms: list[Platform] = Field(default_factory=lambda: ["android", "ios", "web"])
    enabled: bool = True


def _default_banners() -> list[Banner]:
    return [
        Banner(
            id="welcome",
            title="Trusted care, at home",
            subtitle="Verified nurses & caregivers. Pay after the visit.",
            cta_label="Book a visit",
            deeplink="/book",
        )
    ]


class BannersConfig(_Strict):
    items: list[Banner] = Field(default_factory=_default_banners)


class OnboardingSlide(_Strict):
    title: str = Field(..., max_length=80)
    body: str = Field(..., max_length=240)
    image_url: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=40)


def _default_slides() -> list[OnboardingSlide]:
    return [
        OnboardingSlide(
            title="Care that comes home",
            body="Book verified nurses, physiotherapists and caregivers in a few taps.",
            icon="home-heart",
        ),
        OnboardingSlide(
            title="Background-checked professionals",
            body="Every professional is verified by our team before their first visit.",
            icon="shield-check",
        ),
        OnboardingSlide(
            title="Track every step",
            body="Know when your professional is assigned, on the way and has arrived.",
            icon="map-pin",
        ),
    ]


class OnboardingConfig(_Strict):
    slides: list[OnboardingSlide] = Field(default_factory=_default_slides)


class CopyConfig(_Strict):
    """String overrides per locale: `{"en": {"home.hero.title": "..."}, "hi": {...}}`. The
    apps ship their own strings; anything here wins."""

    locales: dict[str, dict[str, str]] = Field(default_factory=dict)


class Faq(_Strict):
    q: str = Field(..., max_length=200)
    a: str = Field(..., max_length=1000)


class SupportConfig(_Strict):
    phone: str | None = Field(default=None, max_length=20)
    whatsapp: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    hours: str = Field(default="7 AM – 10 PM, all days", max_length=60)
    # India's national emergency number; ambulance is 108 in most states.
    sos_number: str = Field(default="112", max_length=20)
    ambulance_number: str = Field(default="108", max_length=20)
    faqs: list[Faq] = Field(default_factory=list)


class PlatformVersion(_Strict):
    min_supported: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    latest: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    store_url: str | None = Field(default=None, max_length=300)


class VersionConfig(_Strict):
    android: PlatformVersion = Field(default_factory=PlatformVersion)
    ios: PlatformVersion = Field(default_factory=PlatformVersion)
    message: str = Field(
        default="A new version of Mendyr is available with improvements.", max_length=200
    )


class MaintenanceConfig(_Strict):
    enabled: bool = False
    title: str = Field(default="We'll be right back", max_length=80)
    message: str = Field(
        default="Mendyr is getting an upgrade. Please check back in a little while.",
        max_length=300,
    )


class BookingRules(_Strict):
    """Patient-facing slot picker rules, plus the server-side limits that back them."""

    slot_start_hour: int = Field(default=7, ge=0, le=23)
    slot_end_hour: int = Field(default=21, ge=1, le=24)
    slot_step_minutes: int = Field(default=30, ge=15, le=120)
    min_lead_minutes: int = Field(default=60, ge=0, le=24 * 60)
    horizon_days: int = Field(default=14, ge=1, le=90)
    free_cancel_window_minutes: int = Field(
        default_factory=lambda: settings.FREE_CANCELLATION_WINDOW_MINUTES, ge=0
    )
    cancellation_fee_pct: float = Field(
        default_factory=lambda: settings.CANCELLATION_FEE_PCT, ge=0, le=100
    )
    # A professional with a visit at 10:00–11:00 doesn't see requests from 09:30 to 11:30:
    # they need time to travel between homes.
    travel_buffer_minutes: int = Field(default=30, ge=0, le=180)
    early_start_minutes: int = Field(default=120, ge=0, le=24 * 60)

    @field_validator("slot_end_hour")
    @classmethod
    def _end_after_start(cls, end: int, info) -> int:  # type: ignore[no-untyped-def]
        start = info.data.get("slot_start_hour")
        if start is not None and end <= start:
            raise ValueError("slot_end_hour must be after slot_start_hour.")
        return end


class CancelReasons(_Strict):
    patient: list[str] = Field(
        default_factory=lambda: [
            "Booked by mistake",
            "Need a different time",
            "Found care elsewhere",
            "Patient's condition changed",
            "Price is too high",
            "Other",
        ]
    )
    professional: list[str] = Field(
        default_factory=lambda: [
            "Personal emergency",
            "Running late / can't reach in time",
            "Patient asked me to cancel",
            "Address is too far",
            "Other",
        ]
    )


INDIAN_LANGUAGES = [
    "English",
    "Hindi",
    "Bengali",
    "Marathi",
    "Telugu",
    "Tamil",
    "Gujarati",
    "Kannada",
    "Malayalam",
    "Punjabi",
    "Odia",
    "Urdu",
]


class ProSettings(_Strict):
    radius_options_km: list[int] = Field(default_factory=lambda: [3, 5, 10, 15, 20, 30])
    default_radius_km: int = Field(default=10, ge=1, le=50)
    languages: list[str] = Field(default_factory=lambda: list(INDIAN_LANGUAGES))
    required_documents: list[DocumentType] = Field(
        default_factory=lambda: [
            DocumentType.GOVERNMENT_ID,
            DocumentType.PROFILE_PHOTO,
            DocumentType.NURSING_COUNCIL_CERTIFICATE,
        ]
    )


class PollingConfig(_Strict):
    """How often the apps refresh while there's no push channel. Seconds."""

    active_booking: int = Field(default=10, ge=3, le=300)
    lists: int = Field(default=30, ge=5, le=600)
    requests: int = Field(default=15, ge=3, le=300)


# ── Private (backend only) ──────────────────────────────────────────────


class PricingConfig(_Strict):
    commission_pct: float = Field(
        default_factory=lambda: settings.PLATFORM_COMMISSION_PCT, ge=0, le=100
    )
    gst_pct: float = Field(default_factory=lambda: settings.GST_PCT, ge=0, le=50)


class VerificationConfig(_Strict):
    # Off: new professionals start PENDING and see no requests until a super admin approves
    # them in the portal.
    auto_approve: bool = False


class PrivacyConfig(_Strict):
    # Once a booking ends this way, neither side sees the other's phone number or the exact
    # address any more — only the booking code and a short user reference.
    hide_contact_on_statuses: list[BookingStatus] = Field(
        default_factory=lambda: [
            BookingStatus.CANCELLED,
            BookingStatus.NO_SHOW,
            BookingStatus.FAILED,
        ]
    )
    # Also hide them this long after a completed visit. 0 keeps them visible.
    hide_contact_hours_after_completion: int = Field(default=24, ge=0, le=24 * 30)


class ServiceContent(_Strict):
    image_url: str | None = Field(default=None, max_length=500)
    tagline: str | None = Field(default=None, max_length=120)
    badge: str | None = Field(default=None, max_length=24)  # e.g. "Bestseller"
    includes: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    faqs: list[Faq] = Field(default_factory=list)


class CatalogContent(_Strict):
    """Presentation content for catalogue services, keyed by service id. Edited from the
    portal's catalogue screen and merged into `GET /services` — kept out of the catalogue
    tables so it could ship without a migration."""

    services: dict[str, ServiceContent] = Field(default_factory=dict)


# ── Registry ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConfigSpec:
    model: type[BaseModel]
    label: str
    group: Literal["experience", "booking", "content", "operations", "platform"]
    description: str
    public: bool


REGISTRY: dict[str, ConfigSpec] = {
    "app.features": ConfigSpec(
        FeatureFlags, "Feature flags", "experience", "Turn app features on or off.", True
    ),
    "app.theme": ConfigSpec(
        ThemeConfig, "Theme", "experience", "Brand colours and corner radius.", True
    ),
    "app.home": ConfigSpec(
        HomeConfig, "Home layout", "experience", "Order and visibility of home sections.", True
    ),
    "app.banners": ConfigSpec(
        BannersConfig, "Banners", "content", "Promotional banners on the home screen.", True
    ),
    "app.onboarding": ConfigSpec(
        OnboardingConfig, "Onboarding", "content", "First-launch intro slides.", True
    ),
    "app.copy": ConfigSpec(
        CopyConfig, "App text", "content", "Override any app string, per language.", True
    ),
    "app.support": ConfigSpec(
        SupportConfig, "Support & SOS", "content", "Helpline, WhatsApp, SOS numbers, FAQs.", True
    ),
    "app.version": ConfigSpec(
        VersionConfig, "App versions", "platform", "Minimum supported and latest versions.", True
    ),
    "app.maintenance": ConfigSpec(
        MaintenanceConfig, "Maintenance mode", "platform", "Show a maintenance screen.", True
    ),
    "app.polling": ConfigSpec(
        PollingConfig, "Refresh intervals", "platform", "How often apps refresh data.", True
    ),
    "booking.rules": ConfigSpec(
        BookingRules, "Booking rules", "booking", "Slots, lead time, cancellation policy.", True
    ),
    "booking.cancel_reasons": ConfigSpec(
        CancelReasons, "Cancel reasons", "booking", "Reasons shown when cancelling.", True
    ),
    "pro.settings": ConfigSpec(
        ProSettings, "Professional settings", "operations", "Radius, languages, documents.", True
    ),
    "pricing": ConfigSpec(
        PricingConfig, "Pricing", "booking", "Platform commission and GST.", False
    ),
    "verification": ConfigSpec(
        VerificationConfig,
        "Verification policy",
        "operations",
        "Whether new professionals need manual approval.",
        False,
    ),
    "catalog.content": ConfigSpec(
        CatalogContent,
        "Service content",
        "content",
        "Images, highlights and FAQs for each service.",
        False,
    ),
    "privacy": ConfigSpec(
        PrivacyConfig, "Privacy", "operations", "When contact details are hidden.", False
    ),
}


def default_value(key: str) -> dict:
    return REGISTRY[key].model().model_dump(mode="json")


def validate_value(key: str, value: object) -> object:
    """Normalised value for a registered key (raises pydantic.ValidationError); unknown keys
    pass through untouched."""
    spec = REGISTRY.get(key)
    if spec is None:
        return value
    return spec.model.model_validate(value).model_dump(mode="json")
