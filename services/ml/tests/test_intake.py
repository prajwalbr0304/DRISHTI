"""Phase 2 — FIR/case structured intake tests.

Unit (no DB): category rules + party-role gates + CrimeNo/status mappings +
localhost/synthetic guards.

Integration (@requires_db, all inside a ROLLED-BACK transaction via the
``rw_rollback`` fixture so nothing is persisted to the synthetic dev DB):
  * golden create -> validate -> submit -> approve paths for FIR / Zero FIR /
    UDR / Missing Person, asserting the canonical CaseMaster/CaseVersion/
    CaseEvent/CasePartyRole rows + 18-digit CrimeNo;
  * blocking validation (missing required, out-of-state, temporal order);
  * duplicate/source-key detection;
  * category state-machine rejection of invalid combinations (accused on a
    UDR/Missing Person, arrest on a UDR, chargesheet without investigation,
    missing-person chargesheet without conversion);
  * idempotent create + optimistic-concurrency update.

API (TestClient): read-only endpoints, policymaker block, and the submit gate.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.intake import guards, service, workflow as wf
from app.intake.schemas import (ActSection, CreateDraftRequest, DraftPayload,
                                 PartyInput, UpdateDraftRequest)
from app.main import app
from conftest import requires_db

CRIME_NO_RE = re.compile(r"^[0-9]{18}$")


# ===========================================================================
# Unit — category rules / mappings / guards (no DB)
# ===========================================================================
def test_allowed_party_roles_by_kind():
    assert "accused" in wf.allowed_party_roles("fir_standard")
    assert "accused" not in wf.allowed_party_roles("missing_person")
    assert "accused" not in wf.allowed_party_roles("udr")
    assert "accused" in wf.allowed_party_roles("ncr")  # NCR allows accused, not arrest


def test_capabilities_are_category_specific():
    assert wf.capability("fir_standard") == {
        "allow_accused": True, "allow_arrest": True,
        "allow_chargesheet": True, "allow_court": True}
    assert wf.capability("udr")["allow_arrest"] is False
    assert wf.capability("udr")["allow_chargesheet"] is False
    assert wf.capability("missing_person")["allow_accused"] is False
    assert wf.capability("ncr")["allow_arrest"] is False


def test_crimeno_codes_and_status_mapping():
    assert wf.CATEGORY_CRIMENO_CODE == {"FIR": 1, "UDR": 3, "Zero FIR": 8, "PAR": 4, "NCR": 5}
    assert wf.STATUS_TO_LEGACY[wf.S_CHARGESHEETED] == "Charge Sheeted"
    assert wf.STATUS_TO_LEGACY[wf.S_MISSING_TRACING] == "Missing - Under Trace"


def test_guard_localhost_only():
    class _C:
        def __init__(self, h): self.host = h

    class _R:
        def __init__(self, h): self.client = _C(h)

    # With intake_writes_localhost_only=False (default), all IPs are allowed
    guards.require_localhost(_R("127.0.0.1"))  # no raise
    guards.require_localhost(_R("testclient"))  # no raise (TestClient)
    guards.require_localhost(_R("203.0.113.9"))  # no raise — restriction disabled


@requires_db
def test_hackathon_status_shape():
    st = guards.hackathon_status()
    assert st["environment_label"] == "Synthetic Hackathon Demo"
    # Phase 3 enables submit by default against the synthetic DB.
    assert st["submit_enabled"] is True
    assert st["submit_disabled_reason"] is None
    assert "submit_disabled_reason" in st


# ===========================================================================
# Integration helpers
# ===========================================================================
def _reference(conn) -> dict:
    """Pick real reference ids that satisfy every FK + spatial gate."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT ul."UnitID", u."DistrictID", ST_Y(ul."geom"), ST_X(ul."geom") '
            'FROM "UnitLocation" ul JOIN "Unit" u ON u."UnitID"=ul."UnitID" '
            'WHERE ul."IsCurrent" AND u."DistrictID" IS NOT NULL ORDER BY ul."UnitID" LIMIT 1')
        unit_id, district_id, lat, lon = cur.fetchone()
        cur.execute('SELECT "EmployeeID" FROM "Employee" ORDER BY "EmployeeID" LIMIT 1')
        officer_id = int(cur.fetchone()[0])
        cur.execute('SELECT "CrimeHeadID" FROM "CrimeHead" ORDER BY "CrimeHeadID" LIMIT 1')
        head_id = int(cur.fetchone()[0])
        cur.execute('SELECT "CrimeSubHeadID" FROM "CrimeSubHead" WHERE "CrimeHeadID"=%s LIMIT 1', (head_id,))
        r = cur.fetchone(); subhead_id = int(r[0]) if r else None
        cur.execute('SELECT "GravityOffenceID" FROM "GravityOffence" ORDER BY "GravityOffenceID" LIMIT 1')
        gravity_id = int(cur.fetchone()[0])
        cur.execute('SELECT "ActCode","SectionCode" FROM "Section" ORDER BY "SectionCode" LIMIT 1')
        act_code, section_code = cur.fetchone()
    return {"unit_id": int(unit_id), "district_id": int(district_id),
            "lat": float(lat), "lon": float(lon), "officer_id": officer_id,
            "head_id": head_id, "subhead_id": subhead_id, "gravity_id": gravity_id,
            "act_code": act_code, "section_code": section_code}


