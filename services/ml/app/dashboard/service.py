"""Dashboard summary served from the mv_case_daily rollup.

WHY A ROLLUP AT ALL
Every KPI card reads base tables live. /performance/overview alone is seven
sequential aggregates over CaseMaster JOIN Unit JOIN CaseStatusMaster; unfiltered,
each is a full scan. mv_case_daily pre-aggregates to one row per
(unit, crime head, registered date, status), which is bounded by the case count
rather than the product of its keys, and carries district_id denormalised so the
Unit join disappears.

WHAT IT CANNOT ANSWER
The rollup has no PolicePersonID and no chargesheet linkage, so officer-load
distribution and chargesheet throughput are NOT servable from it and stay on
/performance/overview. This module answers the count questions only and says so,
rather than inventing a rollup column that would silently diverge from the base
tables it is meant to summarise.

STALENESS IS A REFUSAL, NOT A CAVEAT
The view's definition embeds the fail-closed analytics-eligibility predicate, which
reads CaseVersion. It therefore goes stale when a case VERSION changes, not only
when a case is registered — a case excluded from derived analytics after the last
refresh is still counted in it. mv_refresh_state records the policy attestation each
refresh ran under; if that no longer matches the current one, the rollup is
serving figures computed under a superseded policy and this module declines it so
the caller can fall back to the live path.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .. import db
from ..cases import analytics_policy


class RollupUnavailable(RuntimeError):
    """The rollup cannot be trusted for this request.

    Carries the reason so the caller can report which of the three cases it hit —
    never refreshed, superseded policy, or absent attestation — rather than a bare
    "unavailable" that reads as a fault.
    """

    def __init__(self, reason: str, *, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def rollup_state(conn) -> dict:
    """The rollup's freshness and policy attestation, without serving from it."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "refreshed_at", "policy_version", "policy_sha256", '
            '       "source_row_count", "refresh_seconds", "refreshed_by" '
            '  FROM "mv_refresh_state" WHERE "matview_name" = %s',
            ("mv_case_daily",))
        row = cur.fetchone()
    if row is None:
        return {"registered": False}
    return {
        "registered": True,
        "refreshed_at": row[0].isoformat() if row[0] else None,
        "policy_version": row[1],
        "policy_sha256": row[2],
        "rollup_rows": int(row[3]) if row[3] is not None else None,
        "refresh_seconds": float(row[4]) if row[4] is not None else None,
        "refreshed_by": row[5],
    }


def evaluate_rollup(state: dict, current) -> Optional[tuple[str, str]]:
    """Decide whether the rollup may be served. ``None`` means yes.

    PURE, and separated from the database read on purpose. The decision is the part
    worth testing exhaustively — three distinct refusal reasons — and testing it
    through the endpoint meant mutating the shared `mv_refresh_state` row to force
    each branch. That is shared state: a run interrupted between the mutation and
    its cleanup leaves the ledger poisoned for every later test and for the next
    run, which is exactly what happened. A pure function needs no such fixture.
    """
    if not state.get("registered"):
        return ("not_registered",
                "mv_case_daily has no refresh ledger entry, so nothing records "
                "which policy it was built under.")
    if not state.get("refreshed_at"):
        return ("never_refreshed",
                "mv_case_daily has never been refreshed. It is created WITH NO "
                "DATA, so serving it would report zero cases everywhere.")

    stamped = analytics_policy.coerce_attestation({
        "version": state.get("policy_version"),
        "sha256": state.get("policy_sha256"),
        "relevant_case_versions": state.get("rollup_rows"),
    })
    if stamped is None:
        return ("no_attestation",
                "mv_case_daily carries no usable policy attestation, so there is "
                "no evidence it applied the current eligibility rules.")

    # Compared on the policy identity — version plus digest. The digest covers only
    # the EXCLUSION COHORT (current CaseVersions that are excluded or public-source
    # curated), not every case version, so an ordinary FIR registration does not
    # invalidate the rollup. What does invalidate it is a change to which records
    # are excluded, which is precisely when the rollup's filtering became wrong.
    if stamped.version != current.version or stamped.sha256 != current.sha256:
        return ("policy_superseded",
                f"mv_case_daily was built under analytics policy "
                f"{stamped.version}/{stamped.sha256[:12]} but the current policy is "
                f"{current.version}/{current.sha256[:12]}. A case excluded from "
                f"derived analytics since the last refresh would still be counted, "
                f"so the rollup is not served.")
    return None


