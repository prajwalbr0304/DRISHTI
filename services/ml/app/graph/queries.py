"""Postgres-native graph queries (Option A): recursive-CTE N-hop neighbourhood
and shortest-path (pgRouting with a recursive-CTE fallback).

Traversal is treated as UNDIRECTED (edges are expanded both ways) and fan-out is
capped per hop to the top-N neighbours by edge weight — both for performance and
for a legible canvas (doc 04 §8: cap depth + fan-out).
"""
from __future__ import annotations

from typing import Optional

# N-hop reachable nodes via a recursive CTE, fan-out capped by edge weight.
# The bidirectional edge set is a non-recursive CTE (materialized once); the
# recursive term keeps only the top-N heaviest neighbours of each frontier node.
_NEIGHBOURHOOD_NODES = """
WITH RECURSIVE ud (edge_id, a, b, w) AS (
    SELECT "EdgeID", "Source", "Target", COALESCE("Weight", 0)
    FROM "NetworkEdge"
    UNION ALL
    SELECT "EdgeID", "Target", "Source", COALESCE("Weight", 0)
    FROM "NetworkEdge"
),
bfs (node, hop) AS (
    SELECT %(entity_id)s::bigint, 0
    UNION ALL
    SELECT nb.b, bfs.hop + 1
    FROM bfs
    CROSS JOIN LATERAL (
        SELECT ud.b
        FROM ud
        WHERE ud.a = bfs.node
        ORDER BY ud.w DESC
        LIMIT %(top_n)s
    ) AS nb
    WHERE bfs.hop < %(max_hops)s
)
SELECT node AS entity_id, MIN(hop) AS distance
FROM bfs
GROUP BY node
"""


def neighbourhood(conn, entity_id: int, max_hops: int = 2, top_n: int = 15):
    """Return (nodes, edges) for the capped N-hop subgraph around entity_id."""
    max_hops = max(1, min(int(max_hops), 3))          # hard cap: 3 hops
    top_n = max(1, min(int(top_n), 50))               # hard cap: 50 fan-out
    with conn.cursor() as cur:
        cur.execute(_NEIGHBOURHOOD_NODES,
                    {"entity_id": entity_id, "max_hops": max_hops, "top_n": top_n})
        dist = {int(r[0]): int(r[1]) for r in cur.fetchall()}
        if not dist:
            return [], []
        ids = list(dist)
        # node detail
        cur.execute(
            'SELECT "EntityID","EntityType"::text,"Label","RefTable",'
            'COALESCE("Attributes",\'{}\'::jsonb) '
            'FROM "EntityGraph" WHERE "EntityID" = ANY(%s)',
            (ids,),
        )
        nodes = [
            {"entity_id": int(r[0]), "entity_type": r[1], "label": r[2],
             "ref_table": r[3], "distance": dist[int(r[0])], "attributes": r[4]}
            for r in cur.fetchall()
        ]
        # induced edges (both endpoints inside the subgraph)
        cur.execute(
            'SELECT "EdgeID","Source","Target","RelationshipType"::text,'
            'COALESCE("Weight",0)::float,COALESCE("Confidence",0)::float '
            'FROM "NetworkEdge" WHERE "Source" = ANY(%s) AND "Target" = ANY(%s)',
            (ids, ids),
        )
        edges = [
            {"edge_id": int(r[0]), "source": int(r[1]), "target": int(r[2]),
             "relationship_type": r[3], "weight": r[4], "confidence": r[5]}
            for r in cur.fetchall()
        ]
    return nodes, edges


# Shortest path via the pgRouting helper (fn_entity_shortest_path); wraps
# pgr_dijkstra over NetworkEdge(id, source, target, cost, reverse_cost).
_PATH_PGR = "SELECT seq, node, edge, cost, agg_cost FROM fn_entity_shortest_path(%s, %s)"

# CTE fallback (used if pgRouting / the helper is unavailable): bounded BFS that
# records the path array, undirected, with a cycle guard.
_PATH_CTE = """
WITH RECURSIVE ud (a, b, edge_id, w) AS (
    SELECT "Source", "Target", "EdgeID", COALESCE("Weight",0) FROM "NetworkEdge"
    UNION ALL
    SELECT "Target", "Source", "EdgeID", COALESCE("Weight",0) FROM "NetworkEdge"
),
walk (node, path, edges, hop) AS (
    SELECT %(source)s::bigint, ARRAY[%(source)s::bigint], ARRAY[]::bigint[], 0
    UNION ALL
    SELECT ud.b, walk.path || ud.b, walk.edges || ud.edge_id, walk.hop + 1
    FROM walk
    JOIN ud ON ud.a = walk.node
    WHERE walk.hop < %(max_hops)s
      AND NOT ud.b = ANY(walk.path)
      AND walk.node <> %(target)s::bigint
)
SELECT path, edges, hop FROM walk
WHERE node = %(target)s::bigint
ORDER BY hop ASC
LIMIT 1
"""


def pgrouting_available(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='public' AND p.proname='fn_entity_shortest_path'"
        )
        return cur.fetchone() is not None


def shortest_path(conn, source: int, target: int, max_hops: int = 6):
    """Return {'nodes':[...], 'edge_ids':[...], 'method':...} or None if no path."""
    if pgrouting_available(conn):
        with conn.cursor() as cur:
            cur.execute(_PATH_PGR, (source, target))
            rows = cur.fetchall()
        if rows:
            node_seq = [int(r[1]) for r in rows]
            edge_seq = [int(r[2]) for r in rows if r[2] is not None and int(r[2]) != -1]
            return {"nodes": node_seq, "edge_ids": edge_seq, "method": "pgrouting"}
        # pgRouting ran but found no path
        return None
    # fallback
    with conn.cursor() as cur:
        cur.execute(_PATH_CTE, {"source": source, "target": target, "max_hops": max_hops})
        row = cur.fetchone()
    if not row:
        return None
    return {"nodes": [int(x) for x in row[0]], "edge_ids": [int(x) for x in row[1]],
            "method": "recursive_cte"}


def nodes_detail(conn, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EntityID","EntityType"::text,"Label","RefTable" '
            'FROM "EntityGraph" WHERE "EntityID" = ANY(%s)',
            (ids,),
        )
        return [{"entity_id": int(r[0]), "entity_type": r[1], "label": r[2],
                 "ref_table": r[3]} for r in cur.fetchall()]


def edges_detail(conn, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EdgeID","Source","Target","RelationshipType"::text,'
            'COALESCE("Weight",0)::float FROM "NetworkEdge" WHERE "EdgeID" = ANY(%s)',
            (ids,),
        )
        return [{"edge_id": int(r[0]), "source": int(r[1]), "target": int(r[2]),
                 "relationship_type": r[3], "weight": r[4]} for r in cur.fetchall()]
