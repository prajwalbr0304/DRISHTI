"""Category-specific case lifecycle rules + server-side transition validation.

The audit (roadmap §2) found every case category shared one generic
arrest/chargesheet lifecycle. Phase 1 fixed generation with scenario-driven state
machines and seeded them into the ``CaseCategoryWorkflow`` table. Phase 2 makes
the *intake API* enforce those same rules:

  * which party roles / capabilities a category permits (accused, arrest,
    chargesheet, court) — a Missing Person or UDR must not silently take an
    accused or a chargesheet;
  * which lifecycle events/transitions are valid, read from
    ``CaseCategoryWorkflow`` (the DB is the source of truth the UI also renders);
  * event prerequisites (a chargesheet needs prior investigation/arrest; a
    missing-person/UDR/NCR/PAR chargesheet needs a prior conversion event).

These rules are enforced in the API, not hidden in the UI, so an invalid
combination is rejected regardless of how the request is made (DoD §C).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- rich lifecycle status codes (mirror datagen.scenario_registry) ---------
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

# rich status code -> legacy CaseStatusMaster.CaseStatusName (FK-valid).
STATUS_TO_LEGACY: dict[str, str] = {
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

STATUS_LABELS: dict[str, str] = {
    S_UNDER_INVESTIGATION: "Under investigation",
    S_CHARGESHEETED: "Charge sheeted",
    S_PENDING_TRIAL: "Pending trial",
    S_CONVICTED: "Convicted",
    S_ACQUITTED: "Acquitted",
    S_UNDETECTED: "Undetected (B-report)",
    S_FALSE: "False (C-report)",
    S_TRANSFERRED: "Transferred",
    S_MISSING_TRACING: "Missing — under trace",
    S_MISSING_RECOVERED: "Missing — recovered",
    S_MISSING_UNTRACED: "Missing — untraced",
    S_ENQUIRY_CLOSED: "Enquiry closed",
    S_INQUEST_CLOSED: "Inquest closed",
    S_CONVERTED: "Converted / reclassified",
}

# --- lifecycle event types (mirror datagen.scenario_registry) ---------------
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

EVENT_LABELS: dict[str, str] = {
    E_REGISTERED: "FIR registered",
    E_ZERO_FIR_REGISTERED: "Zero FIR registered",
    E_TRANSFERRED_OUT: "Transferred to another unit",
    E_RECEIVED_ACK: "Receiving unit acknowledged",
    E_INVESTIGATION: "Investigation progress",
    E_ARREST: "Arrest / surrender",
    E_CHARGESHEET_FILED: "Chargesheet filed",
    E_SUPPLEMENTARY_CS: "Supplementary chargesheet",
    E_COURT_ASSIGNED: "Committed to court",
    E_HEARING: "Court hearing",
    E_JUDGMENT: "Judgment",
    E_MISSING_REPORTED: "Missing person reported",
    E_LAST_SEEN: "Last-seen details recorded",
    E_SEARCH: "Search conducted",
    E_TRACED: "Traced",
    E_RECOVERED: "Recovered",
    E_INQUEST: "Inquest",
    E_POSTMORTEM: "Postmortem",
    E_ENQUIRY: "Enquiry",
    E_CONVERTED: "Converted / reclassified",
    E_REOPENED: "Reopened",
    E_CORRECTED: "Corrected",
    E_CLOSED: "Closed",
}

# All valid CasePartyRole role types.
PARTY_ROLES = (
    "complainant", "victim", "accused", "witness",
    "informant", "guardian", "organisation", "unknown",
)
PARTY_ROLE_LABELS: dict[str, str] = {
    "complainant": "Complainant",
    "victim": "Victim",
    "accused": "Accused / suspect",
    "witness": "Witness",
    "informant": "Informant",
    "guardian": "Guardian",
    "organisation": "Organisation",
    "unknown": "Unknown / unidentified",
}


@dataclass
class CaseKind:
    name: str
    category: str                 # CaseCategory.LookupValue
    label: str
    allow_accused: bool
    allow_arrest: bool
    allow_chargesheet: bool
    allow_court: bool
    initial_event: str
    initial_status: str
    description: str = ""
    # roles beyond complainant/witness/informant/guardian/organisation/unknown
    # that this kind permits (accused is gated by allow_accused).
    extra_roles: tuple[str, ...] = field(default_factory=tuple)


# Category-specific rules. Authoritative server-side rule set for validation
# (mirrors datagen.scenario_registry.CASE_KINDS; the DB CaseCategoryWorkflow
# supplies the transition table the UI renders and validation checks).
CASE_KINDS: dict[str, CaseKind] = {
    "fir_standard": CaseKind(
        "fir_standard", "FIR", "Standard FIR",
        allow_accused=True, allow_arrest=True, allow_chargesheet=True, allow_court=True,
        initial_event=E_REGISTERED, initial_status=S_UNDER_INVESTIGATION,
        description="Standard cognizable FIR investigation path."),
    "zero_fir": CaseKind(
        "zero_fir", "Zero FIR", "Zero FIR",
        allow_accused=True, allow_arrest=True, allow_chargesheet=True, allow_court=True,
        initial_event=E_ZERO_FIR_REGISTERED, initial_status=S_UNDER_INVESTIGATION,
        description="Zero FIR registered out-of-jurisdiction, transferred to the jurisdiction unit."),
    "udr": CaseKind(
        "udr", "UDR", "Unnatural Death Report",
        allow_accused=False, allow_arrest=False, allow_chargesheet=False, allow_court=False,
        initial_event=E_REGISTERED, initial_status=S_UNDER_INVESTIGATION,
        description="Unnatural Death Report: inquest/postmortem; may convert to FIR."),
    "ncr": CaseKind(
        "ncr", "NCR", "Non-Cognizable Report",
        allow_accused=True, allow_arrest=False, allow_chargesheet=False, allow_court=False,
        initial_event=E_REGISTERED, initial_status=S_UNDER_INVESTIGATION,
        description="Non-Cognizable Report: enquiry path; escalation/conversion possible."),
    "par": CaseKind(
        "par", "PAR", "Preventive Action Report",
        allow_accused=True, allow_arrest=False, allow_chargesheet=False, allow_court=True,
        initial_event=E_REGISTERED, initial_status=S_UNDER_INVESTIGATION,
        description="Preventive Action Report: bond/enquiry path; no chargesheet."),
    "missing_person": CaseKind(
        "missing_person", "FIR", "Missing Person",
        allow_accused=False, allow_arrest=False, allow_chargesheet=False, allow_court=False,
        initial_event=E_MISSING_REPORTED, initial_status=S_MISSING_TRACING,
        description="Missing person: report/last-seen/search/trace/recovery; no chargesheet unless converted."),
}

# category code -> allowed case kinds (a category may host several kinds).
CATEGORY_TO_KINDS: dict[str, list[str]] = {}
for _k in CASE_KINDS.values():
    CATEGORY_TO_KINDS.setdefault(_k.category, []).append(_k.name)

# 1-digit case-category code used as the CrimeNo prefix (police_fir_schema).
CATEGORY_CRIMENO_CODE: dict[str, int] = {"FIR": 1, "UDR": 3, "Zero FIR": 8, "PAR": 4, "NCR": 5}

# --- prerequisite semantics (mirror scenario_registry) ----------------------
STATUS_REQUIRES_EVENT: dict[str, str] = {
    S_CHARGESHEETED: E_CHARGESHEET_FILED,
    S_PENDING_TRIAL: E_CHARGESHEET_FILED,
    S_CONVICTED: E_JUDGMENT,
    S_ACQUITTED: E_JUDGMENT,
    S_MISSING_RECOVERED: E_RECOVERED,
    S_INQUEST_CLOSED: E_INQUEST,
    S_TRANSFERRED: E_TRANSFERRED_OUT,
}
EVENT_REQUIRES_ANY_PRIOR: dict[str, list[str]] = {
    E_CHARGESHEET_FILED: [E_INVESTIGATION, E_ARREST],
    E_JUDGMENT: [E_CHARGESHEET_FILED],
    E_RECOVERED: [E_MISSING_REPORTED],
    E_TRACED: [E_MISSING_REPORTED],
    E_POSTMORTEM: [E_INQUEST, E_REGISTERED],
    E_RECEIVED_ACK: [E_TRANSFERRED_OUT, E_ZERO_FIR_REGISTERED],
    E_COURT_ASSIGNED: [E_CHARGESHEET_FILED],
}
# Kinds that may NOT emit a chargesheet unless a conversion event precedes it.
CHARGESHEET_REQUIRES_CONVERSION = {"udr", "ncr", "par", "missing_person"}


def kind_or_raise(kind: str) -> CaseKind:
    if kind not in CASE_KINDS:
        raise ValueError(f"Unknown case kind '{kind}'.")
    return CASE_KINDS[kind]


def allowed_party_roles(kind: str) -> list[str]:
    """Party roles a case kind permits. Accused is gated by allow_accused."""
    ck = kind_or_raise(kind)
    roles = ["complainant", "victim", "witness", "informant", "guardian",
             "organisation", "unknown"]
    if ck.allow_accused:
        roles.insert(2, "accused")
    return roles


def is_party_role_allowed(kind: str, role: str) -> bool:
    return role in allowed_party_roles(kind)


def capability(kind: str) -> dict[str, bool]:
    ck = kind_or_raise(kind)
    return {
        "allow_accused": ck.allow_accused,
        "allow_arrest": ck.allow_arrest,
        "allow_chargesheet": ck.allow_chargesheet,
        "allow_court": ck.allow_court,
    }


# --- transition table (read from CaseCategoryWorkflow) ----------------------
def load_transitions(conn, category: str) -> list[dict]:
    """All seeded transitions for a category (UI metadata + validation)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EventType","FromStatus","ToStatus","RequiresPriorEvent",'
            '"IsTerminal","Description" '
            'FROM "CaseCategoryWorkflow" WHERE "CaseCategoryCode"=%s '
            'ORDER BY "CaseCategoryWorkflowID"',
            (category,))
        return [
            {"event_type": r[0], "from_status": r[1], "to_status": r[2],
             "requires_prior_event": r[3], "is_terminal": r[4], "description": r[5]}
            for r in cur.fetchall()
        ]


