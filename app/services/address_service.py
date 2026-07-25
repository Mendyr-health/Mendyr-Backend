"""Patient address book — converts lat/lng in and out of PostGIS geography points."""

import uuid

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.address import Address
from app.schemas.address import AddressCreateIn, AddressRead, AddressUpdateIn


def _to_read_schema(address: Address) -> AddressRead:
    point = to_shape(address.location)
    return AddressRead(
        id=address.id,
        label=address.label,
        line1=address.line1,
        line2=address.line2,
        landmark=address.landmark,
        city=address.city,
        state=address.state,
        pincode=address.pincode,
        is_default=address.is_default,
        latitude=point.y,
        longitude=point.x,
    )


class AddressService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[AddressRead]:
        result = await self.session.execute(select(Address).where(Address.user_id == user_id))
        return [_to_read_schema(a) for a in result.scalars().all()]

    async def create(self, user_id: uuid.UUID, payload: AddressCreateIn) -> AddressRead:
        if payload.is_default:
            await self._clear_existing_default(user_id)

        address = Address(
            user_id=user_id,
            label=payload.label,
            line1=payload.line1,
            line2=payload.line2,
            landmark=payload.landmark,
            city=payload.city,
            state=payload.state,
            pincode=payload.pincode,
            location=WKTElement(
                f"POINT({payload.location.longitude} {payload.location.latitude})", srid=4326
            ),
            is_default=payload.is_default,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            instructions_for_professional=payload.instructions_for_professional,
        )
        self.session.add(address)
        await self.session.flush()
        return _to_read_schema(address)

    async def _clear_existing_default(self, user_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(Address).where(Address.user_id == user_id, Address.is_default.is_(True))
        )
        for existing in result.scalars().all():
            existing.is_default = False

    async def _get_owned(self, address_id: uuid.UUID, user_id: uuid.UUID) -> Address:
        address = await self.session.get(Address, address_id)
        if address is None:
            raise NotFoundError("Address not found.")
        if address.user_id != user_id:
            raise ForbiddenError("This address does not belong to you.")
        return address

    async def update(
        self, address_id: uuid.UUID, user_id: uuid.UUID, payload: AddressUpdateIn
    ) -> AddressRead:
        address = await self._get_owned(address_id, user_id)

        if payload.is_default:
            await self._clear_existing_default(user_id)

        data = payload.model_dump(exclude_unset=True, exclude={"location"})
        for field, value in data.items():
            setattr(address, field, value)
        if payload.location is not None:
            address.location = WKTElement(
                f"POINT({payload.location.longitude} {payload.location.latitude})", srid=4326
            )

        await self.session.flush()
        return _to_read_schema(address)

    async def delete(self, address_id: uuid.UUID, user_id: uuid.UUID) -> None:
        address = await self._get_owned(address_id, user_id)
        await self.session.delete(address)
        await self.session.flush()
