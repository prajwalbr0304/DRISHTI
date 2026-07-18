"""Leakage-safe AGGREGATE station-workload dataset (Phase 13).

Builds the supervised dataset for the approved ``station_workload_band`` task:
predict the band of case-review workload a police station (Unit) will face in a
forward label window, from strictly-pre-cutoff aggregate station features.

Design guarantees (mirrors the governed forecast/backtest protocol):

  * One row per (station, quarterly cutoff). Features are computed ONLY from
    months on/before the cutoff; the label is the count of cases the station
    registers in the DISJOINT forward window (cutoff, cutoff + horizon]. The
    label is a verified future OUTCOME — never the feature formula — so it is
    label-independent and leakage-safe by construction.
  * Band thresholds are computed on the TRAIN split only (never the future), then
    applied unchanged to val/test, so the banding cannot leak test information.
  * Time split: earliest cutoffs -> train, middle -> val, latest -> test (a model
    never trains on the future). Geographic holdout: a deterministic subset of
    districts is flagged so spatial generalisation is measured separately.
  * All features are aggregate + non-protected (no caste/religion/gender/juvenile
    or any protected/proxy attribute). Feature order matches the approved
    ``tabfm-workload-band`` schema (migration 020).

Aggregate area/period resource-planning support only — never a person-level
criminal-justice judgement.
"""
from __future__ import annotations

import calendar
import datetime as dt
from typing import Optional

import numpy as np

# --- task / schema identity -------------------------------------------------
# Aggregate subject is the police DISTRICT: a read-only signal audit showed
# station-level next-quarter counts are pure Poisson noise (unpredictable), while
# district-level workload carries strong persistent signal — and 32 districts x
# ~16 quarterly cutoffs is the small-tabular regime TabFM/TabPFN are built for.
TASK = "area_workload_band"
SCHEMA_NAME = "tabfm-workload-band"
SCHEMA_VERSION = "1"
SUBJECT_KIND = "area_district"

# --- ordinal bands (must stay consistent with the model card + UI) ----------
BANDS = ["Low", "Moderate", "Elevated", "High"]
N_BANDS = len(BANDS)

# --- windows ----------------------------------------------------------------
LABEL_HORIZON_MONTHS = 3        # one quarter of forward case-review workload
MIN_TRAIN_MONTHS = 12           # minimum station history before a cutoff

# Feature order MUST equal the approved schema's FeatureDefinitionIDs order
# (migration 020 insertion order).
FEATURE_NAMES = [
    "wl_recent_case_volume",
    "wl_prev_quarter_volume",
    "wl_trailing_year_volume",
    "wl_trend_slope",
    "wl_seasonal_index",
    "wl_prioryear_same_quarter",
    "wl_chargesheet_trailing_year",
    "wl_backlog_ratio",
    "wl_history_months",
    "wl_active_months_share",
]
FEATURE_LABELS = {
    "wl_recent_case_volume": "Cases registered (trailing 90d)",
    "wl_prev_quarter_volume": "Cases registered (prior 90-180d)",
    "wl_trailing_year_volume": "Cases registered (trailing 365d)",
    "wl_trend_slope": "Monthly trend slope (12m)",
    "wl_seasonal_index": "Upcoming-quarter seasonal factor",
    "wl_prioryear_same_quarter": "Cases same quarter last year",
    "wl_chargesheet_trailing_year": "Charge sheets filed (trailing 365d)",
    "wl_backlog_ratio": "Uncharged backlog ratio (trailing year)",
    "wl_history_months": "Observed months of history",
    "wl_active_months_share": "Active-month share (12m)",
}


