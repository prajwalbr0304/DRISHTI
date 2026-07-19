"""Scoped WebSocket/SSE channel token (Prompt 14 Part F, item 1).

The browser never talks to AWS or AppSail CRUD directly — everything flows
through the authenticated Catalyst API Gateway -> ``gateway_api`` -> AppSail
facade. The ONE exception F.1 permits is a **direct** AppSail Server-Sent-Events
/ WebSocket channel for pushing prediction-result notices to the UI, and it is
allowed *only when* it is protected by:

  * a **short-lived** token (expiry),
  * **audience/board/user binding** (the token is minted for one user + one
    investigation board + the ``drishti-channel`` audience), and
  * **strict Origin checks** (the token embeds the exact browser origin and the
    server also checks the live ``Origin`` header against an allow-list).

The token is minted ONLY on the authenticated Gateway path
(``infra/catalyst/functions/channel_token``), which derives the user from
Catalyst Authentication server-side. AppSail then verifies the token before it
opens the stream. This module is the AppSail verifier + a matching minter (so the
exact scheme is documented and round-trip-testable).

Signing scheme mirrors ``gateway_context.py`` exactly: HMAC-SHA256 over the
base64url payload STRING, hex-encoded; timestamps in milliseconds. The signing
secret is ``DRISHTI_CHANNEL_SIGNING_SECRET`` (falls back to
``ZOHO_APPSAIL_SIGNING_SECRET`` so a single secret can be shared with the
gateway). The audience is distinct (``drishti-channel``) so a gateway/service
context can never be used as a channel token, or vice versa.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

CHANNEL_AUDIENCE = "drishti-channel"
CHANNEL_SCOPE = "channel"
# Default validity of a minted channel token. The stream stays open until this
# expiry, then the client must re-handshake through the authenticated gateway.
DEFAULT_CHANNEL_TTL_MS = 5 * 60 * 1000       # 5 minutes
_MAX_SKEW_MS = 60_000
# Hard ceiling on a single stream's lifetime regardless of a longer token.
MAX_STREAM_SECONDS = 15 * 60


class ChannelError(ValueError):
    """Raised when a channel token is missing, malformed, expired or unbound."""


@dataclass(frozen=True)
class ChannelContext:
    """The verified, server-trusted channel binding."""
    user_id: str
    board_id: str
    origin: str
    ts: int
    exp: int
    nonce: str
    request_id: str
    aud: str = CHANNEL_AUDIENCE
    scope: str = CHANNEL_SCOPE

    def remaining_seconds(self, now_ms: Optional[int] = None) -> int:
        now = now_ms if now_ms is not None else _now_ms()
        return max(0, min(MAX_STREAM_SECONDS, int((self.exp - now) / 1000)))


def channel_signing_secret() -> str:
    """Server-side HMAC secret (never committed, never sent to the browser)."""
    return os.getenv("DRISHTI_CHANNEL_SIGNING_SECRET") \
        or os.getenv("ZOHO_APPSAIL_SIGNING_SECRET", "")


def channel_enabled() -> bool:
    """The direct SSE/WS channel is OFF unless explicitly enabled (deployed)."""
    return os.getenv("DRISHTI_STREAM_CHANNEL_ENABLED", "").strip().lower() == "true"


def allowed_origins() -> frozenset[str]:
    """Exact allow-list of browser origins permitted to open the channel."""
    raw = os.getenv("DRISHTI_CHANNEL_ALLOWED_ORIGINS", "")
    return frozenset(o.strip() for o in raw.split(",") if o.strip())


def _b64url(buf: bytes) -> str:
    return base64.urlsafe_b64encode(buf).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _now_ms() -> int:
    return int(time.time() * 1000)


def mint_channel_token(secret: str, *, user_id: str, board_id: str, origin: str,
                       ttl_ms: int = DEFAULT_CHANNEL_TTL_MS,
                       now_ms: Optional[int] = None) -> tuple[str, str, dict]:
    """Mint a signed channel token. This is what the authenticated Gateway
    function does; kept here so the scheme is one source of truth + testable."""
    now = now_ms if now_ms is not None else _now_ms()
    ctx = {
        "scope": CHANNEL_SCOPE, "aud": CHANNEL_AUDIENCE,
        "user_id": str(user_id), "board_id": str(board_id), "origin": origin,
        "ts": now, "exp": now + ttl_ms,
        "nonce": uuid.uuid4().hex, "request_id": uuid.uuid4().hex,
    }
    payload = _b64url(json.dumps(ctx, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"),
                         hashlib.sha256).hexdigest()
    return payload, signature, ctx


def pack_token(payload_b64: str, signature_hex: str) -> str:
    """Combine into one opaque ``payload.signature`` string for the SSE URL."""
    return f"{payload_b64}.{signature_hex}"


def split_token(token: Optional[str]) -> tuple[str, str]:
    """Split a ``payload.signature`` token. Raises ``ChannelError`` if malformed."""
    if not token or "." not in token:
        raise ChannelError("malformed token")
    payload, _, signature = token.partition(".")
    if not payload or not signature:
        raise ChannelError("malformed token")
    return payload, signature


def verify_channel_token(payload_b64: Optional[str], signature_hex: Optional[str], *,
                         request_origin: Optional[str], expected_board_id: str,
                         secret: Optional[str] = None,
                         allowed: Optional[frozenset[str]] = None,
                         now_ms: Optional[int] = None) -> ChannelContext:
    """Verify a channel token and its bindings. Raises ``ChannelError`` on any
    failure. Order: secret -> fields -> signature (constant-time) -> audience ->
    scope -> expiry -> user/board binding -> strict Origin binding."""
    key = secret if secret is not None else channel_signing_secret()
    if not key:
        raise ChannelError("channel signing secret not configured")
    if not payload_b64 or not signature_hex:
        raise ChannelError("missing token or signature")

    expected = hmac.new(key.encode("utf-8"), payload_b64.encode("utf-8"),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_hex):
        raise ChannelError("signature mismatch")

    try:
        data = json.loads(_b64url_decode(payload_b64))
    except (ValueError, binascii.Error):
        raise ChannelError("malformed token payload")
    if not isinstance(data, dict):
        raise ChannelError("malformed token payload")

    if data.get("aud") != CHANNEL_AUDIENCE:
        raise ChannelError("audience mismatch")
    if data.get("scope") != CHANNEL_SCOPE:
        raise ChannelError("scope mismatch")

    ts, exp = data.get("ts"), data.get("exp")
    if not isinstance(ts, (int, float)) or not isinstance(exp, (int, float)):
        raise ChannelError("missing ts/exp")
    now = now_ms if now_ms is not None else _now_ms()
    if now > exp:
        raise ChannelError("token expired")
    if ts > now + _MAX_SKEW_MS:
        raise ChannelError("token timestamp in the future")

    user_id = str(data.get("user_id") or "")
    board_id = str(data.get("board_id") or "")
    token_origin = str(data.get("origin") or "")
    if not user_id or not board_id:
        raise ChannelError("token missing user/board binding")
    # Board binding: the token must be for the board the client is opening.
    if board_id != str(expected_board_id):
        raise ChannelError("board mismatch")

    # Strict Origin check: the live Origin must be allow-listed AND equal to the
    # origin the token was minted for (so a token leaked to another origin fails).
    allow = allowed if allowed is not None else allowed_origins()
    if not allow:
        raise ChannelError("no allowed origins configured")
    if not request_origin or request_origin not in allow:
        raise ChannelError("origin not allowed")
    if request_origin != token_origin:
        raise ChannelError("origin does not match token binding")

    return ChannelContext(
        user_id=user_id, board_id=board_id, origin=token_origin,
        ts=int(ts), exp=int(exp), nonce=str(data.get("nonce", "")),
        request_id=str(data.get("request_id", "")))
