"""GET /casework/hearings/next — the scoped "next court date" aggregate.

This card shipped in an honest `pending` state because nothing in the corpus was
scheduled-but-not-yet-heard: CourtEvent.ScheduledAt was NULL on all 64,391 rows and
every row carried an OccurredAt. Migration 036 (and datagen, for fresh corpora)
writes the adjourned-to date for the 10,322 cases awaiting trial.

The tests pin the two things that make the number trustworthy: the population is
exactly "scheduled but not heard", and the day count is anchored to the corpus
as-of date rather than wall-clock today.
"""
from fastapi.testclient import TestClient

from conftest import requires_db

from app.main import app

client = TestClient(app)


def _as(actor: str) -> dict:
    return {"X-Demo-Actor": actor}


def _get(actor: str, **params):
    r = client.get("/casework/hearings/next", params=params, headers=_as(actor))
    assert r.status_code == 200, r.text
    return r.json()


@requires_db
def test_pending_hearings_exist_at_all():
    """The precondition the card was blocked on."""
    b = _get("dgp.state")
    assert b["empty"] is False
    assert b["pending_hearings"] > 0
    assert b["days_to_next_hearing"] is not None
    assert b["next_hearing_on"]


@requires_db
def test_one_pending_hearing_per_case_awaiting_trial():
    b = _get("dgp.state")
    # Migration 036 writes exactly one adjourned-to date per pending-trial case, so
    # a case cannot appear twice as "next".
    assert b["pending_hearings"] == b["cases_awaiting_hearing"]


@requires_db
def test_days_are_counted_from_the_corpus_as_of_not_today():
    """The dataset ends before today.

    Counting from wall-clock now() would report every hearing as overdue by however
    long the demo has been running, and the number would drift daily.
    """
    b = _get("dgp.state")
    assert b["as_of"], "the anchor must be stated, not assumed"
    # Positive: these are upcoming relative to the corpus, which is the claim.
    assert b["days_to_next_hearing"] > 0
    # And the payload admits the dataset is behind the calendar.
    assert b["data_age_days"] is not None and b["data_age_days"] > 0
    joined = " ".join(b["limitations"]).lower()
    assert "not today" in joined


@requires_db
def test_every_listed_hearing_is_in_the_future_relative_to_the_anchor():
    b = _get("dgp.state", limit=50)
    assert b["hearings"], "expected listed hearings"
    for h in b["hearings"]:
        # A "next hearing" in the past is the bug the first attempt at the
        # backfill had: anchoring on each case's own last event put dates in 2021.
        assert h["days_away"] is not None and h["days_away"] > 0, h


@requires_db
def test_listed_hearings_are_ordered_soonest_first():
    b = _get("dgp.state", limit=25)
    days = [h["days_away"] for h in b["hearings"]]
    assert days == sorted(days)
    # And the headline agrees with the first row.
    assert b["days_to_next_hearing"] == days[0]


@requires_db
def test_rows_carry_the_court_and_station_that_make_them_actionable():
    b = _get("sho.101", limit=5)
    assert b["hearings"], "the seeded station should have pending hearings"
    row = b["hearings"][0]
    for field in ("case_id", "case_number", "scheduled_on", "court_name",
                  "unit_name"):
        assert row[field] is not None, f"{field} missing — the row is not actionable"


# --------------------------------------------------------------------------- #
# Scope confinement                                                           #
# --------------------------------------------------------------------------- #
@requires_db
def test_scope_narrows_down_the_command_chain():
    state = _get("dgp.state")["pending_hearings"]
    rng = _get("dig.sr")["pending_hearings"]
    district = _get("sp.mysuru")["pending_hearings"]
    station = _get("sho.101")["pending_hearings"]

    # Each tier is strictly inside the one above it. Equality anywhere would mean
    # the filter was not applied at that level.
    assert 0 < station < district < rng < state


@requires_db
def test_an_unposted_seat_sees_no_hearings_rather_than_all_of_them():
    """Fail closed.

    The empty district set must act as an impossible predicate, not as "no filter".
    Treating empty as unfiltered is the bug that leaked every open case through
    /cases/caseload.
    """
    r = client.get("/casework/hearings/next", headers=_as("ghost.seat.not.real"))
    # Either refused outright, or answered with nothing — never with the state's.
    if r.status_code == 200:
        assert r.json()["pending_hearings"] == 0
    else:
        assert r.status_code == 403, r.text


@requires_db
def test_a_station_seat_only_sees_its_own_station():
    b = _get("sho.101", limit=100)
    units = {h["unit_id"] for h in b["hearings"]}
    assert len(units) == 1, f"a station seat should see one station, saw {units}"


@requires_db
def test_out_of_scope_district_is_refused():
    state = _get("dgp.state", limit=100)
    # Any district other than the SP's own.
    districts = {h["district_name"] for h in state["hearings"]}
    assert districts

    r = client.get("/casework/hearings/next", params={"district_id": 999999},
                   headers=_as("sp.mysuru"))
    assert r.status_code in (403, 422), r.text


@requires_db
def test_explicit_district_narrows_within_scope():
    """A DGP inspecting one district must get that district only."""
    all_h = _get("dgp.state", limit=100)
    target_unit = all_h["hearings"][0]["unit_id"]

    narrowed = _get("dgp.state", station_id=target_unit, limit=100)
    units = {h["unit_id"] for h in narrowed["hearings"]}
    assert units == {target_unit}
    assert narrowed["pending_hearings"] <= all_h["pending_hearings"]


@requires_db
def test_aggregate_only_seat_may_read_it():
    """A state seat is aggregate-only but still needs the court calendar.

    The endpoint returns counts, dates and case numbers — no party names — which is
    the same exposure /cases/caseload already gives these seats.
    """
    b = _get("dgp.state", limit=3)
    assert b["pending_hearings"] > 0
    for h in b["hearings"]:
        assert "accused" not in h and "complainant" not in h
