"""High-level graph operations: assemble typed payloads + the AiResult contract.

Reads run on the restricted read-only connection (db.ro_conn); compute/refresh
jobs run read-write (db.rw_conn). Deterministic graph queries report confidence
1.0 (exact); learned metrics carry their model's version label.
"""
from __future__ import annotations

from .. import db
from ..contracts import AiResult
from . import algorithms, archive, hidden, queries
from .schemas import (ArchiveStatusResponse, ArchiveTableStatus, CentralityResponse,
                      CommunitiesResponse, GraphEdge, GraphNode, HiddenAssociationCard,
                      HiddenFeedResponse, PathResponse, PersonOfInterest, ProofPathResponse,
                      RebuildResponse, ReviewResponse, SubgraphResponse)

GRAPH_MODEL = "drishti-graph@1.0.0"


def _entity_exists(conn, entity_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "EntityGraph" WHERE "EntityID"=%s', (entity_id,))
        return cur.fetchone() is not None


def neighbourhood(entity_id: int, max_hops: int, top_n: int) -> SubgraphResponse:
    with db.ro_conn() as conn:
        exists = _entity_exists(conn, entity_id)
        nodes, edges = ([], []) if not exists else queries.neighbourhood(conn, entity_id, max_hops, top_n)
    capped_hops = max(1, min(int(max_hops), 3))
    capped_top = max(1, min(int(top_n), 50))
    focal = next((n for n in nodes if n["entity_id"] == entity_id), None)
    focal_label = focal["label"] if focal else str(entity_id)
    result = AiResult(
        answer=(f"{len(nodes) - 1} entities are connected to {focal_label} within "
                f"{capped_hops} hop(s)." if exists else f"Entity {entity_id} not found."),
        confidence=1.0 if exists else 0.0,
        source_record_ids=[f"EntityGraph:{entity_id}"] + [f"EntityGraph:{n['entity_id']}" for n in nodes[:50]],
        reasoning_summary=(f"Recursive-CTE BFS, max {capped_hops} hop(s), fan-out "
                           f"capped at top {capped_top} neighbours by edge weight."),
        model_version=GRAPH_MODEL,
    )
    return SubgraphResponse(
        result=result, focal_entity=entity_id, max_hops=capped_hops, top_n=capped_top,
        node_count=len(nodes), edge_count=len(edges),
        nodes=[GraphNode(**n) for n in nodes], edges=[GraphEdge(**e) for e in edges],
    )


def path(source: int, target: int) -> PathResponse:
    with db.ro_conn() as conn:
        p = queries.shortest_path(conn, source, target)
        if p:
            nodes = queries.nodes_detail(conn, p["nodes"])
            edges = queries.edges_detail(conn, p["edge_ids"])
        else:
            nodes, edges = [], []
    found = p is not None
    # order path nodes as returned
    order = {eid: i for i, eid in enumerate(p["nodes"])} if found else {}
    nodes.sort(key=lambda n: order.get(n["entity_id"], 0))
    hops = (len(p["nodes"]) - 1) if found else None
    result = AiResult(
        answer=(f"Shortest path found in {hops} hop(s) between {source} and {target}."
                if found else f"No path found between {source} and {target}."),
        confidence=1.0 if found else 0.0,
        source_record_ids=[f"EntityGraph:{n}" for n in (p["nodes"] if found else [source, target])],
        reasoning_summary=(f"Shortest path via {p['method']}." if found
                           else "Exhausted bounded traversal without reaching target."),
        model_version=GRAPH_MODEL,
    )
    return PathResponse(result=result, found=found, method=(p["method"] if found else None),
                        hops=hops, nodes=[GraphNode(**n) for n in nodes],
                        edges=[GraphEdge(**e) for e in edges])


def run_communities() -> CommunitiesResponse:
    with db.rw_conn() as conn:
        m = algorithms.detect_communities(conn)
    result = AiResult(
        answer=(f"Detected {m['num_communities']} communities; rediscovered "
                f"{m['rediscovered_gangs']}/{m['known_gangs']} known gangs "
                f"(precision {m['precision']:.2f}, recall {m['recall']:.2f}) and "
                f"flagged {m['candidate_new_groups']} candidate new groups."),
        confidence=round(float(m["f1"]), 5),
        source_record_ids=["GangMembership", "EntityGraph", "NetworkEdge"],
        reasoning_summary=("Louvain community detection over EntityGraph+NetworkEdge; "
                           "labels written to EntityGraph.Attributes.community; "
                           "validated by pairwise precision/recall vs GangMembership."),
        model_version=f"drishti-graph-louvain@1.0.0 (id {m['model_version_id']})",
    )
    return CommunitiesResponse(result=result, **{k: m[k] for k in (
        "num_communities", "modularity", "known_gangs", "precision", "recall", "f1",
        "rediscovered_gangs", "candidate_new_groups")})


def centrality(top: int = 20, entity_type: str = "person") -> CentralityResponse:
    top = max(1, min(int(top), 200))
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "EntityID","Label","EntityType"::text,'
                '("Attributes"->>\'pagerank\')::float,'
                '("Attributes"->>\'betweenness\')::float,'
                '("Attributes"->>\'community\')::int '
                'FROM "EntityGraph" '
                'WHERE "Attributes" ? \'pagerank\' AND "EntityType"::text = %s '
                'ORDER BY ("Attributes"->>\'pagerank\')::float DESC NULLS LAST '
                'LIMIT %s',
                (entity_type, top),
            )
            rows = cur.fetchall()
    poi = [PersonOfInterest(entity_id=int(r[0]), label=r[1], entity_type=r[2],
                            pagerank=r[3] or 0.0, betweenness=r[4] or 0.0, community=r[5])
           for r in rows]
    computed = len(poi) > 0
    result = AiResult(
        answer=(f"Top {len(poi)} persons of interest by PageRank." if computed
                else "Centrality not computed yet — run the `centrality` batch job."),
        confidence=1.0 if computed else 0.0,
        source_record_ids=[f"EntityGraph:{p.entity_id}" for p in poi],
        reasoning_summary="Precomputed PageRank (influence) + k-sampled betweenness "
                          "(brokerage) read from EntityGraph.Attributes.",
        model_version="drishti-graph-centrality@1.0.0",
    )
    return CentralityResponse(result=result, computed=computed, persons_of_interest=poi)


