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

# Canonical six functional roles — MUST mirror
# services/ml/app/org/hierarchy.py FUNCTIONAL_ROLES and the Node gateway_api
# role mapper. AppSail re-validates the signed role against this set (defence in
# depth): a signed context carrying any other non-empty role is rejected as
# forged/misconfigured. (test_gateway_authz asserts this stays in sync.)
FUNCTIONAL_ROLES = frozenset({
    "investigator", "analyst", "supervisor", "policymaker",
    "disaster_coordinator", "super_admin",
})
# A service-scope context (event/cron/job) is not a user seat; it carries the
# default role only and is authorised by its service scope, not a functional role.
_SERVICE_DEFAULT_ROLE = "investigator"

# Audience the signed context is minted for. Every Node signer (gateway_api +
# event/cron functions) and the smoke test embed this exact ``aud`` claim, and
# AppSail rejects a context minted for any other audience. Overridable via
# DRISHTI_CONTEXT_AUDIENCE; set it to an empty string to disable the check.
DEFAULT_AUDIENCE = "drishti-appsail"


class ContextError(ValueError):
    """Raised when a signed context is missing, malformed, expired or forged."""


@dataclass(frozen=True)
class GatewayContext:
    """The verified, server-trusted caller context.

    ``role`` + the organizational scope fields (``scope_level``/``district_id``/
    ``unit_id``) are resolved SERVER-SIDE by the gateway function and signed, so
    AppSail trusts them and never a browser-supplied role/district/unit header
    (Prompt 21 §E.3)."""
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
    # Server-resolved organizational scope (from trusted Data Store/attributes).
    scope_level: Optional[str] = None
    district_id: Optional[int] = None
    unit_id: Optional[int] = None

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


def _shared_nonce_enabled() -> bool:
    """True when the deployed AppSail uses Catalyst Cache for cross-instance
    nonce replay protection (DRISHTI_USE_CATALYST_CACHE=true)."""
    return os.getenv("DRISHTI_USE_CATALYST_CACHE", "").strip().lower() == "true"


def _nonce_is_replay(nonce: str) -> bool:
    """Return True if this nonce has already been consumed (a replay).

    Prompt 21 §G.1 (shared state): when Catalyst Cache is enabled the nonce is
    recorded in the shared ``nonce`` segment via an atomic set-if-absent, so a
    replay is caught across ALL AppSail instances (not just the one that first
    saw it). The in-process cache is the local/last line of defence and the
    fallback when the shared cache is unavailable.
    """
    if _shared_nonce_enabled():
        try:
            from .cache import SEG_NONCE, get_cache
            newly_added = get_cache().add_if_absent(SEG_NONCE, nonce, ttl_s=_NONCE_TTL_S)
            return not newly_added
        except Exception:  # noqa: BLE001 — never fail closed on a cache outage
            pass
    return _nonce_cache.seen(nonce)


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

    # Validate the server-resolved functional role against the canonical six
    # (defence in depth). A user-scope context MUST carry one of the six roles;
    # any other non-empty value is a forged/misconfigured context. A service-
    # scope context is authorised by its scope, not a functional role.
    raw_role = str(data.get("role", "") or "").strip()
    if scope == "gateway":
        role = raw_role or "investigator"
        if role not in FUNCTIONAL_ROLES:
            raise ContextError("unknown role")
    else:
        role = raw_role if raw_role in FUNCTIONAL_ROLES else _SERVICE_DEFAULT_ROLE

    # Parse the signed organizational scope. A present-but-malformed scope id is
    # a forged/misconfigured context (ambiguous scope) and is rejected.
    def _scope_int(key: str) -> Optional[int]:
        v = data.get(key)
        if v is None or v == "":
            return None
        try:
            iv = int(v)
        except (TypeError, ValueError):
            raise ContextError("ambiguous scope")
        if iv <= 0:
            raise ContextError("ambiguous scope")
        return iv

    district_id = _scope_int("district_id")
    unit_id = _scope_int("unit_id")
    scope_level = (str(data.get("scope_level")).strip() or None) if data.get("scope_level") else None

    # Replay is checked LAST so a request that fails signature/scope/audience/
    # expiry never consumes (burns) a nonce it would otherwise be allowed to use.
    nonce = str(data.get("nonce", ""))
    if check_replay and nonce and _nonce_is_replay(nonce):
        raise ContextError("replayed nonce")

    return GatewayContext(
        scope=scope,
        request_id=str(data.get("request_id", "")),
        ts=int(ts),
        exp=int(exp),
        nonce=nonce,
        role=role,
        user_id=(str(data["user_id"]) if data.get("user_id") is not None else None),
        email=data.get("email") or None,
        source=data.get("source") or None,
        aud=aud,
        scope_level=scope_level,
        district_id=district_id,
        unit_id=unit_id,
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
