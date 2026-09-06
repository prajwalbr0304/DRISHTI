"""Aggregate court outcomes: the conviction rate, and what its denominator is.

The card this backs sat in a `pending` state because the data was reachable only
per case, and the seats that need the metric are exactly the ones that must not
read case rows. These tests pin the arithmetic and the confinement.
"""
import pytest
from fastapi.testclient import TestClient

from conftest import requires_db

from app.main import app
from app.org import service as org_service

client = TestClient(app)


def _as(actor: str) -> dict:
    return {"X-Demo-Actor": actor}


@requires_db
def test_conviction_rate_counts_only_cases_that_reached_a_verdict():
    """The denominator is convictions + acquittals, NOT all disposals.

    A B-report (undetected) and a C-report (false complaint) are decisions not to
    prosecute. Counting them as failed convictions would conflate "never went to
    court" with "lost in court" and understate court performance — on this dataset
    it would report roughly 16% instead of roughly 54%.
    """
    r = client.get("/outcomes/overview", headers=_as("dgp.state"))
    assert r.status_code == 200, r.text
    b = r.json()

    assert b["verdicts"] == b["convicted"] + b["acquitted"]
    assert b["verdicts"] > 0, "fixture should contain verdicts"
    expected = round(b["convicted"] / b["verdicts"], 4)
    assert b["conviction_rate"] == expected

    # And the wider mix is strictly larger, proving the denominators differ.
    assert b["total_disposed"] > b["verdicts"]
    naive = b["convicted"] / b["total_disposed"]
    assert b["conviction_rate"] > naive


@requires_db
def test_breakdown_covers_every_disposal_and_shares_sum_to_one():
    r = client.get("/outcomes/overview", headers=_as("dgp.state"))
    b = r.json()
    assert sum(d["count"] for d in b["breakdown"]) == b["total_disposed"]
    shares = sum(d["share_of_disposed"] for d in b["breakdown"])
    assert abs(shares - 1.0) < 0.01
    # B- and C-reports are reported, not silently folded into the rate.
    kinds = {d["disposition_type"] for d in b["breakdown"]}
    assert "closed_b_report" in kinds


@requires_db
def test_no_verdicts_reports_null_rather_than_a_zero_percent_rate():
    """"No verdicts yet" is not "a 0% conviction rate"."""
    r = client.get("/outcomes/overview", params={"window_days": 1},
                   headers=_as("sho.101"))
    assert r.status_code == 200, r.text
    b = r.json()
    if b["verdicts"] == 0:
        assert b["conviction_rate"] is None
    else:
        assert b["conviction_rate"] is not None


@requires_db
def test_outcomes_are_confined_to_the_seat():
    state = client.get("/outcomes/overview", headers=_as("dgp.state")).json()
    sp = client.get("/outcomes/overview", headers=_as("sp.mysuru"))
    assert sp.status_code == 200, sp.text
    own = next(iter(org_service.resolve_scope_for_user(username="sp.mysuru").district_ids))
    assert sp.json()["scope"]["district_ids"] == [own]
    assert sp.json()["total_disposed"] < state["total_disposed"]


@requires_db
def test_range_outcomes_sit_between_district_and_state():
    dig = org_service.resolve_scope_for_user(username="dig.sr")
    inside = sorted(dig.district_ids)[0]

    state = client.get("/outcomes/overview", headers=_as("dgp.state")).json()["total_disposed"]
    rng = client.get("/outcomes/overview", headers=_as("dig.sr")).json()["total_disposed"]
    one = client.get("/outcomes/overview", params={"district_id": inside},
                     headers=_as("dig.sr")).json()["total_disposed"]
    assert one < rng < state


@requires_db
def test_aggregate_only_seats_may_read_outcomes():
    """The point of the endpoint: the seats refused case rows still get the metric
    they are accountable for."""
    for actor in ("dgp.state", "adgp.cts"):
        r = client.get("/outcomes/overview", headers=_as(actor))
        assert r.status_code == 200, (actor, r.text)
        assert r.json()["total_disposed"] > 0, actor


@requires_db
def test_unposted_seat_reads_no_outcomes():
    r = client.get("/outcomes/overview", headers={"X-Role": "sho"})
    assert r.status_code == 403
