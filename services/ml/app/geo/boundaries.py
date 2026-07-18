"""Administrative boundary overlays for the map (state / district / taluk) and
derived SHO (police-station jurisdiction) regions.

The state/district/taluk polygons are the vendored, simplified KGIS boundaries
bundled under ``app/geo/boundaries/`` (see datagen/geo/SOURCES.md for provenance
and licence). SHO regions are *derived on read*: the Voronoi tessellation of the
real station points (``service.stations``) clipped to each district polygon, so
the jurisdictions tile the district and always follow the actual data.

Everything is plain GeoJSON so the deck.gl ``GeoJsonLayer`` can render it
directly. No database writes; the boundary files are read-only reference data.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Dict, List, Optional

import numpy as np
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

BOUNDARIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boundaries")
LEVELS = {"state": "state.geojson", "districts": "districts.geojson", "taluks": "taluks.geojson"}


@lru_cache(maxsize=len(LEVELS))
def load_boundary(level: str) -> dict:
    """Return the vendored FeatureCollection for a boundary level (cached)."""
    fname = LEVELS.get(level)
    if fname is None:
        raise KeyError(level)
    with open(os.path.join(BOUNDARIES_DIR, fname), encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=len(LEVELS))
def load_boundary_text(level: str) -> str:
    """Raw GeoJSON text for a boundary level (cached) — served verbatim so the
    static levels are not re-serialised on every request."""
    fname = LEVELS.get(level)
    if fname is None:
        raise KeyError(level)
    with open(os.path.join(BOUNDARIES_DIR, fname), encoding="utf-8") as fh:
        return fh.read()


@lru_cache(maxsize=1)
def _district_polys() -> Dict[str, object]:
    polys: Dict[str, object] = {}
    for f in load_boundary("districts")["features"]:
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        polys[f["properties"]["district"]] = g
    return polys


# ---------------------------------------------------------------------------
# Voronoi -> SHO regions (ported from datagen/boundaries.py, standard 2D recipe)
# ---------------------------------------------------------------------------
def _voronoi_finite_polygons_2d(vor, radius: float):
    new_regions = []
    new_vertices = vor.vertices.tolist()
    center = vor.points.mean(axis=0)
    all_ridges: Dict[int, list] = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))
    for p1, region_idx in enumerate(vor.point_region):
        vertices = vor.regions[region_idx]
        if vertices and all(v >= 0 for v in vertices):
            new_regions.append(vertices)
            continue
        ridges = all_ridges.get(p1, [])
        new_region = [v for v in vertices if v >= 0]
        for p2, v1, v2 in ridges:
            if v2 < 0:
                v1, v2 = v2, v1
            if v1 >= 0:
                continue
            t = vor.points[p2] - vor.points[p1]
            t = t / np.linalg.norm(t)
            n = np.array([-t[1], t[0]])
            midpoint = vor.points[[p1, p2]].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, n)) * n
            far_point = vor.vertices[v2] + direction * radius
            new_region.append(len(new_vertices))
            new_vertices.append(far_point.tolist())
        vs = np.asarray([new_vertices[v] for v in new_region])
        c = vs.mean(axis=0)
        angles = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        new_region = [new_region[i] for i in np.argsort(angles)]
        new_regions.append(new_region)
    return new_regions, np.asarray(new_vertices)


def _voronoi_clip(points: np.ndarray, boundary) -> List[Optional[object]]:
    """Voronoi cells of ``points`` (Nx2), each clipped to ``boundary``."""
    from scipy.spatial import Voronoi, QhullError

    n = len(points)
    if n == 0:
        return []
    if n < 3:
        return [boundary for _ in range(n)]
    bminx, bminy, bmaxx, bmaxy = boundary.bounds
    radius = max(bmaxx - bminx, bmaxy - bminy) * 3 + 1.0
    try:
        vor = Voronoi(points)
        regions, vertices = _voronoi_finite_polygons_2d(vor, radius)
    except (QhullError, ValueError, IndexError):
        return [boundary for _ in range(n)]
    out: List[Optional[object]] = []
    for i in range(n):
        try:
            poly = Polygon(vertices[regions[i]])
            if not poly.is_valid:
                poly = poly.buffer(0)
            cell = poly.intersection(boundary)
            out.append(None if cell.is_empty or cell.area <= 0 else cell)
        except Exception:
            out.append(None)
    return out


def sho_regions_geojson(stations: List[dict], simplify_tol: float = 0.0015) -> dict:
    """Build SHO jurisdiction polygons from station points.

    ``stations`` is a list of dicts with ``station_id, name, district, lon, lat,
    case_count``. Groups by district, computes the per-district Voronoi clipped
    to the district polygon, and returns a GeoJSON FeatureCollection.
    """
    dpolys = _district_polys()
    by_district: Dict[str, List[dict]] = {}
    for s in stations:
        d = s.get("district")
        if d is None or s.get("lon") is None or s.get("lat") is None:
            continue
        by_district.setdefault(d, []).append(s)

    features: List[dict] = []
    for dname, sts in by_district.items():
        dgeom = dpolys.get(dname)
        if dgeom is None:
            continue
        pts = np.array([[float(s["lon"]), float(s["lat"])] for s in sts], dtype=float)
        cells = _voronoi_clip(pts, dgeom)
        for s, cell in zip(sts, cells):
            if cell is None or cell.is_empty:
                continue
            simple = cell.simplify(simplify_tol, preserve_topology=True)
            simple = simple.intersection(dgeom)  # never bulge past the district
            if simple.is_empty:
                simple = cell
            features.append({
                "type": "Feature",
                "geometry": mapping(simple),
                "properties": {
                    "station_id": s.get("station_id"),
                    "name": s.get("name"),
                    "district": dname,
                    "case_count": s.get("case_count"),
                    "level": "sho",
                },
            })
    return {"type": "FeatureCollection", "features": features}
