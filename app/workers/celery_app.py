"""Celery application + beat schedule.

Run with:
    celery -A app.workers.celery_app worker --loglevel=info
    celery -A app.workers.celery_app beat --loglevel=info
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "mendyr",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.matching",
        "app.workers.tasks.notifications",
        "app.workers.tasks.payouts",
        "app.workers.tasks.reminders",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "expire-stale-booking-offers": {
        "task": "app.workers.tasks.matching.sweep_expired_offers",
        "schedule": 15.0,  # seconds — offers have a short TTL, so the sweep runs frequently
    },
    "send-visit-reminders": {
        "task": "app.workers.tasks.reminders.send_upcoming_visit_reminders",
        "schedule": crontab(minute="*/15"),
    },
    "generate-weekly-payouts": {
        "task": "app.workers.tasks.payouts.run_weekly_payout_generation",
        "schedule": crontab(hour=3, minute=0, day_of_week="monday"),
    },
}
