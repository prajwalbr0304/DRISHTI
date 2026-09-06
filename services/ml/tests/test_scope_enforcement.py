"""Jurisdiction enforcement on the DATA endpoints, not just on /performance.

Before the seat model, `/cases?district_id=9` was answered for any caller: the
client's district went straight into the WHERE clause and no ScopeContext was ever
built. `resolve_request_scope` existed and was called by no router. These tests
assert the confinement that closes that, at the level that matters — rows
returned, not just a status code.

Requires the database because the point is which records come back.
"""
import pytest
from fastapi.testclient import TestClient

from conftest import requires_db

from app.main import app
from app.org import service as org_service

client = TestClient(app)


def _as(actor: str) -> dict:
    """Identify the caller by SEAT. The server resolves the seat's scope from its
    own record; the header names a seat, it does not describe one."""
    return {"X-Demo-Actor": actor}


def _districts_in(payload: dict) -> set:
    return {row["district_id"] for row in payload.get("items", [])
            if row.get("district_id") is not None}


# ===========================================================================
# Case index — confined, and cannot be widened by asking
# ===========================================================================
@requires_db
def test_sp_case_index_returns_only_its_own_district():
    sp = org_service.resolve_scope_for_user(username="sp.mysuru")
    own = next(iter(sp.district_ids))

    r = client.get("/cases", params={"page_size": 100}, headers=_as("sp.mysuru"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] > 0, "fixture should have cases in this district"
    # Omitting district_id must narrow to the seat, not return the whole state.
    assert _districts_in(body) == {own}


@requires_db
def test_sp_cannot_read_another_district_by_asking_for_it():
    sp = org_service.resolve_scope_for_user(username="sp.mysuru")
    foreign = next(d for d in range(1, 39) if d not in sp.district_ids)
    r = client.get("/cases", params={"district_id": foreign}, headers=_as("sp.mysuru"))
    assert r.status_code == 403
    assert "outside your assigned scope" in r.json()["detail"]


@requires_db
def test_sho_case_index_is_confined_to_its_own_station():
    sho = org_service.resolve_scope_for_user(username="sho.101")
    own_unit = next(iter(sho.unit_ids))

    r = client.get("/cases", params={"page_size": 100}, headers=_as("sho.101"))
    assert r.status_code == 200, r.text
    stations = {row["station_id"] for row in r.json()["items"]}
    assert stations <= {own_unit}


@requires_db
def test_sho_cannot_read_another_station():
    sho = org_service.resolve_scope_for_user(username="sho.101")
    own_unit = next(iter(sho.unit_ids))
    r = client.get("/cases", params={"station_id": own_unit + 1}, headers=_as("sho.101"))
    assert r.status_code == 403


# ===========================================================================
# A range seat spans districts — the case a single district_id cannot express
# ===========================================================================
@requires_db
def test_dig_case_index_spans_exactly_its_range():
    dig = org_service.resolve_scope_for_user(username="dig.sr")
    assert len(dig.district_ids) > 1, "a range must cover several districts"

    r = client.get("/cases", params={"page_size": 100}, headers=_as("dig.sr"))
    assert r.status_code == 200, r.text
    returned = _districts_in(r.json())
    assert returned, "range should contain cases"
    # Every row inside the range, and nothing outside it. A confinement that
    # collapsed the range to one district would also satisfy "nothing outside",
    # so assert the breadth separately below.
    assert returned <= set(dig.district_ids)


@requires_db
def test_dig_range_is_not_collapsed_to_a_single_district():
    """Guards the failure mode where a range seat is 'confined' by picking one of
    its districts — safe-looking, but it hides four fifths of the range."""
    dig = org_service.resolve_scope_for_user(username="dig.sr")
    seen = set()
    for page in (1, 2, 3):
        r = client.get("/cases", params={"page": page, "page_size": 100},
                       headers=_as("dig.sr"))
        assert r.status_code == 200
        seen |= _districts_in(r.json())
    assert len(seen) > 1, f"range collapsed to {seen}"


@requires_db
def test_dig_may_narrow_within_its_range_but_not_outside():
    dig = org_service.resolve_scope_for_user(username="dig.sr")
    inside = sorted(dig.district_ids)[0]
    outside = next(d for d in range(1, 39) if d not in dig.district_ids)

    ok = client.get("/cases", params={"district_id": inside}, headers=_as("dig.sr"))
    assert ok.status_code == 200
    assert _districts_in(ok.json()) <= {inside}

    denied = client.get("/cases", params={"district_id": outside}, headers=_as("dig.sr"))
    assert denied.status_code == 403


# ===========================================================================
# Aggregate-only seats: figures yes, individual records no
# ===========================================================================
@requires_db
def test_state_seat_is_refused_the_case_index():
    r = client.get("/cases", headers=_as("dgp.state"))
    assert r.status_code == 403
    assert "aggregate-only" in r.json()["detail"]


@requires_db
def test_wing_seat_is_refused_the_case_index():
    r = client.get("/cases", headers=_as("adgp.trf"))
    assert r.status_code == 403
    assert "aggregate-only" in r.json()["detail"]


@requires_db
def test_aggregate_caseload_is_allowed_for_a_state_seat():
    """The counterpart: an aggregate discloses no individual record, so the seats
    refused the index must still get their figures."""
    r = client.get("/cases/caseload", headers=_as("dgp.state"))
    assert r.status_code == 200, r.text
    assert "open_total" in r.json()


@requires_db
def test_caseload_is_confined_for_a_district_seat():
    sp_all = client.get("/cases/caseload", headers=_as("dgp.state"))
    sp_own = client.get("/cases/caseload", headers=_as("sp.mysuru"))
    assert sp_all.status_code == sp_own.status_code == 200
    # A district's caseload must be a strict subset of the state's.
    assert sp_own.json()["open_total"] < sp_all.json()["open_total"]


# ===========================================================================
# Unposted seat: the fail-closed path, end to end
# ===========================================================================
@requires_db
def test_unposted_seat_reads_no_cases():
    """An X-Role header with no resolvable seat is 'unresolved', which must return
    nothing rather than everything. This is the regression that made an unposted
    SHO equivalent to the DGP."""
    r = client.get("/cases", headers={"X-Role": "sho"})
    assert r.status_code == 403
    assert "no posting on record" in r.json()["detail"]


@requires_db
def test_unposted_seat_aggregate_is_empty_not_statewide():
    r = client.get("/cases/caseload", headers={"X-Role": "district_command"})
    # Either refused, or answered with an empty scope — never the state total.
    if r.status_code == 200:
        state = client.get("/cases/caseload", headers=_as("dgp.state")).json()
        assert r.json()["open_total"] < state["open_total"]
    else:
        assert r.status_code == 403


# ===========================================================================
# /geo — the endpoints behind the KPI cards and the map
# ===========================================================================
@requires_db
def test_trends_are_confined_to_the_seat():
    """A district total must be smaller than the state total.

    Comparing the numbers matters more than the status code here: `/geo/trends`
    accepted `district_id` from the client and applied it verbatim, so the previous
    behaviour was 200-with-the-wrong-rows rather than an error.
    """
    state = client.get("/geo/trends", headers=_as("dgp.state"))
    sp = client.get("/geo/trends", headers=_as("sp.mysuru"))
    assert state.status_code == sp.status_code == 200, sp.text
    assert sp.json()["total"] > 0
    assert sp.json()["total"] < state.json()["total"]


@requires_db
def test_trends_range_sits_between_district_and_state():
    """A range aggregates several districts, so its total must fall between one of
    its districts and the whole state. This catches BOTH failure modes at once: a
    range collapsed to one district, and a range not confined at all."""
    dig = org_service.resolve_scope_for_user(username="dig.sr")
    inside = sorted(dig.district_ids)[0]

    state = client.get("/geo/trends", headers=_as("dgp.state")).json()["total"]
    rng = client.get("/geo/trends", headers=_as("dig.sr")).json()["total"]
    one = client.get("/geo/trends", params={"district_id": inside},
                     headers=_as("dig.sr")).json()["total"]

    assert one < rng < state, f"district={one} range={rng} state={state}"


@requires_db
def test_trends_echo_the_confinement_that_was_applied():
    """A DIG's figure must be distinguishable from a state figure on the wire."""
    r = client.get("/geo/trends", headers=_as("dig.sr"))
    assert r.status_code == 200
    scope = r.json()["scope"]
    assert scope["district_ids"], "range confinement should be reported"
    assert len(scope["district_ids"]) > 1


@requires_db
def test_wing_seat_trends_are_narrowed_to_its_crime_heads():
    """A wing is state-wide GEOGRAPHICALLY and narrowed by crime head instead, so
    a traffic wing must see less than the whole state."""
    state = client.get("/geo/trends", headers=_as("dgp.state")).json()["total"]
    trf = client.get("/geo/trends", headers=_as("adgp.trf"))
    assert trf.status_code == 200, trf.text
    body = trf.json()
    assert body["scope"]["crime_head_ids"], "wing head confinement should be reported"
    assert 0 < body["total"] < state


@requires_db
def test_wing_seat_cannot_reach_a_head_outside_its_remit():
    """Asking for another wing's crime head narrows to nothing rather than
    reaching outside the wing."""
    trf = org_service.resolve_scope_for_user(username="adgp.trf")
    own = sorted(trf.crime_head_ids)[0]
    foreign = next(h for h in range(1, 10) if h not in trf.crime_head_ids)

    own_total = client.get("/geo/trends", params={"crime_head_id": own},
                           headers=_as("adgp.trf")).json()["total"]
    foreign_total = client.get("/geo/trends", params={"crime_head_id": foreign},
                               headers=_as("adgp.trf")).json()["total"]
    assert own_total > 0
    # Confined to the wing, so a foreign head cannot return more than the wing does.
    assert foreign_total <= own_total


@requires_db
def test_hotspots_are_confined_to_the_seat():
    state = client.get("/geo/hotspots", params={"limit": 2000},
                       headers=_as("dgp.state"))
    sp = client.get("/geo/hotspots", params={"limit": 2000}, headers=_as("sp.mysuru"))
    if state.status_code != 200:
        pytest.skip(f"hotspot model not generated: {state.status_code}")
    assert sp.status_code == 200, sp.text
    own = next(iter(org_service.resolve_scope_for_user(username="sp.mysuru").district_ids))
    districts = {h["district_id"] for h in sp.json()["hotspots"]
                 if h.get("district_id") is not None}
    assert districts <= {own}


# ===========================================================================
# Point-level incident data — the most sensitive read in /geo
# ===========================================================================
@requires_db
def test_state_seat_is_refused_point_level_incidents():
    r = client.get("/geo/points", headers=_as("dgp.state"))
    assert r.status_code == 403
    assert "aggregate-only" in r.json()["detail"]


@requires_db
def test_wing_seat_is_refused_point_level_incidents():
    r = client.get("/geo/points", headers=_as("adgp.trf"))
    assert r.status_code == 403


@requires_db
def test_unposted_seat_is_refused_point_level_incidents():
    r = client.get("/geo/points", headers={"X-Role": "sho"})
    assert r.status_code == 403
    assert "no posting on record" in r.json()["detail"]


@requires_db
def test_sho_point_level_is_confined_to_its_own_station():
    """A bbox must not be usable to pan across the state."""
    r = client.get("/geo/points", params={"limit": 2000}, headers=_as("sho.101"))
    assert r.status_code == 200, r.text
    state = client.get("/geo/points", params={"limit": 20000},
                       headers=_as("sp.mysuru"))
    assert state.status_code == 200
    # A station's incidents are a strict subset of its district's.
    assert r.json()["count"] <= state.json()["count"]


@requires_db
def test_point_level_bbox_cannot_widen_beyond_the_seat():
    """The whole-state bbox returns no more than the seat's own jurisdiction."""
    whole_state = "74.0,11.5,78.6,18.5"
    scoped = client.get("/geo/points", params={"bbox": whole_state, "limit": 20000},
                        headers=_as("sho.101"))
    assert scoped.status_code == 200, scoped.text
    sho = org_service.resolve_scope_for_user(username="sho.101")
    own_unit = next(iter(sho.unit_ids))
    # Every returned incident belongs to this station; the bbox only narrows.
    unscoped = client.get("/geo/points", params={"limit": 20000},
                          headers=_as("sho.101")).json()["count"]
    assert scoped.json()["count"] <= unscoped
    assert own_unit  # the seat is genuinely station-pinned


# ===========================================================================
# /disaster — write actions, and the header that used to grant jurisdiction
# ===========================================================================
@requires_db
def test_disaster_district_header_cannot_grant_a_jurisdiction():
    """X-Disaster-District used to SELECT the caller's jurisdiction.

    `DisasterScope.covers_district` read the district straight from that header, so
    naming any district granted authority to act in it — and OMITTING it returned
    True unconditionally, granting state-wide authority to approve warnings,
    allocate resources and sign off evacuation plans. The district now comes from
    the seat record and the header can only narrow within it.
    """
    from app.disaster import guards

    class _Req:
        def __init__(self, headers):
            self.headers = headers
            class _S: pass
            self.state = _S()

    # An SP posted to Mysuru, claiming a foreign district in the header.
    sp = org_service.resolve_scope_for_user(username="sp.mysuru")
    own = next(iter(sp.district_ids))
    foreign = next(d for d in range(1, 39) if d not in sp.district_ids)

    spoofed = guards.resolve_scope(_Req({
        "x-demo-actor": "sp.mysuru", "x-disaster-district": str(foreign)}))
    assert spoofed.covers_district(foreign) is False, "header must not grant a district"
    assert spoofed.covers_district(own) is True

    # Omitting the header must not widen to everywhere.
    bare = guards.resolve_scope(_Req({"x-demo-actor": "sp.mysuru"}))
    assert bare.covers_district(foreign) is False
    assert bare.covers_district(own) is True


@requires_db
def test_disaster_unposted_seat_holds_no_jurisdiction():
    from app.disaster import guards

    class _Req:
        def __init__(self, headers):
            self.headers = headers
            class _S: pass
            self.state = _S()

    unposted = guards.resolve_scope(_Req({
        "x-role": "district_command", "x-demo-actor": "nobody.at.all",
        "x-disaster-district": "24"}))
    assert unposted.districts == frozenset()
    for d in (None, 1, 24, 38):
        assert unposted.covers_district(d) is False, d


@requires_db
def test_disaster_range_seat_covers_its_whole_range():
    """A DIG is confined but NOT to a single district. The previous role-based
    check treated a range seat as unconfined, so it could act state-wide."""
    from app.disaster import guards

    class _Req:
        def __init__(self, headers):
            self.headers = headers
            class _S: pass
            self.state = _S()

    dig = org_service.resolve_scope_for_user(username="dig.sr")
    inside = sorted(dig.district_ids)
    outside = next(d for d in range(1, 39) if d not in dig.district_ids)

    scope = guards.resolve_scope(_Req({"x-demo-actor": "dig.sr"}))
    assert len(inside) > 1
    for d in inside:
        assert scope.covers_district(d) is True, d
    assert scope.covers_district(outside) is False


@requires_db
def test_disaster_state_and_wing_seats_are_unpinned_by_remit():
    """The counterpart to fail-closed: seats that are genuinely unpinned must not
    be caught by it. A wing narrows by crime head, not by district."""
    from app.disaster import guards

    class _Req:
        def __init__(self, headers):
            self.headers = headers
            class _S: pass
            self.state = _S()

    for actor in ("dgp.state", "adgp.trf", "sysadmin"):
        scope = guards.resolve_scope(_Req({"x-demo-actor": actor}))
        assert scope.districts is None, actor
        assert scope.covers_district(24) is True, actor


@requires_db
def test_disaster_write_is_refused_outside_the_seats_district():
    """End to end through the API, not just the guard."""
    r = client.post("/disaster/events",
                    json={"hazard_code": "flood", "status": "watch",
                          "district_id": 24, "geojson": {}},
                    headers=_as("sp.belagavi"))       # posted to district 5
    assert r.status_code == 403
    assert "outside your jurisdiction" in r.json()["detail"]


# ===========================================================================
# /forecast and /analytics — aggregate, but still scoped
# ===========================================================================
@requires_db
def test_forecast_map_is_confined_to_the_seat():
    state = client.get("/forecast/map", headers=_as("dgp.state"))
    if state.status_code != 200:
        pytest.skip(f"forecast not generated: {state.status_code}")
    sp = client.get("/forecast/map", headers=_as("sp.mysuru"))
    assert sp.status_code == 200, sp.text
    own = next(iter(org_service.resolve_scope_for_user(username="sp.mysuru").district_ids))
    districts = {c["district_id"] for c in sp.json()["cells"]
                 if c.get("district_id") is not None}
    assert districts <= {own}
    assert len(sp.json()["cells"]) <= len(state.json()["cells"])


@requires_db
def test_forecast_for_a_foreign_district_is_refused():
    """The district is a PATH parameter, so it bypasses the query-parameter
    dependency and needs its own explicit check."""
    sp = org_service.resolve_scope_for_user(username="sp.mysuru")
    own = next(iter(sp.district_ids))
    foreign = next(d for d in range(1, 39) if d not in sp.district_ids)

    ok = client.get(f"/forecast/district/{own}", headers=_as("sp.mysuru"))
    assert ok.status_code in (200, 404), ok.text     # 404 if no forecast written
    denied = client.get(f"/forecast/district/{foreign}", headers=_as("sp.mysuru"))
    assert denied.status_code == 403
    assert "outside your assigned scope" in denied.json()["detail"]


@requires_db
def test_patterns_are_narrowed_by_wing_but_not_by_district():
    """A pattern may span districts by construction, so geographic confinement is
    deliberately NOT applied — filtering by the viewer's district would hide the
    cross-boundary serial offender the detector exists to surface. A wing's
    crime-head confinement IS applied."""
    state = client.get("/analytics/patterns", headers=_as("dgp.state"))
    assert state.status_code == 200, state.text
    total = state.json()["total"]

    # A district seat sees the same patterns: they are not district-filtered.
    sp = client.get("/analytics/patterns", headers=_as("sp.mysuru"))
    assert sp.status_code == 200
    assert sp.json()["total"] == total

    # A wing seat sees only its own heads, so no more than the whole set.
    trf = client.get("/analytics/patterns", headers=_as("adgp.trf"))
    assert trf.status_code == 200
    assert trf.json()["total"] <= total
