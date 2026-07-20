"""Committed-FIR event flow: idempotent ledger + read-only projection recompute
+ freshness state (Prompt 20 Part E).

The projections are recomputed READ-ONLY from the committed case's district; the
flow never writes a person score or a dispatch. A duplicate case.committed is
suppressed (idempotent). In deployment the ledger/dedup is Catalyst Data Store +
the single case.committed Signal; locally it is this in-process store polled by
the freshness endpoint.
"""
from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass, field
from typing import Optional

from .. import db
from ..signals import EVENT_CASE_COMMITTED, get_signals

# Open lifecycle statuses (mirror app/performance OPEN_STATUSES).
_OPEN_STATUSES = ("Under Investigation", "Pending Trial", "Missing - Under Trace")
# Near-repeat lookback window (days, relative to the district's as-of date).
_NEAR_REPEAT_DAYS = 30

_PROJECTIONS = ("district_statistic", "supervisor_workload", "hotspot_near_repeat")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@dataclass
class ProcessedFir:
    case_id: int
    dedup_key: str
    source_ts: Optional[str]
    processed_ts: str
    status: str                       # "success" | "failed"
    district_id: Optional[int]
    projections: dict = field(default_factory=dict)
    signal_published: bool = False
    detail: Optional[str] = None


class _Ledger:
    """Idempotent in-process committed-FIR ledger + per-projection freshness."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_key: dict[str, ProcessedFir] = {}
        self._order: list[str] = []
        self.duplicate_suppressed = 0
        # per-projection freshness state
        self._proj_state: dict[str, dict] = {
            p: {"last_processed_ts": None, "last_success_ts": None,
                "last_failure_ts": None, "processed_count": 0} for p in _PROJECTIONS
        }

    def seen(self, key: str) -> Optional[ProcessedFir]:
        with self._lock:
            return self._by_key.get(key)

    def record(self, rec: ProcessedFir) -> None:
        with self._lock:
            self._by_key[rec.dedup_key] = rec
            self._order.append(rec.dedup_key)
            for name in _PROJECTIONS:
                st = self._proj_state[name]
                st["last_processed_ts"] = rec.processed_ts
                st["processed_count"] += 1
                if rec.status == "success":
                    st["last_success_ts"] = rec.processed_ts
                else:
                    st["last_failure_ts"] = rec.processed_ts

    def bump_duplicate(self) -> None:
        with self._lock:
            self.duplicate_suppressed += 1

    def recent(self, limit: int = 20) -> list[ProcessedFir]:
        with self._lock:
            keys = self._order[-limit:][::-1]
            return [self._by_key[k] for k in keys if k in self._by_key]

    def projection_state(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self._proj_state.items()}

    def reset(self) -> None:
        with self._lock:
            self._by_key.clear()
            self._order.clear()
            self.duplicate_suppressed = 0
            for st in self._proj_state.values():
                st.update(last_processed_ts=None, last_success_ts=None,
                          last_failure_ts=None, processed_count=0)


_LEDGER = _Ledger()


def _fmt(ts) -> Optional[str]:
    if ts is None:
        return None
    return ts.isoformat() if hasattr(ts, "isoformat") else str(ts)


def _recompute_projections(conn, case_id: int) -> tuple[Optional[int], dict]:
    """Read-only recompute of the aggregate projections a committed FIR touches.

    Returns (district_id, projections). NEVER writes; never scores a person."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT u."DistrictID", cm."PoliceStationID", cm."CrimeMajorHeadID", '
            '       cm."CrimeRegisteredDate", d."DistrictName" '
            'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'LEFT JOIN "District" d ON d."DistrictID"=u."DistrictID" '
            'WHERE cm."CaseMasterID"=%s', (case_id,))
        row = cur.fetchone()
        if not row:
            raise LookupError(f"case {case_id} not found")
        district_id, station_id, head_id, reg_date, district_name = row
        open_list = ",".join(["%s"] * len(_OPEN_STATUSES))

        # district statistic: total cases in the district (committed FIR included).
        cur.execute(
            'SELECT count(*) FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'WHERE u."DistrictID"=%s', (district_id,))
        district_count = int(cur.fetchone()[0])

        # supervisor workload: active (open) cases in the district.
        cur.execute(
            'SELECT count(*) FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
            'JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID" '
            f'WHERE u."DistrictID"=%s AND st."CaseStatusName" IN ({open_list})',
            [district_id] + list(_OPEN_STATUSES))
        active_workload = int(cur.fetchone()[0])

        # near-repeat eligibility: another case of the SAME crime head in the SAME
        # district within the lookback window before this FIR's registration.
        near_repeat_prior = 0
        if reg_date is not None:
            since = reg_date - dt.timedelta(days=_NEAR_REPEAT_DAYS)
            cur.execute(
                'SELECT count(*) FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                'WHERE u."DistrictID"=%s AND cm."CrimeMajorHeadID"=%s '
                '  AND cm."CrimeRegisteredDate" BETWEEN %s AND %s AND cm."CaseMasterID" <> %s',
                (district_id, head_id, since, reg_date, case_id))
            near_repeat_prior = int(cur.fetchone()[0])

    projections = {
        "district_statistic": {
            "district_id": district_id, "district_name": district_name,
            "total_cases": district_count,
            "note": "Committed FIR is reflected in the district case count.",
        },
        "supervisor_workload": {
            "district_id": district_id, "station_id": station_id,
            "active_workload": active_workload,
            "note": "District active workload including the committed FIR (if open).",
        },
        "hotspot_near_repeat": {
            "district_id": district_id, "crime_head_id": head_id,
            "prior_similar_in_window": near_repeat_prior,
            "near_repeat_eligible": near_repeat_prior > 0,
            "window_days": _NEAR_REPEAT_DAYS,
            "note": ("Area/time near-repeat eligibility (same crime head, same "
                     "district, recent window). Aggregate only — not a person score."),
        },
    }
    return district_id, projections


def on_fir_committed(case_id: int, *, source_ts: Optional[str] = None,
                     conn=None) -> ProcessedFir:
    """Process a committed-FIR event idempotently.

    A repeated event for the same case is suppressed (returns the prior record).
    Recomputes the aggregate projections read-only, records freshness, and emits
    the case.committed Signal (data-minimised). Never rescores a person or
    dispatches staff."""
    key = f"case:{int(case_id)}"
    prior = _LEDGER.seen(key)
    if prior is not None:
        _LEDGER.bump_duplicate()
        return prior

    owns = conn is None
    c = conn or db._connect()
    try:
        district_id, projections = _recompute_projections(c, case_id)
        status, detail = "success", None
    except LookupError as exc:
        district_id, projections, status, detail = None, {}, "failed", str(exc)
    finally:
        if owns:
            c.close()

    rec = ProcessedFir(
        case_id=int(case_id), dedup_key=key, source_ts=source_ts,
        processed_ts=_fmt(_now()), status=status, district_id=district_id,
        projections=projections, detail=detail)

    # Emit the data-minimised Signal (published only when Signals is enabled).
    published = False
    if status == "success":
        try:
            ev = get_signals().publish(EVENT_CASE_COMMITTED, {
                "case_id": int(case_id), "district_id": district_id,
                "source_ts": source_ts})
            published = bool(ev.published)
        except Exception:  # noqa: BLE001 — a signal failure must not break the flow
            published = False
    rec.signal_published = published
    _LEDGER.record(rec)
    return rec


def project_committed_fir(*, district_id: int, crime_head_id: Optional[int] = None,
                          station_id: Optional[int] = None, conn=None) -> dict:
    """Read-only WHAT-IF: show how one new committed FIR in this district would
    move the aggregates (before -> after +1), demonstrating the flow without
    persisting anything. Never rescores a person or dispatches."""
    owns = conn is None
    c = conn or db._connect()
    try:
        with c.cursor() as cur:
            cur.execute(
                'SELECT count(*), max(cm."CrimeRegisteredDate") '
                'FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                'WHERE u."DistrictID"=%s', (district_id,))
            total, as_of = cur.fetchone()
            total = int(total or 0)
            open_list = ",".join(["%s"] * len(_OPEN_STATUSES))
            cur.execute(
                'SELECT count(*) FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                'JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID" '
                f'WHERE u."DistrictID"=%s AND st."CaseStatusName" IN ({open_list})',
                [district_id] + list(_OPEN_STATUSES))
            active = int(cur.fetchone()[0])
            near_repeat_prior = 0
            if crime_head_id is not None and as_of is not None:
                since = as_of - dt.timedelta(days=_NEAR_REPEAT_DAYS)
                cur.execute(
                    'SELECT count(*) FROM "CaseMaster" cm JOIN "Unit" u ON u."UnitID"=cm."PoliceStationID" '
                    'WHERE u."DistrictID"=%s AND cm."CrimeMajorHeadID"=%s '
                    '  AND cm."CrimeRegisteredDate" BETWEEN %s AND %s',
                    (district_id, crime_head_id, since, as_of))
                near_repeat_prior = int(cur.fetchone()[0])
    finally:
        if owns:
            c.close()

    return {
        "district_id": district_id, "station_id": station_id,
        "crime_head_id": crime_head_id, "as_of": _fmt(as_of),
        "district_statistic": {"before": total, "after": total + 1, "delta": 1},
        "supervisor_workload": {"before": active, "after": active + 1, "delta": 1,
                                "note": "A newly committed FIR is an open case."},
        "hotspot_near_repeat": {
            "prior_similar_in_window": near_repeat_prior,
            "near_repeat_eligible_after": near_repeat_prior > 0,
            "window_days": _NEAR_REPEAT_DAYS},
        "guarantees": {"person_rescored": False, "auto_dispatch": False},
        "note": ("Deterministic projection of a committed FIR's effect on aggregates "
                 "(read-only, not persisted). No person is scored; no staff dispatched."),
    }


def freshness_state() -> dict:
    """Poll-friendly freshness + last-success/failure state for the dashboard."""
    recent = _LEDGER.recent()
    now = _now()
    proj = _LEDGER.projection_state()
    for name, st in proj.items():
        lp = st.get("last_processed_ts")
        st["freshness_seconds"] = None
        if lp:
            try:
                st["freshness_seconds"] = int((now - dt.datetime.fromisoformat(lp)).total_seconds())
            except Exception:  # noqa: BLE001
                st["freshness_seconds"] = None
    return {
        "transport": "poll (local); Catalyst Signal `case.committed` + scoped channel in Prompt 23",
        "event_type": EVENT_CASE_COMMITTED,
        "processed_count": len(_LEDGER._by_key),
        "duplicate_suppressed": _LEDGER.duplicate_suppressed,
        "projections": proj,
        "recent": [
            {"case_id": r.case_id, "district_id": r.district_id, "status": r.status,
             "source_ts": r.source_ts, "processed_ts": r.processed_ts,
             "signal_published": r.signal_published}
            for r in recent
        ],
        "guarantees": {"person_rescored": False, "auto_dispatch": False},
    }
