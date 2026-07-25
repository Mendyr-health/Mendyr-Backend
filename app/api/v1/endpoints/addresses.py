"""Patient address book."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.address import AddressCreateIn, AddressRead, AddressUpdateIn
from app.schemas.common import MessageResponse
from app.services.address_service import AddressService

router = APIRouter(prefix="/addresses", tags=["addresses"])


@router.get("", response_model=list[AddressRead])
async def list_addresses(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AddressRead]:
    return await AddressService(db).list_for_user(current_user.id)


@router.post("", response_model=AddressRead)
async def create_address(
    payload: AddressCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AddressRead:
    return await AddressService(db).create(current_user.id, payload)


@router.patch("/{address_id}", response_model=AddressRead)
async def update_address(
    address_id: uuid.UUID,
    payload: AddressUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AddressRead:
    return await AddressService(db).update(address_id, current_user.id, payload)


@router.delete("/{address_id}", response_model=MessageResponse)
async def delete_address(
    address_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await AddressService(db).delete(address_id, current_user.id)
    return MessageResponse(message="Address deleted.")
