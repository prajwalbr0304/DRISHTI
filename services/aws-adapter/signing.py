"""Request/response signing for the protected AWS adapter (Prompt 14 Part F, items 4+5).

This is the AWS-side counterpart of the signing in
``services/ml/app/predict/adapter.py``. It runs INSIDE the AWS VPC (Lambda/ECS)
behind the AWS API Gateway and is a SEPARATE deployment from the AppSail image,
so — like ``services/gpu-worker/schema.py`` — it keeps a self-contained copy of
the wire contract rather than importing the FastAPI app.

Authentication (F.4): an API key alone is NOT authentication. Every inbound
request must carry a short-lived HMAC signature with a timestamp + single-use
nonce, so a captured request cannot be replayed. The scheme is identical to the
client's:

    signature = HMAC_SHA256(secret, b"<ts>|<nonce>|<canonical-body-bytes>")

where ``<canonical-body-bytes>`` is exactly the request body the client sent
(the client signs the canonical JSON it also transmits, so the server verifies
over the raw received bytes — no re-serialisation ambiguity).

The signed RESULT returned to the client is verified by
``SignedHttpsAdapter._verify`` in the AppSail app; ``sign_result`` below produces
a payload that verifier accepts (the canonical payload includes ``signed_at`` and
excludes ``signature`` / ``_sig_nonce``).

Nothing here logs a secret or a request body.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import uuid
from typing import Callable, Optional

# The wire envelope version this adapter speaks. Must match
# services/ml/app/predict/envelope.py :: ENVELOPE_VERSION and
# services/gpu-worker/schema.py :: ENVELOPE_VERSION.
ENVELOPE_VERSION = "1.0.0"

# A signed request is accepted only within this clock-skew window (seconds).
DEFAULT_MAX_SKEW_S = 300
# In-process nonce retention. In deployment a shared store (DynamoDB TTL /
# ElastiCache) must back this so replay is caught across Lambda/ECS instances.
DEFAULT_NONCE_TTL_S = 600


class SignatureError(ValueError):
    """Raised for a missing/expired/replayed/forged request signature."""


def canonical(obj) -> bytes:
    """Stable canonical JSON (sorted keys, no whitespace drift) — identical to
    the client's ``_canonical``."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(secret: str, payload: bytes, ts: str, nonce: str) -> str:
    """HMAC-SHA256 over ``ts|nonce|payload`` — the one routine both sides use."""
    mac = hmac.new(secret.encode("utf-8"),
                   b"|".join((ts.encode(), nonce.encode(), payload)),
                   hashlib.sha256)
    return mac.hexdigest()


class NonceCache:
    """Tiny thread-safe TTL set for single-instance replay protection.

    Deployment note: back this with a shared TTL store so a nonce consumed on one
    Lambda/ECS instance is rejected on another. The in-process cache is the local
    last line of defence.
    """

    def __init__(self, ttl_s: int = DEFAULT_NONCE_TTL_S,
                 time_fn: Callable[[], float] = time.time) -> None:
        self._ttl = ttl_s
        self._now = time_fn
        self._d: dict[str, float] = {}
        self._lock = threading.Lock()

    def seen(self, nonce: str) -> bool:
        """Return True if the nonce was already used (and remember it if not)."""
        now = self._now()
        with self._lock:
            if len(self._d) > 8192:  # opportunistic purge
                self._d = {k: exp for k, exp in self._d.items() if exp >= now}
            if nonce in self._d and self._d[nonce] >= now:
                return True
            self._d[nonce] = now + self._ttl
            return False


def verify_request(secret: str, raw_body: bytes, *, ts: Optional[str],
                   nonce: Optional[str], signature: Optional[str],
                   envelope_version: Optional[str] = None,
                   max_skew_s: int = DEFAULT_MAX_SKEW_S,
                   nonce_cache: Optional[NonceCache] = None,
                   now_s: Optional[float] = None) -> None:
    """Verify an inbound signed request. Raises ``SignatureError`` on any failure.

    Order: secret present -> fields present -> envelope version -> signature
    (constant-time) -> timestamp skew -> replay. Replay is checked LAST so a
    request that fails an earlier check never consumes (burns) a nonce.
    """
    if not secret:
        raise SignatureError("adapter secret not configured")
    if not ts or not nonce or not signature:
        raise SignatureError("missing timestamp/nonce/signature")
    if envelope_version is not None and envelope_version != ENVELOPE_VERSION:
        raise SignatureError(
            f"unsupported envelope version {envelope_version!r} (expected {ENVELOPE_VERSION})")

    expected = sign_payload(secret, raw_body, ts, nonce)
    if not hmac.compare_digest(expected, signature):
        raise SignatureError("signature mismatch")

    try:
        ts_val = int(ts)
    except (TypeError, ValueError):
        raise SignatureError("malformed timestamp")
    now = int(now_s if now_s is not None else time.time())
    if abs(now - ts_val) > max_skew_s:
        raise SignatureError("timestamp outside allowed skew")

    if nonce_cache is not None and nonce_cache.seen(nonce):
        raise SignatureError("replayed nonce")


def sign_result(secret: str, result: dict, *,
                now_s: Optional[float] = None) -> dict:
    """Attach a signature the AppSail client (``SignedHttpsAdapter._verify``)
    accepts. The canonical payload includes ``signed_at`` and excludes
    ``signature`` / ``_sig_nonce`` (matching the client's ``unsigned`` view)."""
    signed_at = str(int(now_s if now_s is not None else time.time()))
    nonce = uuid.uuid4().hex
    d = {k: v for k, v in result.items() if k not in ("signature", "_sig_nonce")}
    d["signed_at"] = signed_at
    payload = canonical(d)
    d["signature"] = sign_payload(secret, payload, signed_at, nonce)
    d["_sig_nonce"] = nonce
    return d
