"""Admin console: UI visibility switches, admin-created roles, profile edits.

The tables shipped in migrations 029/030/035 with no code above them. These tests
pin the five rules the migration footer records as un-expressible in SQL, plus the
two design choices that are easy to get backwards:

  * clearing a UI override DELETES the row rather than writing enabled=TRUE, so the
    element follows its registry default again instead of being pinned visible;
  * a profile edit writes only the fields that were sent, so a partial edit cannot
    blank a rank the admin never touched.

Every custom role created here is torn down, so the suite can run repeatedly
against the live database without leaving roles behind.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from conftest import requires_db

from app.main import app

client = TestClient(app)

ADMIN = {"X-Demo-Actor": "platform.admin"}


def _unique_role() -> str:
    # uuid, not a fixed name: a failed run must not collide with the next one.
    return f"test_role_{uuid.uuid4().hex[:10]}"


@pytest.fixture
def temp_role():
    """Yields a factory; deletes whatever it created, even on failure."""
    created: list[str] = []

    def make(**overrides):
        body = {
            "role_name": _unique_role(),
            "description": "Created by test_admin_console.",
            "base_surface": "district_command",
            "allowed_scope_types": ["district"],
            "permission_keys": ["dashboard.read", "analytics.read"],
        }
        body.update(overrides)
        r = client.post("/admin/roles", json=body, headers=ADMIN)
        if r.status_code == 201:
            created.append(r.json()["role_name"])
        return r

    yield make

    for name in created:
        client.delete(f"/admin/roles/{name}", headers=ADMIN)


# --------------------------------------------------------------------------- #
# Catalogue                                                                   #
# --------------------------------------------------------------------------- #
@requires_db
def test_permission_catalogue_is_grouped_and_flags_sensitive_permissions():
    r = client.get("/admin/permissions")
    assert r.status_code == 200, r.text
    b = r.json()

    assert b["total"] > 0
    assert b["categories"], "the console builds its picker from these groups"

    flat = [p for group in b["categories"].values() for p in group]
    assert len(flat) == b["total"]

    by_key = {p["permission_key"]: p for p in flat}
    # PII-bearing and coercive permissions must be marked, because the console
    # requires a reason before granting one.
    assert by_key["cases.detail_read"]["is_sensitive"] is True
    assert by_key["cases.detail_read"]["requires_scope"] == "district"
    # And an aggregate metric is not sensitive, so the reason prompt stays rare
    # enough to mean something.
    assert by_key["dashboard.read"]["is_sensitive"] is False


# --------------------------------------------------------------------------- #
# Rule 1 — built-in roles are not editable structure                          #
# --------------------------------------------------------------------------- #
@requires_db
def test_builtin_roles_cannot_be_deleted():
    """The six built-in roles are named in the frontend registry, the gateway and
    roles.py. Deleting one would break rendering for every seat holding it."""
    r = client.delete("/admin/roles/dgp_state_command", headers=ADMIN)
    assert r.status_code == 409, r.text
    assert "built-in" in r.json()["detail"]

    # Still there, and still holding its seats.
    assert client.get("/admin/roles/dgp_state_command").status_code == 200


@requires_db
def test_role_list_reports_seat_counts_and_surfaces():
    r = client.get("/admin/roles")
    assert r.status_code == 200, r.text
    b = r.json()

    roles = {x["role_name"]: x for x in b["items"]}
    for name in ("dgp_state_command", "senior_command", "district_command",
                 "sho", "investigating_officer", "system_admin"):
        assert name in roles, f"{name} missing from the role list"
        assert roles[name]["is_system"] is True
        # Every built-in role must render something, or a seat holding it sees a
        # blank workspace.
        assert roles[name]["base_surface"] in b["base_surfaces"]

    # ADGP and DIG share senior_command and differ only by scope type — the
    # consolidation the whole model rests on.
    assert set(roles["senior_command"]["allowed_scope_types"]) == {"wing", "range"}
    assert set(roles["district_command"]["allowed_scope_types"]) == {
        "district", "commissionerate"}

    # SHO seats are the 1,000-odd station posts; the count should be in that order,
    # not zero and not the whole force.
    assert roles["sho"]["seat_count"] > 900


# --------------------------------------------------------------------------- #
# Role creation                                                               #
# --------------------------------------------------------------------------- #
@requires_db
def test_admin_can_create_a_role_with_an_arbitrary_permission_set(temp_role):
    r = temp_role(
        permission_keys=["dashboard.read", "analytics.read", "map.read",
                         "disaster.read"],
        allowed_scope_types=["district", "commissionerate"],
    )
    assert r.status_code == 201, r.text
    b = r.json()

    assert b["is_system"] is False
    assert b["created_by"] == "platform.admin"
    assert b["granted_count"] == 4
    assert b["sensitive_count"] == 0
    assert {g["permission_key"] for g in b["grants"]} == {
        "dashboard.read", "analytics.read", "map.read", "disaster.read"}
    # A brand-new role has no seats, which is what makes it safe to delete.
    assert b["seat_count"] == 0


@requires_db
def test_created_role_renders_an_existing_surface(temp_role):
    """`base_surface` is what lets a new role work with no new frontend code."""
    r = temp_role(base_surface="station")
    assert r.status_code == 201, r.text
    assert r.json()["base_surface"] == "station"


@requires_db
def test_role_name_is_constrained_to_a_safe_identifier():
    # Role names end up in URLs, config and the legacy role_permissions
    # projection, so they are constrained up front rather than sanitised later.
    r = client.post("/admin/roles", json={
        "role_name": "bad name!", "base_surface": "station",
        "allowed_scope_types": ["station"], "permission_keys": [],
    }, headers=ADMIN)
    assert r.status_code == 422, r.text


@requires_db
def test_duplicate_role_name_is_refused(temp_role):
    first = temp_role()
    assert first.status_code == 201, first.text
    name = first.json()["role_name"]

    again = client.post("/admin/roles", json={
        "role_name": name, "base_surface": "station",
        "allowed_scope_types": ["station"], "permission_keys": [],
    }, headers=ADMIN)
    assert again.status_code == 409, again.text


@requires_db
def test_unknown_permission_is_refused():
    r = client.post("/admin/roles", json={
        "role_name": _unique_role(), "base_surface": "station",
        "allowed_scope_types": ["station"],
        "permission_keys": ["cases.read", "not.a.permission"],
    }, headers=ADMIN)
    assert r.status_code == 400, r.text
    assert "not.a.permission" in r.json()["detail"]
    # The catalogue exists precisely so a typo cannot invent a permission that
    # nothing ever checks.


# --------------------------------------------------------------------------- #
# Rule 2 — a permission must be meaningful at the role's widest scope          #
# --------------------------------------------------------------------------- #
@requires_db
def test_permission_needing_district_grain_is_refused_for_a_state_role():
    """A state seat is aggregate-only, so `cases.detail_read` could never be used
    there. Granting it would advertise a capability the seat cannot exercise."""
    r = client.post("/admin/roles", json={
        "role_name": _unique_role(), "base_surface": "state_command",
        "allowed_scope_types": ["state"],
        "permission_keys": ["cases.detail_read"],
        "reason": "testing rule 2",
    }, headers=ADMIN)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "cases.detail_read" in detail
    assert "district" in detail and "state" in detail


@requires_db
def test_same_permission_is_allowed_for_a_district_role(temp_role):
    """The mirror of the previous test: the permission is not forbidden, it is
    forbidden AT STATE SCOPE. A district role may hold it."""
    r = temp_role(
        base_surface="district_command",
        allowed_scope_types=["district"],
        permission_keys=["cases.detail_read"],
        reason="district command needs the case file",
    )
    assert r.status_code == 201, r.text
    assert r.json()["sensitive_count"] == 1


@requires_db
def test_rule_two_is_checked_against_the_widest_allowed_scope():
    """A role issuable at BOTH state and district level must fail: the state seat
    holding it would have a permission it cannot use."""
    r = client.post("/admin/roles", json={
        "role_name": _unique_role(), "base_surface": "senior_command",
        "allowed_scope_types": ["state", "district"],
        "permission_keys": ["cases.detail_read"],
        "reason": "testing widest-scope check",
    }, headers=ADMIN)
    assert r.status_code == 400, r.text


# --------------------------------------------------------------------------- #
# Rule 3 — sensitive grants need a stated reason                               #
# --------------------------------------------------------------------------- #
@requires_db
def test_sensitive_permission_requires_a_reason():
    r = client.post("/admin/roles", json={
        "role_name": _unique_role(), "base_surface": "station",
        "allowed_scope_types": ["station"],
        "permission_keys": ["cases.write"],  # is_sensitive, no reason given
    }, headers=ADMIN)
    assert r.status_code == 400, r.text
    assert "reason is required" in r.json()["detail"]


@requires_db
def test_non_sensitive_permissions_need_no_reason(temp_role):
    # Otherwise the prompt would appear constantly and be clicked through.
    r = temp_role(permission_keys=["dashboard.read", "map.read"])
    assert r.status_code == 201, r.text


# --------------------------------------------------------------------------- #
# Grant editing                                                               #
# --------------------------------------------------------------------------- #
@requires_db
def test_replacing_grants_sets_the_whole_set(temp_role):
    created = temp_role(permission_keys=["dashboard.read", "analytics.read"])
    name = created.json()["role_name"]

    r = client.put(f"/admin/roles/{name}/grants",
                   json={"permission_keys": ["map.read"]}, headers=ADMIN)
    assert r.status_code == 200, r.text
    # A replace, not a merge: the console posts its checkbox state, so anything
    # absent is deliberately revoked.
    assert {g["permission_key"] for g in r.json()["grants"]} == {"map.read"}
    assert r.json()["granted_count"] == 1


@requires_db
def test_toggling_one_grant_leaves_the_others_alone(temp_role):
    created = temp_role(permission_keys=["dashboard.read", "analytics.read"])
    name = created.json()["role_name"]

    r = client.patch(f"/admin/roles/{name}/grants/analytics.read",
                     json={"granted": False}, headers=ADMIN)
    assert r.status_code == 200, r.text
    granted = {g["permission_key"] for g in r.json()["grants"] if g["granted"]}
    assert granted == {"dashboard.read"}


@requires_db
def test_toggling_on_still_enforces_the_scope_rule(temp_role):
    """The scope check cannot be bypassed by creating a clean role and then
    switching the permission on afterwards."""
    created = temp_role(base_surface="state_command",
                        allowed_scope_types=["state"],
                        permission_keys=["dashboard.read"])
    name = created.json()["role_name"]

    r = client.patch(f"/admin/roles/{name}/grants/cases.detail_read",
                     json={"granted": True, "reason": "trying to sneak in"},
                     headers=ADMIN)
    assert r.status_code == 400, r.text


@requires_db
def test_grants_are_reprojected_onto_legacy_role_permissions(temp_role):
    """Rule 5. The whitelisted-SELECT executor reads role_permissions, so a
    revocation that did not reach it would keep being honoured."""
    from app import db

    created = temp_role(permission_keys=["dashboard.read", "analytics.read"])
    name = created.json()["role_name"]

    def legacy_resources() -> dict:
        # role_permissions keys on role_id, so the projection has to bridge from
        # role_grant's role_name. Joining here proves it bridged correctly.
        with db.ro_conn() as conn, conn.cursor() as cur:
            cur.execute(
                'SELECT rp."resource", rp."action"::text'
                '  FROM "role_permissions" rp'
                '  JOIN "roles" r ON r."role_id" = rp."role_id"'
                ' WHERE r."role_name" = %s', (name,))
            return dict(cur.fetchall())

    before = legacy_resources()
    assert before, "creating a role should have projected legacy rows"

    client.put(f"/admin/roles/{name}/grants",
               json={"permission_keys": []}, headers=ADMIN)
    assert legacy_resources() == {}, (
        "revoking every grant must clear the legacy projection, or the executor "
        "keeps honouring permissions the admin removed")


@requires_db
def test_custom_role_can_be_deleted_and_takes_its_grants_with_it():
    r = client.post("/admin/roles", json={
        "role_name": _unique_role(), "base_surface": "station",
        "allowed_scope_types": ["station"],
        "permission_keys": ["dashboard.read"],
    }, headers=ADMIN)
    assert r.status_code == 201, r.text
    name = r.json()["role_name"]

    assert client.delete(f"/admin/roles/{name}", headers=ADMIN).status_code == 204
    assert client.get(f"/admin/roles/{name}").status_code == 404


# --------------------------------------------------------------------------- #
# UI visibility                                                               #
# --------------------------------------------------------------------------- #
@requires_db
def test_ui_visibility_override_round_trips():
    body = {
        "role_name": "district_command", "element_kind": "kpi",
        "element_id": "kpi-conviction", "enabled": False,
        "reason": "test: district boards trialling without this card",
    }
    r = client.put("/admin/ui-visibility", json=body, headers=ADMIN)
    assert r.status_code == 200, r.text
    grant_id = r.json()["id"]
    try:
        assert r.json()["enabled"] is False
        assert r.json()["updated_by"] == "platform.admin"

        listed = client.get("/admin/ui-visibility",
                            params={"role_name": "district_command"})
        assert listed.status_code == 200
        ids = {g["id"] for g in listed.json()["items"]}
        assert grant_id in ids

        # The response must not let a reader mistake this for access control.
        assert "Presentation only" in listed.json()["enforcement"]
    finally:
        client.delete(f"/admin/ui-visibility/{grant_id}", headers=ADMIN)


@requires_db
def test_setting_the_same_element_twice_updates_rather_than_duplicating():
    """The unique index COALESCEs scope_type to '*'. Two role-wide rows for one
    element would make the effective value depend on row order."""
    body = {"role_name": "sho", "element_kind": "widget",
            "element_id": "officer-load", "enabled": False}
    first = client.put("/admin/ui-visibility", json=body, headers=ADMIN)
    assert first.status_code == 200, first.text
    grant_id = first.json()["id"]
    try:
        second = client.put("/admin/ui-visibility",
                            json={**body, "enabled": True}, headers=ADMIN)
        assert second.status_code == 200, second.text
        assert second.json()["id"] == grant_id, "should have updated in place"
        assert second.json()["enabled"] is True
    finally:
        client.delete(f"/admin/ui-visibility/{grant_id}", headers=ADMIN)


@requires_db
def test_scope_specific_override_is_separate_from_the_role_wide_one():
    """An admin can hide a card from wing seats and leave range seats alone, so
    the two rows must coexist."""
    wide = {"role_name": "senior_command", "element_kind": "kpi",
            "element_id": "kpi-hotspots", "enabled": False}
    narrow = {**wide, "scope_type": "wing", "enabled": True}

    a = client.put("/admin/ui-visibility", json=wide, headers=ADMIN)
    b = client.put("/admin/ui-visibility", json=narrow, headers=ADMIN)
    assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
    try:
        assert a.json()["id"] != b.json()["id"]
        assert a.json()["scope_type"] is None
        assert b.json()["scope_type"] == "wing"
    finally:
        client.delete(f"/admin/ui-visibility/{a.json()['id']}", headers=ADMIN)
        client.delete(f"/admin/ui-visibility/{b.json()['id']}", headers=ADMIN)


@requires_db
def test_clearing_an_override_removes_the_row_rather_than_enabling_it():
    """Deleting and switching-on are different outcomes.

    An absent row means "use the registry default", so writing TRUE would PIN the
    element visible and a later default change would never reach the role.
    """
    body = {"role_name": "sho", "element_kind": "destination",
            "element_id": "/analytics", "enabled": False}
    created = client.put("/admin/ui-visibility", json=body, headers=ADMIN)
    grant_id = created.json()["id"]

    assert client.delete(f"/admin/ui-visibility/{grant_id}",
                         headers=ADMIN).status_code == 204

    listed = client.get("/admin/ui-visibility", params={"role_name": "sho"})
    remaining = {(g["element_kind"], g["element_id"]) for g in listed.json()["items"]}
    assert ("destination", "/analytics") not in remaining


@requires_db
def test_unknown_role_is_refused_for_a_ui_override():
    r = client.put("/admin/ui-visibility", json={
        "role_name": "no_such_role", "element_kind": "kpi",
        "element_id": "kpi-incidents", "enabled": False,
    }, headers=ADMIN)
    assert r.status_code == 404, r.text


@requires_db
def test_unknown_element_kind_is_refused():
    # Constrained by the table's CHECK; rejected before the round trip.
    r = client.put("/admin/ui-visibility", json={
        "role_name": "sho", "element_kind": "sidebar",
        "element_id": "x", "enabled": False,
    }, headers=ADMIN)
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# Per-seat profile                                                            #
# --------------------------------------------------------------------------- #
@requires_db
def test_profile_edit_writes_only_the_fields_supplied():
    listed = client.get("/org/seats", params={"scope_type": "station",
                                             "page_size": 1})
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    if not items:
        pytest.skip("no station seats provisioned")
    user_id = items[0]["user_id"]

    before = client.get(f"/admin/users/{user_id}/profile").json()

    r = client.put(f"/admin/users/{user_id}/profile",
                   json={"notes": "test note"}, headers=ADMIN)
    assert r.status_code == 200, r.text
    after = r.json()
    try:
        assert after["notes"] == "test note"
        # A partial edit must not blank what it did not mention. Without
        # exclude_unset every omitted field would arrive as None and wipe a rank
        # or a phone number the admin never touched.
        assert after["rank_label"] == before["rank_label"]
        assert after["display_name"] == before["display_name"]
        assert after["posting_label"] == before["posting_label"]
    finally:
        client.put(f"/admin/users/{user_id}/profile",
                   json={"notes": before["notes"]}, headers=ADMIN)


@requires_db
def test_profile_edit_cannot_change_role_or_scope():
    """Role, unit and scope are provisioning decisions with their own audited
    endpoints. Accepting them here would let a display-name edit quietly move a
    seat's jurisdiction."""
    listed = client.get("/org/seats", params={"scope_type": "district",
                                             "page_size": 1})
    items = listed.json()["items"]
    if not items:
        pytest.skip("no district seats provisioned")
    user_id = items[0]["user_id"]
    before = client.get(f"/admin/users/{user_id}/profile").json()

    r = client.put(f"/admin/users/{user_id}/profile", json={
        "display_name": before["display_name"],
        "role": "system_admin", "scope_type": "platform", "district_id": 1,
    }, headers=ADMIN)
    assert r.status_code == 200, r.text

    after = client.get(f"/admin/users/{user_id}/profile").json()
    assert after["role"] == before["role"], "role must not be editable here"
    assert after["scope_type"] == before["scope_type"], (
        "scope_type must not be editable here")


@requires_db
def test_profile_edit_of_unknown_user_is_a_404():
    r = client.put("/admin/users/99999999/profile",
                   json={"notes": "x"}, headers=ADMIN)
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# Role settings                                                               #
# --------------------------------------------------------------------------- #
@requires_db
def test_role_settings_update_is_presentational_only(temp_role):
    created = temp_role()
    name = created.json()["role_name"]
    granted_before = created.json()["granted_count"]

    r = client.put(f"/admin/roles/{name}/settings", json={
        "display_label": "Coastal Security Cell",
        "default_route": "/command",
        "sort_order": 70,
    }, headers=ADMIN)
    assert r.status_code == 200, r.text
    b = r.json()

    assert b["display_label"] == "Coastal Security Cell"
    assert b["default_route"] == "/command"
    # Changing a label must not touch what the role may do.
    assert b["granted_count"] == granted_before


@requires_db
def test_role_settings_route_must_be_absolute(temp_role):
    created = temp_role()
    name = created.json()["role_name"]
    r = client.put(f"/admin/roles/{name}/settings",
                   json={"default_route": "command"}, headers=ADMIN)
    assert r.status_code == 422, r.text
