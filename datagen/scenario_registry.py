"""Scenario-driven case lifecycles expressed as DATA, not scattered if-statements.

Every case belongs to a *case kind* (fir_standard / zero_fir / udr / ncr / par /
missing_person). Each kind declares, declaratively:

  * which categories/statuses it may take;
  * whether accused / arrest / chargesheet / court are permitted;
  * the ordered lifecycle events it emits;
  * its prerequisites (e.g. "Charge Sheeted" requires a chargesheet_filed event
    which itself requires investigation/arrest first).

``WORKFLOW_TRANSITIONS`` is loaded verbatim into the ``CaseCategoryWorkflow``
table so the database documents the same rules the generator enforces. The
golden fixture must hit every ``GOLDEN_SCENARIOS`` minimum (coverage gate).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# --- rich lifecycle status codes (stored in CaseVersion.StatusCode) ---------
S_UNDER_INVESTIGATION = "under_investigation"
S_CHARGESHEETED = "chargesheeted"
S_PENDING_TRIAL = "pending_trial"
S_CONVICTED = "convicted"
S_ACQUITTED = "acquitted"
S_UNDETECTED = "undetected_b_report"
S_FALSE = "false_c_report"
S_TRANSFERRED = "transferred"
S_MISSING_TRACING = "missing_under_trace"
S_MISSING_RECOVERED = "missing_recovered"
S_MISSING_UNTRACED = "missing_untraced"
S_ENQUIRY_CLOSED = "enquiry_closed"
S_INQUEST_CLOSED = "inquest_closed"
S_CONVERTED = "converted_reclassified"

# Map a rich lifecycle status to the legacy CaseStatusMaster name (FK-valid).
STATUS_TO_LEGACY: Dict[str, str] = {
    S_UNDER_INVESTIGATION: "Under Investigation",
    S_CHARGESHEETED: "Charge Sheeted",
    S_PENDING_TRIAL: "Pending Trial",
    S_CONVICTED: "Closed - Convicted",
    S_ACQUITTED: "Closed - Acquitted",
    S_UNDETECTED: "Undetected / B-Report",
    S_FALSE: "False / C-Report",
    S_TRANSFERRED: "Transferred",
    S_MISSING_TRACING: "Missing - Under Trace",
    S_MISSING_RECOVERED: "Missing - Recovered",
    S_MISSING_UNTRACED: "Closed - Untraced",
    S_ENQUIRY_CLOSED: "Enquiry Closed",
    S_INQUEST_CLOSED: "Inquest Closed",
    S_CONVERTED: "Converted / Reclassified",
}

# Additional CaseStatusMaster names v2 needs beyond the legacy 8 (appended by the
# reference loader so both legacy and v2 stay FK-valid).
EXTRA_STATUS_NAMES: List[str] = [
    "Missing - Under Trace", "Missing - Recovered", "Closed - Untraced",
    "Enquiry Closed", "Inquest Closed", "Converted / Reclassified",
]

# --- lifecycle event types --------------------------------------------------
E_REGISTERED = "registered"
E_ZERO_FIR_REGISTERED = "zero_fir_registered"
E_TRANSFERRED_OUT = "transferred_out"
E_RECEIVED_ACK = "receiving_unit_acknowledged"
E_INVESTIGATION = "investigation_progress"
E_ARREST = "arrest"
E_CHARGESHEET_FILED = "chargesheet_filed"
E_SUPPLEMENTARY_CS = "supplementary_chargesheet"
E_COURT_ASSIGNED = "court_assigned"
E_HEARING = "hearing"
E_JUDGMENT = "judgment"
E_MISSING_REPORTED = "missing_reported"
E_LAST_SEEN = "last_seen_recorded"
E_SEARCH = "search_conducted"
E_TRACED = "traced"
E_RECOVERED = "recovered"
E_INQUEST = "inquest"
E_POSTMORTEM = "postmortem"
E_ENQUIRY = "enquiry"
E_CONVERTED = "converted"
E_REOPENED = "reopened"
E_CORRECTED = "corrected"
E_CLOSED = "closed"
E_DISPOSITION = "disposition"


@dataclass
class CaseKind:
    name: str
    category: str                 # CaseCategory.LookupValue this maps to
    allow_accused: bool
    allow_arrest: bool
    allow_chargesheet: bool
    allow_court: bool
    # weighted terminal/interim lifecycle statuses (rich codes)
    status_weights: Dict[str, float] = field(default_factory=dict)
    description: str = ""


# ---------------------------------------------------------------------------
# The case-kind catalogue. Category-specific — NOT one global arrest/CS rate.
# ---------------------------------------------------------------------------
CASE_KINDS: Dict[str, CaseKind] = {
    "fir_standard": CaseKind(
        name="fir_standard", category="FIR",
        allow_accused=True, allow_arrest=True, allow_chargesheet=True, allow_court=True,
        status_weights={
            S_UNDER_INVESTIGATION: 34, S_CHARGESHEETED: 20, S_PENDING_TRIAL: 14,
            S_CONVICTED: 6, S_ACQUITTED: 5, S_UNDETECTED: 13, S_FALSE: 5,
            S_TRANSFERRED: 3,
        },
        description="Standard cognizable FIR investigation path.",
    ),
    "zero_fir": CaseKind(
        name="zero_fir", category="Zero FIR",
        allow_accused=True, allow_arrest=True, allow_chargesheet=True, allow_court=True,
        status_weights={
            S_TRANSFERRED: 45, S_UNDER_INVESTIGATION: 30, S_CHARGESHEETED: 15,
            S_UNDETECTED: 10,
        },
        description="Zero FIR registered out-of-jurisdiction, transferred to the jurisdiction unit.",
    ),
    "udr": CaseKind(
        name="udr", category="UDR",
        allow_accused=False, allow_arrest=False, allow_chargesheet=False, allow_court=False,
        status_weights={
            S_INQUEST_CLOSED: 60, S_UNDER_INVESTIGATION: 22, S_CONVERTED: 18,
        },
        description="Unnatural Death Report: inquest/postmortem; may convert to FIR.",
    ),
    "ncr": CaseKind(
        name="ncr", category="NCR",
        allow_accused=True, allow_arrest=False, allow_chargesheet=False, allow_court=False,
        status_weights={
            S_ENQUIRY_CLOSED: 60, S_UNDER_INVESTIGATION: 22, S_CONVERTED: 10,
            S_TRANSFERRED: 8,
        },
        description="Non-Cognizable Report: enquiry path; escalation/conversion possible.",
    ),
    "par": CaseKind(
        name="par", category="PAR",
        allow_accused=True, allow_arrest=False, allow_chargesheet=False, allow_court=True,
        status_weights={
            S_ENQUIRY_CLOSED: 70, S_UNDER_INVESTIGATION: 20, S_TRANSFERRED: 10,
        },
        description="Preventive Action Report: bond/enquiry path; no chargesheet.",
    ),
    "missing_person": CaseKind(
        name="missing_person", category="FIR",
        allow_accused=False, allow_arrest=False, allow_chargesheet=False, allow_court=False,
        status_weights={
            S_MISSING_TRACING: 30, S_MISSING_RECOVERED: 42, S_MISSING_UNTRACED: 20,
            S_CONVERTED: 8,
        },
        description="Missing person: report/last-seen/search/trace/recovery; no chargesheet unless converted.",
    ),
}

# Sampling weights for the non-missing kinds (missing_person is chosen by profile).
KIND_SAMPLING_WEIGHTS: Dict[str, float] = {
    "fir_standard": 0.78, "zero_fir": 0.05, "udr": 0.05, "ncr": 0.07, "par": 0.05,
}


def classify_kind(subhead: str, sampled_kind: str) -> str:
    """Missing-person crime always drives the missing_person lifecycle; otherwise
    the sampled kind is used."""
    if subhead.strip().lower().startswith("missing"):
        return "missing_person"
    return sampled_kind


# ---------------------------------------------------------------------------
# Prerequisite rules used by validation.py — an event/status is only valid if
# its prerequisite event(s) already occurred.
# ---------------------------------------------------------------------------
# Charge Sheeted status requires a chargesheet_filed event.
STATUS_REQUIRES_EVENT: Dict[str, str] = {
    S_CHARGESHEETED: E_CHARGESHEET_FILED,
    S_PENDING_TRIAL: E_CHARGESHEET_FILED,
    S_CONVICTED: E_JUDGMENT,
    S_ACQUITTED: E_JUDGMENT,
    S_MISSING_RECOVERED: E_RECOVERED,
    S_INQUEST_CLOSED: E_INQUEST,
    S_TRANSFERRED: E_TRANSFERRED_OUT,
}

# chargesheet_filed requires prior investigation OR arrest.
EVENT_REQUIRES_ANY_PRIOR: Dict[str, List[str]] = {
    E_CHARGESHEET_FILED: [E_INVESTIGATION, E_ARREST],
    E_JUDGMENT: [E_CHARGESHEET_FILED],
    E_RECOVERED: [E_MISSING_REPORTED],
    E_TRACED: [E_MISSING_REPORTED],
    E_POSTMORTEM: [E_INQUEST, E_REGISTERED],
    E_RECEIVED_ACK: [E_TRANSFERRED_OUT, E_ZERO_FIR_REGISTERED],
}

# Kinds that may NOT emit a chargesheet unless a conversion event precedes it.
CHARGESHEET_REQUIRES_CONVERSION = {"udr", "ncr", "par", "missing_person"}


# ---------------------------------------------------------------------------
# CaseCategoryWorkflow seed rows: (category, event, from_status, to_status,
# requires_prior_event, is_terminal, description). Loaded into the DB.
# ---------------------------------------------------------------------------
def _wf(cat, ev, frm, to, req=None, term=False, desc=""):
    return (cat, ev, frm, to, req, term, desc)


WORKFLOW_TRANSITIONS = [
    # FIR
    _wf("FIR", E_REGISTERED, None, S_UNDER_INVESTIGATION, None, False, "FIR registered."),
    _wf("FIR", E_INVESTIGATION, S_UNDER_INVESTIGATION, S_UNDER_INVESTIGATION, E_REGISTERED, False, "Investigation progresses."),
    _wf("FIR", E_ARREST, S_UNDER_INVESTIGATION, S_UNDER_INVESTIGATION, E_REGISTERED, False, "Accused arrested."),
    _wf("FIR", E_CHARGESHEET_FILED, S_UNDER_INVESTIGATION, S_CHARGESHEETED, E_INVESTIGATION, False, "Chargesheet filed (requires investigation/arrest)."),
    _wf("FIR", E_COURT_ASSIGNED, S_CHARGESHEETED, S_PENDING_TRIAL, E_CHARGESHEET_FILED, False, "Case committed to court."),
    _wf("FIR", E_JUDGMENT, S_PENDING_TRIAL, S_CONVICTED, E_CHARGESHEET_FILED, True, "Conviction."),
    _wf("FIR", E_JUDGMENT, S_PENDING_TRIAL, S_ACQUITTED, E_CHARGESHEET_FILED, True, "Acquittal."),
    _wf("FIR", E_CLOSED, S_UNDER_INVESTIGATION, S_UNDETECTED, E_REGISTERED, True, "Closed as undetected (B-report)."),
    _wf("FIR", E_CLOSED, S_UNDER_INVESTIGATION, S_FALSE, E_REGISTERED, True, "Closed as false (C-report)."),
    _wf("FIR", E_TRANSFERRED_OUT, S_UNDER_INVESTIGATION, S_TRANSFERRED, E_REGISTERED, True, "Transferred to another unit."),
    # Zero FIR
    _wf("Zero FIR", E_ZERO_FIR_REGISTERED, None, S_UNDER_INVESTIGATION, None, False, "Zero FIR registered out-of-jurisdiction."),
    _wf("Zero FIR", E_TRANSFERRED_OUT, S_UNDER_INVESTIGATION, S_TRANSFERRED, E_ZERO_FIR_REGISTERED, False, "Forwarded to jurisdiction unit."),
    _wf("Zero FIR", E_RECEIVED_ACK, S_TRANSFERRED, S_UNDER_INVESTIGATION, E_TRANSFERRED_OUT, False, "Receiving unit acknowledges and continues."),
    _wf("Zero FIR", E_CHARGESHEET_FILED, S_UNDER_INVESTIGATION, S_CHARGESHEETED, E_INVESTIGATION, False, "Chargesheet after transfer."),
    # UDR
    _wf("UDR", E_REGISTERED, None, S_UNDER_INVESTIGATION, None, False, "UDR registered."),
    _wf("UDR", E_INQUEST, S_UNDER_INVESTIGATION, S_UNDER_INVESTIGATION, E_REGISTERED, False, "Inquest conducted."),
    _wf("UDR", E_POSTMORTEM, S_UNDER_INVESTIGATION, S_UNDER_INVESTIGATION, E_INQUEST, False, "Postmortem conducted."),
    _wf("UDR", E_CLOSED, S_UNDER_INVESTIGATION, S_INQUEST_CLOSED, E_INQUEST, True, "UDR closed after inquest."),
    _wf("UDR", E_CONVERTED, S_UNDER_INVESTIGATION, S_CONVERTED, E_INQUEST, True, "Converted to FIR (e.g. suspected murder)."),
    # NCR
    _wf("NCR", E_REGISTERED, None, S_UNDER_INVESTIGATION, None, False, "NCR registered."),
    _wf("NCR", E_ENQUIRY, S_UNDER_INVESTIGATION, S_UNDER_INVESTIGATION, E_REGISTERED, False, "Enquiry conducted."),
    _wf("NCR", E_CLOSED, S_UNDER_INVESTIGATION, S_ENQUIRY_CLOSED, E_ENQUIRY, True, "NCR enquiry closed."),
    _wf("NCR", E_CONVERTED, S_UNDER_INVESTIGATION, S_CONVERTED, E_ENQUIRY, True, "Escalated/converted to cognizable FIR."),
    _wf("NCR", E_TRANSFERRED_OUT, S_UNDER_INVESTIGATION, S_TRANSFERRED, E_REGISTERED, True, "Transferred."),
    # PAR
    _wf("PAR", E_REGISTERED, None, S_UNDER_INVESTIGATION, None, False, "PAR registered."),
    _wf("PAR", E_ENQUIRY, S_UNDER_INVESTIGATION, S_UNDER_INVESTIGATION, E_REGISTERED, False, "Preventive enquiry."),
    _wf("PAR", E_CLOSED, S_UNDER_INVESTIGATION, S_ENQUIRY_CLOSED, E_ENQUIRY, True, "PAR closed with bond."),
    _wf("PAR", E_TRANSFERRED_OUT, S_UNDER_INVESTIGATION, S_TRANSFERRED, E_REGISTERED, True, "Transferred."),
    # Missing person (registered under FIR category, missing lifecycle)
    _wf("FIR", E_MISSING_REPORTED, None, S_MISSING_TRACING, None, False, "Missing person reported."),
    _wf("FIR", E_LAST_SEEN, S_MISSING_TRACING, S_MISSING_TRACING, E_MISSING_REPORTED, False, "Last-seen details recorded."),
    _wf("FIR", E_SEARCH, S_MISSING_TRACING, S_MISSING_TRACING, E_MISSING_REPORTED, False, "Search conducted."),
    _wf("FIR", E_RECOVERED, S_MISSING_TRACING, S_MISSING_RECOVERED, E_MISSING_REPORTED, True, "Missing person recovered/traced."),
    _wf("FIR", E_CLOSED, S_MISSING_TRACING, S_MISSING_UNTRACED, E_SEARCH, True, "Closed untraced."),
    _wf("FIR", E_CONVERTED, S_MISSING_TRACING, S_CONVERTED, E_SEARCH, True, "Converted to kidnapping/abduction FIR."),
    # cross-cutting reopen/correct
    _wf("FIR", E_REOPENED, S_UNDETECTED, S_UNDER_INVESTIGATION, E_CLOSED, False, "Case reopened."),
    _wf("FIR", E_CORRECTED, S_UNDER_INVESTIGATION, S_UNDER_INVESTIGATION, E_REGISTERED, False, "Case details corrected."),
]


# ---------------------------------------------------------------------------
# Golden fixture scenario minimums — the coverage gate fails if any is unmet.
# ---------------------------------------------------------------------------
GOLDEN_SCENARIOS: Dict[str, int] = {
    # lifecycle kinds
    "kind_fir_standard": 200,
    "kind_zero_fir": 20,
    "kind_udr": 20,
    "kind_ncr": 20,
    "kind_par": 15,
    "kind_missing_person": 25,
    # branches
    "known_accused": 100,
    "unknown_accused": 40,
    "case_with_arrest": 80,
    "case_without_arrest": 80,
    "case_with_chargesheet": 60,
    "case_without_chargesheet": 100,
    "case_with_court": 40,
    "case_without_court": 80,
    "transfer_with_ack": 10,
    "missing_traced_recovered": 10,
    "missing_untraced": 5,
    "udr_inquest": 10,
    "udr_converted": 3,
    "ncr_converted": 3,
    "reopened_case": 5,
    "corrected_case": 5,
    "supplementary_chargesheet": 5,
    "late_outcome_after_window": 10,
    # identity
    "repeat_offender_multi_case": 30,
    "same_name_different_person": 10,
    "alias_same_person": 10,
    "organisation_party": 8,
    "unknown_unidentified_party": 15,
    "guardian_role": 8,
    "informant_role": 10,
    "witness_role": 40,
    # evidence + digital + property + financial + statements
    "evidence_item": 120,
    "evidence_version_replacement": 5,
    "evidence_multi_case_link": 5,
    "statement_recorded": 60,
    "property_seizure": 30,
    "vehicle_item": 10,
    "weapon_item": 10,
    "device_artifact": 15,
    "communication_event": 40,
    "location_observation": 40,
    "financial_reviewed_link": 15,
    "court_event": 40,
    "bail_event": 15,
    "disposition_final": 20,
    "outcome_observation": 40,
    # graph
    "graph_person_node": 60,
    "graph_provenanced_edge": 40,
    "graph_unverified_edge": 10,
    # quality/error scenarios (staging only)
    "quality_missing_required": 5,
    "quality_duplicate_source": 5,
    "quality_conflicting_dates": 5,
    "quality_invalid_jurisdiction_staged": 5,
    "quality_duplicate_file_hash": 5,
    "quality_corrupt_file": 3,
    "quality_conflicting_evidence_metadata": 3,
    "quality_late_retracted_source": 3,
    "quality_partial_retry_import": 3,
    "audit_actor_action": 10,
}
