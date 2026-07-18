"""Internal router — signed-context trust-boundary proof (Prompt 14 §8.2).

`/internal/ping` requires a valid signed context (from the gateway or an
event/cron function) and echoes back the verified, server-trusted fields. It is
the smoke-test target that proves: (a) an unsigned/forged request is rejected
401, and (b) a correctly signed request is accepted and its identity is derived
server-side — never from client-supplied headers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..gateway_context import GatewayContext, require_gateway_context

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/ping")
@router.post("/ping")
def internal_ping(ctx: GatewayContext = Depends(require_gateway_context)) -> dict:
    """Return the verified context (proves the signed boundary works)."""
    return {
        "ok": True,
        "scope": ctx.scope,
        "role": ctx.role,
        "source": ctx.source,
        "user_id": ctx.user_id,
        "request_id": ctx.request_id,
    }
