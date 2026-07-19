"""Pure-Python geometry helpers for the disaster module (no shapely dependency).

The disaster demo needs only a small, well-tested geometry kernel:
  * haversine distance (km) for nearest-resource + route length;
  * point-in-polygon (ray casting) for zone impact + spatial containment;
  * segment/segment intersection + segment-vs-polygon crossing for hazard-aware
    routing (exclude a road edge that crosses the active hazard polygon);
  * GeoJSON validation (type/coords/closed-ring) so an unvalidated reading can
    never produce a canonical geometry;
  * centroid + bbox helpers.

All coordinates are [lon, lat] in EPSG:4326 (GeoJSON order). Kept dependency-free
so it is importable and testable anywhere in the service.
"""
from __future__ import annotations

import math
from typing import Any, Optional

_EARTH_KM = 6371.0088
_VALID_TYPES = {"Point", "MultiPoint", "LineString", "MultiLineString",
                "Polygon", "MultiPolygon"}


# ---------------------------------------------------------------------------
# distance
# ---------------------------------------------------------------------------
def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in kilometres between two lon/lat points."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = rlat2 - rlat1
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    return 2 * _EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def path_length_km(coords: list[list[float]]) -> float:
    total = 0.0
    for i in range(1, len(coords)):
        x0, y0 = coords[i - 1][0], coords[i - 1][1]
        x1, y1 = coords[i][0], coords[i][1]
        total += haversine_km(x0, y0, x1, y1)
    return total


# ---------------------------------------------------------------------------
# point-in-polygon (ray casting)
# ---------------------------------------------------------------------------
def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-casting point-in-ring test. ``ring`` is a list of [lon, lat]."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (
                lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_contains(lon: float, lat: float, polygon: list) -> bool:
    """A GeoJSON Polygon coordinate array: [outer_ring, hole1, ...]."""
    if not polygon:
        return False
    if not point_in_ring(lon, lat, polygon[0]):
        return False
    for hole in polygon[1:]:
        if point_in_ring(lon, lat, hole):
            return False
    return True


def point_in_geometry(lon: float, lat: float, geom: Optional[dict]) -> bool:
    """True if [lon,lat] is inside a GeoJSON Polygon/MultiPolygon geometry."""
    if not geom or not isinstance(geom, dict):
        return False
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon":
        return _polygon_contains(lon, lat, coords or [])
    if gtype == "MultiPolygon":
        return any(_polygon_contains(lon, lat, poly) for poly in (coords or []))
    return False


# ---------------------------------------------------------------------------
# segment intersection (for hazard-aware routing edge exclusion)
# ---------------------------------------------------------------------------
def _orient(ax, ay, bx, by, cx, cy) -> float:
    return (by - ay) * (cx - bx) - (bx - ax) * (cy - by)


def _on_seg(ax, ay, bx, by, cx, cy) -> bool:
    return (min(ax, bx) <= cx <= max(ax, bx)
            and min(ay, by) <= cy <= max(ay, by))


def segments_intersect(a: list[float], b: list[float],
                       c: list[float], d: list[float]) -> bool:
    """Do segment ab and segment cd intersect? (standard orientation test)."""
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    cx, cy, dx, dy = c[0], c[1], d[0], d[1]
    d1 = _orient(cx, cy, dx, dy, ax, ay)
    d2 = _orient(cx, cy, dx, dy, bx, by)
    d3 = _orient(ax, ay, bx, by, cx, cy)
    d4 = _orient(ax, ay, bx, by, dx, dy)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    if d1 == 0 and _on_seg(cx, cy, dx, dy, ax, ay):
        return True
    if d2 == 0 and _on_seg(cx, cy, dx, dy, bx, by):
        return True
    if d3 == 0 and _on_seg(ax, ay, bx, by, cx, cy):
        return True
    if d4 == 0 and _on_seg(ax, ay, bx, by, dx, dy):
        return True
    return False


def _rings_of(geom: dict) -> list[list[list[float]]]:
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "Polygon":
        return list(coords)
    if gtype == "MultiPolygon":
        rings: list = []
        for poly in coords:
            rings.extend(poly)
        return rings
    return []


