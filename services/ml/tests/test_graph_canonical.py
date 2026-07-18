"""Phase 11 — canonical-graph rebuild, demo-context retrieval, archival isolation.

Real SQL under ``rw_rollback`` (discarded), via internal ``_fn(conn, ...)``. No
secrets printed. Covers the prompt's checklist: case/unit-context-filtered
retrieval, same-model embedding search, no name-based links, edge provenance,
graph-rebuild idempotency, hidden-association proof path (independent evidence +
reviewer state), and archive isolation.
"""
import pytest

from app.cases import corpus, similar
from app.graph import algorithms, archive, hidden
from conftest import requires_db


# ---------------------------------------------------------------------------
# archival isolation (old/new graph spaces never mix)
# ---------------------------------------------------------------------------
@requires_db
def test_archive_isolates_legacy_rows(rw_rollback):
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "EntityGraph" ("EntityType","Label","RefTable","CanonicalEntityID") '
                    "VALUES ('person','LEGACY','Accused',NULL) RETURNING \"EntityID\"")
        legacy_node = int(cur.fetchone()[0])
        cur.execute('SELECT "EntityID" FROM "EntityGraph" WHERE "CanonicalEntityID" IS NOT NULL '
                    'AND "IsArchived"=FALSE LIMIT 2')
        a, b = [int(r[0]) for r in cur.fetchall()]
        cur.execute('INSERT INTO "NetworkEdge" ("Source","Target","RelationshipType","ProvenanceStatus") '
                    "VALUES (%s,%s,'associate',NULL)", (a, b))

    st_before = archive._archive_status(conn)
    assert st_before["EntityGraph"]["legacy_still_live"] >= 1
    assert st_before["clean"] is False

    res = archive._archive_legacy(conn, actor="tester")
    assert res["archived"]["EntityGraph"] >= 1
    assert res["archived"]["NetworkEdge"] >= 1

    st_after = archive._archive_status(conn)
    assert st_after["clean"] is True
    assert st_after["EntityGraph"]["legacy_still_live"] == 0
    # the archived legacy node is flagged, not deleted
    with conn.cursor() as cur:
        cur.execute('SELECT "IsArchived","ArchiveReason" FROM "EntityGraph" WHERE "EntityID"=%s',
                    (legacy_node,))
        arch, reason = cur.fetchone()
    assert arch is True and reason == "legacy_non_canonical_node"


@requires_db
def test_archive_is_idempotent(rw_rollback):
    conn = rw_rollback
    first = archive._archive_legacy(conn, actor="t")
    second = archive._archive_legacy(conn, actor="t")
    # a clean DB archives nothing; a second pass never re-touches archived rows
    assert second["total_archived"] == 0


# ---------------------------------------------------------------------------
# canonical-only graph load + no name-based links
# ---------------------------------------------------------------------------
@requires_db
def test_load_graph_excludes_legacy_and_archived(rw_rollback):
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute('INSERT INTO "EntityGraph" ("EntityType","Label","RefTable","CanonicalEntityID") '
                    "VALUES ('person','LEGACY-NONCANON','Accused',NULL) RETURNING \"EntityID\"")
        non_canon = int(cur.fetchone()[0])
    g = algorithms._load_graph(conn)
    assert non_canon not in g.nodes           # non-canonical node never loaded
    assert g.number_of_nodes() > 0


@requires_db
def test_canonical_edges_have_no_name_matched_endpoints(rw_rollback):
    """Every edge in the canonical view connects canonical entities (true FK),
    never a name-matched node."""
    with rw_rollback.cursor() as cur:
        cur.execute('SELECT count(*) FROM "vw_canonical_graph_edge" e '
                    'JOIN "EntityGraph" s ON s."EntityID"=e."Source" '
                    'JOIN "EntityGraph" t ON t."EntityID"=e."Target" '
                    'WHERE s."CanonicalEntityID" IS NULL OR t."CanonicalEntityID" IS NULL')
        assert int(cur.fetchone()[0]) == 0


@requires_db
def test_canonical_edges_are_provenanced(rw_rollback):
    with rw_rollback.cursor() as cur:
        cur.execute('SELECT count(*) FROM "vw_canonical_graph_edge" WHERE "ProvenanceStatus" IS NULL')
        assert int(cur.fetchone()[0]) == 0


@requires_db
def test_graph_rebuild_communities_idempotent(rw_rollback):
    conn = rw_rollback
    a = algorithms.detect_communities(conn, seed=42)
    b = algorithms.detect_communities(conn, seed=42)
    assert a["num_communities"] == b["num_communities"]
    assert a["modularity"] == b["modularity"]


# ---------------------------------------------------------------------------
# demo-context-filtered similar-case retrieval (same-model, leakage-safe)
# ---------------------------------------------------------------------------
@pytest.fixture
def small_corpus(rw_rollback):
    corpus.embed_corpus(rw_rollback, limit=400, embedder_name="hashing")
    with rw_rollback.cursor() as cur:
        cur.execute("SELECT ce.\"CaseMasterID\", qu.\"DistrictID\", ce.\"ModelVersionID\" "
                    'FROM "CrimeEmbedding" ce '
                    'JOIN "CaseMaster" qm ON qm."CaseMasterID"=ce."CaseMasterID" '
                    'JOIN "Unit" qu ON qu."UnitID"=qm."PoliceStationID" '
                    "WHERE ce.\"SourceType\"='case' AND ce.\"IsArchived\"=FALSE LIMIT 1")
        cid, did, mv = cur.fetchone()
    return int(cid), int(did), int(mv)


