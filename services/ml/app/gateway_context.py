"""Inbound trust boundary — verify the signed context minted by the Catalyst
Gateway / event / cron functions (Prompt 14 Part B, report §8.2).

The browser never reaches AppSail directly. Every request arrives via the
Catalyst ``gateway_api`` (user scope) or an event/cron function (service scope),
which mints a short-lived HMAC-signed context and forwards it as:

    X-DRISHTI-Context   = base64url(JSON {user_id,email,role,scope,aud,ts,exp,
                                          nonce,request_id[,source]})
    X-DRISHTI-Signature = hex HMAC-SHA256(context, ZOHO_APPSAIL_SIGNING_SECRET)

This module verifies the signature, audience, scope, expiry and nonce (replay)
BEFORE the handler trusts the caller identity/role. It is the AppSail counterpart of the
Node signing code in ``infra/catalyst/functions/*``. CORS is never treated as
authentication; identity is only ever this verified context.

Signing detail (must match the Node side exactly): the HMAC is computed over the
base64url payload STRING (not the decoded JSON), hex-encoded. Timestamps are in
milliseconds (JavaScript ``Date.now()``).

Replay protection here is a best-effort in-process nonce cache. The deployed
service also records nonces in Catalyst Cache (matrix row 9) so replay is caught
across AppSail instances; the in-process cache is the local/last line of defence.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request, status

# A signed context is valid for 60s on the wire; allow a small clock skew.
_MAX_SKEW_MS = 60_000
_NONCE_TTL_S = 180
_VALID_SCOPES = ("gateway", "service")

# Audience the signed context is minted for. Every Node signer (gateway_api +
# event/cron functions) and the smoke test embed this exact ``aud`` claim, and
# AppSail rejects a context minted for any other audience. Overridable via
# DRISHTI_CONTEXT_AUDIENCE; set it to an empty string to disable the check.
DEFAULT_AUDIENCE = "drishti-appsail"


class ContextError(ValueError):
    """Raised when a signed context is missing, malformed, expired or forged."""


@dataclass(frozen=True)
class GatewayContext:
    """The verified, server-trusted caller context."""
    scope: str                       # 'gateway' (user) | 'service' (internal)
    request_id: str
    ts: int
    exp: int
    nonce: str
    role: str = "investigator"
    user_id: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None      # event/cron function name for service scope
    aud: Optional[str] = None         # audience the context was minted for

    @property
    def is_service(self) -> bool:
        return self.scope == "service"

    @property
    def is_user(self) -> bool:
        return self.scope == "gateway"


class _NonceCache:
    """Tiny TTL set for single-instance replay protection."""

    def __init__(self) -> None:
        self._d: dict[str, float] = {}
        self._lock = threading.Lock()

    def seen(self, nonce: str) -> bool:
        now = time.time()
        with self._lock:
            # opportunistic purge of expired nonces
            if len(self._d) > 4096:
                for k, exp in list(self._d.items()):
                    if exp < now:
                        self._d.pop(k, None)
            if nonce in self._d and self._d[nonce] >= now:
                return True
            self._d[nonce] = now + _NONCE_TTL_S
            return False


_nonce_cache = _NonceCache()


def signing_secret() -> str:
    """Server-side shared HMAC secret (never committed, never sent to browser)."""
    return os.getenv("ZOHO_APPSAIL_SIGNING_SECRET", "")


def configured_audience() -> str:
    """Expected audience for inbound signed contexts (empty string = no check)."""
    return os.getenv("DRISHTI_CONTEXT_AUDIENCE", DEFAULT_AUDIENCE)


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _now_ms() -> int:
    return int(time.time() * 1000)


def verify_signed_context(
    payload_b64: Optional[str],
    signature_hex: Optional[str],
    *,
    secret: Optional[str] = None,
    now_ms: Optional[int] = None,
    check_replay: bool = True,
    expected_audience: Optional[str] = None,
) -> GatewayContext:
    """Verify and parse a signed context. Raises ``ContextError`` on any failure.

    Constant-time signature comparison; no secret or raw error is echoed to the
    caller by the FastAPI dependency below. When ``expected_audience`` is a
    non-empty string the context's ``aud`` claim must match it exactly (item 12:
    AppSail verifies signature/audience/expiry/replay before handling a request).
    """
    key = secret if secret is not None else signing_secret()
    if not key:
        raise ContextError("signing secret not configured")
    if not payload_b64 or not signature_hex:
        raise ContextError("missing context or signature")

    expected = hmac.new(key.encode("utf-8"), payload_b64.encode("utf-8"),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_hex):
        raise ContextError("signature mismatch")

    try:
        data = json.loads(_b64url_decode(payload_b64))
    except (ValueError, binascii.Error):
        raise ContextError("malformed context payload")
    if not isinstance(data, dict):
        raise ContextError("malformed context payload")

    now = now_ms if now_ms is not None else _now_ms()
    ts = data.get("ts")
    exp = data.get("exp")
    if not isinstance(ts, (int, float)) or not isinstance(exp, (int, float)):
        raise ContextError("missing ts/exp")
    if now > exp:
        raise ContextError("context expired")
    if ts > now + _MAX_SKEW_MS:
        raise ContextError("context timestamp in the future")

    scope = data.get("scope", "")
    if scope not in _VALID_SCOPES:
        raise ContextError("invalid scope")

    aud = data.get("aud") or None
    if expected_audience:
        if aud != expected_audience:
            raise ContextError("audience mismatch")

    # Replay is checked LAST so a request that fails signature/scope/audience/
    # expiry never consumes (burns) a nonce it would otherwise be allowed to use.
    nonce = str(data.get("nonce", ""))
    if check_replay and nonce and _nonce_cache.seen(nonce):
        raise ContextError("replayed nonce")

    return GatewayContext(
        scope=scope,
        request_id=str(data.get("request_id", "")),
        ts=int(ts),
        exp=int(exp),
        nonce=nonce,
        role=str(data.get("role", "investigator")),
        user_id=(str(data["user_id"]) if data.get("user_id") is not None else None),
        email=data.get("email") or None,
        source=data.get("source") or None,
        aud=aud,
    )


# --- FastAPI dependencies ---------------------------------------------------
def _context_from_request(request: Request) -> GatewayContext:
    """Return the verified context, reusing one the enforcement middleware
    already verified for this request (so the nonce is not consumed twice), else
    verifying the inbound headers directly. Raises ``ContextError`` on failure."""
    cached = getattr(request.state, "gateway_context", None)
    if isinstance(cached, GatewayContext):
        return cached
    return verify_signed_context(
        request.headers.get("x-drishti-context"),
        request.headers.get("x-drishti-signature"),
        expected_audience=(configured_audience() or None),
    )


def require_gateway_context(request: Request) -> GatewayContext:
    """Dependency: require ANY valid signed context (user or service scope)."""
    try:
        return _context_from_request(request)
    except ContextError:
        # Never leak the specific reason (avoids an oracle); log server-side only.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="invalid or missing gateway context")


def require_service_context(request: Request) -> GatewayContext:
    """Dependency: require a valid SERVICE-scope context (internal calls only)."""
    try:
        verified = _context_from_request(request)
    except ContextError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="invalid or missing gateway context")
    if not verified.is_service:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="service-scope context required")
    return verified
