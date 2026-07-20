"""Prompt 20 Part B — police rank -> role/scope mapping, server-side scope
derivation, the allow/deny matrix, and SUPERADMIN credential/role provisioning.

Pure mapping + matrix tests run offline. The SUPERADMIN write round-trip and the
trusted scope resolution use ``rw_rollback`` (owner connection that ALWAYS rolls
back) so nothing persists to the synthetic development database. API tests prove
the authorization boundary without persisting a row.
"""
import pytest
from fastapi.testclient import TestClient

from conftest import requires_db

from app.main import app
from app.org import hierarchy, scope as scope_mod, service

client = TestClient(app)


def _hdr(role: str) -> dict:
    return {"X-Role": role}


# ===========================================================================
# B.1 — rank / assignment -> functional role + scope (pure)
# ===========================================================================
def test_rank_mapping_covers_organizer_hierarchy():
    # DGP -> IGP -> DIG -> SP -> Station Chief (SHO) -> Investigating Officer.
    assert hierarchy.map_rank("Director General of Police").functional_role == "supervisor"
    assert hierarchy.map_rank("Director General of Police").scope_level == "state"
    assert hierarchy.map_rank("Inspector General of Police").scope_level == "range"
    assert hierarchy.map_rank("Deputy Inspector General").scope_level == "range"
    assert hierarchy.map_rank("Superintendent of Police").scope_level == "district"
    # A Police Inspector who is the SHO is a station-chief supervisor.
    assert hierarchy.map_rank("Police Inspector", "Station House Officer").scope_level == "station"
    assert hierarchy.map_rank("Police Inspector", "Station House Officer").functional_role == "supervisor"
    # A PSI who is the IO is a case-scoped investigator.
    m = hierarchy.map_rank("Police Sub-Inspector", "Investigating Officer")
    assert m.functional_role == "investigator" and m.scope_level == "assigned_case"


def test_rank_mapping_abbreviations_and_aliases():
    assert hierarchy.map_rank("SP").scope_level == "district"
    assert hierarchy.map_rank("SHO").functional_role == "supervisor"
    assert hierarchy.map_rank("station chief").scope_level == "station"
    assert hierarchy.role_for_rank("bogus rank") is None


def test_scope_levels_ordering():
    assert hierarchy.scope_covers("state", "station") is True
    assert hierarchy.scope_covers("district", "state") is False
    assert hierarchy.scope_covers("station", "station") is True


def test_six_functional_roles_present():
    assert set(hierarchy.FUNCTIONAL_ROLES) == {
        "investigator", "analyst", "supervisor", "policymaker",
        "disaster_coordinator", "super_admin"}


# ===========================================================================
# B.2/B.3 — server-side scope + allow/deny matrix (pure)
# ===========================================================================
def test_policymaker_is_aggregate_only():
    sc = scope_mod.derive_scope("policymaker")
    assert scope_mod.can_view_case_detail(sc, district_id=5, case_id=1) is False
    assert scope_mod.can_view_aggregate_dashboard(sc) is True
    assert scope_mod.can_use_investigation_board(sc) is False   # Board denied (Prompt 16)
    assert scope_mod.can_export(sc, aggregate=True) is True
    assert scope_mod.can_export(sc, aggregate=False) is False


def test_district_supervisor_confined_to_assigned_district():
    # A trusted district-3 supervisor cannot open a case in district 9.
    sc = scope_mod.derive_scope("supervisor", district_id=3, rank="Superintendent of Police")
    assert sc.district_ids == frozenset({3})
    assert scope_mod.can_view_case_detail(sc, district_id=3) is True
    assert scope_mod.can_view_case_detail(sc, district_id=9) is False


def test_investigator_case_scoped_to_assigned_cases():
    sc = scope_mod.derive_scope("investigator", district_id=3,
                                rank="Police Sub-Inspector", designation="Investigating Officer",
                                assigned_case_ids=[101, 102])
    assert scope_mod.can_view_case_detail(sc, district_id=3, case_id=101) is True
    assert scope_mod.can_view_case_detail(sc, district_id=3, case_id=999) is False


def test_disaster_approval_only_for_coordinator_in_district():
    dc = scope_mod.derive_scope("disaster_coordinator", district_id=7)
    assert scope_mod.can_approve_disaster(dc, district_id=7) is True
    assert scope_mod.can_approve_disaster(dc, district_id=8) is False
    inv = scope_mod.derive_scope("investigator")
    assert scope_mod.can_approve_disaster(inv, district_id=7) is False
    sa = scope_mod.derive_scope("super_admin")
    assert scope_mod.can_approve_disaster(sa, district_id=7) is True


def test_super_admin_all_actions_true():
    sc = scope_mod.derive_scope("super_admin")
    for action in scope_mod.MATRIX_ACTIONS:
        assert scope_mod.decide(sc, action, district_id=1, case_id=1) is True


