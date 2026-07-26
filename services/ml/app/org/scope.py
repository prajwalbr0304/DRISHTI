"""Server-side organizational scope derivation + allow/deny decision matrix
(Prompt 20 Part B.2/B.3).

The caller's role + geographic scope are derived from the TRUSTED identity — the
Catalyst-authenticated user record (``users.role_id`` + ``users.unit_id``) and,
where present, the officer establishment row (``Employee`` rank/district/unit) —
NEVER from a browser-supplied district/unit header. A browser header may hint the
UI's default view, but it is discarded for every authorization decision here.

The pure decision functions take an explicit :class:`ScopeContext` so the whole
allow/deny matrix is deterministic and unit-testable without a database; the
DB-backed :func:`resolve_scope_for_user` is the thin trusted-lookup wrapper.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import hierarchy
from ..roles import ALL_ROLES, DEFAULT_ROLE, normalize_role

# Roles that are never geographically pinned (platform-wide seats).
UNPINNED_ROLES = {"system_admin"}

# Actions the allow/deny matrix covers (Prompt 20 Part B.3).
MATRIX_ACTIONS = (
    "case_detail", "aggregate_dashboard", "export_case_data", "export_aggregate",
    "investigation_board", "disaster_approval",
)


@dataclass(frozen=True)
class ScopeContext:
    """The resolved, server-trusted scope for one caller.

    ``district_ids``/``unit_ids`` of ``None`` mean "not geographically
    restricted within the role's capability" (e.g. a state-level seat). An empty
    frozenset means "assigned to nothing yet" -> no geographic resource passes.
    ``assigned_case_ids`` is only meaningful for the case-scoped investigator
    level; ``None`` there means "not restricted to a specific case list".
    """
    role: str
    scope_level: str
    district_ids: Optional[frozenset] = None
    unit_ids: Optional[frozenset] = None
    assigned_case_ids: Optional[frozenset] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    rank: Optional[str] = None
    source: str = "role-default"          # provenance of the derivation
    trusted: bool = True                  # False if we had to fall back

    def as_dict(self) -> dict:
        return {
            "role": self.role, "scope_level": self.scope_level,
            "district_ids": (sorted(self.district_ids) if self.district_ids is not None else None),
            "unit_ids": (sorted(self.unit_ids) if self.unit_ids is not None else None),
            "assigned_case_scoped": self.assigned_case_ids is not None,
            "user_id": self.user_id, "username": self.username, "rank": self.rank,
            "source": self.source, "trusted": self.trusted,
        }


# ---------------------------------------------------------------------------
# Derivation from TRUSTED fields (pure — no DB). The DB wrapper is below.
# ---------------------------------------------------------------------------
def derive_scope(role: str, *, user_id: Optional[int] = None,
                 username: Optional[str] = None, rank: Optional[str] = None,
                 designation: Optional[str] = None,
                 district_id: Optional[int] = None, unit_id: Optional[int] = None,
                 assigned_case_ids: Optional[list] = None,
                 source: str = "trusted-assignment") -> ScopeContext:
    """Build a :class:`ScopeContext` from trusted assignment fields.

    The scope LEVEL comes from the rank mapping when a rank/designation is known,
    otherwise from the role default. The geographic sets come only from the
    trusted ``district_id``/``unit_id`` assignment (never a client header)."""
    role = (role or DEFAULT_ROLE).strip()
    mapping = hierarchy.map_rank(rank, designation)
    scope_level = mapping.scope_level if mapping else hierarchy.scope_level_for_role(role)

    # State/range seats and the platform admin are not district-pinned unless assigned.
    broad = scope_level in ("state", "range")
    districts: Optional[frozenset]
    units: Optional[frozenset]
    if role in UNPINNED_ROLES:
        districts, units = None, None
    elif district_id is not None:
        districts = frozenset({int(district_id)})
        units = frozenset({int(unit_id)}) if unit_id is not None else None
    elif broad:
        districts, units = None, None
    else:
        # District/station/case seat without a trusted district assignment: the
        # role's capability still applies but no geographic narrowing is asserted
        # (documented demo fallback; a real deployment pins this from SSO).
        districts, units = None, None

    cases: Optional[frozenset] = None
    if scope_level == "assigned_case" and assigned_case_ids is not None:
        cases = frozenset(int(c) for c in assigned_case_ids)

    return ScopeContext(
        role=role, scope_level=scope_level, district_ids=districts, unit_ids=units,
        assigned_case_ids=cases, user_id=user_id, username=username,
        rank=(mapping.rank if mapping else rank), source=source,
        trusted=(district_id is not None or broad or role in UNPINNED_ROLES),
    )


# ---------------------------------------------------------------------------
# Geographic containment
# ---------------------------------------------------------------------------
def within_geo_scope(scope: ScopeContext, *, district_id: Optional[int] = None,
                     unit_id: Optional[int] = None) -> bool:
    """True when a resource in ``district_id``/``unit_id`` is inside the seat's
    geographic scope. ``None`` sets mean "no restriction at that level"."""
    if scope.district_ids is not None:
        if district_id is None or int(district_id) not in scope.district_ids:
            return False
    if scope.unit_ids is not None:
        if unit_id is None or int(unit_id) not in scope.unit_ids:
            return False
    return True


# ---------------------------------------------------------------------------
# Allow/deny decisions (Prompt 20 Part B.3)
# ---------------------------------------------------------------------------
def can_view_case_detail(scope: ScopeContext, *, district_id: Optional[int] = None,
                         unit_id: Optional[int] = None,
                         case_id: Optional[int] = None) -> bool:
    """Individual case/FIR detail (PII).

    INTERIM: every command role holds case-detail capability. What still applies
    is GEOGRAPHIC containment (a district/station seat cannot read another
    district) and, for a case-scoped seat with a known assignment list, the
    assigned-case narrowing."""
    role = scope.role
    if role not in ALL_ROLES:
        return False
    if role in UNPINNED_ROLES:
        return True
    if not within_geo_scope(scope, district_id=district_id, unit_id=unit_id):
        return False
    # A case-scoped seat only sees its assigned cases (when the set is known).
    if scope.scope_level == "assigned_case" and scope.assigned_case_ids is not None:
        return case_id is not None and int(case_id) in scope.assigned_case_ids
    return True


def can_view_aggregate_dashboard(scope: ScopeContext) -> bool:
    """Every functional role may see aggregate dashboards for its own scope."""
    return scope.role in ALL_ROLES


def can_export(scope: ScopeContext, *, aggregate: bool) -> bool:
    """Exports. INTERIM: every command role may export both aggregate and
    case-level extracts (case-level extracts remain audited)."""
    return scope.role in ALL_ROLES


def can_use_investigation_board(scope: ScopeContext) -> bool:
    """Investigation Board — INTERIM: open to every command role."""
    return scope.role in ALL_ROLES


def can_approve_disaster(scope: ScopeContext, *, district_id: Optional[int] = None) -> bool:
    """Disaster warning/allocation/evacuation approval. INTERIM: every command
    role may approve, still confined to its geographic scope."""
    if scope.role not in ALL_ROLES:
        return False
    if scope.role in UNPINNED_ROLES:
        return True
    return within_geo_scope(scope, district_id=district_id)


def decide(scope: ScopeContext, action: str, *, district_id: Optional[int] = None,
           unit_id: Optional[int] = None, case_id: Optional[int] = None) -> bool:
    """Single entry point used by the matrix endpoint + tests."""
    if action == "case_detail":
        return can_view_case_detail(scope, district_id=district_id, unit_id=unit_id, case_id=case_id)
    if action == "aggregate_dashboard":
        return can_view_aggregate_dashboard(scope)
    if action == "export_case_data":
        return can_export(scope, aggregate=False)
    if action == "export_aggregate":
        return can_export(scope, aggregate=True)
    if action == "investigation_board":
        return can_use_investigation_board(scope)
    if action == "disaster_approval":
        return can_approve_disaster(scope, district_id=district_id)
    raise ValueError(f"unknown action: {action}")


class ScopeDenied(PermissionError):
    """Raised when a requested geographic filter exceeds the caller's scope."""


