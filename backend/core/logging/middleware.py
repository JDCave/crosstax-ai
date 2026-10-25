"""Middleware to inject a unique request_id into every request."""

from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request_id to each incoming request and propagate it to logs."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        log_context = logging.LoggerAdapter(logger, {"request_id": request_id})
        log_context.debug("Request started: %s %s", request.method, request.url.path)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
