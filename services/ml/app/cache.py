"""Catalyst Cache contract for bounded-TTL state (Prompt 14 Part B, matrix row 9).

Cache is used ONLY for short-lived, reconstructable state — never a system of
record:
  * idempotency keys (dedupe of prediction/import/report requests),
  * rate-limit counters (per-IP / per-role sliding windows),
  * signed-context nonce replay guard (cross-instance; see app/gateway_context.py),
  * short reference lookups / dashboard summaries.

Every entry has a TTL. Narrow interface + in-memory fake (tests/local) +
Catalyst-SDK impl (deployed). Namespaces + TTLs live in
`infra/catalyst/cache/namespaces.json`.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from typing import Optional

# Cache segments (Catalyst Cache supports named segments). Bounded TTL only.
SEG_IDEMPOTENCY = "idempotency"
SEG_RATE_LIMIT = "ratelimit"
SEG_NONCE = "nonce"
SEG_LOOKUP = "lookup"

# Default TTLs (seconds). Kept short so nothing here is authoritative.
DEFAULT_TTL_S = {SEG_IDEMPOTENCY: 86400, SEG_RATE_LIMIT: 60, SEG_NONCE: 180, SEG_LOOKUP: 300}


class CacheClient(ABC):
    @abstractmethod
    def get(self, segment: str, key: str) -> Optional[str]: ...

    @abstractmethod
    def put(self, segment: str, key: str, value: str, *, ttl_s: Optional[int] = None) -> None: ...

    @abstractmethod
    def incr(self, segment: str, key: str, *, ttl_s: Optional[int] = None) -> int: ...

    def add_if_absent(self, segment: str, key: str, value: str = "1",
                      *, ttl_s: Optional[int] = None) -> bool:
        """Atomic-ish set-if-absent. Returns True if newly added (not a duplicate).

        Used for idempotency + nonce replay: False means 'already seen'.
        """
        if self.get(segment, key) is not None:
            return False
        self.put(segment, key, value, ttl_s=ttl_s)
        return True


class InMemoryCache(CacheClient):
    def __init__(self) -> None:
        self._d: dict[tuple[str, str], tuple[str, Optional[float]]] = {}

    def _live(self, seg, key):
        rec = self._d.get((seg, key))
        if not rec:
            return None
        val, exp = rec
        if exp and exp < time.time():
            self._d.pop((seg, key), None)
            return None
        return val

    def get(self, segment, key):
        return self._live(segment, key)

    def put(self, segment, key, value, *, ttl_s=None):
        ttl = ttl_s if ttl_s is not None else DEFAULT_TTL_S.get(segment)
        self._d[(segment, key)] = (value, (time.time() + ttl) if ttl else None)

    def incr(self, segment, key, *, ttl_s=None):
        cur = int(self._live(segment, key) or 0) + 1
        self.put(segment, key, str(cur), ttl_s=ttl_s)
        return cur


class CatalystCache(CacheClient):
    """Deployed impl over the Catalyst SDK (Cache). SDK import deferred."""

    def __init__(self, app=None):
        import zcatalyst_sdk
        self._app = app or zcatalyst_sdk.initialize()
        self._cache = self._app.cache()

    def _seg(self, segment: str):
        return self._cache.segment(segment)

    def get(self, segment, key):
        v = self._seg(segment).get(key)
        return None if v is None else str(v)

    def put(self, segment, key, value, *, ttl_s=None):
        ttl = ttl_s if ttl_s is not None else DEFAULT_TTL_S.get(segment, 300)
        # Catalyst Cache expiry is in hours; round up to at least 1h where required.
        self._seg(segment).put(key, value, max(1, round(ttl / 3600)))

    def incr(self, segment, key, *, ttl_s=None):
        cur = int(self.get(segment, key) or 0) + 1
        self.put(segment, key, str(cur), ttl_s=ttl_s)
        return cur


def get_cache() -> CacheClient:
    if os.getenv("DRISHTI_USE_CATALYST_CACHE", "").lower() == "true":
        return CatalystCache()
    return InMemoryCache()
