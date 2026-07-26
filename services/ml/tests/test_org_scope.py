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
    assert hierarchy.map_rank("Director General of Police").functional_role == "dgp_state_command"
    assert hierarchy.map_rank("Director General of Police").scope_level == "state"
    assert hierarchy.map_rank("Inspector General of Police").functional_role == "adgp_igp_range"
    assert hierarchy.map_rank("Inspector General of Police").scope_level == "range"
    assert hierarchy.map_rank("Deputy Inspector General").scope_level == "range"
    assert hierarchy.map_rank("Superintendent of Police").functional_role == "sp_district_command"
    assert hierarchy.map_rank("Superintendent of Police").scope_level == "district"
    assert hierarchy.map_rank("Dy.SP").functional_role == "dysp_acp"
    # A Police Inspector who is the SHO is a station-chief supervisor.
    assert hierarchy.map_rank("Police Inspector", "Station House Officer").scope_level == "station"
    assert hierarchy.map_rank("Police Inspector", "Station House Officer").functional_role == "sho"
    # A PSI who is the IO is a case-scoped investigator.
    m = hierarchy.map_rank("Police Sub-Inspector", "Investigating Officer")
    assert m.functional_role == "investigating_officer" and m.scope_level == "assigned_case"


def test_rank_mapping_abbreviations_and_aliases():
    assert hierarchy.map_rank("SP").scope_level == "district"
    assert hierarchy.map_rank("SHO").functional_role == "sho"
    assert hierarchy.map_rank("station chief").scope_level == "station"
    assert hierarchy.role_for_rank("bogus rank") is None


def test_scope_levels_ordering():
    assert hierarchy.scope_covers("state", "station") is True
    assert hierarchy.scope_covers("district", "state") is False
    assert hierarchy.scope_covers("station", "station") is True


def test_ten_command_roles_present():
    assert set(hierarchy.FUNCTIONAL_ROLES) == {
        "dgp_state_command", "adgp_igp_range", "sp_district_command", "dysp_acp",
        "sho", "investigating_officer", "crime_analyst", "cyber_cell",
        "traffic_command", "system_admin"}


# ===========================================================================
# B.2/B.3 — server-side scope + allow/deny matrix (pure)
# ===========================================================================
def test_state_command_holds_every_capability():
    # INTERIM ("all roles have access to everything"): a state-command seat is
    # no longer aggregate-only — it holds case detail, board and both exports.
    sc = scope_mod.derive_scope("dgp_state_command")
    assert scope_mod.can_view_case_detail(sc, district_id=5, case_id=1) is True
    assert scope_mod.can_view_aggregate_dashboard(sc) is True
    assert scope_mod.can_use_investigation_board(sc) is True
    assert scope_mod.can_export(sc, aggregate=True) is True
    assert scope_mod.can_export(sc, aggregate=False) is True


def test_unknown_role_holds_nothing():
    # A role outside the canonical set is still refused (forged/stale header).
    sc = scope_mod.derive_scope("wizard")
    assert sc.role == "wizard"
    assert scope_mod.can_view_case_detail(sc, district_id=5, case_id=1) is False
    assert scope_mod.can_view_aggregate_dashboard(sc) is False
    assert scope_mod.can_use_investigation_board(sc) is False
    assert scope_mod.can_approve_disaster(sc, district_id=5) is False


def test_district_supervisor_confined_to_assigned_district():
    # A trusted district-3 supervisor cannot open a case in district 9.
    sc = scope_mod.derive_scope("sho", district_id=3, rank="Superintendent of Police")
    assert sc.district_ids == frozenset({3})
    assert scope_mod.can_view_case_detail(sc, district_id=3) is True
    assert scope_mod.can_view_case_detail(sc, district_id=9) is False


def test_investigator_case_scoped_to_assigned_cases():
    sc = scope_mod.derive_scope("investigating_officer", district_id=3,
                                rank="Police Sub-Inspector", designation="Investigating Officer",
                                assigned_case_ids=[101, 102])
    assert scope_mod.can_view_case_detail(sc, district_id=3, case_id=101) is True
    assert scope_mod.can_view_case_detail(sc, district_id=3, case_id=999) is False


def test_disaster_approval_confined_to_the_assigned_district():
    # Every command role may approve (interim), but a district-assigned seat is
    # still confined to its own district.
    dc = scope_mod.derive_scope("dysp_acp", district_id=7)
    assert scope_mod.can_approve_disaster(dc, district_id=7) is True
    assert scope_mod.can_approve_disaster(dc, district_id=8) is False
    # A seat with no district assignment is not geographically narrowed.
    io = scope_mod.derive_scope("investigating_officer")
    assert scope_mod.can_approve_disaster(io, district_id=7) is True
    sa = scope_mod.derive_scope("system_admin")
    assert scope_mod.can_approve_disaster(sa, district_id=7) is True