def hidden_feed(page: int, page_size: int, min_links: int, refresh: bool = False) -> HiddenFeedResponse:
    if refresh:
        with db.rw_conn() as conn:
            hidden.materialize(conn, min_links=min_links)
    with db.ro_conn() as conn:
        total, items = hidden.feed(conn, page=page, page_size=page_size, min_links=min_links)
    result = AiResult(
        answer=(f"{total} hidden associations (>= {min_links} independent links, "
                f"zero shared FIRs). Showing page {page}."),
        confidence=1.0,
        source_record_ids=[f"drishti_hidden_associations:{it['association_id']}" for it in items],
        reasoning_summary="Entity pairs sharing >=2 distinct indirect link kinds "
                          "(phone/vehicle/address/account) with no common FIR; "
                          "materialized nightly, ranked by strength.",
        model_version="drishti-graph-hidden@1.0.0",
    )
    return HiddenFeedResponse(result=result, total=total, page=page, page_size=page_size,
                              items=[HiddenAssociationCard(**it) for it in items])


def proof_path(association_id: int) -> ProofPathResponse | None:
    with db.ro_conn() as conn:
        p = hidden.proof_path(conn, association_id)
    if not p:
        return None
    result = AiResult(
        answer=(f"Proof path: entities {p['entity_a']} and {p['entity_b']} share "
                f"{len(p['link_kinds'])} independent link kind(s): {', '.join(p['link_kinds'])}."),
        confidence=1.0,
        source_record_ids=([f"EntityGraph:{n['entity_id']}" for n in p["nodes"]]
                           + [f"NetworkEdge:{e['edge_id']}" for e in p["edges"]]),
        reasoning_summary="Subgraph of the two entities and the intermediary nodes "
                          "they both connect to — the evidence for the association.",
        model_version="drishti-graph-hidden@1.0.0",
    )
    return ProofPathResponse(result=result, entity_a=p["entity_a"], entity_b=p["entity_b"],
                             link_kinds=p["link_kinds"],
                             review_status=p.get("review_status", "candidate"),
                             independent_evidence_kinds=p.get("independent_evidence_kinds", []),
                             nodes=[GraphNode(**n) for n in p["nodes"]],
                             edges=[GraphEdge(**e) for e in p["edges"]])


# ===========================================================================
# Phase 11 — canonical-space isolation, rebuild, reviewer disposition
# ===========================================================================
_CANON_MODEL = "drishti-graph-canonical@1.1.0"


def _canonical_counts(conn) -> tuple[int, int, int]:
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "vw_canonical_graph_node"')
        nodes = int(cur.fetchone()[0])
        cur.execute('SELECT count(*) FROM "vw_canonical_graph_edge"')
        edges = int(cur.fetchone()[0])
        cur.execute('SELECT count(*) FROM "vw_canonical_graph_edge" WHERE "ReviewStatus"=\'confirmed\'')
        confirmed = int(cur.fetchone()[0])
    return nodes, edges, confirmed


