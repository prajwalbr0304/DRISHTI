"""Scoped AppSail SSE channel (Prompt 14 Part F, item 1).

A direct browser -> AppSail Server-Sent-Events channel that pushes prediction /
forecast *result-ready* notices to the UI (the alternative to Gateway polling in
the G prediction flow). It is the ONE direct AppSail connection F.1 permits, and
it is fenced accordingly:

  * OFF unless ``DRISHTI_STREAM_CHANNEL_ENABLED=true`` (else 404 — no surface);
  * every connection must present a short-lived channel token minted on the
    authenticated Gateway path (``channel_token`` function), verified here for
    signature / audience / board+user binding / expiry;
  * a STRICT Origin check (live ``Origin`` allow-listed AND equal to the origin
    the token was minted for);
  * the stream self-closes at the token expiry, forcing a re-handshake through
    the authenticated gateway; total lifetime is hard-capped.

The channel only ever carries data-minimized notices (ids + a template name) —
never predictions, scores, narratives, evidence or PII. Enforcement of the signed
gateway context is skipped for this path (see ``gateway_enforcement``) precisely
because the channel token is its dedicated, stricter auth.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..channel import (ChannelContext, ChannelError, allowed_origins,
                       channel_enabled, split_token, verify_channel_token)

router = APIRouter(prefix="/stream", tags=["stream"])

# Heartbeat cadence — keeps the connection + any intermediary from idling out.
_HEARTBEAT_S = 15


class ChannelHub:
    """Bounded, in-memory per-(board,user) notice queue.

    Deployment note: this is the single-instance fan-out. Across AppSail
    instances, the Signals -> notify path (Catalyst) is the durable source; this
    hub only buffers the data-minimized notices for a currently-open stream.
    """

    def __init__(self, max_per_key: int = 100) -> None:
        self._max = max_per_key
        self._q: dict[str, deque] = defaultdict(lambda: deque(maxlen=self._max))
        self._lock = threading.Lock()

    @staticmethod
    def key(board_id: str, user_id: str) -> str:
        return f"{board_id}:{user_id}"

    def publish(self, board_id: str, user_id: str, notice: dict) -> None:
        with self._lock:
            self._q[self.key(board_id, user_id)].append(notice)

    def drain(self, board_id: str, user_id: str) -> list[dict]:
        with self._lock:
            q = self._q.get(self.key(board_id, user_id))
            if not q:
                return []
            out = list(q)
            q.clear()
            return out


_HUB = ChannelHub()


def publish_to_channel(board_id: str, user_id: str, notice: dict) -> None:
    """Enqueue a data-minimized notice for an open stream (used by the internal
    notify path). Callers MUST pass ids/template only — never scores/PII."""
    _HUB.publish(str(board_id), str(user_id), notice)


def format_sse(data, *, event: Optional[str] = None, comment: bool = False) -> str:
    """Format one SSE frame. ``comment=True`` emits a ``: ...`` keep-alive."""
    if comment:
        return f": {data}\n\n"
    payload = data if isinstance(data, str) else json.dumps(data, separators=(",", ":"))
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {payload}\n\n"


def _verify_from_request(request: Request, board_id: str) -> ChannelContext:
    token = request.query_params.get("token") or ""
    payload, signature = split_token(token)
    return verify_channel_token(
        payload, signature,
        request_origin=request.headers.get("origin"),
        expected_board_id=board_id,
        allowed=allowed_origins())


async def _event_stream(ctx: ChannelContext):
    """Async SSE generator: greet, drain notices, heartbeat, close at expiry."""
    yield format_sse({"type": "ready", "board_id": ctx.board_id,
                      "expires_in_s": ctx.remaining_seconds()}, event="ready")
    deadline = time.monotonic() + ctx.remaining_seconds()
    while time.monotonic() < deadline:
        for notice in _HUB.drain(ctx.board_id, ctx.user_id):
            yield format_sse(notice, event="notice")
        # Sleep in short slices so we stop promptly at the deadline.
        slept = 0.0
        while slept < _HEARTBEAT_S and time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            slept += 0.5
            for notice in _HUB.drain(ctx.board_id, ctx.user_id):
                yield format_sse(notice, event="notice")
        if time.monotonic() < deadline:
            yield format_sse("keep-alive", comment=True)
    yield format_sse({"type": "expired"}, event="expired")


@router.get("/predictions")
async def stream_predictions(request: Request):
    """Open the scoped SSE channel for a board. Requires a valid channel token +
    strict Origin. Returns 404 when the channel is disabled (no surface)."""
    if not channel_enabled():
        return JSONResponse(status_code=404, content={"detail": "not found"})
    board_id = (request.query_params.get("board_id") or "").strip()
    if not board_id:
        return JSONResponse(status_code=400, content={"detail": "board_id required"})
    try:
        ctx = _verify_from_request(request, board_id)
    except ChannelError:
        # Opaque — never reveal which binding/check failed.
        return JSONResponse(status_code=401, content={"detail": "invalid channel token"})
    return StreamingResponse(
        _event_stream(ctx), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform",
                 "Connection": "keep-alive", "X-Accel-Buffering": "no"})
