"""Protected AWS analytics adapter client — NARROW typed operations (Prompt 21 §C).

Graph-heavy / geospatial / derived-historical analytics that genuinely need AWS
RDS/PostGIS are reached from AppSail ONLY through this narrow, typed, signed
client — never a direct AppSail->RDS connection and never a generic SQL proxy.
It reuses the same signed-request discipline as the model adapter
(app/predict/adapter.py): server identity via a short-lived HMAC signature over
ts|nonce|payload, TLS, bounded timeout, row/byte caps and an audit trail. No
DATABASE_URL, evidence bytes or narratives ever cross this boundary, and no AWS
URL/credential is ever exposed to the browser.

Operations are an explicit allow-list (typed params), e.g. ``graph_neighbourhood``
for the Investigation Board's Search Around (Prompt 16 §F / Prompt 21 §C.3). The
result is a data-minimized aggregate/authorized object.

Two implementations:
  * ``InMemoryAnalyticsAdapter`` — deterministic offline fake for unit tests.
  * ``SignedHttpsAnalyticsAdapter`` — deployed client to the AWS API Gateway.

``get_analytics_adapter()`` returns the signed client when the adapter is
configured server-side (DRISHTI_AWS_ADAPTER_URL + secret), else ``None`` so a
caller uses its local dev path (the only place a direct RDS read remains, and
only outside AppSail's deployed configuration).
"""
from __future__ import annotations

import os
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

# Reuse the exact model-adapter signing routine + circuit breaker so there is one
# signed-request discipline, not a second drifting one.
from .predict.adapter import AdapterError, sign_payload, _canonical
from .predict.circuit import CircuitBreaker, CircuitOpenError

# Typed analytics operations allow-list (no generic query). Each maps to a
# server-side handler on the protected adapter; anything else is rejected.
ANALYTICS_OPERATIONS = frozenset({
    "graph_neighbourhood",   # Board Search Around subgraph (Prompt 16 §F)
    "geo_hotspots",          # PostGIS hotspot clusters (aggregate)
    "geo_trends",            # area/period trend aggregates
})

# Hard caps enforced client-side (defence in depth vs the server boundary).
MAX_HOPS = 3
MAX_NEIGHBORS = 50
MAX_RESULT_BYTES = 1_000_000     # 1 MB — aggregate/authorized objects only


class AnalyticsAdapter(ABC):
    @abstractmethod
    def graph_neighbourhood(self, entity_id: int, hops: int, max_neighbors: int, *,
                            types: Optional[list[str]] = None,
                            role: Optional[str] = None,
                            district_id: Optional[int] = None) -> tuple[bool, list, list]:
        """Return (exists, nodes, edges) for a capped subgraph around ``entity_id``.
        nodes/edges use the canonical id-keyed graph projection shape."""


class InMemoryAnalyticsAdapter(AnalyticsAdapter):
    """Deterministic offline fake. Returns a small, capped synthetic subgraph so
    the Search Around contract is testable without RDS/PostGIS."""

    def __init__(self, graph: Optional[dict[int, list[int]]] = None):
        # entity_id -> immediate neighbour ids (synthetic).
        self._graph = graph or {}

    def graph_neighbourhood(self, entity_id, hops, max_neighbors, *, types=None,
                            role=None, district_id=None):
        hops = max(1, min(int(hops), MAX_HOPS))
        max_neighbors = max(1, min(int(max_neighbors), MAX_NEIGHBORS))
        if entity_id not in self._graph:
            return (False, [], [])
        nodes = [{"entity_id": int(entity_id), "label": f"E{entity_id}",
                  "entity_type": "person", "distance": 0, "attributes": {}}]
        edges = []
        for nb in self._graph.get(entity_id, [])[:max_neighbors]:
            nodes.append({"entity_id": int(nb), "label": f"E{nb}",
                          "entity_type": "person", "distance": 1, "attributes": {}})
            edges.append({"source": int(entity_id), "target": int(nb),
                          "weight": 1.0, "relationship_type": "associate"})
        return (True, nodes, edges)


class SignedHttpsAnalyticsAdapter(AnalyticsAdapter):
    """Deployed client: signed HTTPS typed analytics calls to the AWS adapter."""

    def __init__(self, base_url: Optional[str] = None, secret: Optional[str] = None,
                 timeout_s: float = 20.0, breaker: Optional[CircuitBreaker] = None):
        self.base_url = (base_url or os.getenv("DRISHTI_AWS_ADAPTER_URL", "")).rstrip("/")
        self._secret = secret or os.getenv("DRISHTI_AWS_ADAPTER_SECRET", "")
        self.timeout_s = timeout_s
        self._breaker = breaker or CircuitBreaker(
            failure_threshold=int(os.getenv("DRISHTI_AWS_ADAPTER_CB_FAILURES", "5")),
            reset_timeout_s=float(os.getenv("DRISHTI_AWS_ADAPTER_CB_RESET_S", "30")),
            name="aws-analytics-adapter")
        if not self.base_url or not self._secret:
            raise AdapterError("AWS analytics adapter URL/secret not configured.")

    def _call(self, operation: str, params: dict) -> dict:
        if operation not in ANALYTICS_OPERATIONS:
            raise AdapterError(f"unknown analytics operation {operation!r}")
        body = {"operation": operation, "params": params,
                "max_result_bytes": MAX_RESULT_BYTES}
        payload = _canonical(body)
        ts, nonce = str(int(time.time())), uuid.uuid4().hex
        headers = {
            "Content-Type": "application/json",
            "X-DRISHTI-Timestamp": ts, "X-DRISHTI-Nonce": nonce,
            "X-DRISHTI-Signature": sign_payload(self._secret, payload, ts, nonce),
            "X-DRISHTI-Analytics-Op": operation,
        }
        try:
            self._breaker.before_call()
        except CircuitOpenError as exc:
            raise AdapterError(f"AWS analytics adapter circuit open: {exc}") from None
        try:
            import httpx
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(f"{self.base_url}/analytics/{operation}",
                                   content=payload, headers=headers)
            if resp.status_code >= 500:
                raise AdapterError(f"AWS analytics adapter {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        if len(_canonical(data)) > MAX_RESULT_BYTES:
            raise AdapterError("analytics result exceeds byte cap")
        return data

    def graph_neighbourhood(self, entity_id, hops, max_neighbors, *, types=None,
                            role=None, district_id=None):
        hops = max(1, min(int(hops), MAX_HOPS))
        max_neighbors = max(1, min(int(max_neighbors), MAX_NEIGHBORS))
        data = self._call("graph_neighbourhood", {
            "entity_id": int(entity_id), "hops": hops, "max_neighbors": max_neighbors,
            "types": sorted(types) if types else None,
            "role": role, "district_id": district_id})
        return (bool(data.get("exists", False)),
                data.get("nodes") or [], data.get("edges") or [])


def adapter_configured() -> bool:
    """True when the protected AWS adapter is configured server-side (deployed)."""
    return bool(os.getenv("DRISHTI_AWS_ADAPTER_URL") and os.getenv("DRISHTI_AWS_ADAPTER_SECRET"))


def get_analytics_adapter() -> Optional[AnalyticsAdapter]:
    """Return the signed HTTPS analytics adapter when configured, else None.

    ``None`` signals the caller to use its local dev path (the only place a
    direct RDS read remains — never in the deployed AppSail configuration, where
    the adapter is always configured)."""
    if adapter_configured():
        return SignedHttpsAnalyticsAdapter()
    if os.getenv("DRISHTI_ANALYTICS_ADAPTER_FAKE", "").lower() == "true":
        return InMemoryAnalyticsAdapter()
    return None