def test_every_role_allows_all_actions_unscoped():
    for role in hierarchy.FUNCTIONAL_ROLES:
        sc = scope_mod.derive_scope(role)
        for action in scope_mod.MATRIX_ACTIONS:
            assert scope_mod.decide(sc, action, district_id=1, case_id=1) is True, (role, action)


def test_scope_matrix_shape_and_interim_full_access():
    m = scope_mod.matrix_for_roles()
    assert set(m) == set(hierarchy.FUNCTIONAL_ROLES)
    for role in hierarchy.FUNCTIONAL_ROLES:
        assert set(m[role]) == set(scope_mod.MATRIX_ACTIONS)
        # INTERIM: every command role is allowed every matrix action.
        assert all(m[role][a] for a in scope_mod.MATRIX_ACTIONS), role


def test_browser_header_cannot_widen_scope():
    # derive_scope only consumes TRUSTED fields; there is no code path where a
    # request header widens district_ids. A district-3 seat stays district-3.
    sc = scope_mod.derive_scope("sho", district_id=3)
    # Simulate an attacker header claiming district 9 -> still denied.
    assert scope_mod.within_geo_scope(sc, district_id=9) is False
    assert scope_mod.within_geo_scope(sc, district_id=3) is True


# ===========================================================================
# API authorization (no persistence)
# ===========================================================================
def test_scope_matrix_endpoint_open_to_every_role_and_refuses_unknown():
    # INTERIM: admin_read is granted to every command role.
    for role in hierarchy.FUNCTIONAL_ROLES:
        r = client.get("/org/scope-matrix", headers=_hdr(role))
        assert r.status_code == 200, role
        assert r.json()["matrix"][role]["case_detail"] is True
    # An unknown role falls back to the configured default seat, not an error.
    assert client.get("/org/scope-matrix", headers=_hdr("wizard")).status_code == 200


def test_hierarchy_endpoint_lists_ranks():
    r = client.get("/org/hierarchy", headers=_hdr("system_admin"))
    assert r.status_code == 200
    abbrs = {m["abbr"] for m in r.json()["mappings"]}
    assert {"DGP", "IGP", "SP", "SHO", "IO"} <= abbrs


def test_credential_provisioning_granted_to_every_role():
    # INTERIM: admin_write (credential provisioning) is held by every command
    # role; an unknown role still holds nothing.
    from app.admin import permissions as perms
    for role in hierarchy.FUNCTIONAL_ROLES:
        assert perms.has_permission(role, "admin_write") is True, role
    assert perms.has_permission("wizard", "admin_write") is False


@requires_db
def test_create_reaches_service_without_persist():
    # A non-admin seat now passes the gate + write guard and reaches the service,
    # which rejects a duplicate username -> proves the gate without persisting.
    body = {"username": "admin", "role": "crime_analyst"}  # 'admin' already exists
    for role in ("system_admin", "investigating_officer"):
        r = client.post("/org/users", json=body, headers=_hdr(role))
        assert r.status_code == 400, role
        assert "exists" in r.json()["detail"].lower()


# ===========================================================================
# SUPERADMIN credential/role round-trip (rollback — nothing persists)
# ===========================================================================
@requires_db
def test_ensure_roles_seeds_every_command_role(rw_rollback):
    service.ensure_roles(conn=rw_rollback)
    with rw_rollback.cursor() as cur:
        for role in hierarchy.FUNCTIONAL_ROLES:
            cur.execute('SELECT count(*) FROM "roles" WHERE "role_name"=%s', (role,))
            assert cur.fetchone()[0] == 1, role


@requires_db
def test_superadmin_creates_credential_assigns_role_and_scope(rw_rollback):
    # 1. create a credential for a role (SUPERADMIN action).
    created = service.create_user("io.newbie.p20", "PSI Newbie", "investigating_officer",
                                  actor="demo.system_admin", conn=rw_rollback)
    uid = created["user_id"]
    assert created["role"] == "investigating_officer"
    assert created["must_reset_password"] is True
    # 2. assign a different role to the created credential.
    changed = service.assign_role(uid, "sho", actor="demo.system_admin", conn=rw_rollback)
    assert changed["role"] == "sho"
    # 3. assign an organizational scope (Unit -> District).
    with rw_rollback.cursor() as cur:
        cur.execute('SELECT "UnitID" FROM "Unit" ORDER BY "UnitID" LIMIT 1')
        unit_id = int(cur.fetchone()[0])
    scoped = service.set_scope(uid, unit_id, actor="demo.system_admin", conn=rw_rollback)
    assert scoped["unit_id"] == unit_id
    # 4. the trusted scope now derives from the stored record (not a header).
    sc = service.resolve_scope_for_user(user_id=uid, conn=rw_rollback)
    assert sc.role == "sho"
    assert sc.trusted is True


@requires_db
def test_create_user_rejects_unknown_role_and_duplicate(rw_rollback):
    with pytest.raises(service.OrgError):
        service.create_user("x.bad.role", "X", "wizard", conn=rw_rollback)
    with pytest.raises(service.OrgError):
        service.create_user("admin", "dup", "crime_analyst", conn=rw_rollback)  # exists