def _payload(ref: dict, kind: str) -> DraftPayload:
    p = DraftPayload()
    p.source.source_system_code = "FIR_FORM"
    p.source.source_method = "walk_in"
    if kind == "zero_fir":
        p.source.originating_unit_id = ref["unit_id"]
        p.source.receiving_unit_id = ref["unit_id"]
    p.registration.registration_date = "2025-06-01"
    p.registration.station_id = ref["unit_id"]
    p.registration.district_id = ref["district_id"]
    p.registration.registering_officer_id = ref["officer_id"]
    p.registration.assigned_io_id = ref["officer_id"]
    p.incident.incident_from = "2025-05-31T22:00:00+05:30"
    p.incident.incident_to = "2025-05-31T23:30:00+05:30"
    p.incident.info_received_at = "2025-06-01T08:00:00+05:30"
    p.incident.latitude = ref["lat"]
    p.incident.longitude = ref["lon"]
    p.incident.occurrence_description = "Synthetic occurrence for intake tests."
    p.classification.major_head_id = ref["head_id"]
    p.classification.minor_head_id = ref["subhead_id"]
    p.classification.gravity_id = ref["gravity_id"]
    p.classification.acts_sections = [ActSection(act_code=ref["act_code"], section_code=ref["section_code"])]
    if kind == "missing_person":
        p.classification.category_specific = {"last_seen_at": "2025-05-30T18:00:00+05:30",
                                              "last_seen_location": "Near bus stand"}
    if kind == "udr":
        p.classification.category_specific = {"apparent_cause": "unknown"}
    p.narrative.brief_facts = ("Synthetic brief facts describing the reported incident "
                               "in sufficient detail for validation.")
    p.narrative.language = "en"
    return p


def _parties(kind: str) -> list[PartyInput]:
    parties = [PartyInput(role_type="complainant", display_name="Test Complainant",
                          attributes={"age": 40, "gender_id": 1})]
    if kind in ("fir_standard", "zero_fir"):
        parties.append(PartyInput(role_type="accused", display_name="Test Accused",
                                  attributes={"age": 30, "gender_id": 1}))
        parties.append(PartyInput(role_type="victim", display_name="Test Victim",
                                  attributes={"age": 28, "gender_id": 2}))
    else:
        parties.append(PartyInput(role_type="victim", display_name="Missing/Deceased Person",
                                  attributes={"age": 22, "gender_id": 2}))
    parties.append(PartyInput(role_type="witness", display_name="Test Witness"))
    return parties


def _create(conn, ref, kind) -> str:
    req = CreateDraftRequest(case_kind=kind, payload=_payload(ref, kind),
                             parties=_parties(kind), created_by_actor="io.test")
    return service._create_draft(conn, req)


