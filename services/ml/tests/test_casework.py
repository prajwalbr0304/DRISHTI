"""Phase 7 casework tests.

DB write-path tests drive the real SQL against the live schema through the
``rw_rollback`` fixture and ROLL BACK. They cover the Phase-7 checklist: valid +
invalid event transitions (court/disposition/outcome prerequisites), evidence
linkage, statement version history, charge-sheeted prerequisites, restricted
statement access, and 'outcome not available before a final event'.
"""
import pytest

from app.config import get_settings
from app.casework import service as cw
from app.casework import schemas as S
from app.casework.service import CaseworkConflict, CaseworkValidationError

requires_db = pytest.mark.skipif(not get_settings().database_url,
                                 reason="DATABASE_URL not configured")


# ---------------------------------------------------------------------------
# helpers (run inside the rolled-back connection)
# ---------------------------------------------------------------------------
def _any_case(conn) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "CaseMaster" ORDER BY "CaseMasterID" LIMIT 1')
        return int(cur.fetchone()[0])


def _clean_case(conn, under_investigation: bool = False) -> int:
    """A case with no chargesheet / court event / final disposition / court
    lifecycle event — a clean slate for prerequisite tests."""
    status_join = 'JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID"'
    status_where = "AND st.\"CaseStatusName\"='Under Investigation'" if under_investigation else ""
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout='25000'")
        cur.execute(
            f'SELECT cm."CaseMasterID" FROM "CaseMaster" cm {status_join if under_investigation else ""} '
            'WHERE NOT EXISTS (SELECT 1 FROM "ChargesheetDetails" c WHERE c."CaseMasterID"=cm."CaseMasterID") '
            '  AND NOT EXISTS (SELECT 1 FROM "CourtEvent" ce WHERE ce."CaseMasterID"=cm."CaseMasterID") '
            '  AND NOT EXISTS (SELECT 1 FROM "CaseDisposition" d WHERE d."CaseMasterID"=cm."CaseMasterID" AND d."IsFinal") '
            '  AND NOT EXISTS (SELECT 1 FROM "CaseEvent" e WHERE e."CaseMasterID"=cm."CaseMasterID" '
            "        AND e.\"EventType\" IN ('chargesheet_filed','court_assigned','judgment')) "
            f'  {status_where} '
            'ORDER BY cm."CaseMasterID" LIMIT 1')
        r = cur.fetchone()
    if r is None:
        pytest.skip("no clean case available for prerequisite test")
    return int(r[0])


def _make_case(conn) -> int:
    """Create a minimal fresh CaseMaster (rolled back with the test) — a true
    clean slate (no CaseEvent/CourtEvent/chargesheet) for bootstrap + derived
    timeline tests. Every existing synthetic case already carries CaseEvents."""
    import random
    with conn.cursor() as cur:
        cur.execute('SELECT "EmployeeID" FROM "Employee" LIMIT 1')
        emp = int(cur.fetchone()[0])
        cur.execute('SELECT "UnitID" FROM "Unit" LIMIT 1')
        unit = int(cur.fetchone()[0])
        cur.execute("SELECT \"CaseCategoryID\" FROM \"CaseCategory\" WHERE \"LookupValue\"='FIR' LIMIT 1")
        cat = int(cur.fetchone()[0])
        cur.execute("SELECT \"CaseStatusID\" FROM \"CaseStatusMaster\" WHERE \"CaseStatusName\"='Under Investigation' LIMIT 1")
        stt = int(cur.fetchone()[0])
        crime_no = "".join(["1", "9999", "9999", "2099", f"{random.randint(10000, 99999):05d}"])
        cur.execute(
            'INSERT INTO "CaseMaster" ("CrimeNo","CrimeRegisteredDate","PolicePersonID",'
            '"PoliceStationID","CaseCategoryID","CaseStatusID") '
            'VALUES (%s, CURRENT_DATE, %s, %s, %s, %s) RETURNING "CaseMasterID"',
            (crime_no, emp, unit, cat, stt))
        return int(cur.fetchone()[0])


