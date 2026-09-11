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

from dataclasses import dataclass, field, replace
from typing import Optional

from . import hierarchy
from .. import roles as _roles
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
    # --- seat model (migrations 026/027) ------------------------------------
    # scope_type is what the seat actually carries; scope_level above remains the
    # ordered geographic ladder used by hierarchy.scope_covers.
    scope_type: str = "unresolved"
    wing_id: Optional[int] = None
    range_id: Optional[int] = None
    # Crime heads a WING seat is accountable for. None = every head. This is the
    # only narrowing a wing seat gets; it has no geographic filter.
    crime_head_ids: Optional[frozenset] = None
    is_lead_investigator: bool = False

    @property
    def aggregate_only(self) -> bool:
        """True when this seat must never read individual case rows.

        State and wing seats are accountable for the whole force or a whole
        functional wing; neither has a case-level remit, and both would otherwise
        be able to page through every FIR in Karnataka.
        """
        return self.scope_type in ("state", "wing")

    @property
    def resolved(self) -> bool:
        """False when the seat has no posting on record. Such a seat must see
        NOTHING rather than everything (see derive_scope)."""
        return self.scope_type != "unresolved"

    def as_dict(self) -> dict:
        return {
            "role": self.role, "scope_level": self.scope_level,
            "scope_type": self.scope_type,
            "district_ids": (sorted(self.district_ids) if self.district_ids is not None else None),
            "unit_ids": (sorted(self.unit_ids) if self.unit_ids is not None else None),
            "wing_id": self.wing_id, "range_id": self.range_id,
            "crime_head_ids": (sorted(self.crime_head_ids)
                               if self.crime_head_ids is not None else None),
            "assigned_case_scoped": self.assigned_case_ids is not None,
            "aggregate_only": self.aggregate_only,
            "is_lead_investigator": self.is_lead_investigator,
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
                 source: str = "trusted-assignment",
                 scope_type: Optional[str] = None,
                 wing_id: Optional[int] = None, range_id: Optional[int] = None,
                 district_ids: Optional[list] = None,
                 crime_head_ids: Optional[list] = None,
                 is_lead_investigator: bool = False) -> ScopeContext:
    """Build a :class:`ScopeContext` from trusted assignment fields.

    The scope LEVEL comes from the rank mapping when a rank/designation is known,
    otherwise from the role default. The geographic sets come only from the
    trusted ``district_id``/``unit_id`` assignment (never a client header)."""
    # translate_legacy_role, NOT normalize_role: a superseded name is mapped
    # forward, but an unknown or forged role is preserved so that every capability
    # check below refuses it. Coercing it to the default seat here would hand a
    # forged role a real seat's authority.
    role = _roles.translate_legacy_role(role) or DEFAULT_ROLE
    mapping = hierarchy.map_rank(rank, designation)
    scope_level = mapping.scope_level if mapping else hierarchy.scope_level_for_role(role)

    # The seat's scope_type is authoritative. When a caller has not supplied one
    # (legacy call sites, the offline dev path), infer it from whichever anchor is
    # present, and fall back to the role default -- which is 'unresolved' for
    # every posted role.
    st = (scope_type or "").strip()
    if not st:
        if role in UNPINNED_ROLES:
            st = "platform"
        elif wing_id is not None:
            st = "wing"
        elif range_id is not None:
            st = "range"
        elif unit_id is not None:
            st = "station" if scope_level == "station" else "assigned_case"
        elif district_id is not None:
            # A rank that is a city command (CP) is a commissionerate seat, not a
            # district one. Both anchor on district_id, so the rank is the only
            # thing that tells them apart.
            st = (mapping.scope_type if mapping and mapping.scope_type == "commissionerate"
                  else "district")
        elif mapping and mapping.scope_type in ("wing", "platform"):
            # A wing or platform seat needs no geographic anchor to be resolved:
            # a wing is state-wide by construction. Without this, an ADGP with no
            # district would fall through to 'unresolved' and see nothing.
            st = mapping.scope_type
        else:
            st = _roles.ROLE_DEFAULT_SCOPE_TYPE.get(role, "unresolved")

    districts: Optional[frozenset] = None
    units: Optional[frozenset] = None
    heads: Optional[frozenset] = None

    if st == "platform":
        # Platform admin is not geographically pinned.
        districts, units = None, None
    elif st == "state":
        # State command sees every district: no narrowing, by remit.
        districts, units = None, None
    elif st == "wing":
        # A wing is state-wide GEOGRAPHICALLY and narrowed by crime head instead.
        districts, units = None, None
        if crime_head_ids is not None:
            heads = frozenset(int(h) for h in crime_head_ids)
    elif st == "range":
        # Range districts must be expanded by the caller (DB lookup) and passed in
        # via district_ids. An empty set means "range with no districts", which
        # correctly yields nothing rather than everything.
        districts = (frozenset(int(d) for d in district_ids)
                     if district_ids is not None else frozenset())
    elif st in ("district", "commissionerate"):
        districts = (frozenset({int(district_id)}) if district_id is not None
                     else frozenset())
    elif st in ("station", "assigned_case"):
        units = frozenset({int(unit_id)}) if unit_id is not None else frozenset()
        if district_id is not None:
            districts = frozenset({int(district_id)})
    else:
        # FAIL CLOSED. An unposted seat previously fell through to
        # `districts, units = None, None`, which means "no restriction" -- so an
        # SHO with no posting on record saw the entire state, identically to the
        # DGP. Empty frozensets mean "assigned to nothing", so nothing passes
        # within_geo_scope until the seat is actually posted.
        st = "unresolved"
        districts, units = frozenset(), frozenset()

    cases: Optional[frozenset] = None
    if st == "assigned_case" and assigned_case_ids is not None:
        cases = frozenset(int(c) for c in assigned_case_ids)

    return ScopeContext(
        role=role, scope_level=scope_level, district_ids=districts, unit_ids=units,
        assigned_case_ids=cases, user_id=user_id, username=username,
        rank=(mapping.rank if mapping else rank), source=source,
        trusted=(st not in ("unresolved",)),
        scope_type=st, wing_id=wing_id, range_id=range_id, crime_head_ids=heads,
        is_lead_investigator=bool(is_lead_investigator),
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


def can_approve_disaster(scope: ScopeContext, *, district_id: Optional[int] = None,
                         unit_id: Optional[int] = None) -> bool:
    """Disaster warning/allocation/evacuation approval. INTERIM: every command
    role may approve, still confined to its geographic scope.

    ``unit_id`` must be forwarded for a station seat. Without it, a seat whose
    ``unit_ids`` is set can never satisfy :func:`within_geo_scope` — so an SHO
    would be refused approval inside its own district, which is the one place it
    certainly holds authority.
    """
    if scope.role not in ALL_ROLES:
        return False
    if scope.role in UNPINNED_ROLES:
        return True
    if not scope.resolved:
        return False
    return within_geo_scope(scope, district_id=district_id, unit_id=unit_id)


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
        return can_approve_disaster(scope, district_id=district_id, unit_id=unit_id)
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
    # A seat confined to NOTHING must be refused, not left unfiltered.
    #
    # An empty frozenset means "assigned to nothing" (an unposted seat, or a range
    # with no member districts). The forcing branches below only fire on a set of
    # exactly one, so an empty set used to fall straight through and return
    # (None, None) — i.e. no filter at all, which every service reads as
    # "state-wide". That handed an unposted seat the entire force: verified as
    # /cases/caseload returning the full 58,011 open cases, identical to the DGP.
    if ((scope.unit_ids is not None and len(scope.unit_ids) == 0)
            or (scope.district_ids is not None and len(scope.district_ids) == 0)):
        raise ScopeDenied(
            "this seat has no jurisdiction on record, so no data is in scope")

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
    by the browser. Used by the deployed AppSail path.

    ONE EXCEPTION, for the demo-auth path. When the context carries a requested
    seat name and NO geographic scope of its own, that seat is looked up in the
    ``users`` table and its real posting is used. This exists because demo auth
    (DRISHTI_DEMO_AUTH) mints a single full-access ``system_admin`` context for
    every caller: without the lookup, all ~11,800 seats collapsed onto one
    platform-wide identity, so an SP posted to one district was served — and
    offered in the district selector — all 38.

    Three properties make this safe rather than a hole:

      * the signed context supplies a NAME; the scope comes from the database, so
        it is still derived server-side from trusted data and never asserted;
      * a signed geographic scope always WINS. The lookup only runs when the
        context carries none, so the authenticated path (where `resolveIdentity`
        resolved a real district/unit) is untouched;
      * in demo mode the baseline is unrestricted platform access, so resolving a
        named seat can only ever NARROW what is served.

    A failed lookup — unknown seat, inactive seat, DB down — falls back to the
    signed context unchanged, which is the pre-existing behaviour.
    """
    requested = (getattr(ctx, "actor", None) or "").strip()
    if requested and ctx.district_id is None and ctx.unit_id is None:
        try:
            # Local import: org.service imports this module, so a top-level import
            # would be circular.
            from . import service as org_service
            seat = org_service.resolve_scope_for_user(username=requested)
        except Exception:  # noqa: BLE001 — unknown/inactive seat, or DB unavailable
            seat = None
        if seat is not None and seat.resolved:
            return replace(seat, source="signed-gateway-context+seat")

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
