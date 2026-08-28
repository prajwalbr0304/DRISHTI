"""Socio-economic correlation compute.

Correlates DISTRICT-level per-capita crime rates (per 100k, never raw counts —
raw counts just redraw the population map) against averaged Social / Economic /
Weather indicators over a matching period. Pearson r across districts, with
k-anonymity suppression of small (district, category) cells.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import numpy as np
from scipy.stats import pearsonr

# indicator key -> (table, column). Averaged per district over the period.
INDICATORS: dict[str, tuple[str, str]] = {
    "unemployment_rate": ("SocialIndicator", "UnemploymentRate"),
    "literacy_rate": ("SocialIndicator", "LiteracyRate"),
    "youth_ratio": ("SocialIndicator", "YouthRatio"),
    "population_density": ("SocialIndicator", "PopulationDensity"),
    "migration_index": ("SocialIndicator", "MigrationIndex"),
    "per_capita_income": ("EconomicIndicator", "PerCapitaIncome"),
    "poverty_index": ("EconomicIndicator", "PovertyIndex"),
    "business_density": ("EconomicIndicator", "BusinessDensity"),
    "rainfall_mm": ("WeatherIndicator", "RainfallMm"),
    "temperature_c": ("WeatherIndicator", "TemperatureC"),
}
_DATE_COL = {"SocialIndicator": "ObservedDate", "EconomicIndicator": "PeriodStart",
             "WeatherIndicator": "ObservedAt"}


def _strength(r: float) -> str:
    a = abs(r)
    if a < 0.2:
        return "negligible"
    if a < 0.4:
        return "weak"
    if a < 0.6:
        return "moderate"
    if a < 0.8:
        return "strong"
    return "very strong"


def _population(conn, start, end) -> dict[int, int]:
    """Most recent Population per district within the period."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT DISTINCT ON ("DistrictID") "DistrictID", "Population" '
            'FROM "SocialIndicator" '
            'WHERE "DistrictID" IS NOT NULL AND "Population" IS NOT NULL '
            '  AND "ObservedDate" >= %s AND "ObservedDate" < %s '
            'ORDER BY "DistrictID", "ObservedDate" DESC',
            (start, end))
        return {int(r[0]): int(r[1]) for r in cur.fetchall()}


def _indicator_means(conn, start, end) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    with conn.cursor() as cur:
        for key, (table, col) in INDICATORS.items():
            dcol = _DATE_COL[table]
            cur.execute(
                f'SELECT "DistrictID", AVG("{col}")::float FROM "{table}" '
                f'WHERE "DistrictID" IS NOT NULL AND "{col}" IS NOT NULL '
                f'  AND "{dcol}" >= %s AND "{dcol}" < %s GROUP BY "DistrictID"',
                (start, end))
            for did, val in cur.fetchall():
                out.setdefault(int(did), {})[key] = float(val)
    return out


def _crime_counts(conn, start, end):
    """Return (district_names, {(district, category): count}, categories)."""
    from ..cases import casedata

    with conn.cursor() as cur:
        cur.execute(
            'SELECT u."DistrictID", d."DistrictName", ch."CrimeGroupName", COUNT(*) '
            'FROM "CaseMaster" cm '
            'JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
            'JOIN "District" d ON d."DistrictID" = u."DistrictID" '
            'JOIN "CrimeHead" ch ON ch."CrimeHeadID" = cm."CrimeMajorHeadID" '
            'WHERE cm."CrimeRegisteredDate" >= %s AND cm."CrimeRegisteredDate" < %s '
            f'AND {casedata.analytics_eligible_sql("cm")} '
            'GROUP BY 1,2,3',
            (start, end))
        rows = cur.fetchall()
    names: dict[int, str] = {}
    counts: dict[tuple[int, str], int] = {}
    cats = set()
    for did, dname, cat, cnt in rows:
        names[int(did)] = dname
        counts[(int(did), cat)] = int(cnt)
        cats.add(cat)
    return names, counts, sorted(cats)