def _an_evidence_item(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT "EvidenceItemID" FROM "EvidenceItem" ORDER BY "EvidenceItemID" LIMIT 1')
        r = cur.fetchone()
    return int(r[0]) if r else None


def _a_person(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT "CanonicalPersonID" FROM "CanonicalPerson" ORDER BY "CanonicalPersonID" LIMIT 1')
        r = cur.fetchone()
    return int(r[0]) if r else None


# ===========================================================================
# STATEMENTS
# ===========================================================================
@requires_db
def test_statement_create_and_immutable_version_history(rw_rollback):
    conn = rw_rollback
    cid = _any_case(conn)
    sid = cw._create_statement(conn, cid, S.StatementCreate(
        statement_type="witness", statement_text="Saw the incident near the gate.",
        recorded_by_actor="demo.investigating_officer"), "investigating_officer")
    st = cw._serialize_statement(conn, sid, "investigating_officer")
    assert st.current_version_no == 1 and len(st.versions) == 1
    v1_id = st.versions[0].statement_version_id
    cw._correct_statement(conn, sid, S.StatementCorrection(
        statement_text="Saw the incident near the market gate at dusk.",
        correction_reason="clarified location/time", actor="demo.sho"), "sho")
    st2 = cw._serialize_statement(conn, sid, "investigating_officer")
    assert st2.current_version_no == 2 and len(st2.versions) == 2
    # v1 is preserved unchanged (append-only history)
    assert st2.versions[0].statement_version_id == v1_id
    assert "market gate" in st2.current_text


@requires_db
def test_restricted_statement_visible_to_command_seats(rw_rollback):
    conn = rw_rollback
    cid = _any_case(conn)
    sid = cw._create_statement(conn, cid, S.StatementCreate(
        statement_type="witness", access_classification="restricted",
        statement_text="Sensitive witness account naming a suspect."), "investigating_officer")
    # INTERIM ("all roles have access to everything"): every command seat may
    # read restricted statement text.
    as_analyst = cw._serialize_statement(conn, sid, "senior_command")
    assert as_analyst.is_restricted and not as_analyst.access_limited
    assert "Sensitive witness" in as_analyst.current_text
    # A role outside the canonical set is still served the redaction.
    as_other = cw._serialize_statement(conn, sid, "wizard")
    assert as_other.access_limited and as_other.current_text == cw.REDACTED_TEXT
    assert all(v.statement_text == cw.REDACTED_TEXT for v in as_other.versions)
    as_io = cw._serialize_statement(conn, sid, "investigating_officer")
    assert not as_io.access_limited and "Sensitive witness" in as_io.current_text


@requires_db
def test_statement_evidence_linkage(rw_rollback):
    conn = rw_rollback
    eid = _an_evidence_item(conn)
    if eid is None:
        pytest.skip("no evidence item to link")
    cid = _any_case(conn)
    sid = cw._create_statement(conn, cid, S.StatementCreate(
        statement_type="expert", statement_text="Expert opinion attached.",
        evidence_item_id=eid), "investigating_officer")
    st = cw._serialize_statement(conn, sid, "investigating_officer")
    assert st.evidence_item_id == eid


@requires_db
def test_reviewed_statement_is_locked(rw_rollback):
    conn = rw_rollback
    cid = _any_case(conn)
    sid = cw._create_statement(conn, cid, S.StatementCreate(
        statement_type="witness", statement_text="A statement."), "investigating_officer")
    cw._review_statement(conn, sid, S.StatementReview(actor="demo.sho"))
    with pytest.raises(CaseworkConflict):
        cw._correct_statement(conn, sid, S.StatementCorrection(
            statement_text="changed", correction_reason="x"), "sho")


# ===========================================================================
# PROPERTY / SEIZURE
# ===========================================================================
@requires_db
def test_seizure_with_items_and_memo_and_unlinked(rw_rollback):
    conn = rw_rollback
    cid = _any_case(conn)
    eid = _an_evidence_item(conn)
    cw._create_seizure(conn, cid, S.SeizureCreate(
        seizure_type="seizure", place="Market", memo_evidence_item_id=eid,
        items=[S.PropertyItemInput(item_type="vehicle", synthetic_identifier="SYN-VEH-1",
                                   description="Two-wheeler", vehicle_fields={"reg": "SYN-KA-0001"}),
               S.PropertyItemInput(item_type="weapon", description="Knife")]), "investigating_officer")
    listing = cw._list_seizures(conn, cid)
    assert len(listing.seizures) >= 1
    seiz = next(s for s in listing.seizures if s.place == "Market")
    assert len(seiz.items) == 2
    assert seiz.memo_evidence_item_id == eid
    # standalone (unlinked) property item
    pid = cw._insert_property_item(conn, cid, None, S.PropertyItemInput(item_type="substance",
                                                                        description="Sample"))
    listing2 = cw._list_seizures(conn, cid)
    assert any(i.property_item_id == pid for i in listing2.unlinked_items)


@requires_db
def test_property_status_change(rw_rollback):
    conn = rw_rollback
    cid = _any_case(conn)
    pid = cw._insert_property_item(conn, cid, None, S.PropertyItemInput(
        item_type="property", description="Recovered cash", status="seized"))
    cw._change_property_status(conn, pid, S.PropertyStatusChange(status="disposed", note="auctioned"))
    row = cw._fetch_property_item(conn, pid)
    assert cw._serialize_property_item(conn, row).status == "disposed"


# ===========================================================================
# LAB RESULTS
# ===========================================================================
@requires_db
def test_lab_result_create_update_and_restricted_redaction(rw_rollback):
    conn = rw_rollback
    cid = _any_case(conn)
    eid = _an_evidence_item(conn)
    lid = cw._create_lab(conn, cid, S.LabResultInput(
        test_type="dna", lab_name="Synthetic FSL", result_summary="Match to reference sample.",
        status="completed", access_classification="restricted", report_evidence_item_id=eid),
        "investigating_officer")
    # INTERIM: a command seat sees the restricted summary; a non-canonical role
    # still gets the redaction.
    labs_analyst = cw._list_labs(conn, cid, "senior_command")
    lab = next(x for x in labs_analyst.items if x.lab_result_id == lid)
    assert not lab.access_limited and "Match" in lab.result_summary
    labs_other = cw._list_labs(conn, cid, "wizard")
    lab_other = next(x for x in labs_other.items if x.lab_result_id == lid)
    assert lab_other.access_limited and lab_other.result_summary == cw.REDACTED_TEXT
    labs_io = cw._list_labs(conn, cid, "investigating_officer")
    lab_io = next(x for x in labs_io.items if x.lab_result_id == lid)
    assert not lab_io.access_limited and "Match" in lab_io.result_summary
    cw._update_lab(conn, lid, S.LabResultUpdate(status="inconclusive", result_summary="Re-test needed."))
    labs_io2 = cw._list_labs(conn, cid, "investigating_officer")
    assert next(x for x in labs_io2.items if x.lab_result_id == lid).status == "inconclusive"


# ===========================================================================
# COURT / DISPOSITION / OUTCOME — prerequisites (valid + invalid transitions)
# ===========================================================================
@requires_db
def test_court_event_prerequisites(rw_rollback):
    conn = rw_rollback
    cid = _clean_case(conn)
    # hearing / judgment before any chargesheet -> rejected
    with pytest.raises(CaseworkValidationError):
        cw._add_court_event(conn, cid, S.CourtEventInput(event_type="hearing"), "investigating_officer")
    with pytest.raises(CaseworkValidationError):
        cw._add_court_event(conn, cid, S.CourtEventInput(event_type="judgment"), "investigating_officer")
    # file the chargesheet, then hearing + judgment are allowed
    cw._add_court_event(conn, cid, S.CourtEventInput(event_type="chargesheet_filed"), "investigating_officer")
    cw._add_court_event(conn, cid, S.CourtEventInput(event_type="hearing", outcome="adjourned"), "investigating_officer")
    cw._add_court_event(conn, cid, S.CourtEventInput(event_type="judgment", outcome="convicted"), "investigating_officer")
    view = cw._lifecycle_view(conn, cid)
    kinds = {ce.event_type for ce in view.court_events}
    assert {"chargesheet_filed", "hearing", "judgment"} <= kinds


@requires_db
def test_disposition_requires_judgment(rw_rollback):
    conn = rw_rollback
    cid = _clean_case(conn)
    with pytest.raises(CaseworkValidationError):
        cw._add_disposition(conn, cid, S.DispositionInput(disposition_type="convicted"), "sho")
    # a closure report needs no judgment
    cw._add_disposition(conn, cid, S.DispositionInput(disposition_type="closed_b_report"), "sho")
    # after a judgment, a conviction disposition is allowed and is final
    cw._add_court_event(conn, cid, S.CourtEventInput(event_type="chargesheet_filed"), "investigating_officer")
    cw._add_court_event(conn, cid, S.CourtEventInput(event_type="judgment"), "investigating_officer")
    cw._add_disposition(conn, cid, S.DispositionInput(disposition_type="convicted"), "sho")
    view = cw._lifecycle_view(conn, cid)
    conv = [d for d in view.dispositions if d.disposition_type == "convicted"]
    assert conv and conv[0].is_final is True


@requires_db
def test_outcome_not_available_before_final_event(rw_rollback):
    conn = rw_rollback
    cid = _clean_case(conn)
    # no final event yet -> outcome refused
    with pytest.raises(CaseworkConflict):
        cw._add_outcome(conn, cid, S.OutcomeInput(), "sho")
    # record a final disposition, then an outcome is allowed
    cw._add_disposition(conn, cid, S.DispositionInput(disposition_type="closed_c_report"), "sho")
    cw._add_outcome(conn, cid, S.OutcomeInput(observation_type="case_outcome"), "sho")
    view = cw._lifecycle_view(conn, cid)
    assert len(view.outcomes) == 1 and view.has_final_disposition and view.can_record_outcome


@requires_db
def test_outcome_rejects_leakage_before_window_end(rw_rollback):
    conn = rw_rollback
    cid = _clean_case(conn)
    cw._add_disposition(conn, cid, S.DispositionInput(disposition_type="withdrawn"), "sho")
    with pytest.raises(CaseworkValidationError):
        cw._add_outcome(conn, cid, S.OutcomeInput(
            observed_at="2024-01-01T00:00:00+00:00",
            observation_window_end="2024-06-01T00:00:00+00:00"), "sho")


@requires_db
def test_bail_event_recorded(rw_rollback):
    conn = rw_rollback
    cid = _any_case(conn)
    cw._add_bail(conn, cid, S.BailInput(status="granted", bail_type="regular",
                                        canonical_person_id=_a_person(conn)), "investigating_officer")
    view = cw._lifecycle_view(conn, cid)
    assert any(b.status == "granted" for b in view.bail_events)


# ===========================================================================
# LIFECYCLE (bootstrap a version, then valid/invalid transitions)
# ===========================================================================
@requires_db
def test_lifecycle_bootstrap_and_transitions(rw_rollback):
    conn = rw_rollback
    cid = _make_case(conn)
    # first event bootstraps a CaseVersion + seeds the initial 'registered' event
    res1 = cw._add_lifecycle_event(conn, cid, "investigation_progress", None, "investigating_officer", {})
    assert res1.bootstrapped_version is True
    assert res1.to_status == cw.wf.S_UNDER_INVESTIGATION
    res2 = cw._add_lifecycle_event(conn, cid, "chargesheet_filed", None, "investigating_officer", {})
    assert res2.to_status == cw.wf.S_CHARGESHEETED
    view = cw._lifecycle_view(conn, cid)
    assert view.has_case_version and view.current_status == cw.wf.S_CHARGESHEETED
    # invalid transition from chargesheeted (judgment needs pending_trial)
    with pytest.raises(CaseworkConflict):
        cw._add_lifecycle_event(conn, cid, "judgment", None, "investigating_officer", {})


# ===========================================================================
# TIMELINE
# ===========================================================================
@requires_db
def test_timeline_event_backed_and_derived(rw_rollback):
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout='20000'")
        cur.execute('SELECT "CaseMasterID" FROM "CaseEvent" LIMIT 1')
        r = cur.fetchone()
    if r:
        tl = cw._timeline(conn, int(r[0]))
        assert tl.event_backed and tl.count > 0
    # an event-free case falls back to derived base dates (still useful)
    cid = _make_case(conn)
    tl2 = cw._timeline(conn, cid)
    assert tl2.event_backed is False
    assert any(e.type == "registered" for e in tl2.entries)


# ===========================================================================
# API surface (read + guard rejections; no committed writes)
# ===========================================================================
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_lookups_endpoint():
    r = client.get("/casework/lookups", headers={"X-Role": "investigating_officer"})
    assert r.status_code == 200
    body = r.json()
    assert any(t["value"] == "witness" for t in body["statement_types"])
    assert any(t["value"] == "judgment" for t in body["court_event_types"])


def test_casework_reads_open_to_every_command_role():
    # INTERIM ("all roles have access to everything"): the casework read gate no
    # longer denies any command seat (it reuses the intake read gate).
    from app.intake.guards import require_intake_read
    from app.roles import FUNCTIONAL_ROLES
    for role in FUNCTIONAL_ROLES:
        assert require_intake_read(role) == role
    assert client.get("/casework/lookups",
                      headers={"X-Role": "dgp_state_command"}).status_code == 200
