"""Scenario-driven, versioned case lifecycles (append-only CaseEvents).

``build_lifecycle`` runs a category-specific state machine (from
``scenario_registry``) forward: it samples a terminal/interim rich status for the
case's kind, then constructs the minimal *prerequisite-consistent* event chain
that reaches it. Status is therefore always derivable from events, and the
audit's contradictions (Charge Sheeted without a chargesheet; Missing Person with
a chargesheet; every case having a court) cannot occur by construction.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import scenario_registry as SR
from . import v2common as C
from .db import Json

C.register("CaseSource",
           ["CaseMasterID", "SourceSystemID", "SourceRecordID", "ExternalRef",
            "IngestionMethod"])
C.register("CaseVersion", [
    "CaseVersionID", "CaseMasterID", "VersionNo", "CaseCategoryCode",
    "StatusCode", "IsCurrent", "IncidentLatitude", "IncidentLongitude",
    "AssignedDistrictID", "AssignedUnitID", "SnapshotAttributes", "ChangeReason",
    "Actor",
])
C.register("CaseEvent", [
    "CaseMasterID", "EventType", "EventCategory", "SequenceNo", "OccurredAt",
    "FromStatus", "ToStatus", "Payload", "ActorRole", "Provenance",
])
C.register("CaseCategoryWorkflow", [
    "CaseCategoryCode", "EventType", "FromStatus", "ToStatus",
    "RequiresPriorEvent", "IsTerminal", "Description",
])


@dataclass
class LifeEvent:
    event_type: str
    category: str
    day_offset: int
    from_status: Optional[str]
    to_status: Optional[str]
    payload: dict = field(default_factory=dict)


@dataclass
class LifecyclePlan:
    kind: str
    category_code: str
    status_code: str            # rich lifecycle status
    events: List[LifeEvent]
    has_accused: bool
    has_arrest: bool
    has_chargesheet: bool
    has_supplementary_cs: bool
    has_court: bool
    transferred: bool
    receiving_ack: bool
    converted: bool
    reopened: bool
    corrected: bool
    disposition: Optional[str]   # convicted|acquitted|closed_*|transferred|None
    outcome_day_offset: Optional[int]
    late_outcome: bool


def _wchoice(rng, weights: Dict[str, float]) -> str:
    keys = list(weights.keys())
    w = np.array([weights[k] for k in keys], dtype=float)
    w = w / w.sum()
    return keys[int(np.searchsorted(np.cumsum(w), rng.g.random()))]


def build_lifecycle(kind_name: str, rng, cfg,
                    observation_window_days: int) -> LifecyclePlan:
    kind = SR.CASE_KINDS[kind_name]
    status = _wchoice(rng, kind.status_weights)
    events: List[LifeEvent] = []
    day = 0

    def push(et, cat, frm, to, payload=None, gap_lo=1, gap_hi=20):
        nonlocal day
        day += int(rng.g.integers(gap_lo, gap_hi + 1)) if events else 0
        events.append(LifeEvent(et, cat, day, frm, to, payload or {}))

    has_accused = kind.allow_accused
    has_arrest = has_court = has_chargesheet = False
    has_supp = transferred = receiving_ack = converted = reopened = corrected = False
    disposition = None
    S = SR

    if kind_name == "missing_person":
        push(S.E_MISSING_REPORTED, "lifecycle", None, S.S_MISSING_TRACING, gap_lo=0, gap_hi=0)
        push(S.E_LAST_SEEN, "lifecycle", S.S_MISSING_TRACING, S.S_MISSING_TRACING)
        push(S.E_SEARCH, "lifecycle", S.S_MISSING_TRACING, S.S_MISSING_TRACING)
        if status == S.S_MISSING_RECOVERED:
            push(S.E_RECOVERED, "lifecycle", S.S_MISSING_TRACING, S.S_MISSING_RECOVERED)
        elif status == S.S_MISSING_UNTRACED:
            push(S.E_CLOSED, "lifecycle", S.S_MISSING_TRACING, S.S_MISSING_UNTRACED)
        elif status == S.S_CONVERTED:
            converted = True
            has_accused = True  # reclassified to kidnapping -> accused exist
            push(S.E_CONVERTED, "lifecycle", S.S_MISSING_TRACING, S.S_CONVERTED,
                 {"converted_to": "kidnapping_fir"})
        # else remains under trace

    elif kind_name == "udr":
        push(S.E_REGISTERED, "lifecycle", None, S.S_UNDER_INVESTIGATION, gap_lo=0, gap_hi=0)
        push(S.E_INQUEST, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_UNDER_INVESTIGATION)
        if rng.bernoulli(0.7):
            push(S.E_POSTMORTEM, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_UNDER_INVESTIGATION)
        if status == S.S_INQUEST_CLOSED:
            push(S.E_CLOSED, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_INQUEST_CLOSED)
        elif status == S.S_CONVERTED:
            converted = True
            has_accused = True
            push(S.E_CONVERTED, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_CONVERTED,
                 {"converted_to": "murder_fir"})

    elif kind_name in ("ncr", "par"):
        push(S.E_REGISTERED, "lifecycle", None, S.S_UNDER_INVESTIGATION, gap_lo=0, gap_hi=0)
        push(S.E_ENQUIRY, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_UNDER_INVESTIGATION)
        if status == S.S_ENQUIRY_CLOSED:
            push(S.E_CLOSED, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_ENQUIRY_CLOSED)
        elif status == S.S_CONVERTED:
            converted = True
            push(S.E_CONVERTED, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_CONVERTED,
                 {"converted_to": "cognizable_fir"})
        elif status == S.S_TRANSFERRED:
            transferred = True
            push(S.E_TRANSFERRED_OUT, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_TRANSFERRED)

    else:  # fir_standard / zero_fir
        if kind_name == "zero_fir":
            push(S.E_ZERO_FIR_REGISTERED, "lifecycle", None, S.S_UNDER_INVESTIGATION, gap_lo=0, gap_hi=0)
            push(S.E_TRANSFERRED_OUT, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_TRANSFERRED, gap_lo=0, gap_hi=2)
            transferred = True
            if status != S.S_TRANSFERRED:
                push(S.E_RECEIVED_ACK, "admin", S.S_TRANSFERRED, S.S_UNDER_INVESTIGATION)
                receiving_ack = True
        else:
            push(S.E_REGISTERED, "lifecycle", None, S.S_UNDER_INVESTIGATION, gap_lo=0, gap_hi=0)

        if status == S.S_TRANSFERRED and kind_name == "fir_standard":
            transferred = True
            push(S.E_TRANSFERRED_OUT, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_TRANSFERRED)
        elif status in (S.S_UNDETECTED, S.S_FALSE):
            push(S.E_INVESTIGATION, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_UNDER_INVESTIGATION)
            if rng.bernoulli(0.4):
                has_arrest = True
                push(S.E_ARREST, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_UNDER_INVESTIGATION)
            push(S.E_CLOSED, "lifecycle", S.S_UNDER_INVESTIGATION, status)
        elif status == S.S_UNDER_INVESTIGATION:
            push(S.E_INVESTIGATION, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_UNDER_INVESTIGATION)
            if rng.bernoulli(0.55):
                has_arrest = True
                push(S.E_ARREST, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_UNDER_INVESTIGATION)
        else:
            # chargesheeted / pending_trial / convicted / acquitted
            push(S.E_INVESTIGATION, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_UNDER_INVESTIGATION)
            if rng.bernoulli(0.82):
                has_arrest = True
                push(S.E_ARREST, "lifecycle", S.S_UNDER_INVESTIGATION, S.S_UNDER_INVESTIGATION)
            has_chargesheet = True
            push(S.E_CHARGESHEET_FILED, "court", S.S_UNDER_INVESTIGATION, S.S_CHARGESHEETED,
                 {"chargesheet": True})
            if rng.bernoulli(0.15):
                has_supp = True
                push(S.E_SUPPLEMENTARY_CS, "court", S.S_CHARGESHEETED, S.S_CHARGESHEETED,
                     {"supplementary": True})
            if status in (S.S_PENDING_TRIAL, S.S_CONVICTED, S.S_ACQUITTED):
                has_court = True
                push(S.E_COURT_ASSIGNED, "court", S.S_CHARGESHEETED, S.S_PENDING_TRIAL)
                push(S.E_HEARING, "court", S.S_PENDING_TRIAL, S.S_PENDING_TRIAL)
                if status in (S.S_CONVICTED, S.S_ACQUITTED):
                    push(S.E_JUDGMENT, "court", S.S_PENDING_TRIAL, status,
                         {"verdict": status})
                    disposition = "convicted" if status == S.S_CONVICTED else "acquitted"

    # disposition mapping for non-court terminals
    if disposition is None:
        if status == S.S_UNDETECTED:
            disposition = "closed_b_report"
        elif status == S.S_FALSE:
            disposition = "closed_c_report"
        elif status == S.S_TRANSFERRED:
            disposition = "transferred"

    # A final court judgment may occur after the observation window (late outcome).
    outcome_day = None
    late = False
    last_day = events[-1].day_offset if events else 0
    if disposition in ("convicted", "acquitted", "closed_b_report", "closed_c_report"):
        outcome_day = last_day
        late = outcome_day > observation_window_days

    # occasional reopen / correction on closed FIRs
    if kind_name == "fir_standard" and status == S.S_UNDETECTED and rng.bernoulli(0.06):
        reopened = True
        push(S.E_REOPENED, "admin", S.S_UNDETECTED, S.S_UNDER_INVESTIGATION)
    if kind_name in ("fir_standard", "zero_fir") and rng.bernoulli(0.05):
        corrected = True
        push(S.E_CORRECTED, "admin", None, None, {"correction": "typo_fix"})

    return LifecyclePlan(
        kind=kind_name, category_code=kind.category, status_code=status,
        events=events, has_accused=has_accused, has_arrest=has_arrest,
        has_chargesheet=has_chargesheet, has_supplementary_cs=has_supp,
        has_court=has_court, transferred=transferred, receiving_ack=receiving_ack,
        converted=converted, reopened=reopened, corrected=corrected,
        disposition=disposition, outcome_day_offset=outcome_day, late_outcome=late,
    )


def emit_case_workflow_seed(world: C.World) -> None:
    """Seed CaseCategoryWorkflow from the declarative transition table (once)."""
    for row in SR.WORKFLOW_TRANSITIONS:
        world.add("CaseCategoryWorkflow", row)


def emit_case(world: C.World, *, case_id: int, source_system_id: int,
              source_record_id: Optional[int], external_ref: str,
              category_code: str, lifecycle: LifecyclePlan,
              reg_date: dt.date, lat: float, lon: float,
              district_id: int, unit_id: int) -> None:
    """Write CaseSource + CaseVersion (canonical coords) + append-only CaseEvents."""
    w = world
    w.add("CaseSource", (case_id, source_system_id, source_record_id, external_ref,
                         "manual_form"))

    cv_id = w.next_id("CaseVersion")
    w.add("CaseVersion", (
        cv_id, case_id, 1, category_code, lifecycle.status_code, True,
        round(lat, 6), round(lon, 6), district_id, unit_id,
        Json({"kind": lifecycle.kind, "converted": lifecycle.converted}),
        "initial registration", "system_demo",
    ))

    base = dt.datetime(reg_date.year, reg_date.month, reg_date.day, 10, 0, 0)
    for seq, ev in enumerate(lifecycle.events, start=1):
        occurred = base + dt.timedelta(days=ev.day_offset,
                                       hours=int(w.rng.g.integers(0, 10)))
        w.add("CaseEvent", (
            case_id, ev.event_type, ev.category, seq,
            occurred.strftime("%Y-%m-%d %H:%M:%S+00"),
            ev.from_status, ev.to_status, Json(ev.payload), "io_demo",
            Json({"source_record_id": source_record_id}),
        ))
