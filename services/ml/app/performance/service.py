"""Operational station/officer performance metrics (Prompt 20 Part C).

All reads use db.ro_conn(). Windows are computed relative to the DATA as-of date
(max registration date in scope) — not wall-clock — so the synthetic 2021-2025
dataset yields meaningful "recent" windows, and the data-age is surfaced honestly.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .. import db

# Lifecycle status names grouped for operational metrics (see CaseStatusMaster).
OPEN_STATUSES = ("Under Investigation", "Pending Trial", "Missing - Under Trace")
DISPOSED_STATUSES = (
    "Charge Sheeted", "Closed - Convicted", "Closed - Acquitted",
    "Undetected / B-Report", "False / C-Report", "Enquiry Closed",
    "Inquest Closed", "Closed - Untraced", "Converted / Reclassified",
    "Missing - Recovered",
)

OVERDUE_DAYS = 90          # an open case older than this is an overdue review
HEAVY_LOAD = 15            # an officer holding more than this many OPEN cases
_STATION_CAP = 25          # bound the per-station breakdown list


def _scope_where(unit_id: Optional[int], district_id: Optional[int]) -> tuple[str, list]:
    clauses, params = [], []
    if unit_id is not None:
        clauses.append('cm."PoliceStationID" = %s')
        params.append(int(unit_id))
    if district_id is not None:
        clauses.append('u."DistrictID" = %s')
        params.append(int(district_id))
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _as_of(cur, where: str, params: list) -> Optional[dt.date]:
    cur.execute(
        'SELECT max(cm."CrimeRegisteredDate") FROM "CaseMaster" cm '
        'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" WHERE TRUE' + where, params)
    r = cur.fetchone()
    return r[0] if r and r[0] else None


def station_officer_performance(*, unit_id: Optional[int] = None,
                                district_id: Optional[int] = None,
                                window_days: int = 30) -> dict:
    open_list = ",".join(["%s"] * len(OPEN_STATUSES))
    limitations = [
        "Synthetic hackathon data; not an operational HR appraisal.",
        "Windows are relative to the dataset as-of date, not today.",
        "Disposal time is measured to chargesheet filing (time-to-chargesheet), "
        "not final court disposal.",
        "Officer load is an aggregate distribution — never a punitive per-officer rank.",
    ]

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            where, sp = _scope_where(unit_id, district_id)
            as_of = _as_of(cur, where, sp)
            if as_of is None:
                return {
                    "scope": {"unit_id": unit_id, "district_id": district_id},
                    "as_of": None, "data_age_days": None, "empty": True,
                    "window_days": window_days,
                    "totals": {}, "ageing": [], "chargesheet": {},
                    "workload_balance": {}, "officers": {}, "stations": [],
                    "limitations": limitations + ["No cases in the requested scope."],
                }
            win_start = as_of - dt.timedelta(days=window_days)
            overdue_cut = as_of - dt.timedelta(days=OVERDUE_DAYS)

            # --- headline totals -------------------------------------------
            cur.execute(
                'SELECT count(*) AS total, '
                f'count(*) FILTER (WHERE st."CaseStatusName" IN ({open_list})) AS open_cases, '
                'count(*) FILTER (WHERE cm."CrimeRegisteredDate" > %s) AS new_cases, '
                f'count(*) FILTER (WHERE st."CaseStatusName" IN ({open_list}) '
                '  AND cm."CrimeRegisteredDate" <= %s) AS overdue, '
                'count(DISTINCT cm."PoliceStationID") AS stations, '
                'count(DISTINCT cm."PolicePersonID") AS officers '
                'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                'JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID" '
                'WHERE TRUE' + where,
                list(OPEN_STATUSES) + [win_start] + list(OPEN_STATUSES) + [overdue_cut] + sp)
            row = cur.fetchone()
            total, open_cases, new_cases, overdue, stations_n, officers_n = row

            # --- ageing buckets for OPEN cases (relative to as_of) ---------
            cur.execute(
                'SELECT '
                "  count(*) FILTER (WHERE age <= 30) AS d0_30, "
                "  count(*) FILTER (WHERE age > 30 AND age <= 90) AS d31_90, "
                "  count(*) FILTER (WHERE age > 90 AND age <= 180) AS d91_180, "
                "  count(*) FILTER (WHERE age > 180) AS d180p "
                'FROM (SELECT (%s - cm."CrimeRegisteredDate") AS age '
                '      FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                '      JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID" '
                f'     WHERE st."CaseStatusName" IN ({open_list}){where}) q',
                [as_of] + list(OPEN_STATUSES) + sp)
            b = cur.fetchone()
            ageing = [
                {"bucket": "0-30d", "count": int(b[0])},
                {"bucket": "31-90d", "count": int(b[1])},
                {"bucket": "91-180d", "count": int(b[2])},
                {"bucket": ">180d", "count": int(b[3])},
            ]

            # --- chargesheet throughput + time-to-chargesheet --------------
            cur.execute(
                'SELECT count(*) AS cs_in_window, '
                '  percentile_disc(0.5) WITHIN GROUP (ORDER BY (cs."csdate"::date - cm."CrimeRegisteredDate"::date)) AS median_days, '
                '  avg(cs."csdate"::date - cm."CrimeRegisteredDate"::date)::float AS avg_days '
                'FROM "ChargesheetDetails" cs '
                'JOIN "CaseMaster" cm ON cm."CaseMasterID"=cs."CaseMasterID" '
                'JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                'WHERE cs."csdate" > %s' + where, [win_start] + sp)
            cs = cur.fetchone()
            cs_in_window = int(cs[0] or 0)
            new_cases = int(new_cases or 0)
            chargesheet = {
                "filed_in_window": cs_in_window,
                "new_cases_in_window": new_cases,
                "throughput_ratio": round(cs_in_window / new_cases, 3) if new_cases else None,
                "throughput_ratio_denominator": "chargesheets filed / new cases, same window",
                "median_days_to_chargesheet": int(cs[1]) if cs[1] is not None else None,
                "avg_days_to_chargesheet": round(cs[2], 1) if cs[2] is not None else None,
            }

            # --- officer OPEN-load distribution (aggregate, not a ranking) --
            cur.execute(
                'SELECT '
                '  percentile_disc(0.5) WITHIN GROUP (ORDER BY n) AS median_load, '
                '  percentile_disc(0.9) WITHIN GROUP (ORDER BY n) AS p90_load, '
                '  max(n) AS max_load, '
                '  count(*) FILTER (WHERE n > %s) AS heavy_officers, '
                '  count(*) AS officers_with_open '
                'FROM (SELECT cm."PolicePersonID" pid, count(*) n '
                '      FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                '      JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID" '
                f'     WHERE st."CaseStatusName" IN ({open_list}){where} '
                '      GROUP BY cm."PolicePersonID") q',
                [HEAVY_LOAD] + list(OPEN_STATUSES) + sp)
            od = cur.fetchone()
            officers = {
                "officers_with_open_cases": int(od[4] or 0),
                "median_open_per_officer": int(od[0]) if od[0] is not None else 0,
                "p90_open_per_officer": int(od[1]) if od[1] is not None else 0,
                "max_open_per_officer": int(od[2]) if od[2] is not None else 0,
                "heavy_load_officers": int(od[3] or 0),
                "heavy_load_threshold": HEAVY_LOAD,
                "note": "Aggregate distribution of open-case load; not an individual ranking.",
            }

            # --- per-station breakdown (bounded) ---------------------------
            cur.execute(
                'SELECT u."UnitID", u."UnitName", d."DistrictName", '
                '  count(*) total, '
                f' count(*) FILTER (WHERE st."CaseStatusName" IN ({open_list})) open_cases, '
                '  count(*) FILTER (WHERE cm."CrimeRegisteredDate" > %s) new_cases, '
                f' count(*) FILTER (WHERE st."CaseStatusName" IN ({open_list}) '
                '    AND cm."CrimeRegisteredDate" <= %s) overdue '
                'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                'LEFT JOIN "District" d ON d."DistrictID"=u."DistrictID" '
                'JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID" '
                'WHERE TRUE' + where + ' GROUP BY u."UnitID", u."UnitName", d."DistrictName" '
                'ORDER BY open_cases DESC LIMIT %s',
                list(OPEN_STATUSES) + [win_start] + list(OPEN_STATUSES) + [overdue_cut] + sp + [_STATION_CAP])
            st_rows = cur.fetchall()
            station_list = [{
                "unit_id": int(r[0]), "unit_name": r[1], "district_name": r[2],
                "total": int(r[3]), "open_cases": int(r[4]), "new_cases": int(r[5]),
                "overdue": int(r[6]),
            } for r in st_rows]

            # --- workload balance across ALL stations in scope -------------
            cur.execute(
                'SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY n) AS median_open, '
                '  max(n) AS max_open, count(*) AS stations_compared, sum(n) AS total_open '
                'FROM (SELECT cm."PoliceStationID" sid, count(*) n '
                '      FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                '      JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID" '
                f'     WHERE st."CaseStatusName" IN ({open_list}){where} '
                '      GROUP BY cm."PoliceStationID") q',
                list(OPEN_STATUSES) + sp)
            bl = cur.fetchone()
            balance = _balance(bl, stations_total=int(stations_n or 0))

    today = dt.date.today()
    data_age = (today - as_of).days
    return {
        "scope": {"unit_id": unit_id, "district_id": district_id},
        "as_of": as_of.isoformat(),
        "data_age_days": data_age,
        "stale": data_age > 45,
        "empty": int(total or 0) == 0,
        "window_days": window_days,
        "totals": {
            "total_cases": int(total or 0),
            "active_workload": int(open_cases or 0),
            "new_cases_in_window": new_cases,
            "overdue_reviews": int(overdue or 0),
            "overdue_threshold_days": OVERDUE_DAYS,
            "stations_in_scope": int(stations_n or 0),
            "officers_in_scope": int(officers_n or 0),
            "disposed_or_closed": int(total or 0) - int(open_cases or 0),
        },
        "ageing": ageing,
        "chargesheet": chargesheet,
        "officers": officers,
        "workload_balance": balance,
        "stations": station_list,
        "limitations": limitations,
        "dataset": "synthetic",
    }


def _balance(row, *, stations_total: int) -> dict:
    """Workload-balance summary across ALL stations in scope (no punitive ranking).

    ``row`` = (median_open, max_open, stations_compared, total_open)."""
    if not row or row[2] in (None, 0):
        return {"stations_compared": 0, "stations_in_scope": stations_total,
                "note": "No open cases to compare."}
    median = int(row[0] or 0)
    mx = int(row[1] or 0)
    n = int(row[2] or 0)
    total = int(row[3] or 0)
    ratio = round(mx / median, 2) if median else None
    return {
        "stations_compared": n,
        "stations_in_scope": stations_total,
        "median_open": median,
        "max_open": mx,
        "total_open_across_stations": total,
        "imbalance_ratio_max_over_median": ratio,
        "note": ("Comparative load only (busiest vs median open cases across all "
                 "stations in scope). Higher ratio = more uneven load, not a "
                 "performance judgement."),
    }
