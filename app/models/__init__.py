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
from app.models.config import Config
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
from app.models.support import SupportTicket, SupportTicketMessage
from app.models.user import DeviceToken, OTPVerification, User
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
    "Config",
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
    "SupportTicket",
    "SupportTicketMessage",
    "DeviceToken",
    "OTPVerification",
    "User",
    "Coupon",
    "CouponRedemption",
    "Wallet",
    "WalletTransaction",
]
