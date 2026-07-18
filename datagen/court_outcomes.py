"""Court events, bail, disposition and verified outcome observations.

Driven entirely by the LifecyclePlan so a court/disposition/outcome can only
exist when the lifecycle produced the prerequisite events. OutcomeObservations
carry the observation window; only post-cutoff verified outcomes may become
labels (see labels.py), which prevents leakage.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from .db import Json
from . import v2common as C

C.register("CourtEvent", [
    "CourtEventID", "CaseMasterID", "CourtID", "EventType", "ScheduledAt",
    "OccurredAt", "Outcome", "Detail",
])
C.register("BailEvent", [
    "CaseMasterID", "CanonicalPersonID", "BailType", "Status", "DecidedAt",
    "CourtID", "Detail",
])
C.register("CaseDisposition", [
    "CaseMasterID", "DispositionType", "DispositionDate", "CourtEventID",
    "IsFinal", "Detail",
])
C.register("OutcomeObservation", [
    "OutcomeObservationID", "CaseMasterID", "ObservationType", "ObservedAt",
    "ObservationWindowStart", "ObservationWindowEnd", "Verified", "SourceEventID",
    "Detail",
])


def _dts(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S+00")


def build_case_court_outcomes(world: C.World, *, case_id: int, lifecycle,
                              reg_date: dt.date, court_id: Optional[int],
                              arrested_cpids: List[int]) -> None:
    w = world
    rng = w.rng
    base = dt.datetime(reg_date.year, reg_date.month, reg_date.day, 11, 0)

    last_court_event_id: Optional[int] = None

    if lifecycle.has_chargesheet:
        ce = w.next_id("CourtEvent")
        day = max(20, lifecycle.outcome_day_offset or 60)
        w.add("CourtEvent", (
            ce, case_id, court_id if lifecycle.has_court else None,
            "chargesheet_filed", None, _dts(base + dt.timedelta(days=min(day, 90))),
            "filed", Json({"synthetic": True}),
        ))
        last_court_event_id = ce
        w.cover("court_event")
        # occasional supplementary/final report after the primary chargesheet
        if rng.bernoulli(0.15):
            ce = w.next_id("CourtEvent")
            w.add("CourtEvent", (
                ce, case_id, court_id if lifecycle.has_court else None,
                "supplementary_chargesheet", None,
                _dts(base + dt.timedelta(days=min(day + 25, 110))), "filed",
                Json({"synthetic": True}),
            ))
            last_court_event_id = ce
            w.cover("court_event")

    if lifecycle.has_court:
        # remand + framing of charges before the hearing (golden coverage of the
        # full court-proceeding vocabulary).
        for et, off, oc in (("remand", 95, "remanded"),
                            ("framing_of_charges", 110, "charges_framed")):
            if rng.bernoulli(0.5):
                ce = w.next_id("CourtEvent")
                w.add("CourtEvent", (
                    ce, case_id, court_id, et, None,
                    _dts(base + dt.timedelta(days=off)), oc, Json({}),
                ))
                last_court_event_id = ce
                w.cover("court_event")
        ce = w.next_id("CourtEvent")
        w.add("CourtEvent", (
            ce, case_id, court_id, "hearing", None,
            _dts(base + dt.timedelta(days=120)), "adjourned", Json({}),
        ))
        last_court_event_id = ce
        w.cover("court_event")
        # a follow-up adjournment on some cases
        if rng.bernoulli(0.3):
            ce = w.next_id("CourtEvent")
            w.add("CourtEvent", (
                ce, case_id, court_id, "adjournment", None,
                _dts(base + dt.timedelta(days=150)), "adjourned", Json({}),
            ))
            last_court_event_id = ce
            w.cover("court_event")
        if lifecycle.disposition in ("convicted", "acquitted"):
            ce = w.next_id("CourtEvent")
            jday = lifecycle.outcome_day_offset or 240
            w.add("CourtEvent", (
                ce, case_id, court_id, "judgment", None,
                _dts(base + dt.timedelta(days=jday)), lifecycle.disposition,
                Json({"verdict": lifecycle.disposition}),
            ))
            last_court_event_id = ce

    # bail for arrested accused
    for cpid in arrested_cpids[:2]:
        if rng.bernoulli(0.5):
            w.add("BailEvent", (
                case_id, cpid, "regular",
                "granted" if rng.bernoulli(0.6) else "rejected",
                _dts(base + dt.timedelta(days=int(rng.g.integers(5, 60)))),
                court_id, Json({"synthetic": True}),
            ))
            w.cover("bail_event")

    # disposition + verified outcome observation
    if lifecycle.disposition:
        is_final = lifecycle.disposition in (
            "convicted", "acquitted", "closed_b_report", "closed_c_report", "transferred")
        dday = lifecycle.outcome_day_offset or 200
        disp_dt = base + dt.timedelta(days=dday)
        w.add("CaseDisposition", (
            case_id, lifecycle.disposition, _dts(disp_dt), last_court_event_id,
            is_final, Json({"kind": lifecycle.kind}),
        ))
        if is_final:
            w.cover("disposition_final")
            oo_id = w.next_id("OutcomeObservation")
            w.add("OutcomeObservation", (
                oo_id, case_id, "case_outcome", _dts(disp_dt),
                _dts(world.observation_cutoff), _dts(world.label_window_end),
                True, None,
                Json({"disposition": lifecycle.disposition,
                      "late": bool(lifecycle.late_outcome)}),
            ))
            w.cover("outcome_observation")
            if lifecycle.late_outcome:
                w.cover("late_outcome_after_window")
