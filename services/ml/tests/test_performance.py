"""Prompt 20 Part C — supervisor station/officer performance metrics: scope
enforcement + role gate (offline) and the real metrics payload (DB-gated).

Metrics reads are read-only (ro_conn), so DB tests need no rollback."""
import pytest
from fastapi.testclient import TestClient

from conftest import requires_db

from app.main import app
from app.org import scope as scope_mod

client = TestClient(app)


def _hdr(role: str, actor: str | None = None) -> dict:
    h = {"X-Role": role}
    if actor:
        h["X-Demo-Actor"] = actor
    return h


# ============================ scope enforcement (pure) =====================
def test_station_seat_forced_to_its_unit():
    sc = scope_mod.ScopeContext(role="sho", scope_level="station",
                                district_ids=frozenset({3}), unit_ids=frozenset({90}))
    # no filter requested -> forced to the assigned unit (district implied by it).
    assert scope_mod.enforce_geo_request(sc) == (90, None)
    # requesting the assigned unit is fine.
    assert scope_mod.enforce_geo_request(sc, unit_id=90) == (90, None)
    # requesting a DIFFERENT station is denied.
    with pytest.raises(scope_mod.ScopeDenied):
        scope_mod.enforce_geo_request(sc, unit_id=91)


def test_out_of_scope_request_denied():
    sc = scope_mod.ScopeContext(role="sho", scope_level="district",
                                district_ids=frozenset({3}))
    with pytest.raises(scope_mod.ScopeDenied):
        scope_mod.enforce_geo_request(sc, district_id=9)
    with pytest.raises(scope_mod.ScopeDenied):
        scope_mod.enforce_geo_request(sc, unit_id=None, district_id=9)


def test_unpinned_seat_passes_any_filter():
    """Only seats that are unpinned BY REMIT may request any filter."""
    for role in ("system_admin", "dgp_state_command"):
        sc = scope_mod.derive_scope(role)
        assert scope_mod.enforce_geo_request(sc, unit_id=5, district_id=2) == (5, 2), role


def test_unposted_seat_is_denied_every_filter():
    """This assertion is inverted from what it used to be, deliberately.

    It previously read `test_unrestricted_seat_passes_any_filter` and asserted
    that a role-default SHO could request district 7 — because derive_scope fell
    through to "no restriction" when a posted seat had no assignment. That made an
    unposted station chief indistinguishable from the DGP. An unposted seat is now
    confined to nothing, so any filter it asks for is refused.
    """
    sc = scope_mod.derive_scope("sho")
    assert sc.scope_type == "unresolved"
    with pytest.raises(scope_mod.ScopeDenied):
        scope_mod.enforce_geo_request(sc, district_id=7)
    with pytest.raises(scope_mod.ScopeDenied):
        scope_mod.enforce_geo_request(sc, unit_id=90)


def test_posted_station_seat_is_confined_to_its_own_station():
    sc = scope_mod.derive_scope("sho", unit_id=90, district_id=3, scope_type="station")
    # An unfiltered request is narrowed to the seat's own station rather than being
    # widened to the whole district. The district comes back None because the unit
    # already implies it — adding it would be a redundant predicate, not a wider one.
    assert scope_mod.enforce_geo_request(sc) == (90, None)
    # Asking for its own district alongside its own station is still accepted.
    assert scope_mod.enforce_geo_request(sc, unit_id=90, district_id=3) == (90, 3)
    with pytest.raises(scope_mod.ScopeDenied):
        scope_mod.enforce_geo_request(sc, unit_id=91)


# ============================ API role gate ================================
def test_performance_role_gate_refuses_a_non_canonical_role():
    # INTERIM ("all roles have access to everything"): station/officer
    # performance is open to every command seat; a stale/forged role is refused.
    assert client.get("/performance/overview", headers=_hdr("wizard")).status_code == 403


# ============================ real metrics (DB) ============================
@requires_db
def test_performance_overview_shape_and_denominators():
    # A state seat, because only an unpinned seat may request an arbitrary
    # district. An `sho` header resolves to an unposted seat, which is now
    # confined to nothing and correctly refused (see
    # test_unposted_seat_is_denied_every_filter).
    r = client.get("/performance/overview", params={"district_id": 1, "window_days": 90},
                   headers=_hdr("dgp_state_command"))
    assert r.status_code == 200
    body = r.json()
    assert body["empty"] is False
    assert body["as_of"] is not None
    assert body["data_age_days"] is not None            # freshness surfaced
    t = body["totals"]
    for k in ("total_cases", "active_workload", "new_cases_in_window",
              "overdue_reviews", "stations_in_scope", "officers_in_scope"):
        assert k in t
    # ageing buckets present
    assert {b["bucket"] for b in body["ageing"]} == {"0-30d", "31-90d", "91-180d", ">180d"}
    # chargesheet throughput exposes its denominator (no bare score)
    assert "throughput_ratio_denominator" in body["chargesheet"]
    # officer load is an aggregate distribution, not a ranking
    assert "ranking" in body["officers"]["note"].lower()
    assert body["workload_balance"]["stations_compared"] >= 1
    # honest limitations are always present (no placeholder)
    assert any("synthetic" in l.lower() for l in body["limitations"])


@requires_db
def test_performance_empty_state_for_unknown_scope():
    # district id far outside the seeded range -> honest empty state, not an error.
    r = client.get("/performance/overview", params={"district_id": 999999},
                   headers=_hdr("system_admin"))
    assert r.status_code == 200
    body = r.json()
    assert body["empty"] is True
    assert body["as_of"] is None
    assert any("no cases" in l.lower() for l in body["limitations"])


@requires_db
def test_performance_super_admin_can_request_any_district():
    r = client.get("/performance/overview", params={"district_id": 2},
                   headers=_hdr("system_admin"))
    assert r.status_code == 200
    assert r.json()["scope"]["district_id"] == 2
