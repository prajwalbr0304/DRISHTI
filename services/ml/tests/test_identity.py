"""Phase 4 — canonical identity + entity-resolution tests.

DoD coverage:
  * same name / different person stays separate (candidate is a proposal only);
  * alias / same person resolves after review (merge);
  * merge then unmerge restores links (reversible);
  * case/graph queries use canonical ID (case_network shared-person link);
  * no remaining production code performs name-based identity linking.

Integration tests run inside the ``rw_rollback`` transaction (owner connection
that ALWAYS rolls back) and call the internal ``_fn(conn, ...)`` helpers, so
nothing is persisted to the synthetic development database.
"""
from pathlib import Path

import pytest

from app.identity import service as svc
from app.identity import schemas as S
from conftest import requires_db

_APP_DIR = Path(__file__).resolve().parents[1] / "app"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _mk_person(conn, label, gender=1, **kw):
    return svc._create_person(conn, S.CreatePersonRequest(display_label=label,
                                                          primary_gender_id=gender, **kw))


def _a_case_id(conn) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "CaseMaster" ORDER BY "CaseMasterID" LIMIT 1')
        return int(cur.fetchone()[0])


def _two_case_ids(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "CaseMaster" ORDER BY "CaseMasterID" LIMIT 2')
        rows = cur.fetchall()
    return int(rows[0][0]), int(rows[1][0])


def _status(conn, cpid) -> str:
    with conn.cursor() as cur:
        cur.execute('SELECT "ResolutionStatus","MergedIntoCanonicalPersonID" '
                    'FROM "CanonicalPerson" WHERE "CanonicalPersonID"=%s', (cpid,))
        return cur.fetchone()


# ===========================================================================
# Person CRUD + search + attributes
# ===========================================================================
@requires_db
def test_person_create_get_search_update(rw_rollback):
    conn = rw_rollback
    cpid = _mk_person(conn, "Phase4 Test Person", gender=1, approx_birth_year=1990)
    d = svc._detail(conn, cpid)
    assert d.canonical_person_id == cpid
    assert d.public_ref.startswith("SYN-PERSON-")
    assert d.canonical_entity_id is not None      # person is also a canonical entity
    res = svc._search_persons(conn, "Phase4 Test Person", None, None, None, 1, 25)
    assert any(i.canonical_person_id == cpid for i in res.items)
    svc._update_person(conn, cpid, S.UpdatePersonRequest(display_label="Renamed Person"))
    assert svc._detail(conn, cpid).display_label == "Renamed Person"
    conn.rollback()


@requires_db
def test_person_idempotent_create(rw_rollback):
    conn = rw_rollback
    req = S.CreatePersonRequest(display_label="Idem Person", idempotency_key="idem-identity-001")
    a = svc._create_person(conn, req)
    b = svc._create_person(conn, req)
    assert a == b
    conn.rollback()


@requires_db
def test_alias_identifier_contact_address_with_sensitivity(rw_rollback):
    conn = rw_rollback
    cpid = _mk_person(conn, "Attr Person")
    svc._add_alias(conn, cpid, S.AliasInput(alias_name="Known As X", alias_type="aka"))
    svc._add_identifier(conn, cpid, S.IdentifierInput(
        identifier_type="synthetic_govt_id", identifier_value="SYN-ID-123", sensitivity="restricted"))
    svc._add_contact(conn, cpid, S.ContactInput(
        contact_type="phone", contact_value="90000-SYN-01", sensitivity="restricted"))
    svc._add_address(conn, cpid, S.AddressInput(
        district_id=None, address_text="Synthetic addr", latitude=12.97, longitude=77.59,
        sensitivity="restricted"))
    d = svc._detail(conn, cpid)
    assert len(d.aliases) == 1 and d.aliases[0].alias_type == "aka"
    assert len(d.identifiers) == 1 and d.identifiers[0].sensitivity == "restricted"
    assert len(d.contacts) == 1 and len(d.addresses) == 1
    # invalid sensitivity rejected
    with pytest.raises(svc.IdentityValidationError):
        svc._add_identifier(conn, cpid, S.IdentifierInput(
            identifier_type="x", identifier_value="y", sensitivity="top_secret"))
    conn.rollback()


@requires_db
def test_org_create_and_search(rw_rollback):
    conn = rw_rollback
    oid = svc._create_org(conn, S.CreateOrgRequest(name="Phase4 Syndicate", org_type="gang"))
    res = svc._search_orgs(conn, "Phase4 Syndicate", 1, 25)
    assert any(i.canonical_organisation_id == oid for i in res.items)
    conn.rollback()


# ===========================================================================
# Case-party roles (canonical)
# ===========================================================================
@requires_db
def test_case_party_role_add_update_remove(rw_rollback):
    conn = rw_rollback
    case_id = _a_case_id(conn)
    cpid = _mk_person(conn, "Party Person")
    res = svc._add_party(conn, case_id, S.AddPartyRequest(
        canonical_person_id=cpid, role_type="witness", party_label="Party Person"))
    rid = res.case_party_role_id
    assert res.case_master_id == case_id and res.role_type == "witness"
    upd = svc._update_party(conn, rid, S.UpdatePartyRequest(role_type="informant"))
    assert upd.role_type == "informant"
    out = svc._remove_party(conn, rid, "io.test")
    assert out == case_id
    conn.rollback()


@requires_db
def test_add_party_requires_identity_or_unknown(rw_rollback):
    conn = rw_rollback
    case_id = _a_case_id(conn)
    with pytest.raises(svc.IdentityValidationError):
        svc._add_party(conn, case_id, S.AddPartyRequest(role_type="accused"))
    # explicit unknown party is allowed (no invented identity)
    res = svc._add_party(conn, case_id, S.AddPartyRequest(role_type="accused", is_unknown=True))
    assert res.is_unknown is True
    conn.rollback()


# ===========================================================================
# Entity resolution — same name/different person stays separate
# ===========================================================================
@requires_db
def test_same_name_different_person_stays_separate(rw_rollback):
    conn = rw_rollback
    a = _mk_person(conn, "Ravi Kumar SYN")
    b = _mk_person(conn, "Ravi Kumar SYN")
    assert a != b
    gen = svc._generate_candidates(conn, S.GenerateCandidatesRequest(canonical_person_id=a, limit=10))
    # a proposal linking the two is created — but NEITHER is merged automatically
    assert gen.created >= 1
    assert any({c.person_a.canonical_person_id, c.person_b.canonical_person_id} == {a, b}
               for c in gen.candidates)
    assert _status(conn, a)[0] == "canonical"
    assert _status(conn, b)[0] == "canonical"
    conn.rollback()


@requires_db
def test_review_reject_keeps_persons_distinct(rw_rollback):
    conn = rw_rollback
    a = _mk_person(conn, "Reject Name SYN")
    b = _mk_person(conn, "Reject Name SYN")
    gen = svc._generate_candidates(conn, S.GenerateCandidatesRequest(canonical_person_id=a, limit=5))
    cand = next(c for c in gen.candidates
                if {c.person_a.canonical_person_id, c.person_b.canonical_person_id} == {a, b})
    out = svc._review_candidate(conn, cand.entity_resolution_candidate_id,
                                S.ReviewCandidateRequest(action="reject", actor="sup.test"))
    assert out["status"] == "rejected" and out["merge"] is None
    assert _status(conn, a)[0] == "canonical" and _status(conn, b)[0] == "canonical"
    conn.rollback()


# ===========================================================================
# Merge (alias/same person resolves after review) + reversible unmerge
# ===========================================================================
@requires_db
def test_merge_moves_refs_and_unmerge_restores(rw_rollback):
    conn = rw_rollback
    case_id = _a_case_id(conn)
    winner = _mk_person(conn, "Winner Person SYN")
    loser = _mk_person(conn, "Loser Person SYN")
    # give the loser a case-party role + an alias (references that must move)
    role = svc._add_party(conn, case_id, S.AddPartyRequest(
        canonical_person_id=loser, role_type="witness")).case_party_role_id
    svc._add_alias(conn, loser, S.AliasInput(alias_name="Loser AKA"))

    m = svc._merge(conn, winner, loser, "same person after review", "sup.test")
    assert m.action == "merge" and m.reversible
    assert _status(conn, loser) == ("merged", winner)     # loser merged into winner
    with conn.cursor() as cur:
        cur.execute('SELECT "CanonicalPersonID" FROM "CasePartyRole" WHERE "CasePartyRoleID"=%s', (role,))
        assert int(cur.fetchone()[0]) == winner            # role repointed to winner
        cur.execute('SELECT COUNT(*) FROM "PersonAlias" WHERE "CanonicalPersonID"=%s '
                    'AND "AliasType"=\'merged_alias\'', (winner,))
        assert int(cur.fetchone()[0]) == 1                 # loser label kept as alias

    u = svc._unmerge(conn, winner, loser, "reviewer reversed", "sup.test")
    assert u.action == "split"
    assert _status(conn, loser) == ("canonical", None)     # loser restored
    with conn.cursor() as cur:
        cur.execute('SELECT "CanonicalPersonID" FROM "CasePartyRole" WHERE "CasePartyRoleID"=%s', (role,))
        assert int(cur.fetchone()[0]) == loser             # role restored to loser
        cur.execute('SELECT COUNT(*) FROM "PersonAlias" WHERE "CanonicalPersonID"=%s '
                    'AND "AliasType"=\'merged_alias\'', (winner,))
        assert int(cur.fetchone()[0]) == 0                 # merged alias removed
    conn.rollback()


@requires_db
def test_review_accept_merges(rw_rollback):
    conn = rw_rollback
    a = _mk_person(conn, "Accept Merge SYN")
    b = _mk_person(conn, "Accept Merge SYN")
    gen = svc._generate_candidates(conn, S.GenerateCandidatesRequest(canonical_person_id=a, limit=5))
    cand = next(c for c in gen.candidates
                if {c.person_a.canonical_person_id, c.person_b.canonical_person_id} == {a, b})
    out = svc._review_candidate(conn, cand.entity_resolution_candidate_id,
                                S.ReviewCandidateRequest(action="accept",
                                                         winner_canonical_person_id=a, actor="sup.test"))
    assert out["status"] == "accepted" and out["merge"] is not None
    assert _status(conn, b) == ("merged", a)
    conn.rollback()


@requires_db
def test_merge_rejects_self_and_already_merged(rw_rollback):
    conn = rw_rollback
    a = _mk_person(conn, "Self Merge SYN")
    b = _mk_person(conn, "Other SYN")
    with pytest.raises(svc.IdentityValidationError):
        svc._merge(conn, a, a, "self", "x")
    svc._merge(conn, a, b, "merge", "x")
    with pytest.raises(svc.IdentityConflict):     # b already merged
        svc._merge(conn, a, b, "again", "x")
    conn.rollback()


# ===========================================================================
# Case/graph queries use canonical ID
# ===========================================================================
@requires_db
def test_case_network_links_via_shared_canonical_person(rw_rollback):
    conn = rw_rollback
    c1, c2 = _two_case_ids(conn)
    person = _mk_person(conn, "Shared Accused SYN")
    svc._add_party(conn, c1, S.AddPartyRequest(canonical_person_id=person, role_type="accused"))
    svc._add_party(conn, c2, S.AddPartyRequest(canonical_person_id=person, role_type="accused"))
    # the canonical shared-person view links the two cases (no name match)
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM "vw_related_cases_by_person" '
                    'WHERE "CaseMasterID"=%s AND "RelatedCaseMasterID"=%s', (c1, c2))
        assert int(cur.fetchone()[0]) >= 1
    conn.rollback()


@requires_db
def test_graph_person_nodes_all_canonically_linked(rw_rollback):
    # migration-owned assertion: raises if any graph-person node is unlinked
    with rw_rollback.cursor() as cur:
        cur.execute("SELECT fn_assert_graph_persons_linked()")
    rw_rollback.rollback()


# ===========================================================================
# No name-based identity linking remains in production code
# ===========================================================================
def test_no_name_based_identity_linking_in_code():
    import re
    # name-equality cross-case identity joins (the audited anti-pattern)
    patterns = [
        re.compile(r'AccusedName"\s*\)\s*=\s*lower\(trim\(a1'),      # a2.AccusedName = a1.AccusedName
        re.compile(r'acc\."AccusedName"\s*=\s*ent\."Label"'),         # rank-match join
        re.compile(r'AccusedName"\)\)\s*=\s*lower\(trim\(%s'),        # name == label param
    ]
    offenders = []
    for p in _APP_DIR.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat in patterns:
            if pat.search(text):
                offenders.append(p.name)
    assert offenders == [], f"name-based identity joins still present in: {offenders}"
