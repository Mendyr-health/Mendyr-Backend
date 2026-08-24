"""Shared enums — mirrored as Postgres ENUM types in the Alembic migration.

Keep this file and `alembic/versions/0001_initial_schema.py` in sync: adding a
value here requires an `ALTER TYPE ... ADD VALUE` migration in production.
"""

from enum import StrEnum


class UserRole(StrEnum):
    PATIENT = "patient"
    PROFESSIONAL = "professional"  # nurse-facing role in the current product scope
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"  # platform governance: manage admins, roles, audit logs
    OPS = "ops"  # internal support / dispatch staff


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNSPECIFIED = "unspecified"


class ProfessionalType(StrEnum):
    NURSE = "nurse"
    PHYSIOTHERAPIST = "physiotherapist"
    CARETAKER = "caretaker"
    LAB_TECHNICIAN = "lab_technician"
    DOCTOR = "doctor"
    BABY_CARE_SPECIALIST = "baby_care_specialist"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class DocumentType(StrEnum):
    GOVERNMENT_ID = "government_id"
    NURSING_COUNCIL_CERTIFICATE = "nursing_council_certificate"
    DEGREE_CERTIFICATE = "degree_certificate"
    POLICE_VERIFICATION = "police_verification"
    PROFILE_PHOTO = "profile_photo"
    ADDRESS_PROOF = "address_proof"


class AvailabilityStatus(StrEnum):
    OFFLINE = "offline"
    ONLINE = "online"
    ON_VISIT = "on_visit"
    BREAK = "break"


class BookingType(StrEnum):
    ONE_TIME = "one_time"
    CARE_PLAN = "care_plan"  # multi-day recurring package (e.g. 7-day post-op care)


class BookingStatus(StrEnum):
    CREATED = "created"  # cart-like, not yet paid/confirmed
    SEARCHING = "searching"  # dispatch engine looking for a professional
    ASSIGNED = "assigned"  # professional accepted, en route not yet
    CONFIRMED = "confirmed"  # patient + professional both confirmed
    EN_ROUTE = "en_route"
    IN_PROGRESS = "in_progress"  # checked in, visit ongoing
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    FAILED = "failed"  # no professional found / payment failed


class OfferStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class VisitEvent(StrEnum):
    EN_ROUTE = "en_route"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethod(StrEnum):
    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    CASH = "cash"


class PayoutStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"


class WalletTxnType(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"


class WalletTxnReason(StrEnum):
    REFERRAL_BONUS = "referral_bonus"
    CANCELLATION_REFUND = "cancellation_refund"
    BOOKING_PAYMENT = "booking_payment"
    PAYOUT = "payout"
    ADJUSTMENT = "adjustment"
    PROMOTION = "promotion"


class CouponDiscountType(StrEnum):
    FLAT = "flat"
    PERCENTAGE = "percentage"


class NotificationChannel(StrEnum):
    PUSH = "push"
    SMS = "sms"
    EMAIL = "email"
    IN_APP = "in_app"


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class SupportTicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class SupportTicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class DevicePlatform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


class PreferredContactMethod(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    WHATSAPP = "whatsapp"


class ContactInquiryStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
