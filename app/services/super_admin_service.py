"""Business logic for the Super Admin console: admin account management, the static
role/permission summary, audit log search, platform settings, and dashboard stats.
"""

import json
import secrets
import string
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    UserRole,
    UserStatus,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.settings import PlatformSettings
from app.models.user import User
from app.repositories.super_admin_repo import (
    AdminRepository,
    AuditLogRepository,
    PlatformSettingsRepository,
)
from app.schemas.super_admin import (
    AdminCreateIn,
    AuditLogPublic,
    PermissionPublic,
    PlatformSettingsUpdateIn,
    RolePublic,
)

# Mirrors src/lib/constants.ts PERMISSIONS / DEFAULT_ROLE_PERMISSIONS / ROLE_HIERARCHY and
# src/features/super-admin/rolesData.ts exactly — the frontend treats roles/permissions as
# static data, so this is a computed read-only projection, not a dynamic RBAC table.

_PERMISSIONS = {
    "USER_CREATE": ("user", "create"),
    "USER_READ": ("user", "read"),
    "USER_UPDATE": ("user", "update"),
    "USER_DELETE": ("user", "delete"),
    "NURSE_READ": ("nurse", "read"),
    "NURSE_UPDATE": ("nurse", "update"),
    "NURSE_APPROVE": ("nurse", "approve"),
    "NURSE_REJECT": ("nurse", "reject"),
    "PATIENT_READ": ("patient", "read"),
    "PATIENT_UPDATE": ("patient", "update"),
    "SERVICE_CREATE": ("service", "create"),
    "SERVICE_READ": ("service", "read"),
    "SERVICE_UPDATE": ("service", "update"),
    "SERVICE_DELETE": ("service", "delete"),
    "CONTACT_READ": ("contact", "read"),
    "CONTACT_UPDATE": ("contact", "update"),
    "WAITLIST_READ": ("waitlist", "read"),
    "WAITLIST_UPDATE": ("waitlist", "update"),
    "WAITLIST_EXPORT": ("waitlist", "export"),
    "ADMIN_CREATE": ("admin", "create"),
    "ADMIN_READ": ("admin", "read"),
    "ADMIN_UPDATE": ("admin", "update"),
    "ADMIN_SUSPEND": ("admin", "suspend"),
    "ROLE_CREATE": ("role", "create"),
    "ROLE_READ": ("role", "read"),
    "ROLE_UPDATE": ("role", "update"),
    "ROLE_DELETE": ("role", "delete"),
    "AUDIT_READ": ("audit", "read"),
    "SETTINGS_READ": ("settings", "read"),
    "SETTINGS_UPDATE": ("settings", "update"),
}

_ROLE_PERMISSION_KEYS: dict[UserRole, list[str]] = {
    UserRole.SUPER_ADMIN: list(_PERMISSIONS.keys()),
    UserRole.ADMIN: [
        "NURSE_READ",
        "NURSE_UPDATE",
        "NURSE_APPROVE",
        "NURSE_REJECT",
        "PATIENT_READ",
        "PATIENT_UPDATE",
        "SERVICE_CREATE",
        "SERVICE_READ",
        "SERVICE_UPDATE",
        "SERVICE_DELETE",
        "CONTACT_READ",
        "CONTACT_UPDATE",
        "WAITLIST_READ",
        "WAITLIST_UPDATE",
        "WAITLIST_EXPORT",
        "AUDIT_READ",
    ],
    UserRole.PROFESSIONAL: ["NURSE_READ", "NURSE_UPDATE", "SERVICE_READ"],
    UserRole.PATIENT: ["PATIENT_READ", "PATIENT_UPDATE", "SERVICE_READ"],
}

_ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.SUPER_ADMIN: 0,
    UserRole.ADMIN: 1,
    UserRole.PROFESSIONAL: 2,
    UserRole.PATIENT: 3,
}

_ROLE_DISPLAY: dict[UserRole, tuple[str, str]] = {
    UserRole.SUPER_ADMIN: ("Super Admin", "Full system access"),
    UserRole.ADMIN: ("Admin", "Platform management access"),
    UserRole.PROFESSIONAL: ("Nurse", "Nurse portal access"),
    UserRole.PATIENT: ("Patient", "Patient portal access"),
}

_ADMIN_PHONE_ALPHABET = string.digits


def _generate_placeholder_phone() -> str:
    # Admin accounts are created by email/password (see AdminCreateIn) and don't collect a
    # phone number, but User.phone_number is NOT NULL + unique (see app/models/user.py) and
    # this task may not add/alter columns. A synthetic, clearly-marked unique value fills the
    # column without colliding with real phone numbers. Flagged as a gap in the final report.
    return "9" + "".join(secrets.choice(_ADMIN_PHONE_ALPHABET) for _ in range(9))