# ---------------------------------------------------------------------------
# Month-axis helpers
# ---------------------------------------------------------------------------
def _month_axis(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    out: list[str] = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _period_end_dt(period: str) -> dt.datetime:
    """Last instant of a 'YYYY-MM' month, tz-aware UTC (the observation cutoff)."""
    y, m = map(int, period.split("-"))
    last_day = calendar.monthrange(y, m)[1]
    return dt.datetime(y, m, last_day, 23, 59, 59, tzinfo=dt.timezone.utc)


def _quarter_end_indices(periods: list[str]) -> list[int]:
    """Indices of quarter-end months (Mar/Jun/Sep/Dec) on the shared axis."""
    return [i for i, p in enumerate(periods) if int(p.split("-")[1]) in (3, 6, 9, 12)]


# ---------------------------------------------------------------------------
# Bulk series loading (station-level; two grouped queries)
# ---------------------------------------------------------------------------
def load_area_series(conn, valid_geo_only: bool = True, level: str = "district"):
    """Return (periods, reg, chg, area_names, area_parent) at the given level.

    ``level='district'`` is the APPROVED TASK subject (strong signal). ``level=
    'station'`` is used ONLY by the benchmark to exercise 500/5,000/full-row
    computational scales (station counts are Poisson noise, so it is never the
    task). ``reg``/``chg`` are {subject_id: [monthly counts]} on a shared
    zero-filled month axis; ``area_parent`` maps each subject to its district (for
    the geographic holdout) — identity for the district level.
    """
    from ..geo import geoscope

    if level == "station":
        subject_col, geo_guard = 'cm."PoliceStationID"', 'cm."PoliceStationID" IS NOT NULL'
    else:
        subject_col, geo_guard = 'u."DistrictID"', 'u."DistrictID" IS NOT NULL'

    where = ['cm."CrimeRegisteredDate" IS NOT NULL', geo_guard]
    params: list = []
    geoscope.apply_exclusion(conn, where, params, valid_geo_only)
    reg_sql = (f'SELECT {subject_col}, '
               'to_char(date_trunc(\'month\', cm."CrimeRegisteredDate"), \'YYYY-MM\') ym, COUNT(*) '
               'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
               'WHERE ' + ' AND '.join(where) + ' GROUP BY 1,2')
    with conn.cursor() as cur:
        cur.execute(reg_sql, params)
        reg_rows = cur.fetchall()

    cwhere = ['cs."csdate" IS NOT NULL', geo_guard]
    cparams: list = []
    geoscope.apply_exclusion(conn, cwhere, cparams, valid_geo_only)
    cs_sql = (f'SELECT {subject_col}, '
              'to_char(date_trunc(\'month\', cs."csdate"), \'YYYY-MM\') ym, COUNT(*) '
              'FROM "ChargesheetDetails" cs '
              'JOIN "CaseMaster" cm ON cm."CaseMasterID" = cs."CaseMasterID" '
              'JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
              'WHERE ' + ' AND '.join(cwhere) + ' GROUP BY 1,2')
    with conn.cursor() as cur:
        cur.execute(cs_sql, cparams)
        cs_rows = cur.fetchall()
        if level == "station":
            cur.execute('SELECT "UnitID","UnitName","DistrictID" FROM "Unit"')
            area_names, area_parent = {}, {}
            for uid, uname, did in cur.fetchall():
                area_names[int(uid)] = uname or f"Unit {uid}"
                area_parent[int(uid)] = int(did) if did is not None else int(uid)
        else:
            cur.execute('SELECT "DistrictID","DistrictName" FROM "District"')
            area_names = {int(d): (n or f"District {d}") for d, n in cur.fetchall()}
            area_parent = {}

    if not reg_rows:
        return [], {}, {}, area_names, area_parent

    raw_reg: dict[int, dict[str, int]] = {}
    reg_months = set()
    for s, ym, c in reg_rows:
        if s is None:
            continue
        raw_reg.setdefault(int(s), {})[ym] = int(c)
        reg_months.add(ym)          # axis is REGISTRATION months only (the label source)
    raw_chg: dict[int, dict[str, int]] = {}
    for s, ym, c in cs_rows:
        if s is None:
            continue
        raw_chg.setdefault(int(s), {})[ym] = int(c)

    # The month axis is bounded by the registration series so a label window can
    # never reach beyond observed case data. Charge sheets whose csdate spills
    # past that range are simply not counted (and missing months pad to zero).
    periods = _month_axis(min(reg_months), max(reg_months))
    reg = {s: [m.get(p, 0) for p in periods] for s, m in raw_reg.items()}
    chg = {s: [raw_chg.get(s, {}).get(p, 0) for p in periods] for s in raw_reg}
    if not area_parent:  # district level: subject is its own geo unit
        area_parent = {s: s for s in reg}
    return periods, reg, chg, area_names, area_parent


# ---------------------------------------------------------------------------
# Feature + label computation (all clamped; strictly pre-cutoff for features)
# ---------------------------------------------------------------------------
def _wsum(a: np.ndarray, lo: int, hi: int) -> float:
    """Sum a[lo:hi] with indices clamped to [0, len] (no negative-index wrap)."""
    lo = max(0, lo)
    hi = min(len(a), hi)
    return float(a[lo:hi].sum()) if hi > lo else 0.0


def features_at(reg: np.ndarray, chg: np.ndarray, ci: int) -> dict:
    """Aggregate, strictly-pre-cutoff features for a station at cutoff month ``ci``
    (inclusive). Returns a dict keyed by FEATURE_NAMES."""
    tw = reg[max(0, ci - 11): ci + 1]                 # trailing <=12 months
    year = float(tw.sum())
    tw_mean = float(tw.mean()) if len(tw) else 0.0
    recent = _wsum(reg, ci - 2, ci + 1)               # last 3 months
    recent_months = min(3, ci + 1)
    recent_mean = recent / recent_months if recent_months else 0.0
    prev_q = _wsum(reg, ci - 5, ci - 2)               # months ci-5..ci-3
    prioryear_q = _wsum(reg, ci - 11, ci - 8)         # same quarter one year prior
    cs_year = _wsum(chg, ci - 11, ci + 1)
    backlog = (year - cs_year) / year if year > 0 else 0.0
    slope = float(np.polyfit(np.arange(len(tw)), tw, 1)[0]) if len(tw) >= 2 else 0.0
    seasonal = recent_mean / tw_mean if tw_mean > 0 else 1.0
    nz = np.nonzero(reg[:ci + 1])[0]
    history_months = float(ci - int(nz[0]) + 1) if len(nz) else 0.0
    active_share = float((tw > 0).mean()) if len(tw) else 0.0
    return {
        "wl_recent_case_volume": round(recent, 3),
        "wl_prev_quarter_volume": round(prev_q, 3),
        "wl_trailing_year_volume": round(year, 3),
        "wl_trend_slope": round(slope, 4),
        "wl_seasonal_index": round(seasonal, 4),
        "wl_prioryear_same_quarter": round(prioryear_q, 3),
        "wl_chargesheet_trailing_year": round(cs_year, 3),
        "wl_backlog_ratio": round(float(min(max(backlog, 0.0), 1.0)), 4),
        "wl_history_months": history_months,
        "wl_active_months_share": round(active_share, 4),
    }


def label_at(reg: np.ndarray, ci: int, horizon: int = LABEL_HORIZON_MONTHS) -> float:
    """Verified forward OUTCOME: cases registered in (cutoff, cutoff+horizon]."""
    return _wsum(reg, ci + 1, ci + 1 + horizon)


def _vector(feat: dict) -> list[float]:
    return [float(feat[n]) for n in FEATURE_NAMES]


# ---------------------------------------------------------------------------
# Band thresholds (computed on TRAIN labels only -> leakage-safe)
# ---------------------------------------------------------------------------
def compute_band_thresholds(train_labels, n_bands: int = N_BANDS) -> list[float]:
    """Strictly-increasing quantile cut-points from the TRAIN label counts."""
    arr = np.asarray(list(train_labels), dtype=float)
    if arr.size == 0:
        return list(range(1, n_bands))
    qs = [i / n_bands for i in range(1, n_bands)]
    raw = [float(v) for v in np.quantile(arr, qs)]
    thr: list[float] = []
    last = -np.inf
    for v in raw:
        if v <= last:
            v = last + 1e-6
        thr.append(v)
        last = v
    return thr


def band_of(count: float, thresholds: list[float]) -> int:
    """Map a count to an ordinal band 0..n via the train thresholds."""
    return int(np.digitize([float(count)], thresholds)[0])


# ---------------------------------------------------------------------------
# Dataset assembly (rows + time/geo splits + thresholds)
# ---------------------------------------------------------------------------
class Dataset:
    """Container for the assembled supervised dataset (numpy arrays + metadata)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def split(self, tag: str):
        m = self.split_tags == tag
        return self.X[m], self.y[m]

    def mask(self, tag: str):
        return self.split_tags == tag


def build_dataset(conn, *, valid_geo_only: bool = True, n_bands: int = N_BANDS,
                  label_horizon_months: int = LABEL_HORIZON_MONTHS,
                  min_train_months: int = MIN_TRAIN_MONTHS,
                  geo_holdout_fraction: float = 0.25,
                  train_frac: float = 0.6, val_frac: float = 0.15,
                  level: str = "district") -> Dataset:
    """Assemble the (subject, cutoff) supervised dataset with leakage-safe labels
    and deterministic time + geographic splits. Thresholds are fit on TRAIN only.
    ``level='district'`` is the approved task; ``level='station'`` is used only by
    the benchmark for computational scale."""
    periods, reg, chg, area_names, area_parent = load_area_series(conn, valid_geo_only, level)
    if not periods:
        raise ValueError("no area series available to build the workload dataset")

    n_months = len(periods)
    max_ci = n_months - 1 - label_horizon_months
    cutoffs = [ci for ci in _quarter_end_indices(periods)
               if (min_train_months - 1) <= ci <= max_ci]
    if not cutoffs:
        raise ValueError("insufficient history to form any leakage-safe cutoff")

    # time split by chronological cutoff order (never train on the future)
    n_cut = len(cutoffs)
    n_train = max(1, int(round(train_frac * n_cut)))
    n_val = max(1, int(round(val_frac * n_cut)))
    n_train = min(n_train, n_cut - 2) if n_cut >= 3 else n_train
    train_cuts = set(cutoffs[:n_train])
    val_cuts = set(cutoffs[n_train:n_train + n_val])
    # everything after train+val is test

    # deterministic geographic holdout: every k-th DISTRICT (parent of the
    # subject), held out of training entirely to measure spatial generalisation
    all_districts = sorted(set(area_parent.values()))
    holdout_districts: set[int] = set()
    if all_districts and 0 < geo_holdout_fraction < 1:
        k = max(2, round(1 / geo_holdout_fraction))
        holdout_districts = {d for i, d in enumerate(all_districts) if i % k == 0}

    X_rows: list[list[float]] = []
    feat_dicts: list[dict] = []
    y_counts: list[float] = []
    unit_ids: list[int] = []
    district_ids: list[int] = []
    cutoff_idx: list[int] = []
    cutoff_periods: list[str] = []
    split_tags: list[str] = []
    geo_holdout: list[bool] = []

    area_ids_sorted = sorted(reg)
    for s in area_ids_sorted:
        r = np.asarray(reg[s], dtype=float)
        c = np.asarray(chg.get(s, [0] * n_months), dtype=float)
        did = area_parent.get(s, s)
        for ci in cutoffs:
            f = features_at(r, c, ci)
            feat_dicts.append(f)
            X_rows.append(_vector(f))
            y_counts.append(label_at(r, ci, label_horizon_months))
            unit_ids.append(s)
            district_ids.append(did)
            cutoff_idx.append(ci)
            cutoff_periods.append(periods[ci])
            split_tags.append("train" if ci in train_cuts else "val" if ci in val_cuts else "test")
            geo_holdout.append(did in holdout_districts)

    X = np.asarray(X_rows, dtype=float)
    y_counts_arr = np.asarray(y_counts, dtype=float)
    split_arr = np.asarray(split_tags, dtype=object)

    thresholds = compute_band_thresholds(y_counts_arr[split_arr == "train"], n_bands)
    y_band = np.asarray([band_of(v, thresholds) for v in y_counts_arr], dtype=int)

    band_dist = {int(b): int((y_band == b).sum()) for b in range(n_bands)}
    return Dataset(
        X=X, y=y_band, label_count=y_counts_arr,
        feature_names=list(FEATURE_NAMES), feature_dicts=feat_dicts,
        unit_ids=np.asarray(unit_ids), district_ids=np.asarray(district_ids),
        cutoff_idx=np.asarray(cutoff_idx), cutoff_periods=np.asarray(cutoff_periods, dtype=object),
        split_tags=split_arr, geo_holdout=np.asarray(geo_holdout, dtype=bool),
        thresholds=thresholds, n_bands=n_bands, bands=list(BANDS),
        periods=periods, unit_names=area_names, unit_district=dict(area_parent),
        holdout_districts=sorted(holdout_districts),
        meta={
            "n_rows": int(X.shape[0]), "n_features": int(X.shape[1]),
            "n_areas": len(area_ids_sorted), "subject_level": level, "n_cutoffs": n_cut,
            "cutoffs": [periods[ci] for ci in cutoffs],
            "train_cutoffs": sorted(periods[ci] for ci in train_cuts),
            "val_cutoffs": sorted(periods[ci] for ci in val_cuts),
            "test_cutoffs": sorted(periods[ci] for ci in cutoffs if ci not in train_cuts and ci not in val_cuts),
            "label_horizon_months": label_horizon_months,
            "min_train_months": min_train_months,
            "band_thresholds": thresholds, "band_distribution": band_dist,
            "geo_holdout_fraction": geo_holdout_fraction,
            "n_holdout_districts": len(holdout_districts),
            "axis_first": periods[0], "axis_last": periods[-1],
            "valid_geography": valid_geo_only,
        },
    )


# ---------------------------------------------------------------------------
# Live features for governed prediction (latest cutoff, no observed label yet)
# ---------------------------------------------------------------------------
def build_live_features(conn, *, valid_geo_only: bool = True,
                        cutoff_period: Optional[str] = None) -> dict:
    """Feature vectors for every district at the latest available month (the
    forward quarter is unobserved). Returns a dict suitable for governed snapshot
    persistence: {cutoff, feature_names, rows:[...]}. The served model bands each
    live vector with the thresholds fit on the training split.
    """
    periods, reg, chg, area_names, _parent = load_area_series(conn, valid_geo_only)
    if not periods:
        raise ValueError("no district series available")
    n_months = len(periods)
    ci = n_months - 1 if cutoff_period is None else periods.index(cutoff_period)
    cutoff_dt = _period_end_dt(periods[ci])
    rows = []
    for d in sorted(reg):
        r = np.asarray(reg[d], dtype=float)
        c = np.asarray(chg.get(d, [0] * n_months), dtype=float)
        f = features_at(r, c, ci)
        rows.append({
            "unit_id": d, "district_id": d,
            "unit_name": area_names.get(d, f"District {d}"),
            "features": f, "vector": _vector(f),
        })
    return {"cutoff_period": periods[ci], "cutoff": cutoff_dt.isoformat(),
            "n_areas": len(rows), "feature_names": list(FEATURE_NAMES), "rows": rows}
