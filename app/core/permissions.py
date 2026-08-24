"""Role-based access dependencies, layered on top of `app.api.v1.deps.get_current_user`."""

from collections.abc import Callable

from fastapi import Depends

from app.core.constants import UserRole
from app.core.exceptions import ForbiddenError
from app.models.user import User


def require_roles(*allowed: UserRole) -> Callable:
    """Usage: `Depends(require_roles(UserRole.ADMIN, UserRole.OPS))`."""
    from app.api.v1.deps import get_current_user  # local import avoids a circular import

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise ForbiddenError(f"Requires one of roles: {[r.value for r in allowed]}")
        return current_user

    return _dependency


require_patient = require_roles(UserRole.PATIENT)
require_professional = require_roles(UserRole.PROFESSIONAL)
require_admin = require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)
require_super_admin = require_roles(UserRole.SUPER_ADMIN)
require_ops_or_admin = require_roles(UserRole.OPS, UserRole.ADMIN, UserRole.SUPER_ADMIN)
