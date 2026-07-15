"""Neighbourhood (capped recursive CTE) + shortest-path integration tests."""
import pytest

from conftest import requires_db


def _a_gang_member(conn) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "MemberEntityID" FROM "GangMembership" '
                    'WHERE "MemberEntityID" IS NOT NULL LIMIT 1')
        return int(cur.fetchone()[0])


@requires_db
def test_neighbourhood_respects_hop_cap():
    from app import db
    from app.graph import queries
    with db.ro_conn() as conn:
        focal = _a_gang_member(conn)
        # request 5 hops -> must be clamped to 3
        nodes, edges = queries.neighbourhood(conn, focal, max_hops=5, top_n=10)
    assert nodes, "expected a non-empty neighbourhood"
    assert max(n["distance"] for n in nodes) <= 3
    assert any(n["entity_id"] == focal and n["distance"] == 0 for n in nodes)
    # induced edges only reference nodes in the subgraph
    ids = {n["entity_id"] for n in nodes}
    for e in edges:
        assert e["source"] in ids and e["target"] in ids


@requires_db
def test_neighbourhood_fanout_cap_limits_hop1():
    from app import db
    from app.graph import queries
    with db.ro_conn() as conn:
        focal = _a_gang_member(conn)
        nodes, _ = queries.neighbourhood(conn, focal, max_hops=1, top_n=3)
    hop1 = [n for n in nodes if n["distance"] == 1]
    assert len(hop1) <= 3  # fan-out capped at top_n


@requires_db
def test_shortest_path_between_connected_entities():
    from app import db
    from app.graph import queries
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "GangEntityID", array_agg("MemberEntityID") '
                        'FROM "GangMembership" WHERE "MemberEntityID" IS NOT NULL '
                        'GROUP BY "GangEntityID" HAVING COUNT(*) >= 2 LIMIT 1')
            _, members = cur.fetchone()
        src, tgt = int(members[0]), int(members[1])
        path = queries.shortest_path(conn, src, tgt)
    assert path is not None
    assert path["nodes"][0] == src and path["nodes"][-1] == tgt
    assert path["method"] in ("pgrouting", "recursive_cte")
