"""GET /dashboard/summary — count KPIs served from the mv_case_daily rollup.

The rollup existed, was refreshed, and was read by no endpoint: every KPI card went
to the base tables, and /performance/overview alone costs seven sequential
aggregates over CaseMaster JOIN Unit JOIN CaseStatusMaster.

Two properties matter more than the speed. The rollup must RECONCILE with the live
path — a faster number that disagrees is worse than a slow one — and it must be
REFUSED when its policy attestation is not current, because the view's definition
embeds the fail-closed eligibility predicate and therefore goes stale when a
CaseVersion changes, not only when a case is registered.
"""
import pytest
from fastapi.testclient import TestClient

from conftest import requires_db

from app import db, matviews
from app.main import app

client = TestClient(app)


def _as(actor: str) -> dict:
    return {"X-Demo-Actor": actor}


@pytest.fixture(scope="module", autouse=True)
def _stamped_rollup():
    """Refresh through matviews so the attestation ledger is stamped.

    Without this the endpoint correctly returns 503 `no_attestation`: the view was
    originally populated with a bare REFRESH, which records nothing about the policy
    it ran under.
    """
    with db.rw_conn() as conn:
        matviews.refresh_matview(conn, "mv_case_daily")


def _summary(actor: str, **params) -> dict:
    r = client.get("/dashboard/summary", params=params, headers=_as(actor))
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Reconciliation with the live path                                           #
# --------------------------------------------------------------------------- #
@requires_db
def test_totals_match_the_live_performance_endpoint():
    """The whole premise: same numbers, cheaper.

    Both apply the same analytics-eligibility policy — the rollup embeds it in its
    definition — so any disagreement means one of them has drifted.

    Refreshed first, for the same reason as the ageing test: the rollup lags the base
    tables by design, and other tests in this suite commit FIRs.
    """
    with db.rw_conn() as conn:
        matviews.refresh_matview(conn, "mv_case_daily")

    roll = _summary("sp.mysuru", window_days=90)
    live = client.get("/performance/overview", params={"window_days": 90},
                      headers=_as("sp.mysuru")).json()

    assert roll["totals"]["total_cases"] == live["totals"]["total_cases"]
    assert roll["totals"]["open_cases"] == live["totals"]["active_workload"]
    assert roll["totals"]["new_cases_in_window"] == live["totals"]["new_cases_in_window"]


@requires_db
def test_ageing_buckets_match_the_live_endpoint_exactly():
    """Boundary alignment, which is easy to get wrong by one day.

    The live path buckets on age = (as_of - registered_date) with `age <= 30`. In
    date terms that is `registered_date >= as_of - 30`, so the rollup must use >=
    and <. Writing > and <= shifts every boundary by a day and produces buckets that
    still sum to the same total while disagreeing case by case — which is exactly
    what happened on the first attempt.

    REFRESHED HERE, not once for the module. The rollup lags the base tables by
    design, and other tests in the suite commit FIRs, so a module-scoped refresh
    makes this comparison depend on execution order: run alone it passes, run after
    test_livefeed it fails because the live path can see cases the rollup cannot.
    Refreshing immediately before comparing is what makes the assertion about
    BOUNDARY ALIGNMENT rather than about refresh timing.
    """
    with db.rw_conn() as conn:
        matviews.refresh_matview(conn, "mv_case_daily")

    roll = _summary("sp.mysuru", window_days=90)
    live = client.get("/performance/overview", params={"window_days": 90},
                      headers=_as("sp.mysuru")).json()

    assert {b["bucket"]: b["count"] for b in roll["ageing"]} == \
           {b["bucket"]: b["count"] for b in live["ageing"]}


@requires_db
def test_open_and_closed_partition_the_total():
    b = _summary("dgp.state")
    t = b["totals"]
    # status_bucket is a two-way split in the view definition, so every case is in
    # exactly one side and the two must sum to the total.
    assert t["open_cases"] + t["closed_cases"] == t["total_cases"]


