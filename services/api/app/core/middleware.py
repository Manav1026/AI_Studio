import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.context import correlation_id_var, new_correlation_id
from app.core.logging import get_logger

log = get_logger("http")
HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Accept an inbound correlation id (or create one), expose it on the response and in every log line."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(HEADER, "")
        cid = incoming if 8 <= len(incoming) <= 64 and incoming.replace("-", "").isalnum() else new_correlation_id()
        token = correlation_id_var.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers[HEADER] = cid
        log.info("http_request", method=request.method, path=request.url.path,
                 status=response.status_code, duration_ms=duration_ms)
        correlation_id_var.reset(token)
        return response