# ===========================================================================
# Integration — golden paths (rolled back)
# ===========================================================================
_EXPECTED = {
    "fir_standard":   {"category": "FIR",      "prefix": "1", "event": wf.E_REGISTERED,          "status": wf.S_UNDER_INVESTIGATION},
    "zero_fir":       {"category": "Zero FIR", "prefix": "8", "event": wf.E_ZERO_FIR_REGISTERED, "status": wf.S_UNDER_INVESTIGATION},
    "udr":            {"category": "UDR",      "prefix": "3", "event": wf.E_REGISTERED,          "status": wf.S_UNDER_INVESTIGATION},
    "missing_person": {"category": "FIR",      "prefix": "1", "event": wf.E_MISSING_REPORTED,    "status": wf.S_MISSING_TRACING},
}


@requires_db
@pytest.mark.parametrize("kind", list(_EXPECTED))
def test_golden_path_create_validate_submit_approve(rw_rollback, kind):
    conn = rw_rollback
    ref = _reference(conn)
    key = _create(conn, ref, kind)

    v = service._validate(conn, key, persist=True)
    assert v.ok, [e.message for e in v.errors]
    assert v.jurisdiction.in_state is True

    service._submit(conn, key, "io.test")
    result = service._approve(conn, key, "sup.test")

    exp = _EXPECTED[kind]
    assert CRIME_NO_RE.match(result.crime_no), result.crime_no
    assert result.crime_no.startswith(exp["prefix"])
    assert result.case_master_id and result.case_version_id and result.case_event_id
    assert result.canonical_person_ids  # canonical identities created

    with conn.cursor() as cur:
        cur.execute('SELECT "CaseCategoryID" FROM "CaseMaster" WHERE "CaseMasterID"=%s',
                    (result.case_master_id,))
        assert cur.fetchone() is not None
        cur.execute('SELECT "CaseCategoryCode","StatusCode","IsCurrent" FROM "CaseVersion" '
                    'WHERE "CaseMasterID"=%s', (result.case_master_id,))
        cat, status, is_current = cur.fetchone()
        assert cat == exp["category"] and status == exp["status"] and is_current
        cur.execute('SELECT "EventType","ToStatus" FROM "CaseEvent" WHERE "CaseMasterID"=%s',
                    (result.case_master_id,))
        ev_type, ev_to = cur.fetchone()
        assert ev_type == exp["event"] and ev_to == exp["status"]
        # canonical parties + legacy child rows
        cur.execute('SELECT COUNT(*) FROM "CasePartyRole" WHERE "CaseMasterID"=%s',
                    (result.case_master_id,))
        assert int(cur.fetchone()[0]) == len(_parties(kind))
        cur.execute('SELECT "CanonicalPersonID" FROM "ComplainantDetails" WHERE "CaseMasterID"=%s',
                    (result.case_master_id,))
        comp = cur.fetchone()
        assert comp is not None and comp[0] is not None   # legacy row linked to canonical id
    conn.rollback()


@requires_db
def test_approve_persists_actsection_and_source_committed(rw_rollback):
    conn = rw_rollback
    ref = _reference(conn)
    key = _create(conn, ref, "fir_standard")
    service._validate(conn, key, persist=True)
    service._submit(conn, key, "io.test")
    result = service._approve(conn, key, "sup.test")
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM "ActSectionAssociation" WHERE "CaseMasterID"=%s',
                    (result.case_master_id,))
        assert int(cur.fetchone()[0]) >= 1
        cur.execute('SELECT "Status" FROM "IntakeDraft" WHERE "DraftKey"=%s', (key,))
        assert cur.fetchone()[0] == "approved"
    conn.rollback()


# ===========================================================================
# Integration — validation
# ===========================================================================
@requires_db
def test_validate_flags_missing_required(rw_rollback):
    conn = rw_rollback
    req = CreateDraftRequest(case_kind="fir_standard")  # empty payload, no parties
    key = service._create_draft(conn, req)
    v = service._validate(conn, key, persist=True)
    assert v.ok is False
    codes = {(e.field, e.code) for e in v.errors}
    assert ("registration.registration_date", "required") in codes
    assert ("registration.station_id", "required") in codes
    assert ("registration.registering_officer_id", "required") in codes
    assert ("classification.major_head_id", "required") in codes
    assert ("narrative.brief_facts", "required") in codes
    assert ("people", "reporter_required") in codes
    conn.rollback()