def compute(conn, start: Optional[dt.date] = None, end: Optional[dt.date] = None,
            k_threshold: int = 25, focus_indicator: Optional[str] = None,
            min_districts: int = 6):
    start = start or dt.date(2021, 1, 1)
    end = end or dt.date(2026, 1, 1)

    pop = _population(conn, start, end)
    ind = _indicator_means(conn, start, end)
    names, counts, categories = _crime_counts(conn, start, end)
    categories_all = ["All Crime"] + categories

    districts = sorted(set(pop) & set(ind) & set(names))

    # per-capita rate per 100k, with k-anonymity suppression of small cells
    rate: dict[tuple[int, str], float] = {}
    total_by_district: dict[int, int] = {}
    suppressed = 0
    for did in districts:
        p = pop[did]
        tot = 0
        for cat in categories:
            c = counts.get((did, cat), 0)
            tot += c
            if c < k_threshold:          # small-N suppression at the cell level
                suppressed += 1
                continue
            rate[(did, cat)] = c / p * 100_000.0
        total_by_district[did] = tot
        # overall rate (kept if the district total clears the threshold)
        if tot >= k_threshold:
            rate[(did, "All Crime")] = tot / p * 100_000.0

    def vectors(cat, indicator):
        xs, ys = [], []
        for did in districts:
            if (did, cat) in rate and indicator in ind[did]:
                xs.append(ind[did][indicator])
                ys.append(rate[(did, cat)])
        return np.array(xs), np.array(ys)

    # correlation matrix (category x indicator)
    matrix = []
    best = None  # (abs_r, cell dict)
    for cat in categories_all:
        for indicator in INDICATORS:
            x, y = vectors(cat, indicator)
            n = len(x)
            cell = {"crime_category": cat, "indicator": indicator, "n": n,
                    "r": None, "p_value": None, "strength": None, "direction": None}
            if n >= min_districts and x.std() > 0 and y.std() > 0:
                r, p = pearsonr(x, y)
                cell.update(r=round(float(r), 4), p_value=round(float(p), 5),
                            strength=_strength(r),
                            direction=("positive" if r >= 0 else "negative"))
                # candidate for the narrative: strong, significant, real category
                if cat != "All Crime" and n >= max(min_districts, 10) and p < 0.1:
                    if best is None or abs(r) > best[0]:
                        best = (abs(r), cell.copy())
            matrix.append(cell)

    # focus indicator for scatter (auto = the strongest narrative indicator)
    if focus_indicator not in INDICATORS:
        focus_indicator = best[1]["indicator"] if best else "unemployment_rate"

    scatter = []
    for cat in categories_all:
        pts = []
        for did in districts:
            if (did, cat) in rate and focus_indicator in ind[did]:
                pts.append({"district_id": did, "district_name": names[did],
                            "x": round(ind[did][focus_indicator], 3),
                            "y": round(rate[(did, cat)], 2),
                            "crime_count": counts.get((did, cat), total_by_district[did]),
                            "population": pop[did]})
        r = fit = None
        slope = intercept = None
        if len(pts) >= min_districts:
            xa = np.array([p["x"] for p in pts]); ya = np.array([p["y"] for p in pts])
            if xa.std() > 0 and ya.std() > 0:
                r = round(float(pearsonr(xa, ya)[0]), 4)
                slope, intercept = np.polyfit(xa, ya, 1)
                slope, intercept = round(float(slope), 5), round(float(intercept), 3)
        scatter.append({"crime_category": cat, "indicator": focus_indicator, "r": r,
                        "fit_slope": slope, "fit_intercept": intercept, "points": pts})

    narrative = _narrative(best, ind, rate, districts, names)
    return {
        "period_start": str(start), "period_end": str(end),
        "indicators": list(INDICATORS), "crime_categories": categories_all,
        "districts_analysed": len(districts), "k_threshold": k_threshold,
        "suppressed_cells": suppressed, "focus_indicator": focus_indicator,
        "correlation_matrix": matrix, "scatter": scatter, "narrative": narrative,
        "source_tables": (["CaseMaster", "District"]
                          + sorted({t for t, _ in INDICATORS.values()})),
    }


def _narrative(best, ind, rate, districts, names) -> dict:
    from .schemas import CAUSATION_DISCLAIMER
    if not best:
        return {"headline": "No robust socio-economic correlation found.",
                "detail": "Too few districts cleared the suppression threshold for a "
                          "reliable correlation in this period.",
                "disclaimer": CAUSATION_DISCLAIMER}
    cell = best[1]
    cat, indicator, r = cell["crime_category"], cell["indicator"], cell["r"]
    # above/below-median comparison for a plain-language effect size
    vals = [(did, ind[did][indicator]) for did in districts
            if indicator in ind[did] and (did, cat) in rate]
    med = float(np.median([v for _, v in vals]))
    high = [rate[(did, cat)] for did, v in vals if v > med]
    low = [rate[(did, cat)] for did, v in vals if v <= med]
    pct = None
    if high and low and np.mean(low) > 0:
        pct = round((np.mean(high) - np.mean(low)) / np.mean(low) * 100, 1)
    ind_label = indicator.replace("_", " ")
    direction = "more" if (pct or 0) >= 0 else "less"
    headline = (f"Districts with {ind_label} above {med:.1f} show "
                f"{abs(pct) if pct is not None else '?'}% {direction} {cat.lower()} per capita.")
    detail = (f"Across {len(vals)} districts, {ind_label} and per-capita {cat.lower()} "
              f"have a {cell['strength']} {cell['direction']} correlation (r={r}, "
              f"p={cell['p_value']}). This is a district-level statistical association.")
    return {"headline": headline, "detail": detail, "disclaimer": CAUSATION_DISCLAIMER,
            "indicator": indicator, "crime_category": cat, "r": r,
            "threshold_value": round(med, 2), "pct_difference": pct}
