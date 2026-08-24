"""Super Admin console: admin account management, static role/permission summary, audit
log viewer, platform settings, and dashboard stats. All routes require SUPER_ADMIN.

Grounded in:
- src/features/super-admin/useAdmins.ts (admins list/create/suspend)
- src/features/super-admin/useAuditLogs.ts (audit log search/pagination)
- src/features/super-admin/rolesData.ts + src/lib/constants.ts (static roles/permissions)
- src/components/web/super-admin/WebSuperAdminDashboard.tsx (+ mobile counterpart)
- src/components/web/super-admin/settings/WebSuperAdminSettings.tsx (+ mobile counterpart)
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_super_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse, pagination_meta
from app.schemas.super_admin import (
    AdminCreateIn,
    AdminEntryOut,
    AuditLogPublic,
    PlatformSettingsOut,
    PlatformSettingsUpdateIn,
    RolePublic,
)
from app.services.super_admin_service import SuperAdminService

router = APIRouter(prefix="/admin", tags=["super-admin"])


# ─── Admin accounts ──────────────────────────────────────────────────────


@router.get("/admins", response_model=ApiResponse[list[AdminEntryOut]])
async def list_admins(
    q: str = "",
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AdminEntryOut]]:
    admins, total = await SuperAdminService(db).list_admins(
        query=q or None, page=max(page, 1), limit=min(max(limit, 1), 100)
    )
    data = [AdminEntryOut.model_validate(a) for a in admins]
    return ApiResponse.ok(data, meta=pagination_meta(page=page, limit=limit, total=total))


@router.post("/admins", response_model=ApiResponse[AdminEntryOut])
async def create_admin(
    payload: AdminCreateIn,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AdminEntryOut]:
    admin = await SuperAdminService(db).create_admin(payload)
    return ApiResponse.ok(AdminEntryOut.model_validate(admin))


@router.post("/admins/{public_id}/suspend", response_model=ApiResponse[AdminEntryOut])
async def suspend_admin(
    public_id: uuid.UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AdminEntryOut]:
    admin = await SuperAdminService(db).suspend_admin(public_id)
    return ApiResponse.ok(AdminEntryOut.model_validate(admin))


# ─── Roles & permissions (static/computed) ──────────────────────────────


@router.get("/roles", response_model=ApiResponse[list[RolePublic]])
async def list_roles(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[RolePublic]]:
    return ApiResponse.ok(SuperAdminService(db).get_roles())


# ─── Audit logs ──────────────────────────────────────────────────────────


@router.get("/audit-logs", response_model=ApiResponse[list[AuditLogPublic]])
async def list_audit_logs(
    q: str = "",
    page: int = 1,
    limit: int = 30,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AuditLogPublic]]:
    logs, total = await SuperAdminService(db).list_audit_logs(
        query=q or None, page=max(page, 1), limit=min(max(limit, 1), 100)
    )
    return ApiResponse.ok(logs, meta=pagination_meta(page=page, limit=limit, total=total))


# ─── Platform settings ───────────────────────────────────────────────────


@router.get("/settings", response_model=ApiResponse[PlatformSettingsOut])
async def get_settings(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PlatformSettingsOut]:
    settings = await SuperAdminService(db).get_settings()
    return ApiResponse.ok(PlatformSettingsOut.model_validate(settings))


@router.put("/settings", response_model=ApiResponse[PlatformSettingsOut])
async def update_settings(
    payload: PlatformSettingsUpdateIn,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PlatformSettingsOut]:
    settings = await SuperAdminService(db).update_settings(payload)
    return ApiResponse.ok(PlatformSettingsOut.model_validate(settings))


# Dashboard stats: served by admin.py's GET /admin/dashboard (require_admin already
# permits SUPER_ADMIN too) — the frontend calls the exact same path for both roles
# (WebAdminDashboard.tsx and WebSuperAdminDashboard.tsx both hit /api/v1/admin/dashboard),
# so this router doesn't duplicate it.
