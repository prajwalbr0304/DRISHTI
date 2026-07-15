"""Hidden-association detector (doc 04 §6) — THE headline capability.

Surfaces pairs of entities that share >= 2 DISTINCT kinds of indirect link
(phone / vehicle / address / bank account) yet NEVER co-appear in a case.

"Co-appear in a case" is modelled by a direct `co_accused` NetworkEdge between
the two persons (the generator's co_accused edges mean 'named together in an
FIR'); such pairs are the obvious ones and are excluded. What remains is the
non-obvious connection an analyst could never find by eye.

`materialize()` (nightly batch) UPSERTs candidates into
`drishti_hidden_associations`; the API pages the ranked feed and draws proof
paths without recomputing.
"""
from __future__ import annotations

from psycopg2.extras import Json, execute_values

from .. import models

INTERMEDIARY_KINDS = ("phone", "vehicle", "location", "bank_account")


def detect_hidden_pairs(links, co_accused=(), min_links: int = 2):
    """Backend-agnostic core of the hidden-association rule (doc 04 §6).

    Encodes the SAME rule as the SQL in `materialize()`, but over in-memory data,
    so it is unit-testable on a fixture graph and reusable if the graph backend
    is later swapped to Apache AGE / Neo4j (feed it rows from any source).

      links       : iterable of (person, intermediary, kind)
      co_accused  : iterable of pairs (a, b) that co-appear in a case (excluded)
      min_links   : minimum DISTINCT intermediary kinds required (default 2)

    Returns pairs (a<b) sharing >= min_links distinct kinds and NOT co-accused,
    ranked by independent link count.
    """
    from collections import defaultdict

    inter_persons: dict = defaultdict(set)
    inter_kind: dict = {}
    for person, inter, kind in links:
        inter_persons[inter].add(person)
        inter_kind[inter] = kind

    excluded = {frozenset(p) for p in co_accused}
    pair_kinds: dict = defaultdict(set)
    pair_inters: dict = defaultdict(set)
    for inter, persons in inter_persons.items():
        ordered = sorted(persons)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                key = (ordered[i], ordered[j])
                pair_kinds[key].add(inter_kind[inter])
                pair_inters[key].add(inter)

    out = []
    for (a, b), kinds in pair_kinds.items():
        if len(kinds) >= min_links and frozenset({a, b}) not in excluded:
            out.append({
                "a": a, "b": b, "independent_links": len(kinds),
                "link_kinds": sorted(kinds),
                "shared_intermediaries": sorted(pair_inters[(a, b)]),
            })
    out.sort(key=lambda r: (-r["independent_links"], r["a"], r["b"]))
    return out

# Candidate pairs: persons sharing >= min_links DISTINCT intermediary kinds,
# excluding any pair that shares a direct co_accused edge (i.e. a common FIR).
_CANDIDATES = """
WITH pe AS (
    SELECT e."Source" AS person, e."Target" AS inter, ig."EntityType"::text AS kind
    FROM "NetworkEdge" e
    JOIN "EntityGraph" ig ON ig."EntityID" = e."Target"
    JOIN "EntityGraph" pg ON pg."EntityID" = e."Source"
    WHERE ig."EntityType"::text = ANY(%(kinds)s)
      AND pg."EntityType"::text = 'person'
),
shared AS (
    SELECT p1.person AS a, p2.person AS b, p1.inter, p1.kind
    FROM pe p1
    JOIN pe p2 ON p1.inter = p2.inter AND p1.person < p2.person
),
agg AS (
    SELECT a, b,
           COUNT(DISTINCT kind)  AS independent_links,
           array_agg(DISTINCT kind ORDER BY kind)   AS link_kinds,
           array_agg(DISTINCT inter)                AS shared_inters,
           COUNT(DISTINCT inter) AS n_intermediaries
    FROM shared
    GROUP BY a, b
    HAVING COUNT(DISTINCT kind) >= %(min_links)s
)
SELECT a, b, independent_links, link_kinds, shared_inters, n_intermediaries
FROM agg
WHERE NOT EXISTS (
    SELECT 1 FROM "NetworkEdge" ce
    WHERE ce."RelationshipType" = 'co_accused'
      AND ((ce."Source" = agg.a AND ce."Target" = agg.b)
        OR (ce."Source" = agg.b AND ce."Target" = agg.a))
)
"""


