"""Correlation id: honour an inbound X-Request-ID or mint one, echo it back."""

from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        inbound = request.headers.get("x-request-id", "")
        request_id = inbound if _SAFE.match(inbound) else uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
