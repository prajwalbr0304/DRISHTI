"""Nearest-responder resolution for a confirmed CCTV alert.

"Alert the nearest police station" has to be explainable, so this module returns
ranked candidates each carrying the inputs that produced the ranking: the
distance, WHERE the geometry came from, the ETA speed assumption, and the rule
applied. That payload is stored on ``CctvDispatch.Reason`` and rendered on the
dispatch card — the analyst sees why this station and not another.

Two geometry sources, tried in order, and the one actually used is always
reported rather than silently substituted:

  1. ``postgis_knn`` — a real PostGIS K-nearest-neighbour lookup over
     ``"UnitLocation"`` joined to ``"Unit"``, using the ``<->`` operator against
     the GIST index (the same primitive ``app/intake/service.py`` uses for its
     nearest-station hint) with an accurate geography distance. Available only
     when an analytics ``DATABASE_URL`` is configured and reachable.
  2. ``datastore_haversine`` — a pure-Python great-circle scan over the
     ``PatrolUnit`` rows in Catalyst Data Store. This is the deployed AppSail
     path (which has no RDS) and the offline-test path.

If neither yields a responder inside the radius, that is returned as an explicit
"no responder in range" outcome. It is never rounded up to a far-away station,
because a dispatch card that quietly widens its own search radius is worse than
one that says it found nothing.

This module only RANKS. It never writes a dispatch row and never sends anything;
the service layer persists a proposal and a human confirms it.
"""
from __future__ import annotations

from typing import Any, Optional

from ..config import get_settings
from ..disaster.geometry import haversine_km
from .repo import CctvRepo

# Versioned assumption behind every ETA shown in the UI. Bump it when the model
# changes so an old dispatch row stays interpretable.
ETA_ASSUMPTIONS_VERSION = "cctv-eta-urban@1.0.0"

# Responder kinds ordered by how appropriate they are as a first responder to a
# street incident. Used only as a tie-break nudge, never to override distance.
_KIND_BONUS: dict[str, float] = {
    "patrol_vehicle": 0.10,
    "traffic_patrol": 0.06,
    "station": 0.04,
    "control_room": 0.0,
}


def eta_minutes(distance_km: float, *, speed_kmh: Optional[float] = None) -> float:
    """Travel-time estimate from a single documented average-speed assumption.

    Deliberately crude and labelled as such: there is no live traffic feed here,
    so a precise-looking ETA would be false precision. One minute of dispatch
    overhead is added because a unit does not start moving instantly.
    """
    s = get_settings()
    speed = float(speed_kmh or s.cctv_dispatch_avg_speed_kmh) or 28.0
    return round((distance_km / speed) * 60.0 + 1.0, 1)


def _score(distance_km: float, max_km: float, kind: Optional[str],
           status: Optional[str]) -> float:
    """Higher is better: proximity dominates, with small readiness adjustments."""
    prox = max(0.0, 1.0 - (distance_km / max_km if max_km else 1.0))
    bonus = _KIND_BONUS.get(kind or "", 0.0)
    # An engaged unit is still offered (the analyst may have no better option) but
    # ranks below a free one, and the penalty is visible in the score.
    penalty = 0.25 if status == "engaged" else 0.0
    return round(max(0.0, min(1.0, 0.85 * prox + bonus - penalty)), 4)


# ---------------------------------------------------------------------------
# source 1: PostGIS KNN over the canonical station geometry
# ---------------------------------------------------------------------------
def _postgis_candidates(lon: float, lat: float, *, limit: int) -> list[dict[str, Any]]:
    """K-nearest ``"Unit"`` rows by current ``"UnitLocation"`` point.

    Returns ``[]`` (never raises) when no analytics DB is configured or the query
    cannot run, so the caller can fall back and report the substitution honestly.
    """
    s = get_settings()
    if not s.database_url:
        return []
    try:
        from .. import db
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT u."UnitID", u."UnitName", u."DistrictID", '
                    '       ST_X(ul."geom") AS lon, ST_Y(ul."geom") AS lat, '
                    '       ST_Distance(ul."geom"::geography, '
                    '                   ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) '
                    '         / 1000.0 AS dist_km '
                    'FROM "UnitLocation" ul '
                    'JOIN "Unit" u ON u."UnitID" = ul."UnitID" '
                    'WHERE ul."IsCurrent" '
                    'ORDER BY ul."geom" <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326) '
                    'LIMIT %s',
                    (lon, lat, lon, lat, int(limit)),
                )
                rows = cur.fetchall() or []
    except Exception:  # noqa: BLE001 — an unreachable analytics DB must not break dispatch
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "unit_id": int(r[0]),
            "patrol_unit_id": None,
            "unit_name": r[1],
            "unit_kind": "station",
            "district_id": (int(r[2]) if r[2] is not None else None),
            "lon": (float(r[3]) if r[3] is not None else None),
            "lat": (float(r[4]) if r[4] is not None else None),
            "status": "available",
            "distance_km": round(float(r[5]), 3),
            "geometry_source": "postgis_knn",
        })
    return out


