"""Import every model module so `Base.metadata` is fully populated for Alembic autogenerate."""

from app.models.address import Address
from app.models.audit import AuditLog
from app.models.booking import (
    Booking,
    BookingOffer,
    BookingStatusHistory,
    BookingVisit,
    CarePlan,
    VisitTrackingPing,
)
from app.models.contact import ContactInquiry
from app.models.messaging import Message, MessageThread
from app.models.notification import Notification
from app.models.patient import PatientProfile
from app.models.payment import Payment, Payout
from app.models.professional import (
    ProfessionalAvailabilitySlot,
    ProfessionalDocument,
    ProfessionalProfile,
    ProfessionalSpecialization,
    Specialization,
)
from app.models.review import Review
from app.models.service import ProfessionalService, Service, ServiceCategory
from app.models.settings import PlatformSettings
from app.models.support import SupportTicket, SupportTicketMessage
from app.models.user import DeviceToken, OTPVerification, User
from app.models.waitlist import WaitlistEntry
from app.models.wallet import Coupon, CouponRedemption, Wallet, WalletTransaction

__all__ = [
    "Address",
    "AuditLog",
    "Booking",
    "BookingOffer",
    "BookingStatusHistory",
    "BookingVisit",
    "CarePlan",
    "VisitTrackingPing",
    "ContactInquiry",
    "Message",
    "MessageThread",
    "Notification",
    "PatientProfile",
    "Payment",
    "Payout",
    "ProfessionalAvailabilitySlot",
    "ProfessionalDocument",
    "ProfessionalProfile",
    "ProfessionalSpecialization",
    "Specialization",
    "Review",
    "ProfessionalService",
    "Service",
    "ServiceCategory",
    "PlatformSettings",
    "SupportTicket",
    "SupportTicketMessage",
    "DeviceToken",
    "OTPVerification",
    "User",
    "WaitlistEntry",
    "Coupon",
    "CouponRedemption",
    "Wallet",
    "WalletTransaction",
]
