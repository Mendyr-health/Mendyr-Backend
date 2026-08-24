"""Super Admin console: admin account management, static role/permission summary, audit
log viewer, and platform settings — all camelCase-facing (src/features/super-admin/*,
src/components/{web,mobile}/super-admin/*).
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.core.constants import UserRole, UserStatus
from app.schemas.common import CamelModel, CamelORMModel

# ─── Admin accounts (useAdmins.ts) ──────────────────────────────────────────


class AdminEntryOut(CamelORMModel):
    public_id: uuid.UUID = Field(validation_alias="id", serialization_alias="publicId")
    email: str | None
    full_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime


class AdminCreateIn(CamelModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["ADMIN", "SUPER_ADMIN"] = "ADMIN"


# ─── Roles & permissions (rolesData.ts, lib/constants.ts) ───────────────────
# Static/computed, mirroring the frontend's hardcoded PERMISSIONS / DEFAULT_ROLE_PERMISSIONS —
# not a dynamic RBAC table, so there is no create/update/delete here.


class PermissionPublic(CamelModel):
    public_id: str
    resource: str
    action: str
    description: str | None = None


class RolePublic(CamelModel):
    public_id: str
    name: str
    slug: str
    description: str | None = None
    hierarchy: int
    is_system: bool
    permissions: list[PermissionPublic]


# ─── Audit logs (useAuditLogs.ts) ───────────────────────────────────────────


class AuditLogPublic(CamelModel):
    id: uuid.UUID
    actor_name: str | None = None
    actor_email: str | None = None
    action: str
    resource: str
    resource_id: str | None = None
    old_value: object | None = None
    new_value: object | None = None
    ip_address: str | None = None
    created_at: datetime


# Dashboard stats (WebSuperAdminDashboard.tsx / MobileSuperAdminDashboard.tsx): served by
# admin.py's GET /admin/dashboard using app.schemas.admin_console.DashboardStatsOut — both
# admin and super-admin dashboards call the identical path, so there's no separate schema
# here.


# ─── Platform settings (WebSuperAdminSettings.tsx / MobileSuperAdminSettings.tsx) ──
# The frontend form also collects launchDate, nurseRegistrationEnabled, maxLoginAttempts
# and sessionTimeout, none of which have a backing column on PlatformSettings (see
# app/models/settings.py) — those are accepted on the input schema (so the PUT body the
# frontend actually sends validates) but silently ignored rather than persisted. See the
# gaps note in the implementing agent's final report.


class PlatformSettingsOut(CamelORMModel):
    site_name: str = Field(validation_alias="platform_name", serialization_alias="siteName")
    support_email: str | None = None
    support_phone: str | None = None
    maintenance_mode: bool
    registration_enabled: bool = Field(
        validation_alias="new_registrations_enabled", serialization_alias="registrationEnabled"
    )
    platform_commission_pct: float


class PlatformSettingsUpdateIn(CamelModel):
    site_name: str | None = Field(default=None, max_length=100)
    support_email: EmailStr | None = None
    support_phone: str | None = Field(default=None, max_length=15)
    maintenance_mode: bool | None = None
    registration_enabled: bool | None = None
    platform_commission_pct: float | None = Field(default=None, ge=0, le=100)

    # Accepted for forward-compat with the frontend's form shape; no backing column yet.
    launch_date: str | None = None
    nurse_registration_enabled: bool | None = None
    max_login_attempts: int | None = None
    session_timeout: int | None = None
