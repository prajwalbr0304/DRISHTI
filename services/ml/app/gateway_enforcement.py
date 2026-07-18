"""Inbound gateway enforcement middleware (Prompt 14 Part D, items 10 + 12).

The deployed trust boundary is:

    Browser -> Catalyst API Gateway -> gateway_api function (derives identity from
    Catalyst Authentication, strips client identity headers, mints a short-lived
    HMAC-signed context) -> AppSail (this service).

AppSail must therefore VERIFY that signed context *before handling a request* and
must never trust a client-supplied role. This middleware is that enforcement
point. When enabled it:

  * verifies the signed context (signature / audience / scope / expiry / replay)
    on every non-exempt route and returns 401 for an unsigned/forged/expired
    request — so unauthenticated browser CRUD sent straight at the AppSail URL is
    rejected (item 10);
  * derives the SERVER-TRUSTED role/actor from the verified context and rewrites
    the request headers so the existing per-domain role gates (which read the
    ``X-Role`` header) act on the trusted role, never on a spoofable client value;
  * stashes the verified context on ``request.state`` so downstream dependencies
    (``require_gateway_context`` / ``require_service_context``) reuse it instead
    of re-verifying — which also means a nonce is consumed exactly once.

It is OFF by default (``DRISHTI_REQUIRE_GATEWAY_CONTEXT`` unset/false) so local
development and the test suite — where requests do not carry a signed context and
``X-Role`` is display-only — are unaffected. It is turned ON only in the deployed
AppSail environment. CORS is never treated as authentication.
"""
from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .gateway_context import (ContextError, GatewayContext, configured_audience,
                              verify_signed_context)

# Liveness/readiness probes are hit directly by Catalyst infrastructure (not
# through the gateway), so they must never require a signed context.
_EXEMPT_PATHS = frozenset({"/health", "/health/live", "/health/ready"})

# Client-supplied identity headers are stripped before the trusted role is
# injected, so a caller can never smuggle a role past the boundary. Names are
# lowercased bytes to match the ASGI header representation.
_STRIP_HEADERS = frozenset({
    b"x-role", b"x-demo-actor", b"x-user-id", b"x-user-email", b"x-forwarded-user",
})


def enforcement_enabled() -> bool:
    """True only when the deployed AppSail sets DRISHTI_REQUIRE_GATEWAY_CONTEXT=true."""
    return os.getenv("DRISHTI_REQUIRE_GATEWAY_CONTEXT", "").strip().lower() == "true"


def _inject_trusted_identity(request: Request, ctx: GatewayContext) -> None:
    """Strip client identity headers and inject the server-trusted role + actor
    so the existing X-Role-based role gates operate on the verified identity."""
    trusted_role = (ctx.role or "investigator").strip() or "investigator"
    actor = (ctx.user_id or ctx.email or ctx.source
             or ("service" if ctx.is_service else "gateway"))
    headers = [(k, v) for (k, v) in request.scope["headers"]
               if k.lower() not in _STRIP_HEADERS]
    headers.append((b"x-role", trusted_role.encode("latin-1", "ignore")))
    headers.append((b"x-demo-actor", str(actor).encode("latin-1", "ignore")))
    request.scope["headers"] = headers


class GatewayContextEnforcementMiddleware(BaseHTTPMiddleware):
    """Reject unsigned/forged requests and inject the trusted identity when
    DRISHTI_REQUIRE_GATEWAY_CONTEXT is enabled; otherwise a transparent no-op."""

    async def dispatch(self, request: Request, call_next):
        if not enforcement_enabled():
            return await call_next(request)
        if request.method == "OPTIONS" or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)
        try:
            ctx = verify_signed_context(
                request.headers.get("x-drishti-context"),
                request.headers.get("x-drishti-signature"),
                expected_audience=(configured_audience() or None),
            )
        except ContextError:
            # Opaque 401 — never reveal which check failed (avoids an oracle).
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing gateway context"})
        request.state.gateway_context = ctx
        _inject_trusted_identity(request, ctx)
        return await call_next(request)