def enforce_geo_request(scope: ScopeContext, *, unit_id: Optional[int] = None,
                        district_id: Optional[int] = None) -> tuple:
    """Confine a requested (unit_id, district_id) filter to the caller's scope.

    A station-scoped seat is FORCED to its assigned unit; a district-scoped seat
    to its district. An out-of-scope request raises :class:`ScopeDenied`. An
    unrestricted (state/super_admin) seat may request any/no filter. This is how
    "station chiefs -> their station, SP -> assigned units, higher -> aggregates"
    is enforced server-side (never from a browser header)."""
    if scope.unit_ids is not None:
        if unit_id is not None and int(unit_id) not in scope.unit_ids:
            raise ScopeDenied("requested station is outside your assigned scope")
        if unit_id is None and len(scope.unit_ids) == 1:
            unit_id = next(iter(scope.unit_ids))
    if scope.district_ids is not None:
        if district_id is not None and int(district_id) not in scope.district_ids:
            raise ScopeDenied("requested district is outside your assigned scope")
        if district_id is None and unit_id is None and len(scope.district_ids) == 1:
            district_id = next(iter(scope.district_ids))
    return unit_id, district_id


def scope_from_gateway_context(ctx) -> ScopeContext:
    """Build a trusted :class:`ScopeContext` from a verified signed gateway
    context (Prompt 21 §E.3). The role + district/unit were resolved SERVER-SIDE
    by the gateway function and signed, so this needs no DB and cannot be spoofed
    by the browser. Used by the deployed AppSail path."""
    return derive_scope(
        ctx.role,
        user_id=None,
        username=(ctx.user_id or None),
        district_id=ctx.district_id,
        unit_id=ctx.unit_id,
        source="signed-gateway-context",
    )


def resolve_request_scope(request, *, fallback_role: Optional[str] = None) -> ScopeContext:
    """Resolve the caller's trusted scope for a request.

    Deployed: use the verified signed gateway context on ``request.state`` (role
    + organizational scope, server-resolved and signed). Local/dev: fall back to
    the presentation X-Role header with the role-default scope (no DB needed).
    Never reads a browser-supplied district/unit for an authorization decision.
    """
    ctx = getattr(getattr(request, "state", None), "gateway_context", None)
    if ctx is not None and getattr(ctx, "is_user", False):
        return scope_from_gateway_context(ctx)
    raw = (fallback_role
           or (request.headers.get("x-role") if hasattr(request, "headers") else None))
    return derive_scope(normalize_role(raw), source="role-default")


def matrix_for_roles(district_id: Optional[int] = None) -> dict:
    """The full role x action allow/deny matrix (role-default scope), for the
    /org/scope-matrix endpoint and the matrix tests."""
    out: dict[str, dict[str, bool]] = {}
    for role in hierarchy.FUNCTIONAL_ROLES:
        sc = derive_scope(role, source="role-default")
        out[role] = {action: decide(sc, action, district_id=district_id)
                     for action in MATRIX_ACTIONS}
    return out
