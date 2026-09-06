"""FastAPI router for supervisor station/officer performance (Prompt 20 Part C).

  GET /performance/overview — scoped station/officer operational metrics.

Command-chain view. INTERIM: every command role may open the per-station/officer
performance surface. The requested unit/district filter is confined server-side
to the caller's derived scope (station chief -> their station, SP -> assigned
units, higher ranks -> authorized aggregates); a browser header is never trusted.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ..config import get_settings
from ..org import scope as scope_mod
from ..org import service as org_service
from ..org.deps import GeoScope, geo_scope
from ..roles import ALL_ROLES, DEFAULT_ROLE
from . import service
from .schemas import DistrictPerformanceResponse, PerformanceResponse

router = APIRouter(prefix="/performance", tags=["performance"])

# Station/officer performance. INTERIM ("all roles have access to everything"):
# every command role may open it; the seat's own scope still bounds the numbers.
PERFORMANCE_ROLES = set(ALL_ROLES)


def _role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or DEFAULT_ROLE).strip()


def require_supervisor(x_role: Optional[str] = Header(default=None)) -> str:
    role = _role(x_role)
    if role not in PERFORMANCE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot open station/officer performance — this "
                    "is a command-chain view."))
    return role


def _resolve_scope(role: str, actor: Optional[str]) -> scope_mod.ScopeContext:
    """Trusted scope: prefer the authenticated user's stored assignment; fall
    back to the role default. Never derived from a browser district header."""
    username = (actor or "").strip() or None
    if username:
        try:
            return org_service.resolve_scope_for_user(username=username)
        except Exception:  # noqa: BLE001 — unknown demo actor / DB down -> role default
            pass
    return scope_mod.derive_scope(role, source="role-default")


@router.get("/overview", response_model=PerformanceResponse)
def overview(unit_id: Optional[int] = Query(None, ge=1),
             district_id: Optional[int] = Query(None, ge=1),
             window_days: int = Query(30, ge=1, le=365),
             role: str = Depends(require_supervisor),
             x_demo_actor: Optional[str] = Header(default=None)):
    scope = _resolve_scope(role, x_demo_actor)
    try:
        eff_unit, eff_district = scope_mod.enforce_geo_request(
            scope, unit_id=unit_id, district_id=district_id)
    except scope_mod.ScopeDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return service.station_officer_performance(
        unit_id=eff_unit, district_id=eff_district, window_days=window_days)


@router.get("/districts", response_model=DistrictPerformanceResponse)
def districts(window_days: int = Query(90, ge=1, le=365),
              geo: GeoScope = Depends(geo_scope)):
    """Districts in the caller's scope, side by side.

    Backs the range and wing league tables, which previously approximated the
    comparison client-side by summing HOTSPOT case counts per district. That is a
    different question: a hotspot is a modelled concentration, not a workload, so a
    district with dispersed crime read as idle.

    Uses ``geo_scope`` rather than this module's older ``_resolve_scope`` helper
    because a range seat spans several districts, and ``enforce_geo_request``
    collapses to a single ``district_id``. ``effective_district_ids()`` keeps the
    set — and keeps the EMPTY set, so an unposted seat gets no rows rather than
    every district.
    """
    return service.district_performance(
        district_ids=geo.effective_district_ids(), window_days=window_days)