@requires_db
def test_validate_out_of_state_is_blocking(rw_rollback):
    conn = rw_rollback
    ref = _reference(conn)
    p = _payload(ref, "fir_standard")
    p.incident.latitude = 0.0   # Gulf of Guinea — far outside Karnataka
    p.incident.longitude = 0.0
    req = CreateDraftRequest(case_kind="fir_standard", payload=p, parties=_parties("fir_standard"))
    key = service._create_draft(conn, req)
    v = service._validate(conn, key, persist=True)
    assert v.ok is False
    assert any(e.code == "out_of_state" for e in v.errors)
    conn.rollback()


@requires_db
def test_validate_temporal_order_blocking(rw_rollback):
    conn = rw_rollback
    ref = _reference(conn)
    p = _payload(ref, "fir_standard")
    p.incident.incident_from = "2025-06-01T10:00:00+05:30"
    p.incident.incident_to = "2025-06-01T09:00:00+05:30"   # to < from
    req = CreateDraftRequest(case_kind="fir_standard", payload=p, parties=_parties("fir_standard"))
    key = service._create_draft(conn, req)
    v = service._validate(conn, key, persist=True)
    assert any(e.code == "temporal_order" for e in v.errors)
    conn.rollback()


@requires_db
def test_duplicate_source_key_detected(rw_rollback):
    conn = rw_rollback
    ref = _reference(conn)
    p = _payload(ref, "fir_standard")
    p.source.external_source_id = "SYN-EXT-INTAKE-DUP-001"
    req = CreateDraftRequest(case_kind="fir_standard", payload=p, parties=_parties("fir_standard"))
    key = service._create_draft(conn, req)
    service._validate(conn, key, persist=True)
    service._submit(conn, key, "io.test")
    service._approve(conn, key, "sup.test")
    # a second submission with the same external id should surface a candidate
    cands = service._duplicate_candidates(conn, p)
    assert any(c.match_score >= 0.9 and c.external_ref == "SYN-EXT-INTAKE-DUP-001" for c in cands)
    conn.rollback()


# ===========================================================================
# Integration — category state machine (invalid combinations blocked)
# ===========================================================================
@requires_db
@pytest.mark.parametrize("kind", ["udr", "missing_person"])
def test_accused_rejected_for_kind(rw_rollback, kind):
    conn = rw_rollback
    ref = _reference(conn)
    key = _create(conn, ref, kind)
    with pytest.raises(service.IntakeValidationError):
        service._insert_party(conn, service._draft_id(conn, key), kind,
                              PartyInput(role_type="accused", display_name="X"))
    conn.rollback()


@requires_db
def test_case_event_chargesheet_requires_investigation(rw_rollback):
    conn = rw_rollback
    ref = _reference(conn)
    key = _create(conn, ref, "fir_standard")
    service._validate(conn, key, persist=True)
    service._submit(conn, key, "io.test")
    res = service._approve(conn, key, "sup.test")
    cid = res.case_master_id
    # chargesheet before any investigation/arrest -> blocked
    with pytest.raises(service.IntakeConflict):
        service._add_case_event(conn, cid, wf.E_CHARGESHEET_FILED, None, "io", {})
    # after an investigation event it is allowed and advances status
    service._add_case_event(conn, cid, wf.E_INVESTIGATION, None, "io", {})
    ev = service._add_case_event(conn, cid, wf.E_CHARGESHEET_FILED, None, "io", {})
    assert ev.to_status == wf.S_CHARGESHEETED
    assert ev.legacy_status == "Charge Sheeted"
    conn.rollback()


@requires_db
def test_case_event_arrest_blocked_on_udr(rw_rollback):
    conn = rw_rollback
    ref = _reference(conn)
    key = _create(conn, ref, "udr")
    service._validate(conn, key, persist=True)
    service._submit(conn, key, "io.test")
    res = service._approve(conn, key, "sup.test")
    with pytest.raises(service.IntakeConflict):
        service._add_case_event(conn, res.case_master_id, wf.E_ARREST, None, "io", {})
    conn.rollback()


