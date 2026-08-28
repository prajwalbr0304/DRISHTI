"""Authenticated owner resolution for Ask DRISHTI conversations.

Deployed requests use only the Catalyst identity already verified and attached by
GatewayContextEnforcementMiddleware.  Local development has no signed context,
so it gets an isolated, namespaced subject derived from the demo actor.  The raw
local actor is hashed before persistence to avoid turning display metadata into
stored identity data.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request, status

from ..gateway_enforcement import enforcement_enabled
from ..gateway_context import GatewayContext


@dataclass(frozen=True)
class ChatCaller:
    owner_subject: str
    role: Optional[str]


def _local_subject(actor: Optional[str]) -> str:
    value = (actor or "local-default").strip() or "local-default"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"local:{digest}"


def resolve_chat_caller(
    request: Request,
    *,
    x_role: Optional[str] = None,
    x_demo_actor: Optional[str] = None,
) -> ChatCaller:
    """Return the only identity allowed to own/read/continue a chat thread."""
    ctx = getattr(request.state, "gateway_context", None)
    if enforcement_enabled():
        if not isinstance(ctx, GatewayContext) or not ctx.is_user or not ctx.user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authenticated user context required",
            )
        return ChatCaller(owner_subject=f"catalyst:{ctx.user_id}", role=ctx.role)

    # Offline/local mode only. These headers remain presentation inputs and are
    # never used when signed gateway enforcement is enabled.
    return ChatCaller(owner_subject=_local_subject(x_demo_actor), role=x_role)