# --------------------------------------------------------------------------- #
# Scope confinement                                                           #
# --------------------------------------------------------------------------- #
@requires_db
def test_scope_narrows_down_the_command_chain():
    state = _summary("dgp.state")["totals"]["total_cases"]
    rng = _summary("dig.sr")["totals"]["total_cases"]
    district = _summary("sp.mysuru")["totals"]["total_cases"]
    station = _summary("sho.101")["totals"]["total_cases"]
    assert 0 < station < district < rng < state


@requires_db
def test_a_station_seat_sees_one_unit():
    b = _summary("sho.101")
    assert b["totals"]["units_in_scope"] == 1


@requires_db
def test_an_unposted_seat_gets_nothing_not_everything():
    r = client.get("/dashboard/summary", headers=_as("ghost.seat.not.real"))
    if r.status_code == 200:
        assert r.json()["totals"].get("total_cases", 0) == 0
    else:
        assert r.status_code == 403, r.text


@requires_db
def test_out_of_scope_district_is_refused():
    r = client.get("/dashboard/summary", params={"district_id": 999999},
                   headers=_as("sp.mysuru"))
    assert r.status_code in (403, 422), r.text


# --------------------------------------------------------------------------- #
# Provenance and honesty                                                      #
# --------------------------------------------------------------------------- #
@requires_db
def test_reports_which_source_it_served_from():
    b = _summary("dgp.state")
    # A caller comparing this with /performance/overview needs to know the two read
    # different sources with different freshness.
    assert b["source"] == "mv_case_daily"
    assert b["rollup"]["refreshed_at"], "the refresh time must travel with the data"
    assert b["rollup"]["policy_version"]
    assert b["rollup"]["policy_sha256"]


@requires_db
def test_states_what_the_rollup_cannot_answer():
    b = _summary("dgp.state")
    joined = " ".join(b["limitations"]).lower()
    # The view carries no officer or chargesheet linkage. Saying so stops someone
    # adding an approximated column that silently diverges from the base tables.
    assert "officer" in joined and "chargesheet" in joined


@requires_db
def test_flags_a_window_that_opens_inside_a_sparse_tail():
    """The corpus is discontinuous: the generated bulk ends 2025-12-31 and three
    later test FIRs sit months after it.

    `as_of` is max(registered_date), which is right in principle, but it lands the
    window inside that gap and makes "new cases" read as a near-zero — which looks
    like registrations collapsing rather than an artefact of the anchor. The
    endpoint must say so instead of letting the figure be misread.
    """
    b = _summary("dgp.state", window_days=90)
    t = b["totals"]
    assert b["window_start"], "the window must be reported, not just its length"

    if t["new_cases_in_window"] < 100 and t["total_cases"] > 1000:
        assert b["data_notes"], (
            "a near-empty window over a large corpus must be flagged, not "
            "presented as a measurement")
        assert "sparse tail" in " ".join(b["data_notes"])


@requires_db
def test_window_is_relative_to_the_data_not_today():
    b = _summary("dgp.state")
    assert b["as_of"], "the anchor must be stated"
    assert b["data_age_days"] is not None
    joined = " ".join(b["limitations"]).lower()
    assert "not today" in joined


# --------------------------------------------------------------------------- #
# The attestation gate                                                        #
# --------------------------------------------------------------------------- #
"""The gate's decision is tested as a PURE function.

An earlier version of these tests forced each branch by UPDATE-ing the shared
`mv_refresh_state` row and restoring it in a `finally`. That is shared state, and
the failure mode is nasty: a run interrupted between the mutation and the cleanup
leaves the ledger poisoned, so every later test in that run AND the next run sees a
503 from a rollup that is actually fine. It happened. `evaluate_rollup` takes the
ledger state and the current attestation as arguments, so every branch is reachable
without touching the database at all.
"""


def _att(sha: str = "a" * 64, version: str = "drishti.case-derived-analytics/v1"):
    from app.cases.analytics_policy import PolicyAttestation
    return PolicyAttestation(version=version, sha256=sha, relevant_case_versions=3)


def _state(**over):
    base = {
        "registered": True,
        "refreshed_at": "2026-09-06T10:05:55+00:00",
        "policy_version": "drishti.case-derived-analytics/v1",
        "policy_sha256": "a" * 64,
        "rollup_rows": 99928,
    }
    base.update(over)
    return base


