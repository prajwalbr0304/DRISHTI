"""Valid-geography scope for aggregate forecasting (Phase 12).

Aggregate forecasts must be built from CANONICAL, VALID geography only: an
incident whose coordinates fall outside the Karnataka state boundary is a
data-quality error (Phase 9) and must not shape a beat/area/district forecast.
This module centralises that exclusion so every forecast data tap (the monthly
count series, district centroids, near-repeat points, backtest reads) excludes
out-of-jurisdiction incidents identically.

Performance: the set of out-of-state case ids is discovered ONCE per connection
with an index-assisted PostGIS anti-join (``idx_casemaster_geom``), then cached.
Each forecast tap simply excludes those ids by primary key — which is FREE when
the set is empty (the clean, common case). It degrades safely: when no state
boundary is loaded the filter is inactive (empty set), so a located case is never
wrongly dropped.

Person-level geography is never used here — everything is aggregated to the
area/district level, so no coordinate is tied to an individual.
"""
from __future__ import annotations

from typing import Optional

from ..cases import casedata

_BOUNDARY_ATTR = "_drishti_state_boundary_available"
_OOS_ATTR = "_drishti_out_of_state_case_ids"

# Index-assisted containment: a point is IN-state iff the state polygon contains
# its geom. Uses the GiST index on CaseMaster.geom (fast); NOT EXISTS gives the
# out-of-state anti-set.
_OUT_OF_STATE_SQL = (
    'SELECT cm."CaseMasterID" FROM "CaseMaster" cm '
    'WHERE cm."geom" IS NOT NULL '
    f'AND {casedata.analytics_eligible_sql("cm")} '
    'AND NOT EXISTS ('
    'SELECT 1 FROM "JurisdictionBoundary" sb '
    "WHERE sb.\"Level\" = 'state' AND sb.\"IsCurrent\" AND ST_Contains(sb.\"geom\", cm.\"geom\"))"
)


def boundaries_available(conn) -> bool:
    """True if a current ``state`` JurisdictionBoundary polygon is loaded.
    Cached on the connection so repeated taps do not re-query."""
    cached = getattr(conn, _BOUNDARY_ATTR, None)
    if cached is not None:
        return cached
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT EXISTS (SELECT 1 FROM "JurisdictionBoundary" '
                        "WHERE \"Level\" = 'state' AND \"IsCurrent\")")
            available = bool(cur.fetchone()[0])
    except Exception:  # noqa: BLE001 — a missing table/boundary means "no filter"
        available = False
    try:
        setattr(conn, _BOUNDARY_ATTR, available)
    except Exception:  # noqa: BLE001
        pass
    return available


def out_of_state_case_ids(conn) -> tuple[int, ...]:
    """The (cached) set of CaseMasterIDs whose coordinates fall outside the state
    polygon. Empty when no boundary is loaded (filter inactive) — computed once
    per connection with the index-assisted anti-join."""
    cached = getattr(conn, _OOS_ATTR, None)
    if cached is not None:
        return cached
    ids: tuple[int, ...] = ()
    if boundaries_available(conn):
        try:
            with conn.cursor() as cur:
                cur.execute(_OUT_OF_STATE_SQL)
                ids = tuple(int(r[0]) for r in cur.fetchall())
        except Exception:  # noqa: BLE001
            ids = ()
    try:
        setattr(conn, _OOS_ATTR, ids)
    except Exception:  # noqa: BLE001
        pass
    return ids


def exclusion_predicate(conn, valid_geo_only: bool, alias: str = "cm"):
    """Return ``(sql, param)`` excluding out-of-state cases by primary key, or
    ``(None, None)`` when the filter is inactive/empty (add nothing — the fast
    path). ``param`` is the list of out-of-state CaseMasterIDs."""
    if not valid_geo_only:
        return None, None
    ids = out_of_state_case_ids(conn)
    if not ids:
        return None, None
    return f'{alias}."CaseMasterID" <> ALL(%s)', list(ids)


def apply_exclusion(conn, where: list, params: list, valid_geo_only: bool, alias: str = "cm") -> bool:
    """Append the out-of-state exclusion to ``where``/``params`` in place. Returns
    True if a predicate was added (only when out-of-state cases exist)."""
    pred, param = exclusion_predicate(conn, valid_geo_only, alias)
    if pred is None:
        return False
    where.append(pred)
    params.append(param)
    return True


def count_out_of_state(conn, district_id: Optional[int] = None,
                       head_id: Optional[int] = None) -> int:
    """Count in-scope located cases (with a registration date) whose coordinates
    fall OUTSIDE the state boundary. 0 when no boundary is loaded."""
    if not boundaries_available(conn):
        return 0
    if district_id is None and head_id is None:
        return len(out_of_state_case_ids(conn))
    where = ['cm."geom" IS NOT NULL', 'cm."CrimeRegisteredDate" IS NOT NULL',
             casedata.analytics_eligible_sql("cm"),
             'NOT EXISTS (SELECT 1 FROM "JurisdictionBoundary" sb '
             "WHERE sb.\"Level\" = 'state' AND sb.\"IsCurrent\" "
             'AND ST_Contains(sb."geom", cm."geom"))']
    params: list = []
    joins = ""
    if district_id is not None:
        joins = ' JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID"'
        where.append('u."DistrictID" = %s')
        params.append(district_id)
    if head_id is not None:
        where.append('cm."CrimeMajorHeadID" = %s')
        params.append(head_id)
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM "CaseMaster" cm' + joins +
                    ' WHERE ' + ' AND '.join(where), params)
        return int(cur.fetchone()[0])


def scope_summary(conn) -> dict:
    """A small provenance/diagnostic summary of the valid-geography scope."""
    available = boundaries_available(conn)
    return {
        "valid_geography_filter": "active" if available else "inactive_no_boundary",
        "boundaries_loaded": available,
        "out_of_state_excluded": count_out_of_state(conn) if available else 0,
        "rule": "incidents whose coordinates fall outside the current state polygon are "
                "excluded from aggregate forecasts (index-assisted PostGIS containment); "
                "station-assigned cases without coordinates are retained.",
    }
