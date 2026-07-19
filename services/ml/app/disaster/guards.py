"""Disaster authorization (Prompt 17 application-authorization section).

AWS PostgreSQL RLS/FORCE RLS remain DISABLED (as requested), so the access
boundary is the Catalyst-authenticated API enforced server-side in AppSail:

  * a synthetic ``disaster_coordinator`` role (mapped through Catalyst
    Authentication + the server-side role middleware) may review warnings and
    approve/dispatch allocations + evacuation plans — but only inside the
    assigned synthetic district/unit;
  * ordinary crime roles (investigator/analyst/supervisor/policymaker) receive
    at most the explicitly-allowed READ-ONLY situational view;
  * ``disaster_forecast``, ``resource_allocation`` and ``evacuation_plan`` are
    the enforced permissions on every mutating API action;
  * warning approval, dispatch and evacuation-plan approval require a fresh
    authenticated confirmation (428 without it);
  * every allow/deny decision on a sensitive action is audited (append-only
    DisasterActivity), so the demo can show the decision matrix.

In deployment the trusted role/actor is injected by the gateway
(gateway_enforcement.py); in dev it is the demo header, still enforced here as
defence in depth (matching the board/intake pattern).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request

from ..config import get_settings
from ..intake.guards import require_localhost, synthetic_db_ok

# --- role sets --------------------------------------------------------------
# Full disaster operator: the synthetic DDMA/district coordinator + super admin.
DISASTER_WRITE_ROLES = {"disaster_coordinator", "super_admin"}
# Everyone authenticated may read the situational view (crime roles read-only).
DISASTER_READ_ROLES = {"disaster_coordinator", "super_admin", "investigator",
                       "analyst", "supervisor", "policymaker"}
# Permission -> allowed roles (Prompt 17 authorization section).
DISASTER_FORECAST_ROLES = {"disaster_coordinator", "super_admin"}
RESOURCE_ALLOCATION_ROLES = {"disaster_coordinator", "super_admin"}
EVACUATION_PLAN_ROLES = {"disaster_coordinator", "super_admin"}
# Roles that are scoped to a single assigned district (cannot act state-wide).
DISTRICT_SCOPED_ROLES = {"disaster_coordinator"}


class DisasterScope:
    """The resolved actor scope for a request (demo simulation of a DDMA seat)."""

    def __init__(self, role: str, actor: str, district_id: Optional[int],
                 unit_id: Optional[int]):
        self.role = role
        self.actor = actor
        self.district_id = district_id
        self.unit_id = unit_id
        self.is_super = role in {"super_admin"}

    def covers_district(self, district_id: Optional[int]) -> bool:
        """A super_admin covers everywhere. A district-scoped coordinator covers
        only its assigned district. Other roles never write (read-only)."""
        if self.is_super:
            return True
        if self.role not in DISTRICT_SCOPED_ROLES:
            return self.role in DISASTER_WRITE_ROLES
        if self.district_id is None:
            return False
        return district_id is None or int(district_id) == int(self.district_id)

    def as_dict(self) -> dict:
        return {"role": self.role, "actor": self.actor,
                "district_id": self.district_id, "unit_id": self.unit_id,
                "is_super": self.is_super}


def _resolve_role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or "investigator").strip()


def resolve_actor(request: Request) -> str:
    actor = request.headers.get("x-demo-actor")
    if actor and actor.strip():
        return actor.strip()[:120]
    role = _resolve_role(request.headers.get("x-role"))
    return f"demo.{role}"


def _int_header(request: Request, name: str) -> Optional[int]:
    v = request.headers.get(name)
    if v is None or not str(v).strip():
        return None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def resolve_scope(request: Request) -> DisasterScope:
    """Resolve the caller's disaster scope. District/unit come from demo headers
    (``X-Disaster-District`` / ``X-Disaster-Unit``) which simulate the seat the
    Catalyst-authenticated coordinator is assigned to. Never a security boundary
    on their own — combined with the role gate below."""
    role = _resolve_role(request.headers.get("x-role"))
    return DisasterScope(role=role, actor=resolve_actor(request),
                         district_id=_int_header(request, "x-disaster-district"),
                         unit_id=_int_header(request, "x-disaster-unit"))


# --- coarse role gates (FastAPI dependencies) -------------------------------
def require_disaster_read(x_role: Optional[str] = Header(default=None)) -> str:
    """Any Emergency Response read route. All authenticated roles may read the
    situational view; crime roles are read-only (enforced by the absence of the
    write gates below on mutating routes)."""
    role = _resolve_role(x_role)
    if role not in DISASTER_READ_ROLES:
        raise HTTPException(status_code=403,
                            detail=f"Role '{role}' has no Emergency Response access.")
    return role


def _require_permission(role: str, allowed: set, permission: str) -> str:
    if role not in allowed:
        _record_denied(permission, role)
        raise HTTPException(
            status_code=403,
            detail=(f"Role '{role}' lacks the '{permission}' permission. "
                    "Emergency Response actions are limited to the synthetic "
                    "disaster_coordinator (crime roles are read-only)."))
    return role


def require_disaster_forecast(x_role: Optional[str] = Header(default=None)) -> str:
    return _require_permission(_resolve_role(x_role), DISASTER_FORECAST_ROLES,
                               "disaster_forecast")


def require_resource_allocation(x_role: Optional[str] = Header(default=None)) -> str:
    return _require_permission(_resolve_role(x_role), RESOURCE_ALLOCATION_ROLES,
                               "resource_allocation")


def require_evacuation_plan(x_role: Optional[str] = Header(default=None)) -> str:
    return _require_permission(_resolve_role(x_role), EVACUATION_PLAN_ROLES,
                               "evacuation_plan")


# --- write posture + fresh confirmation -------------------------------------
def require_disaster_write_allowed(request: Request) -> None:
    """Validate the synthetic hackathon posture (fail-closed) for disaster writes.

    Disaster data persists to Catalyst Data Store (not the operational PG), so
    this validates the synthetic posture: localhost-only in staging + explicit
    hackathon/demo flags, and — when an analytics PG is configured — that it too
    is marked synthetic. Testable without a live DB."""
    require_localhost(request)
    s = get_settings()
    if not (s.hackathon_mode and s.demo_data_only):
        raise HTTPException(
            status_code=503,
            detail=("Refusing disaster write: the service is not in synthetic "
                    "hackathon posture (HACKATHON_MODE/DEMO_DATA_ONLY)."))
    if s.database_url and not synthetic_db_ok():
        raise HTTPException(
            status_code=503,
            detail=("Refusing disaster write: the configured analytics database "
                    f"is not marked '{s.synthetic_env_expected}'."))


def require_fresh_confirmation(confirmed: bool, action: str) -> None:
    """Warning approval / dispatch / evacuation-plan approval require a fresh
    authenticated confirmation (Catalyst re-auth challenge in the product; an
    explicit audited ``confirm=true`` at the API). 428 without it."""
    if not confirmed:
        raise HTTPException(
            status_code=428,
            detail=(f"'{action}' requires a fresh authenticated confirmation. "
                    "Re-confirm (confirm=true) to proceed."))


def enforce_district_scope(scope: DisasterScope, district_id: Optional[int],
                           action: str) -> None:
    """A district-scoped coordinator may only act inside its assigned district."""
    if not scope.covers_district(district_id):
        _record_denied(action, scope.role,
                       detail={"assigned": scope.district_id, "target": district_id})
        raise HTTPException(
            status_code=403,
            detail=(f"'{action}' is outside your assigned district "
                    f"({scope.district_id}). A coordinator may only act within "
                    "their assigned synthetic district/unit."))


# --- audit of allow/deny decisions ------------------------------------------
def _record_denied(action: str, role: str, detail: Optional[dict] = None) -> None:
    """Best-effort append-only audit of a DENY decision (never raises)."""
    try:
        from .repo import disaster_repo
        disaster_repo().append_activity(
            "access", f"{action}", actor=f"role:{role}", action="access.denied",
            diff={"action": action, "role": role, **(detail or {})})
    except Exception:  # noqa: BLE001 — auditing a denial must never break the request
        pass
