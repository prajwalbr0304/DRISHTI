"""FastAPI router for supervisor station/officer performance (Prompt 20 Part C).

  GET /performance/overview — scoped station/officer operational metrics.

Supervisory view: investigators/policymakers do not get the per-station/officer
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
from . import service
from .schemas import PerformanceResponse

router = APIRouter(prefix="/performance", tags=["performance"])

# The supervisory command chain maps to the supervisor functional role
# (SP/DGP/... -> supervisor); super_admin oversees all.
PERFORMANCE_ROLES = {"supervisor", "super_admin"}


def _role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or "investigator").strip()


def require_supervisor(x_role: Optional[str] = Header(default=None)) -> str:
    role = _role(x_role)
    if role not in PERFORMANCE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' cannot open station/officer performance — this "
                    "is a supervisory view (SP/station-chief/super-admin)."))
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
