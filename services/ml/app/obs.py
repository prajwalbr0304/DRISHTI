"""Structured, redacted access logging (Prompt 14 Part D, item 8).

Emits one compact JSON line per request to stdout — which Catalyst AppSail
captures into its log viewer — carrying only non-sensitive operational fields:
request id, method, path (NO query string), status, latency, the server-trusted
role/scope (when a verified gateway context is present) and client IP.

It deliberately logs NO request/response bodies, NO headers, NO query string and
NO secrets, so the access log can never leak evidence content, PII, credentials
or a DATABASE_URL. Error detail is already redacted by
``app.hardening.install_error_handlers``.

Disabled by default; the deployed AppSail turns it on with
``DRISHTI_ACCESS_LOG_ENABLED=true`` so the local test suite stays quiet.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

_logger = logging.getLogger("drishti.access")
_configured = False


def access_log_enabled() -> bool:
    return os.getenv("DRISHTI_ACCESS_LOG_ENABLED", "").strip().lower() == "true"


def configure_logging() -> None:
    """Install a single stdout handler that emits the pre-formatted JSON message
    verbatim. Idempotent so repeated app startups do not stack handlers."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.handlers = [handler]
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    _configured = True


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Structured redacted access log. Outermost middleware so it captures the
    final response status and total latency; a no-op unless enabled."""

    async def dispatch(self, request: Request, call_next):
        if not access_log_enabled():
            return await call_next(request)
        configure_logging()
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            ctx = getattr(request.state, "gateway_context", None)
            record = {
                "event": "access",
                "request_id": (getattr(request.state, "request_id", None)
                               or request.headers.get("x-request-id")),
                "method": request.method,
                "path": request.url.path,   # path only — never the query string
                "status": status_code,
                "latency_ms": latency_ms,
                "scope": getattr(ctx, "scope", None),
                "role": getattr(ctx, "role", None),
                "client_ip": request.client.host if request.client else None,
            }
            _logger.info(json.dumps(record, separators=(",", ":")))