def materialize(conn, min_links: int = 2, max_rows: int = 20000) -> dict:
    """Recompute drishti_hidden_associations. Returns summary stats."""
    mv_id = models.get_or_create_model_version(
        conn, model_name="drishti-graph-hidden", model_type="graph", version="1.0.0",
        framework="postgres+networkx",
        metrics={"detector": "shared-intermediary >=2 distinct kinds, 0 common FIR"},
    )
    with conn.cursor() as cur:
        cur.execute(_CANDIDATES, {"kinds": list(INTERMEDIARY_KINDS), "min_links": min_links})
        rows = cur.fetchall()

        cur.execute('TRUNCATE "drishti_hidden_associations" RESTART IDENTITY')

        payload = []
        for a, b, links, kinds, inters, n_inter in rows:
            # score: distinct kinds dominate, extra shared intermediaries add a little
            score = round(float(links) + 0.1 * float(n_inter), 5)
            proof = [f"EntityGraph:{i}" for i in inters]
            payload.append((int(a), int(b), int(links), list(kinds),
                            [int(i) for i in inters], proof, score, 0, mv_id))
        # keep the strongest if extremely large
        payload.sort(key=lambda r: (-r[6], -r[2]))
        payload = payload[:max_rows]

        if payload:
            execute_values(
                cur,
                'INSERT INTO "drishti_hidden_associations" '
                '("EntityA","EntityB","IndependentLinks","LinkKinds",'
                '"SharedIntermediaries","ProofRecordIds","Score","SharedCaseCount","ModelVersionID") '
                "VALUES %s",
                payload, page_size=5000,
            )
        # audit
        models.log_inference(
            conn, mv_id,
            inputs={"min_links": min_links, "kinds": list(INTERMEDIARY_KINDS)},
            outputs={"candidates": len(rows), "materialized": len(payload)},
            ref_table="drishti_hidden_associations",
        )
    top = sorted(payload, key=lambda r: (-r[6], -r[2]))[:5]
    return {
        "candidates": len(rows),
        "materialized": len(payload),
        "model_version_id": mv_id,
        "top_examples": [{"a": r[0], "b": r[1], "links": r[2], "kinds": r[3]} for r in top],
    }


def feed(conn, page: int = 1, page_size: int = 20, min_links: int = 2):
    """Return (total, items) of the ranked hidden-association feed with labels."""
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    offset = (page - 1) * page_size
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM "drishti_hidden_associations" WHERE "IndependentLinks" >= %s',
                    (min_links,))
        total = int(cur.fetchone()[0])
        cur.execute(
            'SELECT h."AssociationID", h."EntityA", h."EntityB", ea."Label", eb."Label", '
            '       h."IndependentLinks", h."LinkKinds", h."ProofRecordIds", '
            '       h."SharedIntermediaries", h."SharedCaseCount", h."Score" '
            'FROM "drishti_hidden_associations" h '
            'JOIN "EntityGraph" ea ON ea."EntityID" = h."EntityA" '
            'JOIN "EntityGraph" eb ON eb."EntityID" = h."EntityB" '
            'WHERE h."IndependentLinks" >= %s '
            'ORDER BY h."Score" DESC, h."IndependentLinks" DESC, h."AssociationID" ASC '
            'LIMIT %s OFFSET %s',
            (min_links, page_size, offset),
        )
        items = [
            {"association_id": int(r[0]), "entity_a": int(r[1]), "entity_b": int(r[2]),
             "label_a": r[3], "label_b": r[4], "independent_links": int(r[5]),
             "link_kinds": list(r[6]), "proof_record_ids": list(r[7]),
             "shared_intermediaries": [int(x) for x in r[8]],
             "shared_case_count": int(r[9]), "score": float(r[10])}
            for r in cur.fetchall()
        ]
    return total, items


def proof_path(conn, association_id: int):
    """Return the subgraph (two entities + shared intermediaries + connecting
    edges) that proves a hidden association."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EntityA","EntityB","LinkKinds","SharedIntermediaries" '
            'FROM "drishti_hidden_associations" WHERE "AssociationID"=%s',
            (association_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        a, b, kinds, inters = int(row[0]), int(row[1]), list(row[2]), [int(x) for x in row[3]]
        node_ids = [a, b] + inters
        cur.execute(
            'SELECT "EntityID","EntityType"::text,"Label","RefTable" '
            'FROM "EntityGraph" WHERE "EntityID" = ANY(%s)',
            (node_ids,),
        )
        nodes = [{"entity_id": int(r[0]), "entity_type": r[1], "label": r[2], "ref_table": r[3]}
                 for r in cur.fetchall()]
        cur.execute(
            'SELECT "EdgeID","Source","Target","RelationshipType"::text,COALESCE("Weight",0)::float '
            'FROM "NetworkEdge" '
            'WHERE "Source" = ANY(%s) AND "Target" = ANY(%s)',
            ([a, b], inters),
        )
        edges = [{"edge_id": int(r[0]), "source": int(r[1]), "target": int(r[2]),
                  "relationship_type": r[3], "weight": r[4]} for r in cur.fetchall()]
    return {"entity_a": a, "entity_b": b, "link_kinds": kinds, "nodes": nodes, "edges": edges}