def archive_status() -> ArchiveStatusResponse:
    st = archive.archive_status()
    tables = {k: ArchiveTableStatus(**v) for k, v in st.items() if k != "clean"}
    clean = bool(st["clean"])
    result = AiResult(
        answer=("Canonical graph space is clean — no legacy rows remain live."
                if clean else "Legacy graph rows are still live; run archive-legacy to isolate them."),
        confidence=1.0,
        source_record_ids=[f"{t}" for t in tables],
        reasoning_summary="Counts of archived vs live rows per derived-intelligence table; "
                          "'legacy_still_live' must be zero (old/new spaces never mix).",
        model_version=_CANON_MODEL)
    return ArchiveStatusResponse(result=result, clean=clean, tables=tables)


def archive_legacy(actor: str = None) -> ArchiveStatusResponse:
    archive.archive_legacy(actor)
    return archive_status()


def rebuild(actor: str = None, run_communities: bool = True, run_centrality: bool = True,
            run_hidden: bool = True) -> RebuildResponse:
    """Idempotently rebuild derived graph analytics from the CANONICAL graph only
    (archives any legacy rows first, so old/new spaces never mix)."""
    arch = archive.archive_legacy(actor)
    communities = modularity = nodes_scored = hidden_candidates = None
    with db.rw_conn() as conn:
        if run_communities:
            c = algorithms.detect_communities(conn)
            communities, modularity = c["num_communities"], c["modularity"]
        if run_centrality:
            cen = algorithms.compute_centrality(conn)
            nodes_scored = cen["nodes_scored"]
        if run_hidden:
            h = hidden.materialize(conn)
            hidden_candidates = h["materialized"]
    with db.ro_conn() as conn:
        nodes, edges, confirmed = _canonical_counts(conn)
    result = AiResult(
        answer=(f"Rebuilt derived graph analytics over {nodes:,} canonical nodes and "
                f"{edges:,} provenanced edges."),
        confidence=1.0, source_record_ids=["vw_canonical_graph_node", "vw_canonical_graph_edge"],
        reasoning_summary="Communities/centrality/hidden-associations recomputed from the canonical, "
                          "non-archived, provenanced graph only. Idempotent.",
        model_version=_CANON_MODEL)
    return RebuildResponse(result=result, canonical_nodes=nodes, canonical_edges=edges,
                           confirmed_edges=confirmed, communities=communities, modularity=modularity,
                           nodes_scored=nodes_scored, hidden_candidates=hidden_candidates,
                           archived=arch["archived"])


def review_edge(edge_id: int, decision: str, actor: str = None, reason: str = None) -> ReviewResponse:
    status = {"confirm": "confirmed", "reject": "rejected", "reset": "candidate"}.get(decision)
    if status is None:
        raise ValueError("decision must be confirm|reject|reset")
    from .. import audit
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE "NetworkEdge" SET "ReviewStatus"=%s, "ReviewedByActor"=%s, '
                        '"ReviewedAt"=now() WHERE "EdgeID"=%s RETURNING "EdgeID"',
                        (status, actor, edge_id))
            found = cur.fetchone() is not None
        if found:
            audit.record(audit.Action.ENTITY_CHANGE, "network_edge_review", edge_id,
                         actor=actor, conn=conn, detail={"decision": decision, "status": status})
    result = AiResult(
        answer=(f"Edge {edge_id} marked {status}." if found else f"Edge {edge_id} not found."),
        confidence=1.0 if found else 0.0, source_record_ids=[f"NetworkEdge:{edge_id}"],
        reasoning_summary="Reviewer disposition on a graph edge (candidate -> confirmed/rejected).",
        model_version=_CANON_MODEL)
    return ReviewResponse(result=result, id=edge_id, kind="network_edge",
                          review_status=status, found=found)


def review_hidden(association_id: int, decision: str, actor: str = None,
                  reason: str = None) -> ReviewResponse:
    with db.rw_conn() as conn:
        r = hidden.review(conn, association_id, decision, actor=actor, reason=reason)
    found = r.get("found", False)
    status = r.get("review_status", "candidate")
    result = AiResult(
        answer=(f"Hidden association {association_id} marked {status}." if found
                else f"Association {association_id} not found."),
        confidence=1.0 if found else 0.0,
        source_record_ids=[f"drishti_hidden_associations:{association_id}"],
        reasoning_summary="Reviewer disposition on a hidden association; a confirmed/rejected "
                          "pair is preserved across re-materialisation.",
        model_version="drishti-graph-hidden@1.0.0")
    return ReviewResponse(result=result, id=association_id, kind="hidden_association",
                          review_status=status, found=found)
