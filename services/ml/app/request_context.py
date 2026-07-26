"""Per-request context (request id + demo actor) for audit and tracing.

Phase 3 (hackathon access mode). The browser sends:
  * ``X-Request-ID``  — a client-generated correlation id (we generate one if
                        absent) echoed back on the response.
  * ``X-Demo-Actor``  — the UX-simulation demo actor key (e.g. ``demo.investigating_officer``).
                        This is DISPLAY/AUDIT ONLY — it is NOT authentication or a
                        security boundary (real auth is deferred post-hackathon).
  * ``X-Role``        — the demo view/role (presentation state, also not security).

A ``ContextVar`` makes the current request context available to the audit layer
without threading it through every function. The middleware sets it per request
and always resets it afterwards so nothing leaks between requests.

Nothing secret is ever read from or written to the context.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"
DEMO_ACTOR_HEADER = "X-Demo-Actor"
ROLE_HEADER = "X-Role"


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    actor: Optional[str] = None      # demo actor key (UX simulation, not auth)
    role: Optional[str] = None       # demo view/role (presentation state)
    client_ip: Optional[str] = None


_ctx: ContextVar[Optional[RequestContext]] = ContextVar("drishti_request_ctx", default=None)


def current_context() -> Optional[RequestContext]:
    return _ctx.get()


def new_request_id() -> str:
    return uuid.uuid4().hex


def _clean_header(value: Optional[str], *, max_len: int = 120) -> Optional[str]:
    """Trim + bound a header value so a hostile/oversized header can't pollute
    logs or the audit trail. Never used for any security decision."""
    if not value:
        return None
    v = value.strip()
    if not v:
        return None
    # keep it to a single safe token-ish line
    v = v.replace("\r", " ").replace("\n", " ")
    return v[:max_len]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Populate the request context and echo the request id on the response."""

    async def dispatch(self, request, call_next):
        req_id = _clean_header(request.headers.get(REQUEST_ID_HEADER)) or new_request_id()
        actor = _clean_header(request.headers.get(DEMO_ACTOR_HEADER))
        role = _clean_header(request.headers.get(ROLE_HEADER), max_len=40)
        client_ip = request.client.host if request.client else None
        # Also stash on request.state so error handlers (which run outside this
        # middleware, after the context var is reset) can still surface it.
        request.state.request_id = req_id
        token = _ctx.set(RequestContext(request_id=req_id, actor=actor,
                                        role=role, client_ip=client_ip))
        try:
            response = await call_next(request)
        finally:
            _ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = req_id
        return response
