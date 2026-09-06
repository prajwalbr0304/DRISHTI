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
    # DGP -> ADGP/IGP -> DIG -> SP/CP -> Station Chief (SHO) -> Investigating Officer.
    assert hierarchy.map_rank("Director General of Police").functional_role == "dgp_state_command"
    assert hierarchy.map_rank("Director General of Police").scope_level == "state"
    assert hierarchy.map_rank("Inspector General of Police").functional_role == "senior_command"
    assert hierarchy.map_rank("Inspector General of Police").scope_level == "range"
    assert hierarchy.map_rank("Deputy Inspector General").scope_level == "range"
    assert hierarchy.map_rank("Superintendent of Police").functional_role == "district_command"
    assert hierarchy.map_rank("Superintendent of Police").scope_level == "district"
    assert hierarchy.map_rank("Dy.SP").functional_role == "district_command"
    # A Police Inspector who is the SHO is a station-chief supervisor.
    assert hierarchy.map_rank("Police Inspector", "Station House Officer").scope_level == "station"
    assert hierarchy.map_rank("Police Inspector", "Station House Officer").functional_role == "sho"
    # A PSI who is the IO is a case-scoped investigator.
    m = hierarchy.map_rank("Police Sub-Inspector", "Investigating Officer")
    assert m.functional_role == "investigating_officer" and m.scope_level == "assigned_case"


def test_adgp_and_dig_share_a_role_but_differ_in_scope_type():
    """The distinction the old single `senior_command` role could not express.

    An ADGP heads a functional wing (state-wide, crime-head narrowed); an IGP/DIG
    commands a geographic range. Same UI surface, different data breadth — so the
    role must match and the scope_type must not.
    """
    adgp = hierarchy.map_rank("Additional Director General of Police")
    dig = hierarchy.map_rank("Deputy Inspector General")
    assert adgp.functional_role == dig.functional_role == "senior_command"
    assert adgp.scope_type == "wing"
    assert dig.scope_type == "range"


def test_sp_and_cp_share_a_role_but_differ_in_scope_type():
    sp = hierarchy.map_rank("Superintendent of Police")
    cp = hierarchy.map_rank("Commissioner of Police")
    assert sp.functional_role == cp.functional_role == "district_command"
    assert sp.scope_type == "district"
    assert cp.scope_type == "commissionerate"


def test_staff_cells_are_wings_not_roles():
    """Crime analyst, cyber and traffic used to be roles of their own. They are
    ADGP wings now, so they must resolve to senior_command at wing scope."""
    for label in ("crime analyst", "SCRB", "cyber cell", "traffic", "intelligence"):
        m = hierarchy.map_rank(label)
        assert m.functional_role == "senior_command", label
        assert m.scope_type == "wing", label


def test_rank_mapping_abbreviations_and_aliases():
    assert hierarchy.map_rank("SP").scope_level == "district"
    assert hierarchy.map_rank("SHO").functional_role == "sho"
    assert hierarchy.map_rank("station chief").scope_level == "station"
    assert hierarchy.role_for_rank("bogus rank") is None


def test_scope_levels_ordering():
    assert hierarchy.scope_covers("state", "station") is True
    assert hierarchy.scope_covers("district", "state") is False
    assert hierarchy.scope_covers("station", "station") is True


def test_six_application_roles_present():
    """Six APPLICATION roles. A role answers only "which UI surface"; how much
    data a seat sees is users.scope_type, which is why ADGP+DIG collapse into
    senior_command and SP+CP into district_command."""
    assert set(hierarchy.FUNCTIONAL_ROLES) == {
        "dgp_state_command", "senior_command", "district_command",
        "sho", "investigating_officer", "system_admin"}


def test_every_role_declares_its_allowed_scope_types():
    from app import roles as R
    for role in hierarchy.FUNCTIONAL_ROLES:
        allowed = R.scope_types_for_role(role)
        assert allowed, role
        for st in allowed:
            assert st in R.SCOPE_TYPES, (role, st)
    # And the pairing is enforced, not advisory.
    assert R.scope_type_allowed("senior_command", "wing") is True
    assert R.scope_type_allowed("senior_command", "state") is False
    assert R.scope_type_allowed("sho", "district") is False


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
    sc = scope_mod.derive_scope("investigating_officer", unit_id=33, district_id=3,
                                scope_type="assigned_case",
                                rank="Police Sub-Inspector", designation="Investigating Officer",
                                assigned_case_ids=[101, 102])
    assert scope_mod.can_view_case_detail(sc, district_id=3, unit_id=33, case_id=101) is True
    assert scope_mod.can_view_case_detail(sc, district_id=3, unit_id=33, case_id=999) is False


