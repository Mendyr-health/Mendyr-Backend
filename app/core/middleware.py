"""Cross-cutting HTTP middleware: request-id propagation, access logging, response shaping."""

import json
import math
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger

logger = get_logger("http")

REQUEST_ID_HEADER = "X-Request-ID"

# Paths whose bodies must reach the client byte-for-byte — wrapping the OpenAPI schema or
# Swagger/Redoc's HTML would break them, and Prometheus's /metrics is plain text, not JSON.
_ENVELOPE_EXEMPT_PATHS = frozenset({"/docs", "/redoc", "/openapi.json", "/metrics"})
_PAGE_KEYS = frozenset({"items", "total", "page", "page_size", "has_next"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Binds a request id + timing to structlog context and logs each request."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_handled",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response


class ResponseEnvelopeMiddleware(BaseHTTPMiddleware):
    """Wraps every JSON response in the `{success, data, meta, error}` envelope the frontend
    (`apps/patient/src/types/index.ts` `ApiResponse<T>`) expects on every call, success or
    failure — the backend previously returned raw models on success and only wrapped errors.

    Runs after routing/exception-handling has already produced the final body (that happens
    inside FastAPI's routing layer, which every `BaseHTTPMiddleware` sits outside of), so this
    only ever needs to reshape an already-complete JSON body — it never sees a raw exception.

    `app.core.exceptions._error_body` already emits `{success: false, ...}` for errors; this
    middleware detects that shape and passes it through unchanged rather than double-wrapping.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)

        if request.url.path in _ENVELOPE_EXEMPT_PATHS:
            return response
        if not response.headers.get("content-type", "").startswith("application/json"):
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[attr-defined]
        try:
            parsed = json.loads(body) if body else None
        except ValueError:
            # Not actually JSON despite the content-type header — pass the original bytes
            # through untouched rather than risk mangling something we can't parse.
            return self._rebuild(response, body, response.media_type)

        if isinstance(parsed, dict) and "success" in parsed and "error" in parsed:
            envelope = parsed  # already {"success": False, ...} from `_error_body`
        elif response.status_code >= 400:
            # An error status that didn't already go through `_error_body` — e.g. Starlette's
            # own 404/405 for a route that never matched, so no exception handler ran at all.
            # Must never be labeled `success: true` just because the body happens to be JSON.
            detail = parsed.get("detail") if isinstance(parsed, dict) else None
            envelope = {
                "success": False,
                "data": None,
                "meta": None,
                "error": {"code": "http_error", "message": detail or "Request failed."},
            }
        elif isinstance(parsed, dict) and _PAGE_KEYS.issubset(parsed):
            total_pages = math.ceil(parsed["total"] / parsed["page_size"]) if parsed["total"] else 0
            envelope = {
                "success": True,
                "data": parsed["items"],
                "meta": {
                    "page": parsed["page"],
                    "limit": parsed["page_size"],
                    "total": parsed["total"],
                    "totalPages": total_pages,
                },
                "error": None,
            }
        else:
            envelope = {"success": True, "data": parsed, "meta": None, "error": None}

        new_body = json.dumps(envelope).encode("utf-8")
        return self._rebuild(response, new_body, "application/json")

    @staticmethod
    def _rebuild(original: Response, body: bytes, media_type: str | None) -> Response:
        """Build a new Response with `body`, carrying over every header from `original`
        except `content-length`/`content-type` (both now stale — Starlette recomputes them
        from `body`/`media_type`). Done via `raw_headers`, not `dict(original.headers)`: a
        plain dict collapses repeated header names to one, which silently drops the second of
        two `Set-Cookie` headers (access-token + refresh-token cookies are both set this way
        by `_set_session_cookies`) — a real bug this replaced.
        """
        new_response = Response(
            content=body, status_code=original.status_code, media_type=media_type
        )
        skip = {b"content-length", b"content-type"}
        new_response.raw_headers += [
            (k, v) for k, v in original.raw_headers if k.lower() not in skip
        ]
        return new_response
