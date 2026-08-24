"""Patient <-> nurse messaging — shared by both portals (see app/models/messaging.py).
Grounded in src/store/slices/nurseSlice.ts's NurseMessageThread/NurseMessage mock shapes;
no patient-side messaging UI reads a real API yet, but the same endpoints serve both once
it does.
"""

import uuid

from fastapi import APIRouter, Depends

from app.api.v1.deps import DbSession, get_current_user, pagination_params
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse, PaginationParams, pagination_meta
from app.schemas.messaging import MessagePublic, MessageThreadPublic, SendMessageIn
from app.services.messaging_service import MessagingService

router = APIRouter(prefix="/messaging", tags=["messaging"])


@router.get("/threads", response_model=ApiResponse[list[MessageThreadPublic]])
async def list_threads(
    current_user: User = Depends(get_current_user), db: DbSession = Depends(get_db)
) -> ApiResponse[list[MessageThreadPublic]]:
    threads = await MessagingService(db).list_threads_for_user(current_user)
    return ApiResponse.ok(threads)


@router.get("/threads/{thread_id}/messages", response_model=ApiResponse[list[MessagePublic]])
async def list_messages(
    thread_id: uuid.UUID,
    pagination: PaginationParams = Depends(pagination_params),
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> ApiResponse[list[MessagePublic]]:
    messages, total = await MessagingService(db).list_messages(
        thread_id, current_user, limit=pagination.page_size, offset=pagination.offset
    )
    return ApiResponse.ok(
        messages,
        meta=pagination_meta(page=pagination.page, limit=pagination.page_size, total=total),
    )


@router.post("/threads/{thread_id}/messages", response_model=ApiResponse[MessagePublic])
async def send_message(
    thread_id: uuid.UUID,
    payload: SendMessageIn,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> ApiResponse[MessagePublic]:
    message = await MessagingService(db).send_message(thread_id, current_user, payload.body)
    return ApiResponse.ok(message)


@router.post("/threads/for-booking/{booking_id}", response_model=ApiResponse[MessageThreadPublic])
async def get_or_create_thread_for_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> ApiResponse[MessageThreadPublic]:
    thread = await MessagingService(db).get_or_create_thread_for_booking(
        booking_id, viewer_id=current_user.id
    )
    return ApiResponse.ok(thread)
