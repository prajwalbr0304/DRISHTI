"""GET /performance/districts — the range and wing league table.

Replaces a client-side approximation that summed HOTSPOT case counts per district.
Hotspots are a modelled concentration, not a workload, so a district with dispersed
crime read as idle. These tests pin that the endpoint answers the workload question
and stays inside the caller's seat.
"""
from fastapi.testclient import TestClient

from conftest import requires_db

from app.main import app

client = TestClient(app)


def _as(actor: str) -> dict:
    return {"X-Demo-Actor": actor}


@requires_db
def test_state_seat_sees_every_district():
    r = client.get("/performance/districts", headers=_as("dgp.state"))
    assert r.status_code == 200, r.text
    b = r.json()

    assert b["empty"] is False
    # 38 district-level units after migration 034; the cap is 60, so none is lost.
    assert b["totals"]["districts_compared"] > 30
    assert len(b["districts"]) == b["totals"]["districts_compared"]


@requires_db
def test_rows_carry_the_denominators_that_make_the_count_readable():
    r = client.get("/performance/districts", headers=_as("dgp.state"))
    row = r.json()["districts"][0]

    # open_cases alone invites a ranking. The denominators are what turn it into
    # workload: a district with 40 stations and one with 8 are not comparable.
    for field in ("district_name", "stations", "officers", "new_cases",
                  "total_cases", "overdue"):
        assert field in row, f"{field} missing from the league-table row"
    assert row["stations"] > 0
    assert row["total_cases"] >= row["open_cases"]


@requires_db
def test_chargesheet_rate_is_null_not_zero_when_no_new_cases():
    """A district that registered nothing in the window has no rate.

    0% would read as a failure to file; the absence of a denominator is a
    different statement.
    """
    r = client.get("/performance/districts",
                   params={"window_days": 1}, headers=_as("dgp.state"))
    assert r.status_code == 200, r.text
    rows = r.json()["districts"]
    # With a one-day window most districts register nothing, so at least one row
    # must decline to report a rate rather than claiming zero.
    nulls = [d for d in rows if d["new_cases"] == 0]
    assert nulls, "expected districts with no new cases in a 1-day window"
    for d in nulls:
        assert d["chargesheet_rate"] is None


@requires_db
def test_a_range_seat_sees_only_its_own_districts():
    state = client.get("/performance/districts", headers=_as("dgp.state")).json()
    rng = client.get("/performance/districts", headers=_as("dig.sr")).json()

    assert rng["empty"] is False
    state_ids = {d["district_id"] for d in state["districts"]}
    range_ids = {d["district_id"] for d in rng["districts"]}

    # A DIG compares the districts of one range, not the state.
    assert range_ids, "the range seat should see its own districts"
    assert range_ids < state_ids, "a range must be a strict subset of the state"
    assert len(range_ids) <= 10, "a Karnataka range covers a handful of districts"


@requires_db
def test_a_district_seat_sees_one_row():
    r = client.get("/performance/districts", headers=_as("sp.mysuru"))
    assert r.status_code == 200, r.text
    rows = r.json()["districts"]
    # Honest rather than useful: an SP's "league table" is their own district. The
    # widget is only placed on the wing and range boards for exactly this reason.
    assert len(rows) == 1


@requires_db
def test_a_station_seat_is_confined_to_its_district():
    r = client.get("/performance/districts", headers=_as("sho.101"))
    assert r.status_code == 200, r.text
    rows = r.json()["districts"]
    assert len(rows) <= 1


@requires_db
def test_an_explicit_district_narrows_within_scope():
    """A DGP inspecting one district must get that district, not all of them.

    This is the confinement bug that is easy to reintroduce: a service handed only
    the seat's full set ignores the narrowing and returns everything, which looks
    correct because nothing out of scope leaked.
    """
    state = client.get("/performance/districts", headers=_as("dgp.state")).json()
    target = state["districts"][0]["district_id"]

    r = client.get("/performance/districts",
                   params={"district_id": target}, headers=_as("dgp.state"))
    assert r.status_code == 200, r.text
    rows = r.json()["districts"]
    assert len(rows) == 1
    assert rows[0]["district_id"] == target


@requires_db
def test_out_of_scope_district_is_refused_not_silently_widened():
    state = client.get("/performance/districts", headers=_as("dgp.state")).json()
    ids = [d["district_id"] for d in state["districts"]]

    sp = client.get("/performance/districts", headers=_as("sp.mysuru")).json()
    own = sp["districts"][0]["district_id"]
    other = next(i for i in ids if i != own)

    r = client.get("/performance/districts",
                   params={"district_id": other}, headers=_as("sp.mysuru"))
    assert r.status_code == 403, r.text


@requires_db
def test_totals_reconcile_with_the_rows():
    b = client.get("/performance/districts", headers=_as("dgp.state")).json()
    rows = b["districts"]
    assert b["totals"]["open_cases"] == sum(d["open_cases"] for d in rows)
    assert b["totals"]["total_cases"] == sum(d["total_cases"] for d in rows)


@requires_db
def test_chargesheets_do_not_inflate_the_case_counts():
    """ChargesheetDetails is one-to-many per case.

    Joining it into the main aggregate would multiply the case rows, so a district
    with several chargesheets per case would report more open cases than it has.
    The counts here must still agree with /performance/overview for one district.
    """
    b = client.get("/performance/districts", headers=_as("sp.mysuru")).json()
    row = b["districts"][0]

    ov = client.get("/performance/overview",
                    params={"window_days": b["window_days"]},
                    headers=_as("sp.mysuru")).json()
    assert row["total_cases"] == ov["totals"]["total_cases"]
    assert row["open_cases"] == ov["totals"]["active_workload"]


@requires_db
def test_reports_its_limitations_and_data_age():
    b = client.get("/performance/districts", headers=_as("dgp.state")).json()
    assert b["as_of"], "the window is relative to the data, so as_of must be stated"
    assert b["data_age_days"] is not None
    joined = " ".join(b["limitations"]).lower()
    # The comparison is the thing most likely to be misread, so the caveat has to
    # travel with the payload.
    assert "population" in joined
