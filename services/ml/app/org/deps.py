"""FastAPI dependencies that make organizational scope ENFORCING, not advisory.

Until now `resolve_request_scope` existed in ``app/org/scope.py`` and was called by
no router: ``/performance/overview`` was the only endpoint applying a jurisdiction
filter, so every other jurisdiction-parameterised endpoint accepted whatever
``district_id`` the client asked for. A district-3 SHO could read district 9.

These dependencies close that by resolving the caller's TRUSTED seat once per
request and confining the requested filters to it. Two layers, deliberately:

  resolve_seat_scope   resolves WHO the caller is (never from a browser value that
                       could widen scope)
  confine_geo          narrows or rejects the REQUESTED filter against that seat

Resolution order, most to least trustworthy:
  1. the verified signed gateway context on ``request.state`` (deployed path);
  2. the seat record looked up from ``X-Demo-Actor`` (local/dev path, and the
     seeded demo logins);
  3. the role-default scope from ``X-Role``, which for every posted role is
     ``unresolved`` and therefore sees nothing.

Step 3 is why this is safe to apply broadly: an unidentified caller does not fall
back to state-wide, it falls back to nothing.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Query, Request

from ..roles import DEFAULT_ROLE, normalize_role
from . import scope as scope_mod
from .scope import ScopeContext, ScopeDenied


def resolve_seat_scope(request: Request) -> ScopeContext:
    """The caller's trusted :class:`ScopeContext` for this request.

    Cached on ``request.state`` so several dependencies on one endpoint share a
    single resolution (and a single DB lookup).
    """
    cached = getattr(request.state, "seat_scope", None)
    if cached is not None:
        return cached

    # 1. Deployed: the gateway resolved role + scope server-side and signed it.
    ctx = getattr(request.state, "gateway_context", None)
    if ctx is not None and getattr(ctx, "is_user", False):
        sc = scope_mod.scope_from_gateway_context(ctx)
        request.state.seat_scope = sc
        return sc

    # 2. Local/dev: resolve the seat record behind the demo actor. This is a
    #    lookup of a server-side record, not a trusted client assertion — the
    #    actor names a seat, it does not describe one.
    actor = (request.headers.get("x-demo-actor") or "").strip()
    if actor:
        try:
            from . import service as org_service
            sc = org_service.resolve_scope_for_user(username=actor)
            request.state.seat_scope = sc
            return sc
        except Exception:  # noqa: BLE001 — unknown/inactive actor, or DB down
            pass

    # 3. Nothing identifiable. Role-default, which is 'unresolved' for every
    #    posted role and therefore confined to nothing.
    role = normalize_role(request.headers.get("x-role"), default=DEFAULT_ROLE)
    sc = scope_mod.derive_scope(role, source="role-default")
    request.state.seat_scope = sc
    return sc


def confine_geo(scope: ScopeContext, *, district_id: Optional[int] = None,
                unit_id: Optional[int] = None) -> tuple[Optional[int], Optional[int]]:
    """Confine a requested (unit_id, district_id) to the seat, or 403.

    Returns the EFFECTIVE filter: a seat that asked for nothing is narrowed to its
    own jurisdiction rather than left unfiltered, which is what stops an omitted
    parameter from being a way to see everything.
    """
    try:
        return scope_mod.enforce_geo_request(scope, unit_id=unit_id,
                                            district_id=district_id)
    except ScopeDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


class GeoScope:
    """Resolved seat plus the effective geographic filter for one request.

    Endpoints take this instead of raw ``district_id`` / ``unit_id`` query
    parameters so the confinement cannot be forgotten at the call site.
    """

    __slots__ = ("scope", "district_id", "unit_id", "district_ids", "crime_head_ids")

    def __init__(self, scope: ScopeContext, district_id: Optional[int],
                 unit_id: Optional[int]):
        self.scope = scope
        self.district_id = district_id
        self.unit_id = unit_id
        # A range seat spans several districts, so a single district_id cannot
        # express it. Services that support a set use this; those that do not fall
        # back to district_id and are honest about the reach.
        self.district_ids = (sorted(scope.district_ids)
                             if scope.district_ids is not None and len(scope.district_ids) > 1
                             else None)
        self.crime_head_ids = (sorted(scope.crime_head_ids)
                               if scope.crime_head_ids is not None else None)

    @property
    def aggregate_only(self) -> bool:
        return self.scope.aggregate_only

    def effective_district_ids(self) -> Optional[list]:
        """The district filter to apply, as a list, or None for no narrowing.

        Collapses the three shapes a confinement can take into one answer, in
        precedence order:

          1. an explicitly requested district (already confirmed in-scope by
             `confine_geo`) — the caller narrowing WITHIN its own jurisdiction;
          2. the seat's district set — a range seat, which a single id cannot express;
          3. None — unpinned by remit.

        Rule 1 is the one that is easy to lose. A service handed only the seat's
        full set ignores the narrowing and returns the whole range, which looks
        correct (nothing out of scope) while silently ignoring what was asked for.
        The EMPTY list is preserved: it means "entitled to nothing".
        """
        if self.district_id is not None:
            return [self.district_id]
        if self.district_ids is not None:
            return self.district_ids
        if self.scope.district_ids is not None:
            return sorted(self.scope.district_ids)
        return None

    def as_filters(self) -> dict:
        """The effective filter as a service-layer filter dict."""
        return {"district_id": self.district_id, "station_id": self.unit_id,
                "district_ids": self.district_ids,
                "crime_head_ids": self.crime_head_ids}

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        return (f"GeoScope(scope_type={self.scope.scope_type!r}, "
                f"district_id={self.district_id!r}, unit_id={self.unit_id!r}, "
                f"district_ids={self.district_ids!r})")


def geo_scope(
    request: Request,
    district_id: Optional[int] = Query(None, ge=1),
    station_id: Optional[int] = Query(None, ge=1),
) -> GeoScope:
    """Dependency: resolve the seat and confine the requested geography.

    Accepts ``district_id`` / ``station_id`` for callers that legitimately narrow
    WITHIN their scope (a DGP inspecting one district, an SP one station). It can
    only ever narrow: an out-of-scope value is a 403, not a silent widening.
    """
    scope = resolve_seat_scope(request)
    unit, district = confine_geo(scope, district_id=district_id, unit_id=station_id)
    return GeoScope(scope, district, unit)


def require_case_level(request: Request) -> ScopeContext:
    """Guard for endpoints that return individual case rows.

    Refuses aggregate-only seats. A state or wing seat is accountable for the whole
    force or a whole functional wing and has no case-level remit; without this it
    could page through every FIR in Karnataka. Refuses unposted seats too, since
    they have no jurisdiction to read within.
    """
    scope = resolve_seat_scope(request)
    if scope.aggregate_only:
        raise HTTPException(
            status_code=403,
            detail=("This seat is aggregate-only: it may read district and state "
                    "figures but not individual case records."))
    if not scope.resolved:
        raise HTTPException(
            status_code=403,
            detail=("This seat has no posting on record, so no case records are in "
                    "scope. An administrator must assign its district, station or "
                    "wing."))
    return scope