def test_disaster_approval_confined_to_the_assigned_district():
    # Every command role may approve (interim), but a district-assigned seat is
    # still confined to its own district.
    dc = scope_mod.derive_scope("district_command", district_id=7)
    assert scope_mod.can_approve_disaster(dc, district_id=7) is True
    assert scope_mod.can_approve_disaster(dc, district_id=8) is False
    # An UNPOSTED seat approves nothing. This is the fail-closed change: it used
    # to fall through to "no geographic narrowing", so an IO with no posting could
    # approve a disaster action in any district in Karnataka.
    io = scope_mod.derive_scope("investigating_officer")
    assert io.scope_type == "unresolved"
    assert scope_mod.can_approve_disaster(io, district_id=7) is False
    # The platform admin is genuinely unpinned, by remit rather than by omission.
    sa = scope_mod.derive_scope("system_admin")
    assert sa.scope_type == "platform"
    assert scope_mod.can_approve_disaster(sa, district_id=7) is True


def test_unposted_seat_is_refused_every_geographic_action():
    """The fail-closed rule, asserted directly.

    `derive_scope` used to fall through to ``districts, units = None, None`` for a
    posted role with no assignment, and None means "no restriction" — so an SHO
    with no posting on record resolved to exactly the same unbounded scope as the
    DGP. An unposted seat must now see nothing.
    """
    geographic = ("case_detail", "disaster_approval")
    for role in ("senior_command", "district_command", "sho", "investigating_officer"):
        sc = scope_mod.derive_scope(role)
        assert sc.scope_type == "unresolved", role
        assert sc.resolved is False, role
        assert sc.district_ids == frozenset(), role
        for action in geographic:
            assert scope_mod.decide(sc, action, district_id=1, case_id=1) is False, (role, action)


def test_posted_seats_hold_their_actions():
    """The counterpart: once posted, a seat holds the interim full action set
    within its own geography."""
    posted = {
        "dgp_state_command": {},
        "senior_command": {"wing_id": 1},
        "district_command": {"district_id": 1},
        "sho": {"unit_id": 33, "district_id": 1},
        "system_admin": {},
    }
    for role, anchor in posted.items():
        sc = scope_mod.derive_scope(role, **anchor)
        assert sc.resolved is True, role
        for action in scope_mod.MATRIX_ACTIONS:
            assert scope_mod.decide(sc, action, district_id=1, unit_id=33,
                                    case_id=1) is True, (role, action)


def test_scope_matrix_shape_and_role_default_access():
    """The matrix is reported at each role's DEFAULT scope, so the two roles that
    are unpinned by remit hold everything and the posted roles hold only the
    non-geographic actions until they are actually posted."""
    m = scope_mod.matrix_for_roles()
    assert set(m) == set(hierarchy.FUNCTIONAL_ROLES)
    for role in hierarchy.FUNCTIONAL_ROLES:
        assert set(m[role]) == set(scope_mod.MATRIX_ACTIONS)

    # Unpinned by remit: state command and the platform admin.
    for role in ("dgp_state_command", "system_admin"):
        assert all(m[role][a] for a in scope_mod.MATRIX_ACTIONS), role

    # Posted roles default to 'unresolved', so anything geographic is refused
    # while the non-geographic capabilities still register.
    for role in ("senior_command", "district_command", "sho", "investigating_officer"):
        assert m[role]["case_detail"] is False, role
        assert m[role]["disaster_approval"] is False, role
        assert m[role]["aggregate_dashboard"] is True, role
        assert m[role]["investigation_board"] is True, role


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
        # Reported at the role's default scope: case detail needs a posting.
        expected = role in ("dgp_state_command", "system_admin")
        assert r.json()["matrix"][role]["case_detail"] is expected, role
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
    body = {"username": "admin", "role": "senior_command"}  # 'admin' already exists
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
        service.create_user("admin", "dup", "senior_command", conn=rw_rollback)  # exists
