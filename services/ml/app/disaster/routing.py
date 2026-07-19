"""Hazard-aware evacuation routing (Prompt 17 §G.6/G.7/G.9).

Builds a SEPARATE geographic road topology (a deterministic synthetic grid for
the hackathon demo) — NEVER the entity-intelligence NetworkEdge graph. The graph
is versioned and records a synthetic OSM extract date + ODbL attribution. A
hand-rolled Dijkstra finds the shortest path from a risk zone to a shelter while
EXCLUDING road edges that intersect the active hazard/block geometry. When the
hazard disconnects the origin from every shelter, an explicit ``no_route`` result
is returned — a route is never described as guaranteed safe.

Post-hackathon: this is replaced by a versioned OpenStreetMap extract loaded via
osm2pgrouting into the AWS PostGIS mirror and routed with pgRouting through the
protected AWS adapter (see 023_disaster_response.sql: DisasterRoadNode/Edge).
"""
from __future__ import annotations

import hashlib
import heapq
import json
from typing import Any, Optional

from .geometry import haversine_km, segment_intersects_geometry

ROAD_GRAPH_VERSION = "osm-ka-demo-grid@2024.10.01"
ROAD_GRAPH_ATTRIBUTION = "Synthetic grid for demo; production uses OpenStreetMap (ODbL)."
ROAD_GRAPH_EXTRACT_DATE = "2024-10-01"
_DEFAULT_SPEED_KMPH = 30.0


class RoadGraph:
    """A deterministic grid road graph over a bounding box (8-connectivity)."""

    def __init__(self, min_lon: float, min_lat: float, max_lon: float,
                 max_lat: float, n: int = 14):
        self.version = ROAD_GRAPH_VERSION
        self.n = max(4, n)
        self.nodes: dict[int, list[float]] = {}
        self.adj: dict[int, list[tuple[int, float]]] = {}
        self._build(min_lon, min_lat, max_lon, max_lat)

    def _build(self, min_lon, min_lat, max_lon, max_lat) -> None:
        n = self.n
        # pad the box a touch so endpoints near the border still have neighbours
        pad_x = (max_lon - min_lon) * 0.08 or 0.02
        pad_y = (max_lat - min_lat) * 0.08 or 0.02
        min_lon, max_lon = min_lon - pad_x, max_lon + pad_x
        min_lat, max_lat = min_lat - pad_y, max_lat + pad_y
        dx = (max_lon - min_lon) / (n - 1)
        dy = (max_lat - min_lat) / (n - 1)
        for j in range(n):
            for i in range(n):
                nid = j * n + i
                self.nodes[nid] = [round(min_lon + i * dx, 6), round(min_lat + j * dy, 6)]
        neigh = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)]
        for j in range(n):
            for i in range(n):
                nid = j * n + i
                self.adj[nid] = []
                for di, dj in neigh:
                    ni, nj = i + di, j + dj
                    if 0 <= ni < n and 0 <= nj < n:
                        mid = nj * n + ni
                        a, b = self.nodes[nid], self.nodes[mid]
                        cost = haversine_km(a[0], a[1], b[0], b[1])
                        self.adj[nid].append((mid, cost))

    def nearest_node(self, lon: float, lat: float) -> int:
        best, bestd = None, float("inf")
        for nid, (nlon, nlat) in self.nodes.items():
            d = (nlon - lon) ** 2 + (nlat - lat) ** 2
            if d < bestd:
                best, bestd = nid, d
        return best if best is not None else 0


def _exclusion_version(hazard_geom: Optional[dict]) -> str:
    h = hashlib.sha256(json.dumps(hazard_geom or {}, sort_keys=True,
                                  separators=(",", ":")).encode()).hexdigest()[:12]
    return f"exclude:{h}"


def route(from_lon: float, from_lat: float, to_lon: float, to_lat: float, *,
          hazard_geom: Optional[dict] = None, block_geoms: Optional[list[dict]] = None,
          speed_kmph: float = _DEFAULT_SPEED_KMPH,
          graph: Optional[RoadGraph] = None) -> dict:
    """Shortest hazard-avoiding path from (from) to (to).

    Excludes any road edge intersecting ``hazard_geom`` or any of ``block_geoms``.
    Returns a dict with status 'selected' (+ geojson/distance/minutes) or
    'no_route' when the exclusion disconnects origin from destination."""
    excl = [g for g in ([hazard_geom] if hazard_geom else []) + (block_geoms or []) if g]
    if graph is None:
        # The routable extent is the origin->destination corridor (padded). The
        # hazard bbox is intentionally NOT added to the extent: a hazard band
        # wider than the corridor then genuinely disconnects it (an explicit
        # no_route), instead of the grid silently extending past the hazard.
        lons = [from_lon, to_lon]
        lats = [from_lat, to_lat]
        graph = RoadGraph(min(lons), min(lats), max(lons), max(lats))

    src = graph.nearest_node(from_lon, from_lat)
    dst = graph.nearest_node(to_lon, to_lat)

    def _blocked(a: int, b: int) -> bool:
        p1, p2 = graph.nodes[a], graph.nodes[b]
        return any(segment_intersects_geometry(p1, p2, g) for g in excl)

    # Dijkstra over non-excluded edges
    dist = {src: 0.0}
    prev: dict[int, int] = {}
    pq: list[tuple[float, int]] = [(0.0, src)]
    visited: set[int] = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == dst:
            break
        for v, w in graph.adj.get(u, []):
            if v in visited or _blocked(u, v):
                continue
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    excl_version = _exclusion_version(hazard_geom if hazard_geom else (excl[0] if excl else None))
    if dst not in dist:
        return {"status": "no_route", "road_graph_version": graph.version,
                "hazard_exclusion_version": excl_version,
                "notes": ("No safe route: the active hazard/block geometry "
                          "disconnects the zone from the shelter on the current "
                          "road graph. Escalated to a human — not declared safe.")}

    # reconstruct path
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    path.reverse()
    coords = [graph.nodes[n] for n in path]
    # prepend/append the exact endpoints for a clean line
    coords = [[round(from_lon, 6), round(from_lat, 6)]] + coords + [[round(to_lon, 6), round(to_lat, 6)]]
    distance_km = round(dist[dst]
                        + haversine_km(from_lon, from_lat, *graph.nodes[src])
                        + haversine_km(to_lon, to_lat, *graph.nodes[dst]), 3)
    est_minutes = round(distance_km / max(1.0, speed_kmph) * 60.0, 1)
    return {"status": "selected",
            "geojson": {"type": "LineString", "coordinates": coords},
            "distance_km": distance_km, "est_minutes": est_minutes,
            "road_graph_version": graph.version,
            "hazard_exclusion_version": excl_version,
            "notes": ("Shortest path avoiding the active hazard geometry on a "
                      "versioned road graph. Not a guaranteed-safe route.")}
