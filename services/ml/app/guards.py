"""Shared honesty guards (doc 02 §10, doc 05 §7).

Two cross-cutting protections applied to every aggregate / exported payload so
nothing leaks an individual or implies causation:

  * k-anonymity — suppress any aggregate cell below a small-count threshold.
  * causation disclaimer — a mandatory, canonical statement that correlations and
    forecasts are decision-support, not causal claims or individual verdicts.

Both are importable helpers; a light middleware also stamps aggregate responses
with honesty headers so the guarantee is observable at the HTTP layer.
"""
from __future__ import annotations

from typing import Any, Iterable

from starlette.middleware.base import BaseHTTPMiddleware

# Canonical disclaimer — the single source of truth (analytics re-exports this).
CAUSATION_DISCLAIMER = (
    "These are statistical correlations across districts, NOT causal claims. "
    "A correlation does not mean one factor causes the other; both may be driven "
    "by unobserved factors, reporting/enforcement bias, or reverse causation. "
    "Use for context and resource planning, never to attribute blame."
)

# Forecasts/predictions get a parallel note (area/period decision support).
FORECAST_DISCLAIMER = (
    "Forecasts are area/period decision support with visible confidence, never "
    "individual targeting or certainty. Keep a human in the loop and audit every use."
)

K_ANON_DEFAULT = 10  # minimum count before an aggregate cell may be shown

# Route prefixes whose payloads are aggregates/forecasts -> honesty headers.
_AGGREGATE_PREFIXES = (
    "/analytics", "/geo/trends", "/geo/hotspots", "/forecast", "/graph/communities",
)


def k_anon_suppress(items: Iterable[Any], count_key: str,
                    k: int = K_ANON_DEFAULT) -> tuple[list, int]:
    """Drop cells whose count is below k. Returns (kept, suppressed_count).

    Works on dicts (by key) or objects (by attribute). Cells with an unknown
    count are kept (the caller is responsible for supplying counts)."""
    kept, suppressed = [], 0
    for it in items:
        c = it.get(count_key) if isinstance(it, dict) else getattr(it, count_key, None)
        if c is not None and c < k:
            suppressed += 1
        else:
            kept.append(it)
    return kept, suppressed


def causation_disclaimer() -> str:
    return CAUSATION_DISCLAIMER


def is_aggregate_path(path: str) -> bool:
    return any(path.startswith(p) for p in _AGGREGATE_PREFIXES)


class HonestyMiddleware(BaseHTTPMiddleware):
    """Stamp aggregate/forecast responses with honesty headers (observable proof
    that the causation + anonymity guards apply). Non-mutating — payload-level
    suppression/disclaimers are enforced inside the endpoints via the helpers."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if is_aggregate_path(request.url.path):
            response.headers["X-DRISHTI-Causation"] = "correlational-not-causal"
            response.headers["X-DRISHTI-Anonymity"] = f"k-anonymity>={K_ANON_DEFAULT}"
            response.headers["X-DRISHTI-Use"] = "area-period-decision-support; human-in-the-loop"
        return response