def segment_intersects_geometry(p1: list[float], p2: list[float],
                                geom: Optional[dict]) -> bool:
    """True if segment p1->p2 crosses a hazard polygon boundary or lies inside it.

    Used to EXCLUDE road edges intersecting the active hazard/block geometry.
    """
    if not geom:
        return False
    # endpoint inside the polygon -> the edge is affected
    if point_in_geometry(p1[0], p1[1], geom) or point_in_geometry(p2[0], p2[1], geom):
        return True
    # midpoint inside (catches a chord fully spanning a convex polygon)
    mid = [(p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0]
    if point_in_geometry(mid[0], mid[1], geom):
        return True
    # boundary crossing
    for ring in _rings_of(geom):
        n = len(ring)
        for i in range(n):
            a = ring[i]
            b = ring[(i + 1) % n]
            if segments_intersect(p1, p2, a, b):
                return True
    return False


# ---------------------------------------------------------------------------
# centroid + bbox
# ---------------------------------------------------------------------------
def _iter_points(geom: dict):
    coords = geom.get("coordinates")
    gtype = geom.get("type")
    if gtype == "Point":
        yield coords
    elif gtype in ("MultiPoint", "LineString"):
        yield from coords
    elif gtype in ("MultiLineString", "Polygon"):
        for part in coords:
            yield from part
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                yield from ring


def centroid(geom: Optional[dict]) -> Optional[tuple[float, float]]:
    """Approximate centroid (mean of vertices) as (lon, lat)."""
    if not geom:
        return None
    xs, ys = [], []
    for pt in _iter_points(geom):
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            xs.append(float(pt[0]))
            ys.append(float(pt[1]))
    if not xs:
        return None
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def bbox(geom: Optional[dict]) -> Optional[tuple[float, float, float, float]]:
    if not geom:
        return None
    xs, ys = [], []
    for pt in _iter_points(geom):
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            xs.append(float(pt[0]))
            ys.append(float(pt[1]))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# GeoJSON validation
# ---------------------------------------------------------------------------
def _num_pair(pt: Any) -> bool:
    return (isinstance(pt, (list, tuple)) and len(pt) >= 2
            and all(isinstance(v, (int, float)) for v in pt[:2]))


def validate_geojson(geom: Any) -> tuple[bool, str]:
    """Validate a GeoJSON geometry. Returns (ok, reason).

    Enforces: known type, numeric coordinate pairs, lon/lat in range, closed
    polygon rings with >= 4 positions. An unvalidated reading must never become
    a canonical geometry (Prompt 17 D.6 / E.7).
    """
    if not isinstance(geom, dict):
        return False, "geometry is not an object"
    gtype = geom.get("type")
    if gtype not in _VALID_TYPES:
        return False, f"unsupported geometry type {gtype!r}"
    coords = geom.get("coordinates")
    if coords is None:
        return False, "missing coordinates"

    def _check_pt(pt) -> Optional[str]:
        if not _num_pair(pt):
            return "coordinate is not a numeric [lon, lat] pair"
        lon, lat = float(pt[0]), float(pt[1])
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            return f"coordinate out of range ({lon},{lat})"
        return None

    def _check_ring(ring) -> Optional[str]:
        if not isinstance(ring, list) or len(ring) < 4:
            return "polygon ring needs >= 4 positions"
        for pt in ring:
            err = _check_pt(pt)
            if err:
                return err
        if list(ring[0][:2]) != list(ring[-1][:2]):
            return "polygon ring is not closed"
        return None

    try:
        if gtype == "Point":
            err = _check_pt(coords)
        elif gtype in ("MultiPoint", "LineString"):
            if not isinstance(coords, list) or len(coords) < (2 if gtype == "LineString" else 1):
                return False, f"{gtype} needs enough positions"
            err = next((e for e in (_check_pt(p) for p in coords) if e), None)
        elif gtype == "Polygon":
            if not isinstance(coords, list) or not coords:
                return False, "polygon has no rings"
            err = next((e for e in (_check_ring(r) for r in coords) if e), None)
        elif gtype == "MultiLineString":
            err = next((e for line in coords for e in (_check_pt(p) for p in line) if e), None)
        elif gtype == "MultiPolygon":
            err = next((e for poly in coords for r in poly for e in [_check_ring(r)] if e), None)
        else:
            err = "unsupported"
    except (TypeError, ValueError, IndexError) as exc:
        return False, f"malformed coordinates ({type(exc).__name__})"
    if err:
        return False, err
    return True, "ok"


def point_geojson(lon: float, lat: float) -> dict:
    return {"type": "Point", "coordinates": [round(float(lon), 6), round(float(lat), 6)]}


def polygon_from_ring(ring: list[list[float]]) -> dict:
    r = [[round(float(x), 6), round(float(y), 6)] for x, y in ring]
    if r and r[0] != r[-1]:
        r.append(r[0])
    return {"type": "Polygon", "coordinates": [r]}