@requires_db
def test_missing_person_chargesheet_blocked_without_conversion(rw_rollback):
    conn = rw_rollback
    ref = _reference(conn)
    key = _create(conn, ref, "missing_person")
    service._validate(conn, key, persist=True)
    service._submit(conn, key, "io.test")
    res = service._approve(conn, key, "sup.test")
    with pytest.raises(service.IntakeConflict):
        service._add_case_event(conn, res.case_master_id, wf.E_CHARGESHEET_FILED, None, "io", {})
    conn.rollback()


# ===========================================================================
# Integration — idempotency + optimistic concurrency
# ===========================================================================
@requires_db
def test_idempotent_create(rw_rollback):
    conn = rw_rollback
    ref = _reference(conn)
    req = CreateDraftRequest(case_kind="fir_standard", idempotency_key="idem-intake-001",
                             payload=_payload(ref, "fir_standard"))
    k1 = service._create_draft(conn, req)
    k2 = service._create_draft(conn, req)
    assert k1 == k2
    conn.rollback()


@requires_db
def test_update_optimistic_concurrency(rw_rollback):
    conn = rw_rollback
    ref = _reference(conn)
    key = _create(conn, ref, "fir_standard")
    p = _payload(ref, "fir_standard")
    p.narrative.brief_facts = "Corrected brief facts for the intake record test."
    # stale expected revision -> conflict
    with pytest.raises(service.IntakeConflict):
        service._update_draft(conn, key, UpdateDraftRequest(payload=p, expected_revision_no=999))
    # correct revision (0 after create) -> ok
    service._update_draft(conn, key, UpdateDraftRequest(payload=p, expected_revision_no=0, autosave=True))
    conn.rollback()


# ===========================================================================
# API — read paths + submit gate (no persistence)
# ===========================================================================
client = TestClient(app)


@requires_db
def test_api_status_submit_enabled_in_phase3():
    r = client.get("/intake/status", headers={"X-Role": "investigator"})
    assert r.status_code == 200
    # Phase 3 turned submit on (synthetic DB confirmed + intake_submit_enabled).
    assert r.json()["submit_enabled"] is True


def test_api_workflow_and_lookups_ok():
    r = client.get("/intake/workflow", headers={"X-Role": "investigator"})
    assert r.status_code == 200 and len(r.json()["kinds"]) == 6
    r = client.get("/intake/lookups", headers={"X-Role": "investigator"})
    assert r.status_code == 200 and len(r.json()["categories"]) == 5


def test_api_policymaker_blocked():
    assert client.get("/intake/lookups", headers={"X-Role": "policymaker"}).status_code == 403


@requires_db
def test_api_submit_gate_returns_409_when_explicitly_disabled(monkeypatch):
    # Re-gate submit via config -> the gate blocks with 409 before the handler.
    monkeypatch.setattr(get_settings(), "intake_submit_enabled", False)
    r = client.post("/intake/drafts/DR-NONEXISTENT/submit", headers={"X-Role": "investigator"}, json={})
    assert r.status_code == 409


@requires_db
def test_api_submit_gate_open_then_404_for_missing():
    # Default (Phase 3) has submit enabled -> gate passes; draft genuinely absent.
    r = client.post("/intake/drafts/DR-NONEXISTENT/submit", headers={"X-Role": "investigator"}, json={})
    assert r.status_code == 404


@requires_db
def test_api_quality_issues_read():
    r = client.get("/intake/quality/issues", headers={"X-Role": "investigator"})
    assert r.status_code == 200
    body = r.json()
    assert "total" in body and isinstance(body["by_severity"], dict)


@requires_db
def test_api_case_parties_uses_canonical_identity():
    # a case with canonical CasePartyRole rows (from the Phase 1 canonical load)
    from app import db
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "CaseMasterID" FROM "CasePartyRole" '
                        'GROUP BY "CaseMasterID" HAVING COUNT(*) > 0 LIMIT 1')
            row = cur.fetchone()
    if row is None:
        pytest.skip("no canonical case parties present")
    r = client.get(f"/intake/cases/{int(row[0])}/parties", headers={"X-Role": "investigator"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert all("role_type" in p for p in body["parties"])