@requires_db
def test_similar_demo_context_filter(rw_rollback, small_corpus):
    conn = rw_rollback
    case_id, district_id, _mv = small_corpus
    scoped = similar.find_similar(conn, case_id, k=6, scope="district")
    unscoped = similar.find_similar(conn, case_id, k=6, scope="all")
    assert scoped["scope_district_id"] == district_id
    # every district-scoped hit is inside the query district
    ids = [r["case_id"] for r in scoped["results"]]
    if ids:
        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                        'WHERE cm."CaseMasterID" = ANY(%s) AND u."DistrictID" <> %s', (ids, district_id))
            assert int(cur.fetchone()[0]) == 0
    assert len(unscoped["results"]) >= len(scoped["results"])


@requires_db
def test_similar_same_model_space_and_provenance(rw_rollback, small_corpus):
    conn = rw_rollback
    case_id, _district, mv = small_corpus
    res = similar.find_similar(conn, case_id, k=5, scope="all")
    assert res["model_version_id"] == mv           # one coherent space per ModelVersion
    for r in res["results"]:
        assert r["source_links"] == [f"CaseMaster:{r['case_id']}"]   # provenance links


@requires_db
def test_similar_query_text_is_leakage_safe(rw_rollback, small_corpus):
    conn = rw_rollback
    case_id, _d, _m = small_corpus
    res = similar.find_similar(conn, case_id, k=3, scope="all")
    text = res["query_text"].lower()
    # outcome/label fields must never enter the similarity query text
    for banned in ("chargesheet", "disposition", "convicted", "acquitted", "status:"):
        assert banned not in text


# ---------------------------------------------------------------------------
# hidden associations: independent evidence kinds + reviewer state
# ---------------------------------------------------------------------------
def _hidden_fixture(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT "CanonicalEntityID" FROM "CanonicalEntity" LIMIT 1')
        cent = int(cur.fetchone()[0])

        def node(etype, label):
            cur.execute('INSERT INTO "EntityGraph" ("EntityType","Label","RefTable","CanonicalEntityID") '
                        "VALUES (%s,%s,'CanonicalEntity',%s) RETURNING \"EntityID\"", (etype, label, cent))
            return int(cur.fetchone()[0])
        p, s = node("person", "P"), node("person", "S")
        ph, veh = node("phone", "phone"), node("vehicle", "vehicle")
        for src, tgt in [(p, ph), (s, ph), (p, veh), (s, veh)]:
            cur.execute('INSERT INTO "NetworkEdge" ("Source","Target","RelationshipType",'
                        '"ProvenanceStatus","Weight") VALUES (%s,%s,\'associate\',\'verified\',1.0)',
                        (src, tgt))
    return p, s


@requires_db
def test_hidden_association_independent_evidence_and_review_persists(rw_rollback):
    conn = rw_rollback
    p, s = _hidden_fixture(conn)
    hidden.materialize(conn, min_links=2)
    with conn.cursor() as cur:
        cur.execute('SELECT "AssociationID","IndependentEvidenceKinds","ReviewStatus" '
                    'FROM "drishti_hidden_associations" WHERE "EntityA"=%s AND "EntityB"=%s',
                    (min(p, s), max(p, s)))
        row = cur.fetchone()
    assert row is not None
    assoc_id = int(row[0])
    assert sorted(row[1]) == ["phone", "vehicle"]     # >= 2 independent evidence kinds
    assert row[2] == "candidate"

    hidden.review(conn, assoc_id, "confirm", actor="sup")
    hidden.materialize(conn, min_links=2)              # re-run must PRESERVE the decision
    with conn.cursor() as cur:
        cur.execute('SELECT "ReviewStatus" FROM "drishti_hidden_associations" WHERE "AssociationID"=%s',
                    (assoc_id,))
        r = cur.fetchone()
    assert r is not None and r[0] == "confirmed"


@requires_db
def test_hidden_requires_two_distinct_evidence_kinds(rw_rollback):
    """A pair sharing only ONE kind of intermediary is not a hidden association."""
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute('SELECT "CanonicalEntityID" FROM "CanonicalEntity" LIMIT 1')
        cent = int(cur.fetchone()[0])

        def node(etype, label):
            cur.execute('INSERT INTO "EntityGraph" ("EntityType","Label","RefTable","CanonicalEntityID") '
                        "VALUES (%s,%s,'CanonicalEntity',%s) RETURNING \"EntityID\"", (etype, label, cent))
            return int(cur.fetchone()[0])
        p, s = node("person", "P1"), node("person", "S1")
        ph = node("phone", "only-phone")
        for src in (p, s):   # share ONE kind (phone) only
            cur.execute('INSERT INTO "NetworkEdge" ("Source","Target","RelationshipType",'
                        '"ProvenanceStatus","Weight") VALUES (%s,%s,\'associate\',\'verified\',1.0)',
                        (src, ph))
    hidden.materialize(conn, min_links=2)
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM "drishti_hidden_associations" WHERE "EntityA"=%s AND "EntityB"=%s',
                    (min(p, s), max(p, s)))
        assert int(cur.fetchone()[0]) == 0