@dataclass
class TransitionResult:
    ok: bool
    to_status: Optional[str] = None
    error: Optional[str] = None
    is_terminal: bool = False


def validate_event(
    conn,
    *,
    kind: str,
    category: str,
    event_type: str,
    from_status: Optional[str],
    prior_event_types: list[str],
) -> TransitionResult:
    """Validate a lifecycle event against category rules + the seeded state
    machine + prerequisite events. Returns the resulting status on success."""
    ck = kind_or_raise(kind)

    # category capability gates first (clearest rejection messages).
    if event_type == E_ARREST and not ck.allow_arrest:
        return TransitionResult(False, error=f"An arrest is not valid for a {ck.label} case.")
    if event_type in (E_CHARGESHEET_FILED, E_SUPPLEMENTARY_CS) and not ck.allow_chargesheet:
        if kind in CHARGESHEET_REQUIRES_CONVERSION and E_CONVERTED not in prior_event_types:
            return TransitionResult(
                False,
                error=f"A {ck.label} case cannot be charge-sheeted unless it is first "
                      "converted/reclassified to a cognizable FIR.")
        return TransitionResult(False, error=f"A chargesheet is not valid for a {ck.label} case.")
    if event_type in (E_COURT_ASSIGNED, E_HEARING, E_JUDGMENT) and not ck.allow_court:
        return TransitionResult(False, error=f"A court event is not valid for a {ck.label} case.")

    # look up the transition in the seeded state machine.
    transitions = load_transitions(conn, category)
    matches = [t for t in transitions if t["event_type"] == event_type]
    if not matches:
        return TransitionResult(
            False, error=f"Event '{event_type}' is not defined for category '{category}'.")

    # match on from_status when the transition constrains it (None = any).
    chosen = None
    for t in matches:
        if t["from_status"] in (None, "", from_status):
            chosen = t
            break
    if chosen is None:
        allowed_from = sorted({t["from_status"] for t in matches if t["from_status"]})
        return TransitionResult(
            False,
            error=(f"Event '{event_type}' cannot be applied from status "
                   f"'{from_status}'. Expected one of: {', '.join(allowed_from) or 'initial'}."))

    # prerequisite: the seeded single prior event.
    req = chosen.get("requires_prior_event")
    if req and req not in prior_event_types:
        return TransitionResult(
            False,
            error=f"Event '{event_type}' requires a prior '{req}' event.")

    # richer 'any-of' prerequisites.
    any_prior = EVENT_REQUIRES_ANY_PRIOR.get(event_type)
    if any_prior and not any(p in prior_event_types for p in any_prior):
        return TransitionResult(
            False,
            error=f"Event '{event_type}' requires a prior event: "
                  f"one of {', '.join(any_prior)}.")

    # conversion gate for non-cognizable kinds emitting a chargesheet.
    if (event_type in (E_CHARGESHEET_FILED, E_SUPPLEMENTARY_CS)
            and kind in CHARGESHEET_REQUIRES_CONVERSION
            and E_CONVERTED not in prior_event_types):
        return TransitionResult(
            False,
            error=f"A {ck.label} case must be converted/reclassified before a chargesheet.")

    return TransitionResult(True, to_status=chosen["to_status"], is_terminal=bool(chosen["is_terminal"]))
