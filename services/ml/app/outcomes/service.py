"""Aggregate court outcomes: conviction rate and the disposal mix.

Counts only — no case rows leave this module — so a state or wing seat that is
aggregate-only can still be shown the metric it is accountable for.

Reads ``CaseDisposition`` where ``IsFinal`` is true, joined through
``CaseMaster -> Unit`` for jurisdiction, because a case carries no district of its
own. Applies the same fail-closed analytics-eligibility policy as every other
aggregate, so the figures reconcile with /performance/overview rather than
counting records that policy excludes.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .. import db
from .schemas import DispositionCount, OutcomesOverview

# Terminal dispositions and how to read them. The split matters: only the first
# two are court VERDICTS. A B-report is "undetected" and a C-report is "false
# complaint" — both are decisions not to prosecute, not lost prosecutions.
VERDICT_TYPES = ("convicted", "acquitted")

LABELS = {
    "convicted": "Convicted",
    "acquitted": "Acquitted",
    "closed_b_report": "Undetected (B-report)",
    "closed_c_report": "False complaint (C-report)",
    "transferred": "Transferred",
    "withdrawn": "Withdrawn",
    "pending": "Pending",
}

STALE_AFTER_DAYS = 45


def _scope_sql(district_ids: Optional[list], unit_id: Optional[int]) -> tuple[str, list]:
    """Jurisdiction predicate. An EMPTY district list means a seat entitled to
    nothing, so it must match no rows rather than be ignored."""
    from ..cases import casedata

    clauses = [casedata.analytics_eligible_sql("cm"), 'cd."IsFinal" = TRUE']
    params: list = []
    if unit_id is not None:
        clauses.append('cm."PoliceStationID" = %s')
        params.append(int(unit_id))
    if district_ids is not None:
        if not district_ids:
            clauses.append("FALSE")
        else:
            clauses.append('u."DistrictID" = ANY(%s)')
            params.append([int(d) for d in district_ids])
    return " AND ".join(clauses), params


def outcomes_overview(*, district_ids: Optional[list] = None,
                      unit_id: Optional[int] = None,
                      crime_head_ids: Optional[list] = None,
                      window_days: Optional[int] = None) -> OutcomesOverview:
    """Conviction rate and disposal mix for a jurisdiction.

    ``window_days`` is measured back from the DATA's most recent disposition, not
    from wall clock, matching /performance/overview — otherwise a stale dataset
    silently reports zero for every window.
    """
    limitations = [
        "Synthetic hackathon data; not an operational court-performance statistic.",
        "Conviction rate counts only cases that reached a verdict. B-reports "
        "(undetected) and C-reports (false complaint) are decisions not to "
        "prosecute and are reported separately rather than as failed convictions.",
        "A disposition is attributed to the district of the registering station.",
    ]

    where, params = _scope_sql(district_ids, unit_id)
    if crime_head_ids:
        where += ' AND cm."CrimeMajorHeadID" = ANY(%s)'
        params.append([int(h) for h in crime_head_ids])

    base_from = (
        'FROM "CaseDisposition" cd '
        'JOIN "CaseMaster" cm ON cm."CaseMasterID" = cd."CaseMasterID" '
        'JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
        'WHERE ' + where
    )

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT max(cd."DispositionDate") {base_from}', params)
            row = cur.fetchone()
            as_of_raw = row[0] if row else None

    # DispositionDate is a timestamptz, so normalise to a date before any date
    # arithmetic — subtracting a datetime from a date raises.
    as_of = as_of_raw.date() if isinstance(as_of_raw, dt.datetime) else as_of_raw

    with db.ro_conn() as conn:
        with conn.cursor() as cur:

            win_params = list(params)
            win_clause = ""
            if window_days and as_of_raw is not None:
                win_clause = ' AND cd."DispositionDate" > %s'
                win_params.append(as_of_raw - dt.timedelta(days=int(window_days)))

            cur.execute(
                f'SELECT cd."DispositionType", count(*) {base_from}{win_clause} '
                'GROUP BY cd."DispositionType"', win_params)
            counts = {r[0]: int(r[1]) for r in cur.fetchall()}

    total = sum(counts.values())
    convicted = counts.get("convicted", 0)
    acquitted = counts.get("acquitted", 0)
    verdicts = convicted + acquitted

    breakdown = [
        DispositionCount(
            disposition_type=key, label=LABELS.get(key, key.replace("_", " ").title()),
            count=n,
            share_of_disposed=(round(n / total, 4) if total else None))
        for key, n in sorted(counts.items(), key=lambda kv: -kv[1])
    ]

    data_age = (dt.date.today() - as_of).days if as_of else None
    return OutcomesOverview(
        scope={"district_ids": list(district_ids) if district_ids is not None else None,
               "unit_id": unit_id,
               "crime_head_ids": list(crime_head_ids) if crime_head_ids else None},
        # None rather than 0 when nothing reached a verdict: "no verdicts yet" is
        # not "a 0% conviction rate".
        conviction_rate=(round(convicted / verdicts, 4) if verdicts else None),
        convicted=convicted, acquitted=acquitted, verdicts=verdicts,
        prosecution_rate=(round(verdicts / total, 4) if total else None),
        total_disposed=total, breakdown=breakdown,
        as_of=(as_of.isoformat() if as_of else None),
        data_age_days=data_age,
        stale=bool(data_age is not None and data_age > STALE_AFTER_DAYS),
        empty=(total == 0), window_days=window_days,
        limitations=limitations,
    )
