"""Search Around / subgraph import (Prompt 16 §F).

Reuses the COMPLETED canonical graph service (app.graph.queries) through the
read-only connection — the same expand-on-demand, capped-fan-out, no-hairball
rule as Network Analysis. It never reintroduces name matching: expansion is over
the id-keyed EntityGraph/NetworkEdge canonical graph only.

This module is a PURE READ (query + rank + cache). The board write (importing
verified relationships as read-only evidence nodes/edges with provenance) lives
in service.import behind the standard mutation path.

Caps: 1 hop default, 3 hops max, a required max_neighbors fan-out cap. Safe
query results are cached in Catalyst Cache keyed by the graph model/version so a
graph rebuild invalidates them.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from .. import db
from ..cache import SEG_LOOKUP
from ..graph import queries
from ..graph.service import GRAPH_MODEL
from .repo import board_cache

MAX_HOPS = 3
MAX_NEIGHBORS = 50


def _cache_key(entity_id: int, hops: int, max_neighbors: int,
               types: Optional[tuple[str, ...]]) -> str:
    t = ",".join(sorted(types)) if types else "*"
    # GRAPH_MODEL is bumped when the graph is rebuilt -> natural invalidation.
    return f"board:sa:{GRAPH_MODEL}:{entity_id}:{hops}:{max_neighbors}:{t}"


def _within_window(attrs: dict, time_from: Optional[str], time_to: Optional[str]) -> bool:
    if not (time_from or time_to):
        return True
    # best-effort: entities carry a last-seen/observed date in Attributes when known
    ts = None
    for k in ("last_seen", "observed_at", "date", "created_at"):
        if attrs.get(k):
            ts = str(attrs[k])
            break
    if ts is None:
        return True                      # no temporal info -> never hide it
    if time_from and ts < time_from:
        return False
    if time_to and ts > time_to:
        return False
    return True


def expand(entity_id: int, hops: int, max_neighbors: int, *,
           types: Optional[list[str]] = None, time_from: Optional[str] = None,
           time_to: Optional[str] = None) -> dict[str, Any]:
    """Capped N-hop expansion around a canonical graph entity. Pure read."""
    hops = max(1, min(int(hops), MAX_HOPS))
    max_neighbors = max(1, min(int(max_neighbors), MAX_NEIGHBORS))
    type_filter = tuple(sorted(types)) if types else None

    cache = board_cache()
    ckey = _cache_key(entity_id, hops, max_neighbors, type_filter)
    if not (time_from or time_to):
        try:
            hit = cache.get(SEG_LOOKUP, ckey)
        except Exception:  # noqa: BLE001
            hit = None
        if hit:
            data = json.loads(hit)
            data["cached"] = True
            return data

    t0 = time.time()
    with db.ro_conn() as conn:
        exists = _entity_exists(conn, entity_id)
        nodes, edges = ([], [])
        if exists:
            nodes, edges = queries.neighbourhood(conn, entity_id, hops, max_neighbors)
    latency_ms = int((time.time() - t0) * 1000)

    neighbors = []
    for n in nodes:
        if int(n["entity_id"]) == int(entity_id):
            continue
        if type_filter and (n.get("entity_type") not in type_filter):
            continue
        if not _within_window(n.get("attributes") or {}, time_from, time_to):
            continue
        neighbors.append({
            "entity_id": int(n["entity_id"]), "label": n.get("label"),
            "entity_type": n.get("entity_type"), "distance": n.get("distance"),
            "relationship_type": None, "weight": 0.0,
            # curated EntityGraph/NetworkEdge projections are reviewed/provenanced
            # (candidate edges stay in AWS) -> treat as verified evidence.
            "verified": True,
        })
    # attach the heaviest incident relationship type/weight to each neighbor
    by_node: dict[int, tuple[str, float]] = {}
    for e in edges:
        for endpoint in (int(e["source"]), int(e["target"])):
            w = float(e.get("weight") or 0.0)
            cur = by_node.get(endpoint)
            if cur is None or w > cur[1]:
                by_node[endpoint] = (e.get("relationship_type"), w)
    for nb in neighbors:
        rt = by_node.get(nb["entity_id"])
        if rt:
            nb["relationship_type"], nb["weight"] = rt[0], rt[1]
    neighbors.sort(key=lambda x: x["weight"], reverse=True)

    focal_label = next((n.get("label") for n in nodes
                        if int(n["entity_id"]) == int(entity_id)), str(entity_id))
    result = {
        "focal_entity": entity_id, "focal_label": focal_label, "hops": hops,
        "max_neighbors": max_neighbors, "node_count": len(nodes),
        "edge_count": len(edges), "neighbors": neighbors, "edges": edges,
        "latency_ms": latency_ms, "cached": False, "exists": exists,
        "answer": (f"{len(neighbors)} verified neighbour(s) within {hops} hop(s) of "
                   f"{focal_label}." if exists else f"Entity {entity_id} not found."),
        "reasoning": (f"Capped recursive-CTE BFS over the canonical id-keyed graph, "
                      f"fan-out top {max_neighbors} by edge weight; no name matching."),
        "model": GRAPH_MODEL,
    }
    if not (time_from or time_to):
        try:
            cache.put(SEG_LOOKUP, ckey, json.dumps(result))
        except Exception:  # noqa: BLE001
            pass
    return result


def _entity_exists(conn, entity_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "EntityGraph" WHERE "EntityID"=%s', (entity_id,))
        return cur.fetchone() is not None


def benchmark_two_hop(entity_id: int, max_neighbors: int = 15) -> dict[str, Any]:
    """Two-hop capped expansion benchmark (Prompt 16 §F.7). Records the measured
    node/edge counts + latency; the environment is documented in the report."""
    t0 = time.time()
    res = expand(entity_id, hops=2, max_neighbors=max_neighbors)
    return {
        "entity_id": entity_id, "hops": 2, "max_neighbors": max_neighbors,
        "node_count": res["node_count"], "edge_count": res["edge_count"],
        "latency_ms": int((time.time() - t0) * 1000),
        "graph_latency_ms": res["latency_ms"], "cached": res["cached"],
        "target_ms": 2000, "model": res["model"],
    }
