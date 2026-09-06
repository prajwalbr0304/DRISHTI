"""Disaster authorization (Prompt 17 application-authorization section).

AWS PostgreSQL RLS/FORCE RLS remain DISABLED (as requested), so the access
boundary is the Catalyst-authenticated API enforced server-side in AppSail:

  * INTERIM: every command role (app/roles.py) may review warnings and
    approve/dispatch allocations + evacuation plans — a seat with an ASSIGNED
    synthetic district stays confined to it;
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
from ..roles import ALL_ROLES, DEFAULT_ROLE, ROLE_SCOPE_LEVEL

# --- role sets --------------------------------------------------------------
# INTERIM ("all roles have access to everything"): every command role may read
# the situational view AND run forecasts, allocate resources and approve
# evacuation plans. District containment below still applies.
DISASTER_WRITE_ROLES = set(ALL_ROLES)
DISASTER_READ_ROLES = set(ALL_ROLES)
DISASTER_FORECAST_ROLES = set(ALL_ROLES)
RESOURCE_ALLOCATION_ROLES = set(ALL_ROLES)
EVACUATION_PLAN_ROLES = set(ALL_ROLES)
# Superseded. Confinement is now decided by the SEAT's district set, not by its
# role, because role no longer determines breadth: `senior_command` is state-wide
# when wing-scoped and multi-district when range-scoped, and this set would have
# treated both as unconfined. Retained only so existing imports keep working.
DISTRICT_SCOPED_ROLES = {r for r, lvl in ROLE_SCOPE_LEVEL.items()
                         if lvl in ("district", "subdivision", "station", "assigned_case")}


class DisasterScope:
    """The resolved actor scope for a request.

    ``districts`` is the seat's TRUSTED district set, resolved server-side from the
    seat record — not from a request header. Semantics match
    :class:`app.org.scope.ScopeContext`:

        None            not geographically narrowed (state seat, wing seat, admin)
        frozenset()     entitled to nothing (unposted seat)
        {1, 4, 9}       confined to those districts (a district or range seat)
    """

    def __init__(self, role: str, actor: str, district_id: Optional[int],
                 unit_id: Optional[int], districts: Optional[frozenset] = None,
                 scope_type: str = "unresolved"):
        self.role = role
        self.actor = actor
        self.district_id = district_id
        self.unit_id = unit_id
        self.districts = districts
        self.scope_type = scope_type
        self.is_super = role in {"system_admin"}

    def covers_district(self, district_id: Optional[int]) -> bool:
        """True when this seat may act on ``district_id``.

        FAIL CLOSED. The previous implementation returned True whenever the seat
        had no asserted district — and the district came from the
        ``X-Disaster-District`` request header, so OMITTING the header granted
        state-wide authority to approve warnings, allocate resources and sign off
        evacuation plans. Setting it granted authority over whichever district the
        client named. Both are now impossible: the district set comes from the seat
        record, and an empty set covers nothing.
        """
        if self.is_super:
            return True
        if self.role not in DISASTER_WRITE_ROLES:
            return False
        if self.districts is None:
            # Unrestricted BY REMIT (state command, or a wing that is state-wide
            # geographically). A wing's narrowing is by crime head, not district.
            return True
        if not self.districts:
            return False          # unposted seat: no jurisdiction, no authority
        if district_id is None:
            # An action with no district cannot be checked against a confined
            # seat, so it is refused rather than waved through.
            return False
        return int(district_id) in self.districts

    def as_dict(self) -> dict:
        return {"role": self.role, "actor": self.actor,
                "district_id": self.district_id, "unit_id": self.unit_id,
                "scope_type": self.scope_type,
                "districts": (sorted(self.districts)
                              if self.districts is not None else None),
                "is_super": self.is_super}


def _resolve_role(x_role: Optional[str]) -> str:
    return (x_role or get_settings().default_role or DEFAULT_ROLE).strip()


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
    """Resolve the caller's disaster scope from the TRUSTED seat record.

    ``X-Disaster-District`` / ``X-Disaster-Unit`` are still read, but only as a
    NARROWING preference within the seat's own scope: a coordinator posted to a
    range may focus one of its districts. A header naming a district outside the
    seat's scope is discarded, so it can no longer be used to select a
    jurisdiction — which is what it previously did.
    """
    from ..org.deps import resolve_seat_scope

    seat = resolve_seat_scope(request)
    role = seat.role or _resolve_role(request.headers.get("x-role"))

    districts = seat.district_ids
    # A wing seat is state-wide geographically; its narrowing is by crime head, so
    # it is not district-confined for disaster actions.
    if seat.scope_type == "wing":
        districts = None

    requested = _int_header(request, "x-disaster-district")
    focus = None
    if requested is not None and (districts is None or requested in districts):
        focus = requested
    elif districts is not None and len(districts) == 1:
        focus = next(iter(districts))

    requested_unit = _int_header(request, "x-disaster-unit")
    unit = None
    if seat.unit_ids is None:
        unit = requested_unit
    elif requested_unit is not None and requested_unit in seat.unit_ids:
        unit = requested_unit
    elif len(seat.unit_ids) == 1:
        unit = next(iter(seat.unit_ids))

    return DisasterScope(role=role, actor=resolve_actor(request),
                         district_id=focus, unit_id=unit,
                         districts=districts, scope_type=seat.scope_type)


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
            detail=(f"Role '{role}' lacks the '{permission}' permission for "
                    "Emergency Response actions."))
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
        if scope.districts is not None and not scope.districts:
            raise HTTPException(
                status_code=403,
                detail=(f"'{action}' is refused: this seat has no district on "
                        "record, so it holds no jurisdiction to act in. An "
                        "administrator must post it first."))
        allowed = (", ".join(str(d) for d in sorted(scope.districts))
                   if scope.districts else "none")
        raise HTTPException(
            status_code=403,
            detail=(f"'{action}' is outside your jurisdiction (districts: "
                    f"{allowed}). A district- or range-scoped seat may only act "
                    "within the districts it is posted to."))


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
