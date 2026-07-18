"""networkx graph algorithms run in a Python batch job that reads
EntityGraph+NetworkEdge and writes results back into EntityGraph.Properties
(Postgres stays the source of truth; the API reads, never recomputes).

  * detect_communities — Louvain; writes 'community' label; cross-checks against
    GangMembership ground truth and reports pairwise precision/recall/F1.
  * compute_centrality — PageRank (exact) + betweenness (k-sampled approximation
    on large graphs); writes 'pagerank'/'betweenness' onto each node.
"""
from __future__ import annotations

import json
from itertools import combinations

import networkx as nx
from psycopg2.extras import execute_values

from .. import models


def _load_graph(conn, confirmed_only: bool = False) -> nx.Graph:
    """Load the CANONICAL, non-archived graph only (Phase 11): nodes must be
    canonical entities and edges must be provenanced — the old synthetic identity
    graph (archived / non-canonical / NULL-provenance) is never mixed in.
    ``confirmed_only`` further restricts to reviewer-confirmed edges."""
    g = nx.Graph()
    with conn.cursor() as cur:
        # canonical, non-archived nodes (the vw_canonical_graph_node contract)
        cur.execute('SELECT "EntityID","EntityType"::text FROM "EntityGraph" '
                    'WHERE "CanonicalEntityID" IS NOT NULL AND "IsArchived" = FALSE')
        for eid, etype in cur.fetchall():
            g.add_node(int(eid), etype=etype)
        # provenanced, non-archived edges between those nodes
        edge_sql = ('SELECT "Source","Target",COALESCE("Weight",0.1)::float FROM "NetworkEdge" '
                    'WHERE "IsArchived" = FALSE AND "ProvenanceStatus" IS NOT NULL')
        if confirmed_only:
            edge_sql += " AND \"ReviewStatus\" = 'confirmed'"
        cur.execute(edge_sql)
        for s, t, w in cur.fetchall():
            s, t = int(s), int(t)
            if s == t or not (g.has_node(s) and g.has_node(t)):
                continue  # skip self-loops + edges to any non-canonical/archived node
            # collapse multi-edges, keep the strongest weight
            if g.has_edge(s, t):
                if w > g[s][t]["weight"]:
                    g[s][t]["weight"] = w
            else:
                g.add_edge(s, t, weight=max(w, 0.01))
    return g


def _gang_ground_truth(conn) -> dict[int, int]:
    """Return {member_entity_id: gang_entity_id} from GangMembership."""
    with conn.cursor() as cur:
        cur.execute('SELECT "MemberEntityID","GangEntityID" FROM "GangMembership" '
                    'WHERE "MemberEntityID" IS NOT NULL')
        return {int(m): int(g) for m, g in cur.fetchall()}


def _write_node_props(conn, mapping: dict[int, dict]) -> None:
    """Merge {entity_id: {key: value}} into EntityGraph.Properties (jsonb ||)."""
    rows = [(eid, json.dumps(props)) for eid, props in mapping.items()]
    with conn.cursor() as cur:
        execute_values(
            cur,
            'UPDATE "EntityGraph" AS e SET "Attributes" = e."Attributes" || v.data '
            'FROM (VALUES %s) AS v(id, data) WHERE e."EntityID" = v.id',
            rows, template="(%s, %s::jsonb)", page_size=5000,
        )


def detect_communities(conn, resolution: float = 1.0, seed: int = 42) -> dict:
    g = _load_graph(conn)
    communities = nx.community.louvain_communities(g, weight="weight",
                                                    resolution=resolution, seed=seed)
    node_comm: dict[int, int] = {}
    for cid, members in enumerate(communities):
        for n in members:
            node_comm[n] = cid
    modularity = nx.community.modularity(g, communities, weight="weight")

    _write_node_props(conn, {n: {"community": cid} for n, cid in node_comm.items()})

    # ---- validate against known gangs (pairwise precision/recall) ----
    truth = _gang_ground_truth(conn)  # member -> gang
    gang_members = [m for m in truth if m in node_comm]
    tp = fp = fn = 0
    for x, y in combinations(gang_members, 2):
        same_gang = truth[x] == truth[y]
        same_comm = node_comm[x] == node_comm[y]
        if same_gang and same_comm:
            tp += 1
        elif same_comm and not same_gang:
            fp += 1
        elif same_gang and not same_comm:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # how many known gangs were "rediscovered" (majority of members co-located)
    from collections import Counter, defaultdict
    gang_to_comms = defaultdict(list)
    for m in gang_members:
        gang_to_comms[truth[m]].append(node_comm[m])
    rediscovered = 0
    for gid, comms in gang_to_comms.items():
        top_cid, cnt = Counter(comms).most_common(1)[0]
        if cnt / len(comms) >= 0.5:
            rediscovered += 1

    # candidate NEW groups: sizable communities dominated by non-gang persons
    comm_sizes = Counter(node_comm.values())
    known_comm = {node_comm[m] for m in gang_members}
    candidate_new = sum(1 for cid, sz in comm_sizes.items()
                        if sz >= 5 and cid not in known_comm)

    mv_id = models.get_or_create_model_version(
        conn, "drishti-graph-louvain", "graph", "1.0.0", framework="networkx",
        metrics={"precision": round(precision, 4), "recall": round(recall, 4),
                 "f1": round(f1, 4), "modularity": round(modularity, 4)})
    models.log_inference(
        conn, mv_id,
        inputs={"resolution": resolution, "nodes": g.number_of_nodes(),
                "edges": g.number_of_edges()},
        outputs={"num_communities": len(communities), "precision": precision,
                 "recall": recall, "f1": f1, "rediscovered_gangs": rediscovered},
        ref_table="EntityGraph")

    return {
        "num_communities": len(communities),
        "modularity": round(modularity, 4),
        "known_gangs": len(gang_to_comms),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "rediscovered_gangs": rediscovered,
        "candidate_new_groups": candidate_new,
        "model_version_id": mv_id,
    }


def compute_centrality(conn, betweenness_k: int = 400, seed: int = 42) -> dict:
    g = _load_graph(conn)
    pagerank = nx.pagerank(g, weight="weight")
    k = min(betweenness_k, g.number_of_nodes())
    # k-sampled approximation keeps betweenness tractable on large graphs
    betweenness = nx.betweenness_centrality(g, k=k, weight="weight", seed=seed, normalized=True)

    props = {}
    for n in g.nodes():
        props[n] = {"pagerank": round(float(pagerank.get(n, 0.0)), 8),
                    "betweenness": round(float(betweenness.get(n, 0.0)), 8)}
    _write_node_props(conn, props)

    mv_id = models.get_or_create_model_version(
        conn, "drishti-graph-centrality", "graph", "1.0.0", framework="networkx",
        metrics={"betweenness_k": k})
    models.log_inference(
        conn, mv_id,
        inputs={"betweenness_k": k, "nodes": g.number_of_nodes(), "edges": g.number_of_edges()},
        outputs={"computed_pagerank": True, "computed_betweenness": True},
        ref_table="EntityGraph")

    top = sorted(pagerank.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {"nodes_scored": g.number_of_nodes(), "betweenness_k": k,
            "model_version_id": mv_id,
            "top_pagerank": [{"entity_id": int(n), "pagerank": round(v, 6)} for n, v in top]}