def test_scope_matrix_shape_and_denials():
    m = scope_mod.matrix_for_roles()
    assert set(m) == set(hierarchy.FUNCTIONAL_ROLES)
    for role in hierarchy.FUNCTIONAL_ROLES:
        assert set(m[role]) == set(scope_mod.MATRIX_ACTIONS)
    # Key organizer guarantee: policymaker never gets individual case detail/board.
    assert m["policymaker"]["case_detail"] is False
    assert m["policymaker"]["investigation_board"] is False
    # Disaster approval is limited to the coordinator (+ super_admin).
    assert m["investigator"]["disaster_approval"] is False
    assert m["disaster_coordinator"]["disaster_approval"] is True


def test_browser_header_cannot_widen_scope():
    # derive_scope only consumes TRUSTED fields; there is no code path where a
    # request header widens district_ids. A district-3 seat stays district-3.
    sc = scope_mod.derive_scope("supervisor", district_id=3)
    # Simulate an attacker header claiming district 9 -> still denied.
    assert scope_mod.within_geo_scope(sc, district_id=9) is False
    assert scope_mod.within_geo_scope(sc, district_id=3) is True


# ===========================================================================
# API authorization (no persistence)
# ===========================================================================
def test_scope_matrix_endpoint_requires_admin_read():
    # investigator cannot open the admin/org console.
    assert client.get("/org/scope-matrix", headers=_hdr("investigator")).status_code == 403
    r = client.get("/org/scope-matrix", headers=_hdr("super_admin"))
    assert r.status_code == 200
    body = r.json()
    assert body["matrix"]["policymaker"]["case_detail"] is False


def test_hierarchy_endpoint_lists_ranks():
    r = client.get("/org/hierarchy", headers=_hdr("super_admin"))
    assert r.status_code == 200
    abbrs = {m["abbr"] for m in r.json()["mappings"]}
    assert {"DGP", "IGP", "SP", "SHO", "IO"} <= abbrs


def test_create_user_denied_for_non_super_admin():
    # investigator / supervisor cannot provision credentials (super_admin only).
    body = {"username": "should.not.persist", "role": "analyst"}
    assert client.post("/org/users", json=body, headers=_hdr("investigator")).status_code == 403
    assert client.post("/org/users", json=body, headers=_hdr("supervisor")).status_code == 403


@requires_db
def test_super_admin_create_reaches_service_without_persist():
    # super_admin passes the gate + write guard and reaches the service, which
    # rejects a duplicate username -> proves authorization without persisting.
    body = {"username": "admin", "role": "analyst"}  # 'admin' already exists
    r = client.post("/org/users", json=body, headers=_hdr("super_admin"))
    assert r.status_code == 400
    assert "exists" in r.json()["detail"].lower()


# ===========================================================================
# SUPERADMIN credential/role round-trip (rollback — nothing persists)
# ===========================================================================
@requires_db
def test_ensure_roles_seeds_disaster_coordinator(rw_rollback):
    out = service.ensure_roles(conn=rw_rollback)
    with rw_rollback.cursor() as cur:
        cur.execute('SELECT count(*) FROM "roles" WHERE "role_name"=%s',
                    ("disaster_coordinator",))
        assert cur.fetchone()[0] == 1


@requires_db
def test_superadmin_creates_credential_assigns_role_and_scope(rw_rollback):
    # 1. create a credential for a role (SUPERADMIN action).
    created = service.create_user("io.newbie.p20", "PSI Newbie", "investigator",
                                  actor="demo.super_admin", conn=rw_rollback)
    uid = created["user_id"]
    assert created["role"] == "investigator"
    assert created["must_reset_password"] is True
    # 2. assign a different role to the created credential.
    changed = service.assign_role(uid, "supervisor", actor="demo.super_admin", conn=rw_rollback)
    assert changed["role"] == "supervisor"
    # 3. assign an organizational scope (Unit -> District).
    with rw_rollback.cursor() as cur:
        cur.execute('SELECT "UnitID" FROM "Unit" ORDER BY "UnitID" LIMIT 1')
        unit_id = int(cur.fetchone()[0])
    scoped = service.set_scope(uid, unit_id, actor="demo.super_admin", conn=rw_rollback)
    assert scoped["unit_id"] == unit_id
    # 4. the trusted scope now derives from the stored record (not a header).
    sc = service.resolve_scope_for_user(user_id=uid, conn=rw_rollback)
    assert sc.role == "supervisor"
    assert sc.trusted is True


@requires_db
def test_create_user_rejects_unknown_role_and_duplicate(rw_rollback):
    with pytest.raises(service.OrgError):
        service.create_user("x.bad.role", "X", "wizard", conn=rw_rollback)
    with pytest.raises(service.OrgError):
        service.create_user("admin", "dup", "analyst", conn=rw_rollback)  # exists