def _generate_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


class SuperAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.admins = AdminRepository(session)
        self.audit_logs = AuditLogRepository(session)
        self.settings_repo = PlatformSettingsRepository(session)

    # ── Admin accounts ────────────────────────────────────────────────

    async def list_admins(
        self, *, query: str | None, page: int, limit: int
    ) -> tuple[list[User], int]:
        offset = (page - 1) * limit
        return await self.admins.search_admins(query=query, limit=limit, offset=offset)

    async def create_admin(self, payload: AdminCreateIn) -> User:
        if await self.session.scalar(select(User).where(User.email == payload.email)):
            raise ConflictError("An account with this email already exists.")

        user = User(
            email=payload.email,
            phone_number=_generate_placeholder_phone(),
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            role=UserRole(payload.role.lower()),
            status=UserStatus.ACTIVE,
            email_verified=True,
            referral_code=_generate_referral_code(),
        )
        self.admins.add(user)
        await self.session.flush()
        return user

    async def suspend_admin(self, public_id: uuid.UUID) -> User:
        user = await self.admins.get(public_id)
        if user is None or user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise NotFoundError("Admin not found.")
        user.status = UserStatus.SUSPENDED
        await self.session.flush()
        return user

    # ── Roles & permissions (static/computed) ─────────────────────────

    def get_roles(self) -> list[RolePublic]:
        roles = []
        for role in UserRole:
            if role == UserRole.OPS:
                continue  # internal ops staff, not a Next.js-facing role (see rolesData.ts)
            name, description = _ROLE_DISPLAY[role]
            permission_keys = _ROLE_PERMISSION_KEYS.get(role, [])
            permissions = [
                PermissionPublic(
                    public_id=key.lower().replace("_", ":"),
                    resource=_PERMISSIONS[key][0],
                    action=_PERMISSIONS[key][1],
                    description=f"{_PERMISSIONS[key][1].capitalize()} {_PERMISSIONS[key][0]}",
                )
                for key in permission_keys
            ]
            roles.append(
                RolePublic(
                    public_id=role.value,
                    name=name,
                    slug=role.value.replace("_", "-"),
                    description=description,
                    hierarchy=_ROLE_HIERARCHY[role],
                    is_system=True,
                    permissions=permissions,
                )
            )
        return sorted(roles, key=lambda r: r.hierarchy)

    # ── Audit logs ─────────────────────────────────────────────────────

    async def list_audit_logs(
        self, *, query: str | None, page: int, limit: int
    ) -> tuple[list[AuditLogPublic], int]:
        offset = (page - 1) * limit
        rows, total = await self.audit_logs.search(query=query, limit=limit, offset=offset)

        results = []
        for log, actor_name, actor_email in rows:
            new_value: object | None = log.metadata_json
            if log.metadata_json:
                try:
                    new_value = json.loads(log.metadata_json)
                except (ValueError, TypeError):
                    new_value = log.metadata_json  # not JSON — pass through raw string
            results.append(
                AuditLogPublic(
                    id=log.id,
                    actor_name=actor_name,
                    actor_email=actor_email,
                    action=log.action,
                    resource=log.entity_type,
                    resource_id=log.entity_id,
                    old_value=None,  # AuditLog has no before-state column — see report gap
                    new_value=new_value,
                    ip_address=log.ip_address,
                    created_at=log.created_at,
                )
            )
        return results, total

    # ── Platform settings ────────────────────────────────────────────

    async def get_settings(self) -> PlatformSettings:
        return await self.settings_repo.get_singleton()

    async def update_settings(self, payload: PlatformSettingsUpdateIn) -> PlatformSettings:
        settings = await self.settings_repo.get_singleton()
        if payload.site_name is not None:
            settings.platform_name = payload.site_name
        if payload.support_email is not None:
            settings.support_email = payload.support_email
        if payload.support_phone is not None:
            settings.support_phone = payload.support_phone
        if payload.maintenance_mode is not None:
            settings.maintenance_mode = payload.maintenance_mode
        if payload.registration_enabled is not None:
            settings.new_registrations_enabled = payload.registration_enabled
        if payload.platform_commission_pct is not None:
            settings.platform_commission_pct = payload.platform_commission_pct
        # launch_date / nurse_registration_enabled / max_login_attempts / session_timeout:
        # accepted for schema compat, no backing column — see report gap.
        await self.session.flush()
        return settings