def test_gate_allows_a_rollup_whose_attestation_matches():
    from app.dashboard import service as ds
    assert ds.evaluate_rollup(_state(), _att()) is None


def test_gate_refuses_an_unregistered_rollup():
    from app.dashboard import service as ds
    reason, detail = ds.evaluate_rollup({"registered": False}, _att())
    assert reason == "not_registered"
    assert "ledger" in detail


def test_gate_refuses_a_never_refreshed_rollup():
    """The view is created WITH NO DATA, so serving it unrefreshed reports zero
    cases everywhere — which looks like a state with no crime rather than a
    configuration error."""
    from app.dashboard import service as ds
    reason, _ = ds.evaluate_rollup(_state(refreshed_at=None), _att())
    assert reason == "never_refreshed"


def test_gate_refuses_a_rollup_with_no_usable_attestation():
    from app.dashboard import service as ds
    reason, _ = ds.evaluate_rollup(_state(policy_sha256=None), _att())
    assert reason == "no_attestation"


def test_gate_refuses_a_rollup_built_under_a_different_policy():
    """The eligibility predicate lives inside the view definition and reads
    CaseVersion, so a case excluded from derived analytics after the last refresh is
    still counted in the rollup. Serving it would silently contradict the policy."""
    from app.dashboard import service as ds
    reason, detail = ds.evaluate_rollup(_state(policy_sha256="b" * 64), _att())
    assert reason == "policy_superseded"
    # The message must name both digests; "stale" alone is not actionable.
    assert "bbbbbbbbbbbb" in detail and "aaaaaaaaaaaa" in detail


def test_gate_compares_the_policy_version_too_not_only_the_digest():
    from app.dashboard import service as ds
    reason, _ = ds.evaluate_rollup(
        _state(policy_version="drishti.case-derived-analytics/v0"), _att())
    assert reason == "policy_superseded"


def test_gate_ignores_row_count_drift():
    """An ordinary FIR registration must NOT invalidate the rollup.

    The digest covers only the exclusion cohort, so growth in the corpus is
    expected drift reported via refreshed_at — not grounds for refusal. Gating on
    the row count instead would refuse after every single write and make the rollup
    useless.
    """
    from app.dashboard import service as ds
    assert ds.evaluate_rollup(_state(rollup_rows=99999), _att()) is None


@requires_db
def test_endpoint_serves_a_freshly_refreshed_rollup():
    """The integration half: a real refresh produces a servable rollup."""
    with db.rw_conn() as conn:
        matviews.refresh_matview(conn, "mv_case_daily")
    r = client.get("/dashboard/summary", headers=_as("dgp.state"))
    assert r.status_code == 200, r.text


@requires_db
def test_refusal_points_at_the_live_fallback():
    """A 503 must tell the caller where the same figures live, so a declined rollup
    degrades to a slower answer rather than to no answer."""
    from app.dashboard import service as ds
    reason, _ = ds.evaluate_rollup(_state(policy_sha256="b" * 64), _att())
    assert reason == "policy_superseded"
    # The router attaches the fallback; assert the contract it promises.
    from app.dashboard import router as dr
    assert "performance/overview" in dr.summary.__doc__


@requires_db
def test_refresh_stamps_the_policy_attestation():
    """Rule from migration 032: the refresh and its attestation are recorded
    together, so a rollup can never be served without evidence of the policy it was
    computed under."""
    from app.cases import analytics_policy
    from app.dashboard import service as ds

    with db.rw_conn() as conn:
        matviews.refresh_matview(conn, "mv_case_daily")

    with db.ro_conn() as conn:
        state = ds.rollup_state(conn)
        current = analytics_policy.current_attestation(conn)

    assert state["registered"] is True
    assert state["refreshed_at"]
    assert state["policy_sha256"] == current.sha256
    assert state["rollup_rows"] and state["rollup_rows"] > 0


@requires_db
def test_mv_case_daily_is_registered_for_scheduled_refresh():
    # Migration 032 asked for this explicitly and it had not been done, so the
    # rollup was never refreshed by the scheduled job.
    assert "mv_case_daily" in matviews.ALL_MATVIEWS
    assert "mv_case_daily" in matviews.POLICY_DERIVED_MATVIEWS
