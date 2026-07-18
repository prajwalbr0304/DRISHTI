"""Real Karnataka geography for the data generator.

Loads the vendored, simplified boundary polygons (``datagen/geo/*.geojson`` —
see ``datagen/geo/SOURCES.md``) and exposes the operations the generator needs
to place every synthetic coordinate on the real Karnataka landmass:

    state  ->  district  ->  taluk  ->  SHO region (police-station jurisdiction)

Nothing here touches the database. Heavy objects (prepared geometries) are built
lazily and cached; the loaded ``Boundaries`` is a process-global singleton so it
is built once per process (including each multiprocessing worker).

Key operations
--------------
* :meth:`Boundaries.district` / :meth:`Boundaries.taluks` — polygon lookup.
* :meth:`Boundaries.district_of` / :meth:`Boundaries.taluk_of` — reverse lookup.
* :func:`uniform_points` — uniform rejection sampling inside a polygon.
* :func:`sample_near` — clustered draw around a seed, rejected outside a polygon
  (this is what replaces the old unbounded Gaussian jitter).
* :func:`sho_regions` — Voronoi tessellation of station seeds, each cell clipped
  to the district so the SHO regions tile the district exactly.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon, shape
from shapely.prepared import PreparedGeometry, prep

GEO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo")

# Coordinate rounding for stored rings (~1.1 m). Keeps the Context small.
_RING_DP = 5


# ---------------------------------------------------------------------------
# Region: a named polygon with a cached bbox + prepared geometry for fast tests
# ---------------------------------------------------------------------------
@dataclass
class Region:
    name: str
    geom: object                      # shapely (Multi)Polygon
    level: str = "region"
    meta: dict = field(default_factory=dict)
    _prep: Optional[PreparedGeometry] = field(default=None, repr=False, compare=False)
    _bounds: Optional[Tuple[float, float, float, float]] = field(default=None, repr=False, compare=False)

    @property
    def prepared(self) -> PreparedGeometry:
        if self._prep is None:
            self._prep = prep(self.geom)
        return self._prep

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        if self._bounds is None:
            self._bounds = tuple(self.geom.bounds)  # (minx, miny, maxx, maxy)
        return self._bounds

    @property
    def area(self) -> float:
        return float(self.geom.area)

    def contains(self, lon: float, lat: float) -> bool:
        minx, miny, maxx, maxy = self.bounds
        if lon < minx or lon > maxx or lat < miny or lat > maxy:
            return False
        return self.prepared.contains(Point(lon, lat))

    def representative(self) -> Tuple[float, float]:
        p = self.geom.representative_point()
        return float(p.x), float(p.y)


# ---------------------------------------------------------------------------
# Sampling helpers (operate on a shapely geometry + its bbox)
# ---------------------------------------------------------------------------
def uniform_points(geom, bounds, gen: np.random.Generator, n: int = 1) -> np.ndarray:
    """``n`` points drawn uniformly at random from inside ``geom`` (lon, lat).

    Batched rejection sampling against the bbox using shapely's vectorised
    ``contains_xy``. Returns an ``(n, 2)`` float array.
    """
    minx, miny, maxx, maxy = bounds
    out = np.empty((n, 2), dtype=float)
    filled = 0
    # Acceptance ratio ~ area/bbox_area; oversample generously to converge fast.
    while filled < n:
        k = max(8, int((n - filled) * 2.2))
        xs = gen.uniform(minx, maxx, k)
        ys = gen.uniform(miny, maxy, k)
        mask = shapely.contains_xy(geom, xs, ys)
        if mask.any():
            good_x = xs[mask]
            good_y = ys[mask]
            take = min(good_x.size, n - filled)
            out[filled:filled + take, 0] = good_x[:take]
            out[filled:filled + take, 1] = good_y[:take]
            filled += take
    return out


def sample_near(region: Region, cx: float, cy: float, sigma: float,
                gen: np.random.Generator, tries: int = 24) -> Tuple[float, float]:
    """A point clustered around ``(cx, cy)`` but guaranteed inside ``region``.

    Draws an isotropic Gaussian around the seed and rejects anything outside the
    polygon (this is the bounded replacement for the old jitter that leaked into
    the sea / neighbouring states). Falls back to a uniform in-polygon draw, then
    to the seed itself.
    """
    minx, miny, maxx, maxy = region.bounds
    prepared = region.prepared
    for _ in range(tries):
        x = cx + gen.normal(0.0, sigma)
        y = cy + gen.normal(0.0, sigma)
        if minx <= x <= maxx and miny <= y <= maxy and prepared.contains(Point(x, y)):
            return float(x), float(y)
    # fallback 1: uniform inside the polygon
    try:
        p = uniform_points(region.geom, region.bounds, gen, 1)[0]
        return float(p[0]), float(p[1])
    except Exception:
        pass
    # fallback 2: the seed (already inside by construction)
    return float(cx), float(cy)


def sigma_for_area(area_deg2: float, lo: float = 0.004, hi: float = 0.045,
                   frac: float = 0.4) -> float:
    """A sensible clustering sigma (degrees) for a cell of the given area."""
    r = math.sqrt(max(area_deg2, 1e-9) / math.pi)  # equivalent radius
    return float(min(hi, max(lo, frac * r)))


# ---------------------------------------------------------------------------
# Ring (de)serialisation so SHO polygons can travel in the pickled Context
# ---------------------------------------------------------------------------
def ring_of(geom, simplify_tol: float = 0.001) -> List[List[float]]:
    """Exterior ring (lon,lat pairs) of the largest polygon in ``geom``.

    The simplified ring is clipped back inside the original geometry so it can
    never bulge past the source cell (which matters where an SHO cell touches
    the coast / state border — no incident should end up a few metres offshore).
    """
    if geom.is_empty:
        return []
    if isinstance(geom, MultiPolygon):
        geom = max(geom.geoms, key=lambda g: g.area)
    simp = geom.simplify(simplify_tol, preserve_topology=True)
    simp = simp.intersection(geom)  # never expand beyond the source cell
    if isinstance(simp, MultiPolygon):
        simp = max(simp.geoms, key=lambda g: g.area)
    if simp.is_empty or not hasattr(simp, "exterior"):
        simp = geom
    return [[round(x, _RING_DP), round(y, _RING_DP)] for x, y in simp.exterior.coords]


def region_from_ring(name: str, ring: Sequence[Sequence[float]], level: str = "sho") -> Region:
    """Rebuild a :class:`Region` from a stored exterior ring (worker side)."""
    poly = Polygon(ring)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return Region(name=name, geom=poly, level=level)


# ---------------------------------------------------------------------------
# Voronoi-based SHO (police-station jurisdiction) regions
# ---------------------------------------------------------------------------
def _voronoi_finite_polygons_2d(vor, radius: float):
    """Reconstruct finite Voronoi regions in 2D (infinite ridges projected out).

    Standard construction: every unbounded ridge is closed off by projecting to a
    far point at ``radius`` from the centroid. Returns (regions, vertices) where
    ``regions[i]`` is the vertex-index polygon for input point ``i``.
    """
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
                continue  # finite ridge
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


def sho_regions(seeds: np.ndarray, boundary) -> List[object]:
    """Voronoi cells of ``seeds`` (Nx2 lon/lat), each clipped to ``boundary``.

    The cells tile ``boundary`` exactly, giving each station a jurisdiction
    polygon. Degenerate inputs (fewer than 3 seeds, or SciPy/Qhull failure) fall
    back to assigning the whole boundary to each seed.
    """
    from scipy.spatial import Voronoi, QhullError

    seeds = np.asarray(seeds, dtype=float)
    n = len(seeds)
    if n == 0:
        return []
    if n < 3:
        return [boundary for _ in range(n)]

    bminx, bminy, bmaxx, bmaxy = boundary.bounds
    radius = max(bmaxx - bminx, bmaxy - bminy) * 3 + 1.0
    try:
        vor = Voronoi(seeds)
        regions, vertices = _voronoi_finite_polygons_2d(vor, radius)
    except (QhullError, ValueError, IndexError):
        return [boundary for _ in range(n)]

    out: List[object] = []
    for i in range(n):
        try:
            poly = Polygon(vertices[regions[i]])
            if not poly.is_valid:
                poly = poly.buffer(0)
            cell = poly.intersection(boundary)
            if cell.is_empty or cell.area <= 0:
                cell = boundary
        except Exception:
            cell = boundary
        out.append(cell)
    return out


def plan_stations(district_region: "Region", taluks: List["Region"], count: int,
                  gen: np.random.Generator) -> List[Tuple[float, float, str, List[List[float]]]]:
    """Place ``count`` stations for one district on the real map.

    Seeds a taluk per station (area-weighted, so larger taluks host more
    stations), samples a station point inside it, then derives the SHO
    jurisdictions as the Voronoi tessellation of those seeds clipped to the
    district. Returns ``[(lon, lat, taluk_name, sho_ring), ...]`` where each
    ``sho_ring`` is the exterior ring of that station's jurisdiction.
    """
    if count <= 0 or not taluks:
        return []
    dgeom = district_region.geom
    # Clip each taluk to the district: taluk and district polygons are simplified
    # independently, so a taluk edge can overhang the district border by ~100 m.
    # Seeding inside the intersection keeps every station strictly in-district.
    clipped: List[Tuple[str, object, tuple]] = []
    for t in taluks:
        try:
            c = t.geom.intersection(dgeom)
            if c.is_empty or c.area <= 0:
                c = t.geom
        except Exception:
            c = t.geom
        clipped.append((t.name, c, tuple(c.bounds)))

    areas = np.array([c.area for _, c, _ in clipped], dtype=float)
    prob = areas / areas.sum()
    pick = gen.choice(len(clipped), size=count, p=prob)
    seeds = np.empty((count, 2), dtype=float)
    tnames: List[str] = []
    for k in range(count):
        name, cgeom, cbounds = clipped[int(pick[k])]
        seeds[k] = uniform_points(cgeom, cbounds, gen, 1)[0]
        tnames.append(name)
    cells = sho_regions(seeds, dgeom)
    out: List[Tuple[float, float, str, List[List[float]]]] = []
    for k in range(count):
        cell = cells[k] if k < len(cells) else district_region.geom
        ring = ring_of(cell) or ring_of(district_region.geom)
        out.append((float(seeds[k, 0]), float(seeds[k, 1]), tnames[k], ring))
    return out


# ---------------------------------------------------------------------------
# Boundaries: the loaded state / districts / taluks
# ---------------------------------------------------------------------------
class Boundaries:
    def __init__(self, state: Region, districts: Dict[str, Region],
                 taluks: Dict[str, List[Region]]):
        self.state = state
        self._districts = districts
        self._taluks = taluks

    # -- lookups ------------------------------------------------------------
    @property
    def district_names(self) -> List[str]:
        return list(self._districts.keys())

    def district(self, name: str) -> Optional[Region]:
        return self._districts.get(name)

    def taluks(self, district_name: str) -> List[Region]:
        """Taluks of a district. BBMP-style districts with no sub-taluks fall
        back to a single taluk equal to the district itself."""
        ts = self._taluks.get(district_name)
        if ts:
            return ts
        d = self._districts.get(district_name)
        return [Region(name=district_name, geom=d.geom, level="taluk")] if d else []

    def district_of(self, lon: float, lat: float) -> Optional[str]:
        for name, region in self._districts.items():
            if region.contains(lon, lat):
                return name
        return None

    def taluk_of(self, lon: float, lat: float,
                 district_name: Optional[str] = None) -> Optional[str]:
        candidates = ([district_name] if district_name else self._districts.keys())
        for dn in candidates:
            for t in self.taluks(dn):
                if t.contains(lon, lat):
                    return t.name
        return None

    def in_state(self, lon: float, lat: float) -> bool:
        return self.state.contains(lon, lat)


# ---------------------------------------------------------------------------
# Loading (cached process-global singleton)
# ---------------------------------------------------------------------------
_CACHE: Optional[Boundaries] = None


def _load_fc(filename: str) -> list:
    path = os.path.join(GEO_DIR, filename)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["features"]


def load_boundaries() -> Boundaries:
    """Load and cache the vendored Karnataka boundaries for this process."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    state_feats = _load_fc("karnataka_state.geojson")
    state_geom = shape(state_feats[0]["geometry"])
    state = Region(name="Karnataka", geom=state_geom, level="state")

    districts: Dict[str, Region] = {}
    for f in _load_fc("karnataka_districts.geojson"):
        props = f["properties"]
        districts[props["district"]] = Region(
            name=props["district"], geom=shape(f["geometry"]), level="district",
            meta={"region_id": props.get("region_id"), "kgis_name": props.get("kgis_name")},
        )

    taluks: Dict[str, List[Region]] = {}
    for f in _load_fc("karnataka_taluks.geojson"):
        props = f["properties"]
        taluks.setdefault(props["district"], []).append(Region(
            name=props["taluk"], geom=shape(f["geometry"]), level="taluk",
            meta={"region_id": props.get("region_id"), "district": props["district"]},
        ))

    _CACHE = Boundaries(state, districts, taluks)
    return _CACHE