# ---------------------------------------------------------------------------
# source 2: haversine scan over the Data Store responder rows
# ---------------------------------------------------------------------------
def _datastore_candidates(repo: CctvRepo, lon: float, lat: float, *,
                          limit: int) -> list[dict[str, Any]]:
    rows = repo.list("PatrolUnit")
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("Lon") is None or r.get("Lat") is None:
            continue
        if r.get("Status") == "offline":
            continue
        dist = haversine_km(lon, lat, float(r["Lon"]), float(r["Lat"]))
        out.append({
            "unit_id": (int(r["UnitID"]) if r.get("UnitID") is not None else None),
            "patrol_unit_id": int(r["PatrolUnitID"]),
            "unit_name": r.get("Name") or r.get("Code"),
            "unit_kind": r.get("Kind") or "station",
            "district_id": (int(r["DistrictID"]) if r.get("DistrictID") is not None else None),
            "lon": float(r["Lon"]),
            "lat": float(r["Lat"]),
            "status": r.get("Status") or "available",
            "code": r.get("Code"),
            "contact_label": r.get("ContactLabel"),
            "distance_km": round(dist, 3),
            "geometry_source": "datastore_haversine",
        })
    out.sort(key=lambda c: c["distance_km"])
    return out[:limit]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def rank_responders(repo: CctvRepo, lon: float, lat: float, *,
                    district_id: Optional[int] = None,
                    limit: int = 5,
                    max_km: Optional[float] = None,
                    prefer_postgis: bool = True) -> dict[str, Any]:
    """Rank the nearest responders to an incident point.

    Returns::

        {"candidates": [...], "geometry_source": "...", "considered": n,
         "max_distance_km": float, "eta_assumptions_version": "...",
         "fallback_reason": str | None}

    ``candidates`` is ordered best-first and each entry carries ``distance_km``,
    ``eta_minutes``, ``score`` and a ``reason`` dict ready to persist.
    """
    s = get_settings()
    radius = float(max_km if max_km is not None else s.cctv_dispatch_max_km)
    fallback_reason: Optional[str] = None

    raw: list[dict[str, Any]] = []
    source = "datastore_haversine"
    if prefer_postgis:
        raw = _postgis_candidates(lon, lat, limit=max(limit * 3, 10))
        if raw:
            source = "postgis_knn"
        else:
            fallback_reason = (
                "no reachable PostGIS UnitLocation geometry; ranked Data Store "
                "responder rows by great-circle distance instead")
    if not raw:
        raw = _datastore_candidates(repo, lon, lat, limit=max(limit * 3, 10))
        source = "datastore_haversine"

    considered = len(raw)
    in_range = [c for c in raw if c["distance_km"] <= radius]
    # District containment is a preference, not a hard filter: an incident just
    # inside a boundary is often best served by the station across it. When a
    # same-district responder exists in range, prefer that set.
    if district_id is not None:
        same = [c for c in in_range if c.get("district_id") == int(district_id)]
        if same:
            in_range = same

    candidates: list[dict[str, Any]] = []
    for c in in_range:
        dist = float(c["distance_km"])
        eta = eta_minutes(dist)
        score = _score(dist, radius, c.get("unit_kind"), c.get("status"))
        candidates.append({
            **c,
            "eta_minutes": eta,
            "score": score,
            "reason": {
                "distance_km": round(dist, 3),
                "eta_minutes": eta,
                "geometry_source": c["geometry_source"],
                "eta_assumptions_version": ETA_ASSUMPTIONS_VERSION,
                "avg_speed_kmh": s.cctv_dispatch_avg_speed_kmh,
                "search_radius_km": radius,
                "responder_status": c.get("status"),
                "responder_kind": c.get("unit_kind"),
                "rule": ("nearest available responder to the camera position, "
                         "within the configured search radius"),
            },
        })
    candidates.sort(key=lambda c: (-c["score"], c["distance_km"]))

    return {
        "candidates": candidates[:limit],
        "geometry_source": source,
        "considered": considered,
        "max_distance_km": radius,
        "eta_assumptions_version": ETA_ASSUMPTIONS_VERSION,
        "fallback_reason": fallback_reason,
    }


def nearest_responder(repo: CctvRepo, lon: float, lat: float, *,
                      district_id: Optional[int] = None,
                      max_km: Optional[float] = None) -> Optional[dict[str, Any]]:
    """The single best responder, or ``None`` when none is inside the radius."""
    plan = rank_responders(repo, lon, lat, district_id=district_id, limit=1, max_km=max_km)
    cands = plan["candidates"]
    return cands[0] if cands else None
