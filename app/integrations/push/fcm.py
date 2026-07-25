"""Firebase Cloud Messaging push client. Swap in `firebase-admin` for production; this thin
HTTP wrapper avoids pulling the full SDK into the base image until push volume needs it."""

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class FCMPushClient:
    async def send(
        self, *, push_token: str, title: str, body: str, data: dict | None = None
    ) -> bool:
        if not settings.FCM_PROJECT_ID:
            logger.info("fcm_push_dev_noop", title=title, body=body)
            return True

        url = f"https://fcm.googleapis.com/v1/projects/{settings.FCM_PROJECT_ID}/messages:send"
        payload = {
            "message": {
                "token": push_token,
                "notification": {"title": title, "body": body},
                "data": {k: str(v) for k, v in (data or {}).items()},
            }
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                logger.warning("fcm_push_failed", status=response.status_code, body=response.text)
                return False
        return True