def _require_fresh_rollup(conn) -> dict:
    """Assert the rollup is usable, or raise RollupUnavailable."""
    state = rollup_state(conn)
    verdict = evaluate_rollup(state, analytics_policy.current_attestation(conn))
    if verdict is not None:
        reason, detail = verdict
        raise RollupUnavailable(reason, detail=detail)
    return state


def _scope_where(district_ids: Optional[list], unit_id: Optional[int]) -> tuple[str, list]:
    """Confine to the seat. No eligibility predicate: the view already applied it."""
    clauses: list[str] = []
    params: list = []
    if district_ids is not None:
        if not district_ids:
            # Entitled to nothing. An impossible predicate, never a skipped filter.
            return " AND FALSE", []
        clauses.append("district_id = ANY(%s)")
        params.append([int(d) for d in district_ids])
    if unit_id is not None:
        clauses.append("unit_id = %s")
        params.append(int(unit_id))
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def dashboard_summary(*, district_ids: Optional[list] = None,
                      unit_id: Optional[int] = None,
                      crime_head_ids: Optional[list] = None,
                      window_days: int = 90) -> dict:
    """Count KPIs for the caller's scope, from the rollup.

    One query instead of the four the equivalent live path costs, over a table
    roughly a tenth the size of CaseMaster.
    """
    where, params = _scope_where(district_ids, unit_id)
    if crime_head_ids is not None:
        if not crime_head_ids:
            where, params = " AND FALSE", []
        else:
            where += " AND crime_head_id = ANY(%s)"
            params.append([int(c) for c in crime_head_ids])

    with db.ro_conn() as conn:
        state = _require_fresh_rollup(conn)

        with conn.cursor() as cur:
            # The window is relative to the DATA's latest registration, not today:
            # the corpus ends before the current date, so a wall-clock window would
            # report zero new cases.
            cur.execute("SELECT max(registered_date) FROM mv_case_daily WHERE TRUE"
                        + where, params)
            row = cur.fetchone()
            as_of = row[0] if row and row[0] else None
            if as_of is None:
                return _empty(state, window_days, district_ids, unit_id)

            win_start = as_of - dt.timedelta(days=window_days)
            overdue_cut = as_of - dt.timedelta(days=90)

            cur.execute(
                "SELECT "
                "  coalesce(sum(case_count), 0) AS total, "
                "  coalesce(sum(case_count) FILTER (WHERE status_bucket = 'open'), 0) AS open_cases, "
                "  coalesce(sum(case_count) FILTER (WHERE registered_date > %s), 0) AS new_cases, "
                "  coalesce(sum(case_count) FILTER (WHERE status_bucket = 'open' "
                "        AND registered_date <= %s), 0) AS overdue, "
                "  coalesce(sum(heinous_count), 0) AS heinous, "
                "  count(DISTINCT unit_id) AS units, "
                "  count(DISTINCT district_id) AS districts, "
                # Ageing of OPEN cases, in the same pass. The live path spends a
                # separate query on this.
                #
                # BOUNDARIES MUST MATCH /performance/overview EXACTLY, which
                # buckets on age = (as_of - registered_date) with `age <= 30`,
                # `age > 30 AND age <= 90`, and so on. In date terms `age <= 30` is
                # `registered_date >= as_of - 30`, so the comparisons are >= and <.
                # Writing them as > and <= (the obvious first guess) shifts every
                # boundary by one day and made the two endpoints disagree by a few
                # cases per bucket while still summing to the same total — the kind
                # of drift that is invisible until someone reconciles them.
                "  coalesce(sum(case_count) FILTER (WHERE status_bucket = 'open' "
                "        AND registered_date >= %s), 0) AS open_0_30, "
                "  coalesce(sum(case_count) FILTER (WHERE status_bucket = 'open' "
                "        AND registered_date < %s AND registered_date >= %s), 0) AS open_31_90, "
                "  coalesce(sum(case_count) FILTER (WHERE status_bucket = 'open' "
                "        AND registered_date < %s AND registered_date >= %s), 0) AS open_91_180, "
                "  coalesce(sum(case_count) FILTER (WHERE status_bucket = 'open' "
                "        AND registered_date < %s), 0) AS open_180p "
                "FROM mv_case_daily WHERE TRUE" + where,
                [win_start, overdue_cut,
                 as_of - dt.timedelta(days=30),
                 as_of - dt.timedelta(days=30), as_of - dt.timedelta(days=90),
                 as_of - dt.timedelta(days=90), as_of - dt.timedelta(days=180),
                 as_of - dt.timedelta(days=180)] + params)
            r = cur.fetchone()

    total, open_cases, new_cases, overdue, heinous = (int(x or 0) for x in r[:5])
    units_n, districts_n = int(r[5] or 0), int(r[6] or 0)
    today = dt.date.today()
    data_age = (today - as_of).days

    # A DISCONTINUOUS corpus makes the window figure misleading, so it is reported
    # rather than left to be misread.
    #
    # `as_of` is max(registered_date), which is right in principle — with live
    # intake, new cases legitimately arrive dated today. But this corpus has a gap:
    # the generated bulk ends 2025-12-31 and a handful of later records (test FIRs
    # written through the intake API) sit months after it. The window then starts
    # inside that sparse tail and "new cases" reads as a near-zero, which looks like
    # a collapse in registrations rather than an artefact of the anchor.
    #
    # Detected by comparing the window's daily rate against the whole corpus's. No
    # extra query: both numbers are already in hand.
    notes: list[str] = []
    span_days = max(1, (as_of - dt.date(2021, 1, 1)).days)
    corpus_rate = total / span_days
    window_rate = new_cases / max(1, window_days)
    if total > 1000 and corpus_rate > 0 and window_rate < corpus_rate * 0.2:
        notes.append(
            f"The window holds {new_cases} case(s), far below this scope's long-run "
            f"rate of about {corpus_rate:.1f}/day. The record's latest registration "
            f"({as_of.isoformat()}) sits in a sparse tail well after the bulk of the "
            f"data, so the window opens inside that gap. Treat the window figure as "
            f"unrepresentative; the totals are unaffected.")

    return {
        "scope": {"district_ids": district_ids, "unit_id": unit_id,
                  "crime_head_ids": crime_head_ids},
        "source": "mv_case_daily",
        "as_of": as_of.isoformat(),
        "data_age_days": data_age,
        "stale": data_age > 45,
        "empty": total == 0,
        "window_days": window_days,
        # Reported so the caller can see the window the counts refer to instead of
        # having to re-derive it from as_of and window_days.
        "window_start": win_start.isoformat(),
        "data_notes": notes,
        "totals": {
            "total_cases": total,
            "open_cases": open_cases,
            "closed_cases": total - open_cases,
            "new_cases_in_window": new_cases,
            "overdue_open": overdue,
            "overdue_threshold_days": 90,
            "heinous_cases": heinous,
            "units_in_scope": units_n,
            "districts_in_scope": districts_n,
        },
        "ageing": [
            {"bucket": "0-30d", "count": int(r[7] or 0)},
            {"bucket": "31-90d", "count": int(r[8] or 0)},
            {"bucket": "91-180d", "count": int(r[9] or 0)},
            {"bucket": ">180d", "count": int(r[10] or 0)},
        ],
        "rollup": state,
        "limitations": [
            "Synthetic hackathon data.",
            "Windows are relative to the dataset as-of date, not today.",
            "Counts come from a pre-aggregated rollup refreshed on a schedule, so "
            "they lag the base tables by up to one refresh interval.",
            "Officer load and chargesheet throughput are NOT in the rollup (it "
            "carries no officer or chargesheet linkage); use /performance/overview.",
        ],
        "dataset": "synthetic",
    }


def _empty(state: dict, window_days: int, district_ids, unit_id) -> dict:
    return {
        "scope": {"district_ids": district_ids, "unit_id": unit_id,
                  "crime_head_ids": None},
        "source": "mv_case_daily",
        "as_of": None, "data_age_days": None, "stale": False, "empty": True,
        "window_days": window_days, "window_start": None, "data_notes": [],
        "totals": {}, "ageing": [], "rollup": state,
        "limitations": ["No cases in the requested scope."],
        "dataset": "synthetic",
    }
