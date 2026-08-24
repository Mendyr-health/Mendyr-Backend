"""Patient portal: dashboard, profile and settings. Grounded in
src/features/patient/dashboardData.ts, src/types/index.ts (PatientProfilePublic), and
src/components/{web,mobile}/patient/*.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import require_patient
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.patient import (
    PatientDashboardOut,
    PatientProfileOut,
    PatientProfileUpdateIn,
    PatientSettingsOut,
    PatientSettingsUpdateIn,
)
from app.services.patient_service import PatientService

router = APIRouter(prefix="/patient", tags=["patient"])


@router.get("/dashboard", response_model=ApiResponse[PatientDashboardOut])
async def get_dashboard(
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PatientDashboardOut]:
    data = await PatientService(db).get_dashboard(current_user)
    return ApiResponse.ok(data)


@router.get("/profile", response_model=ApiResponse[PatientProfileOut])
async def get_profile(
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PatientProfileOut]:
    data = await PatientService(db).get_profile(current_user)
    return ApiResponse.ok(data)


@router.put("/profile", response_model=ApiResponse[PatientProfileOut])
async def update_profile(
    payload: PatientProfileUpdateIn,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PatientProfileOut]:
    data = await PatientService(db).update_profile(current_user, payload)
    return ApiResponse.ok(data)


@router.get("/settings", response_model=ApiResponse[PatientSettingsOut])
async def get_settings(
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PatientSettingsOut]:
    data = await PatientService(db).get_settings(current_user)
    return ApiResponse.ok(data)


@router.put("/settings", response_model=ApiResponse[PatientSettingsOut])
async def update_settings(
    payload: PatientSettingsUpdateIn,
    current_user: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PatientSettingsOut]:
    data = await PatientService(db).update_settings(current_user, payload)
    return ApiResponse.ok(data)
