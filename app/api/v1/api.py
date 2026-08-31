"""Aggregates every v1 endpoint router under a single APIRouter mounted by `app.main`."""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    addresses,
    admin,
    auth,
    bookings,
    configs,
    health,
    offers,
    payments,
    professionals,
    reviews,
    services,
    support,
    users,
    visits,
    wallet,
    webhooks,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(addresses.router)
api_router.include_router(services.router)
api_router.include_router(professionals.router)
api_router.include_router(bookings.router)
api_router.include_router(offers.router)
api_router.include_router(visits.router)
api_router.include_router(payments.router)
api_router.include_router(webhooks.router)
api_router.include_router(wallet.router)
api_router.include_router(reviews.router)
api_router.include_router(support.router)
api_router.include_router(admin.router)
api_router.include_router(configs.router)
