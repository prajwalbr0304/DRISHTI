"""Casework service — statements, property/seizure, lab results, court events,
bail, disposition, verified outcomes, event-backed lifecycle + timeline.

Design (mirrors app/intake/service.py):
  * Internal ``_fn(conn, ...)`` helpers run on an OPEN connection and never
    commit, so tests drive real SQL then ROLL BACK.
  * Public functions open app.db.rw_conn()/ro_conn() and delegate.

Safety rules enforced server-side (Phase 7 DoD):
  * append-only statement versions (never overwrite history);
  * restricted statements are redacted for roles without sensitive access;
  * court/disposition events require their prerequisites;
  * an OutcomeObservation may be created ONLY after a verified final event;
  * uploaded files are linked by id only — content is never parsed.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Optional

from psycopg2.extras import Json

from .. import audit, db
from ..intake import service as intake_service
from ..intake import workflow as wf
from ..roles import ALL_ROLES
from . import schemas as S


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class CaseworkError(Exception):
    pass


class CaseworkNotFound(CaseworkError):
    pass


class CaseworkConflict(CaseworkError):
    pass


class CaseworkValidationError(CaseworkError):
    pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATEMENT_TYPES = ("witness", "complainant", "accused", "expert")
STATEMENT_STATES = ("draft", "recorded", "reviewed")
ACCESS_CLASSIFICATIONS = ("demo_normal", "restricted")
PROPERTY_ITEM_TYPES = ("property", "vehicle", "weapon", "substance", "document")
PROPERTY_STATUSES = ("seized", "recovered", "returned", "disposed")
COURT_EVENT_TYPES = ("chargesheet_filed", "supplementary_chargesheet", "hearing",
                     "remand", "framing_of_charges", "judgment", "adjournment",
                     "bail_hearing", "transfer")
BAIL_STATUSES = ("granted", "rejected", "pending")
DISPOSITION_TYPES = ("convicted", "acquitted", "closed_b_report", "closed_c_report",
                     "transferred", "pending", "withdrawn")
LAB_TEST_TYPES = ("chemical", "dna", "ballistic", "fingerprint", "toxicology",
                  "handwriting", "digital_forensic", "other")
LAB_STATUSES = ("requested", "in_progress", "completed", "inconclusive", "cancelled")

# Roles allowed to read restricted statement/lab text.
# INTERIM ("all roles have access to everything"): every command role may read it.
SENSITIVE_ROLES = set(ALL_ROLES)
REDACTED_TEXT = "[Restricted — limited to assigned investigators / supervisors]"

FINAL_DISPOSITION_TYPES = {"convicted", "acquitted", "closed_b_report",
                           "closed_c_report", "withdrawn"}
DISPOSITION_NEEDS_JUDGMENT = {"convicted", "acquitted"}
TERMINAL_STATUSES = {
    wf.S_CONVICTED, wf.S_ACQUITTED, wf.S_UNDETECTED, wf.S_FALSE, wf.S_TRANSFERRED,
    wf.S_MISSING_RECOVERED, wf.S_MISSING_UNTRACED, wf.S_ENQUIRY_CLOSED,
    wf.S_INQUEST_CLOSED, wf.S_CONVERTED,
}
# reverse of STATUS_TO_LEGACY for deriving a rich status from a legacy row.
LEGACY_TO_STATUS = {v: k for k, v in wf.STATUS_TO_LEGACY.items()}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s(v) -> Optional[str]:
    return str(v) if v is not None else None


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def _can_see_restricted(role: Optional[str]) -> bool:
    return (role or "") in SENSITIVE_ROLES


def _case_exists(conn, cid: int) -> bool:
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "CaseMaster" WHERE "CaseMasterID"=%s', (cid,))
        return cur.fetchone() is not None


def _require_case(conn, cid: int) -> None:
    if not _case_exists(conn, cid):
        raise CaseworkNotFound(f"Case {cid} not found.")


def _person_label(conn, cpid: Optional[int]) -> tuple[Optional[str], Optional[str]]:
    if not cpid:
        return None, None
    with conn.cursor() as cur:
        cur.execute('SELECT "PublicRef", COALESCE("DisplayLabel","PublicRef") '
                    'FROM "CanonicalPerson" WHERE "CanonicalPersonID"=%s', (cpid,))
        r = cur.fetchone()
    return (r[0], r[1]) if r else (None, None)


def _court_name(conn, court_id: Optional[int]) -> Optional[str]:
    if not court_id:
        return None
    with conn.cursor() as cur:
        cur.execute('SELECT "CourtName" FROM "Court" WHERE "CourtID"=%s', (court_id,))
        r = cur.fetchone()
    return r[0] if r else None


# ===========================================================================
# STATEMENTS
# ===========================================================================
def _statement_versions(conn, sid: int, can_see: bool, restricted: bool) -> list[S.StatementVersionOut]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "StatementVersionID","VersionNo","StatementText","CorrectionReason",'
            '"Translation","Redacted","CreatedByActor","CreatedAt" '
            'FROM "StatementVersion" WHERE "StatementID"=%s ORDER BY "VersionNo"', (sid,))
        rows = cur.fetchall()
    out = []
    for r in rows:
        hide = (restricted or bool(r[5])) and not can_see
        out.append(S.StatementVersionOut(
            statement_version_id=int(r[0]), version_no=int(r[1]),
            statement_text=(REDACTED_TEXT if hide else r[2]),
            correction_reason=r[3], translation=(None if hide else r[4]),
            redacted=bool(r[5]), created_by_actor=r[6], created_at=_s(r[7])))
    return out


def _serialize_statement(conn, sid: int, role: Optional[str]) -> S.StatementOut:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "StatementID","CaseMasterID","CanonicalPersonID","CasePartyRoleID",'
            '"StatementType","RecordedByActor","RecordedAt","Place","Language",'
            '"AccessClassification","State","EvidenceItemID","CreatedAt" '
            'FROM "Statement" WHERE "StatementID"=%s', (sid,))
        r = cur.fetchone()
    if r is None:
        raise CaseworkNotFound(f"Statement {sid} not found.")
    restricted = (r[9] == "restricted")
    can_see = _can_see_restricted(role)
    ref, label = _person_label(conn, r[2])
    versions = _statement_versions(conn, sid, can_see, restricted)
    current = versions[-1] if versions else None
    access_limited = restricted and not can_see
    return S.StatementOut(
        statement_id=int(r[0]), case_master_id=int(r[1]), canonical_person_id=r[2],
        speaker_ref=ref, speaker_label=label, case_party_role_id=r[3],
        statement_type=r[4], recorded_by_actor=r[5], recorded_at=_s(r[6]), place=r[7],
        language=r[8], access_classification=r[9], state=r[10], evidence_item_id=r[11],
        current_text=(current.statement_text if current else None),
        current_version_no=(current.version_no if current else None),
        is_restricted=restricted, access_limited=access_limited,
        versions=versions, created_at=_s(r[12]))


def _create_statement(conn, cid: int, req: S.StatementCreate, role: Optional[str]) -> int:
    _require_case(conn, cid)
    _require_procedural_write(conn, cid)
    if req.statement_type not in STATEMENT_TYPES:
        raise CaseworkValidationError(f"Unknown statement type '{req.statement_type}'.")
    if req.access_classification not in ACCESS_CLASSIFICATIONS:
        raise CaseworkValidationError(f"Unknown access classification '{req.access_classification}'.")
    if not req.statement_text or not req.statement_text.strip():
        raise CaseworkValidationError("Statement text is required.")
    if req.canonical_person_id is not None:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "CanonicalPerson" WHERE "CanonicalPersonID"=%s',
                        (req.canonical_person_id,))
            if cur.fetchone() is None:
                raise CaseworkValidationError(f"Canonical person {req.canonical_person_id} not found.")
    if req.evidence_item_id is not None:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "EvidenceItem" WHERE "EvidenceItemID"=%s', (req.evidence_item_id,))
            if cur.fetchone() is None:
                raise CaseworkValidationError(f"Evidence item {req.evidence_item_id} not found.")
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "Statement" ("CaseMasterID","CanonicalPersonID","CasePartyRoleID",'
            '"StatementType","RecordedByActor","RecordedAt","Place","Language",'
            '"AccessClassification","State","EvidenceItemID") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "StatementID"',
            (cid, req.canonical_person_id, req.case_party_role_id, req.statement_type,
             req.recorded_by_actor or (f"demo.{role}" if role else None), req.recorded_at,
             req.place, req.language, req.access_classification, "recorded", req.evidence_item_id))
        sid = int(cur.fetchone()[0])
        cur.execute(
            'INSERT INTO "StatementVersion" ("StatementID","VersionNo","StatementText",'
            '"CorrectionReason","CreatedByActor") VALUES (%s,1,%s,%s,%s)',
            (sid, req.statement_text.strip(), "initial statement", req.actor or (f"demo.{role}" if role else None)))
    audit.record(audit.Action.CREATE, "statement", sid, actor=req.actor, conn=conn,
                 detail={"case_id": cid, "type": req.statement_type,
                         "restricted": req.access_classification == "restricted"})
    return sid


def _correct_statement(conn, sid: int, req: S.StatementCorrection, role: Optional[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "State","AccessClassification","CaseMasterID" '
            'FROM "Statement" WHERE "StatementID"=%s',
            (sid,),
        )
        r = cur.fetchone()
        if r is None:
            raise CaseworkNotFound(f"Statement {sid} not found.")
        _require_procedural_write(conn, int(r[2]))
        if r[0] == "reviewed":
            raise CaseworkConflict("A reviewed statement is locked; reopen review before correcting.")
        cur.execute('SELECT COALESCE(MAX("VersionNo"),0), '
                    '(SELECT "StatementText" FROM "StatementVersion" WHERE "StatementID"=%s '
                    ' ORDER BY "VersionNo" DESC LIMIT 1) '
                    'FROM "StatementVersion" WHERE "StatementID"=%s', (sid, sid))
        maxv, prev_text = cur.fetchone()
        new_no = int(maxv) + 1
        text = (req.statement_text.strip() if req.statement_text and req.statement_text.strip()
                else prev_text)
        cur.execute(
            'INSERT INTO "StatementVersion" ("StatementID","VersionNo","StatementText",'
            '"CorrectionReason","Translation","Redacted","CreatedByActor") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (sid, new_no, text, req.correction_reason, req.translation, req.redact,
             req.actor or (f"demo.{role}" if role else None)))
        if req.redact:
            cur.execute('UPDATE "Statement" SET "AccessClassification"=\'restricted\' WHERE "StatementID"=%s', (sid,))
    audit.record(audit.Action.UPDATE, "statement", sid, actor=req.actor, conn=conn,
                 detail={"version": new_no, "redacted": req.redact})


def _review_statement(conn, sid: int, req: S.StatementReview) -> None:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "Statement" WHERE "StatementID"=%s', (sid,))
        row = cur.fetchone()
        if row is None:
            raise CaseworkNotFound(f"Statement {sid} not found.")
        _require_procedural_write(conn, int(row[0]))
        cur.execute('UPDATE "Statement" SET "State"=\'reviewed\' WHERE "StatementID"=%s', (sid,))
    audit.record(audit.Action.UPDATE, "statement", sid, actor=req.actor, conn=conn,
                 detail={"action": "review", "note": req.note})


def _list_statements(conn, cid: int, role: Optional[str]) -> S.StatementListResponse:
    _require_case(conn, cid)
    with conn.cursor() as cur:
        cur.execute('SELECT "StatementID" FROM "Statement" WHERE "CaseMasterID"=%s '
                    'ORDER BY "StatementID"', (cid,))
        ids = [int(r[0]) for r in cur.fetchall()]
    items = [_serialize_statement(conn, sid, role) for sid in ids]
    return S.StatementListResponse(case_master_id=cid, count=len(items), items=items)


# ===========================================================================
# PROPERTY / SEIZURE
# ===========================================================================
def _serialize_property_item(conn, r) -> S.PropertyItemOut:
    ref, label = _person_label(conn, r[8])
    return S.PropertyItemOut(
        property_item_id=int(r[0]), seizure_id=r[1], case_master_id=int(r[2]),
        item_type=r[3], synthetic_identifier=r[4], description=r[5], quantity=_f(r[6]),
        unit=r[7], estimated_value=_f(r[9]), owner_canonical_person_id=r[8],
        owner_label=label, status=r[10], vehicle_fields=r[11] or {}, weapon_fields=r[12] or {},
        created_at=_s(r[13]))


# _serialize_property_item expects this column order:
# 0 PropertyItemID,1 SeizureID,2 CaseMasterID,3 ItemType,4 SyntheticIdentifier,
# 5 Description,6 Quantity,7 Unit,8 OwnerCanonicalPersonID,9 EstimatedValue,
# 10 Status,11 VehicleFields,12 WeaponFields,13 CreatedAt


def _fetch_property_item(conn, pid: int):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "PropertyItemID","SeizureID","CaseMasterID","ItemType","SyntheticIdentifier",'
            '"Description","Quantity","Unit","OwnerCanonicalPersonID","EstimatedValue","Status",'
            '"VehicleFields","WeaponFields","CreatedAt" FROM "PropertyItem" WHERE "PropertyItemID"=%s',
            (pid,))
        return cur.fetchone()


def _insert_property_item(conn, cid: int, seizure_id: Optional[int], p: S.PropertyItemInput) -> int:
    if p.item_type not in PROPERTY_ITEM_TYPES:
        raise CaseworkValidationError(f"Unknown property item type '{p.item_type}'.")
    if p.status not in PROPERTY_STATUSES:
        raise CaseworkValidationError(f"Unknown property status '{p.status}'.")
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "PropertyItem" ("SeizureID","CaseMasterID","ItemType","SyntheticIdentifier",'
            '"Description","Quantity","Unit","EstimatedValue","OwnerCanonicalPersonID","Status",'
            '"VehicleFields","WeaponFields") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
            'RETURNING "PropertyItemID"',
            (seizure_id, cid, p.item_type, p.synthetic_identifier, p.description, p.quantity,
             p.unit, p.estimated_value, p.owner_canonical_person_id, p.status,
             Json(p.vehicle_fields or {}), Json(p.weapon_fields or {})))
        return int(cur.fetchone()[0])


def _create_seizure(conn, cid: int, req: S.SeizureCreate, role: Optional[str]) -> int:
    _require_case(conn, cid)
    _require_procedural_write(conn, cid)
    if req.memo_evidence_item_id is not None:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "EvidenceItem" WHERE "EvidenceItemID"=%s', (req.memo_evidence_item_id,))
            if cur.fetchone() is None:
                raise CaseworkValidationError(f"Memo evidence item {req.memo_evidence_item_id} not found.")
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "Seizure" ("CaseMasterID","SeizureType","SeizedAt","Place",'
            '"MemoEvidenceItemID","Actor") VALUES (%s,%s,%s,%s,%s,%s) RETURNING "SeizureID"',
            (cid, req.seizure_type, req.seized_at, req.place, req.memo_evidence_item_id,
             req.actor or (f"demo.{role}" if role else None)))
        seizure_id = int(cur.fetchone()[0])
    for p in req.items:
        _insert_property_item(conn, cid, seizure_id, p)
    audit.record(audit.Action.CREATE, "seizure", seizure_id, actor=req.actor, conn=conn,
                 detail={"case_id": cid, "items": len(req.items)})
    return seizure_id


def _change_property_status(conn, pid: int, req: S.PropertyStatusChange) -> None:
    row = _fetch_property_item(conn, pid)
    if row is None:
        raise CaseworkNotFound(f"Property item {pid} not found.")
    _require_procedural_write(conn, int(row[2]))
    if req.status not in PROPERTY_STATUSES:
        raise CaseworkValidationError(f"Unknown property status '{req.status}'.")
    with conn.cursor() as cur:
        cur.execute('UPDATE "PropertyItem" SET "Status"=%s WHERE "PropertyItemID"=%s', (req.status, pid))
    audit.record(audit.Action.UPDATE, "property_item", pid, actor=req.actor, conn=conn,
                 detail={"from": row[10], "to": req.status, "note": req.note})


def _list_seizures(conn, cid: int) -> S.SeizureListResponse:
    _require_case(conn, cid)
    with conn.cursor() as cur:
        cur.execute('SELECT "SeizureID","CaseMasterID","SeizureType","SeizedAt","Place",'
                    '"MemoEvidenceItemID","Actor","CreatedAt" FROM "Seizure" '
                    'WHERE "CaseMasterID"=%s ORDER BY "SeizureID"', (cid,))
        srows = cur.fetchall()
        cur.execute(
            'SELECT "PropertyItemID","SeizureID","CaseMasterID","ItemType","SyntheticIdentifier",'
            '"Description","Quantity","Unit","OwnerCanonicalPersonID","EstimatedValue","Status",'
            '"VehicleFields","WeaponFields","CreatedAt" FROM "PropertyItem" '
            'WHERE "CaseMasterID"=%s ORDER BY "PropertyItemID"', (cid,))
        prows = cur.fetchall()
    items_by_seizure: dict[Optional[int], list] = {}
    for pr in prows:
        items_by_seizure.setdefault(pr[1], []).append(_serialize_property_item(conn, pr))
    seizures = [S.SeizureOut(
        seizure_id=int(s[0]), case_master_id=int(s[1]), seizure_type=s[2], seized_at=_s(s[3]),
        place=s[4], memo_evidence_item_id=s[5], actor=s[6], created_at=_s(s[7]),
        items=items_by_seizure.get(int(s[0]), [])) for s in srows]
    unlinked = items_by_seizure.get(None, [])
    return S.SeizureListResponse(case_master_id=cid, seizures=seizures, unlinked_items=unlinked,
                                 count=len(seizures) + len(unlinked))


# ===========================================================================
# LAB RESULTS
# ===========================================================================
def _serialize_lab(conn, r, role: Optional[str]) -> S.LabResultOut:
    restricted = (r[11] == "restricted")
    hide = restricted and not _can_see_restricted(role)
    return S.LabResultOut(
        lab_result_id=int(r[0]), case_master_id=int(r[1]), property_item_id=r[2], seizure_id=r[3],
        test_type=r[4], lab_name=r[5], synthetic_reference=r[6], requested_at=_s(r[7]),
        result_at=_s(r[8]), result_summary=(REDACTED_TEXT if hide else r[9]), status=r[10],
        report_evidence_item_id=r[12], access_classification=r[11], access_limited=hide,
        created_by_actor=r[13], created_at=_s(r[14]))


_LAB_COLS = ('"LabResultID","CaseMasterID","PropertyItemID","SeizureID","TestType","LabName",'
             '"SyntheticReference","RequestedAt","ResultAt","ResultSummary","Status",'
             '"AccessClassification","ReportEvidenceItemID","CreatedByActor","CreatedAt"')


def _create_lab(conn, cid: int, req: S.LabResultInput, role: Optional[str]) -> int:
    _require_case(conn, cid)
    _require_procedural_write(conn, cid)
    if req.status not in LAB_STATUSES:
        raise CaseworkValidationError(f"Unknown lab status '{req.status}'.")
    if not req.test_type or not req.test_type.strip():
        raise CaseworkValidationError("Lab test type is required.")
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "LabResult" ("CaseMasterID","PropertyItemID","SeizureID","TestType",'
            '"LabName","SyntheticReference","RequestedAt","ResultAt","ResultSummary","Status",'
            '"ReportEvidenceItemID","AccessClassification","CreatedByActor") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "LabResultID"',
            (cid, req.property_item_id, req.seizure_id, req.test_type.strip(), req.lab_name,
             req.synthetic_reference, req.requested_at, req.result_at, req.result_summary,
             req.status, req.report_evidence_item_id, req.access_classification,
             req.actor or (f"demo.{role}" if role else None)))
        lid = int(cur.fetchone()[0])
    audit.record(audit.Action.CREATE, "lab_result", lid, actor=req.actor, conn=conn,
                 detail={"case_id": cid, "test_type": req.test_type})
    return lid


def _update_lab(conn, lid: int, req: S.LabResultUpdate) -> None:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "LabResult" WHERE "LabResultID"=%s', (lid,))
        row = cur.fetchone()
    if row is None:
        raise CaseworkNotFound(f"Lab result {lid} not found.")
    _require_procedural_write(conn, int(row[0]))

    sets, params = [], []
    if req.status is not None:
        if req.status not in LAB_STATUSES:
            raise CaseworkValidationError(f"Unknown lab status '{req.status}'.")
        sets.append('"Status"=%s'); params.append(req.status)
    if req.result_at is not None:
        sets.append('"ResultAt"=%s'); params.append(req.result_at)
    if req.result_summary is not None:
        sets.append('"ResultSummary"=%s'); params.append(req.result_summary)
    if req.report_evidence_item_id is not None:
        sets.append('"ReportEvidenceItemID"=%s'); params.append(req.report_evidence_item_id)
    if not sets:
        raise CaseworkValidationError("No lab-result fields supplied to update.")
    params.append(lid)
    with conn.cursor() as cur:
        cur.execute(f'UPDATE "LabResult" SET {", ".join(sets)} WHERE "LabResultID"=%s', params)
        if cur.rowcount == 0:
            raise CaseworkNotFound(f"Lab result {lid} not found.")
    audit.record(audit.Action.UPDATE, "lab_result", lid, actor=req.actor, conn=conn,
                 detail={"status": req.status})


def _list_labs(conn, cid: int, role: Optional[str]) -> S.LabResultListResponse:
    _require_case(conn, cid)
    with conn.cursor() as cur:
        cur.execute(f'SELECT {_LAB_COLS} FROM "LabResult" WHERE "CaseMasterID"=%s ORDER BY "LabResultID"',
                    (cid,))
        rows = cur.fetchall()
    items = [_serialize_lab(conn, r, role) for r in rows]
    return S.LabResultListResponse(case_master_id=cid, count=len(items), items=items)


# ===========================================================================
# COURT / BAIL / DISPOSITION / OUTCOME
# ===========================================================================
def _curated_procedural_policy(conn, cid: int) -> tuple[bool, Optional[str]]:
    """Return whether generic procedural writes are barred for this case.

    Public-source snapshots are regenerated from reviewed sources; allowing an
    operational UI action to append a judgment or advance status would silently
    convert an attributed presentation record into an unsourced legal claim.
    """
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "SnapshotAttributes" FROM "CaseVersion" '
            'WHERE "CaseMasterID"=%s AND "IsCurrent"=TRUE '
            'ORDER BY "VersionNo" DESC LIMIT 1',
            (cid,),
        )
        row = cur.fetchone()
    attrs = row[0] if row and isinstance(row[0], dict) else {}
    read_only = attrs.get("record_origin") == "public_source_curated"
    reason = (
        "Public-source curated procedure is read-only; update the checked-in "
        "sources and create a reviewed source-qualified version instead."
        if read_only else None
    )
    return read_only, reason


def _require_procedural_write(conn, cid: int) -> None:
    read_only, reason = _curated_procedural_policy(conn, cid)
    if read_only:
        raise CaseworkConflict(reason or "This case is read-only.")


def _court_prior_types(conn, cid: int) -> set[str]:
    with conn.cursor() as cur:
        cur.execute('SELECT DISTINCT "EventType" FROM "CourtEvent" WHERE "CaseMasterID"=%s', (cid,))
        return {r[0] for r in cur.fetchall()}


def _has_chargesheet(conn, cid: int, court_types: set[str]) -> bool:
    if "chargesheet_filed" in court_types:
        return True
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "CaseEvent" WHERE "CaseMasterID"=%s '
                    "AND \"EventType\" IN ('chargesheet_filed','court_assigned') LIMIT 1", (cid,))
        if cur.fetchone():
            return True
        cur.execute('SELECT 1 FROM "ChargesheetDetails" WHERE "CaseMasterID"=%s LIMIT 1', (cid,))
        return cur.fetchone() is not None


def _add_court_event(conn, cid: int, req: S.CourtEventInput, role: Optional[str]) -> int:
    _require_case(conn, cid)
    _require_procedural_write(conn, cid)
    if req.event_type not in COURT_EVENT_TYPES:
        raise CaseworkValidationError(f"Unknown court event type '{req.event_type}'.")
    court_types = _court_prior_types(conn, cid)
    has_cs = _has_chargesheet(conn, cid, court_types)
    et = req.event_type
    if et == "supplementary_chargesheet" and not has_cs:
        raise CaseworkValidationError(
            "A supplementary chargesheet requires a prior chargesheet.")
    if et in ("hearing", "remand", "framing_of_charges", "adjournment") and not has_cs:
        raise CaseworkValidationError(
            f"A '{et}' court event requires the case to be charge-sheeted / committed to court first.")
    if et == "judgment" and not (
            has_cs or "hearing" in court_types or "framing_of_charges" in court_types):
        raise CaseworkValidationError(
            "A judgment requires a prior chargesheet or hearing.")
    if req.court_id is not None and _court_name(conn, req.court_id) is None:
        raise CaseworkValidationError(f"Court {req.court_id} not found.")
    detail = dict(req.detail or {})
    if req.evidence_item_id is not None:
        detail["evidence_item_id"] = req.evidence_item_id
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "CourtEvent" ("CaseMasterID","CourtID","EventType","ScheduledAt",'
            '"OccurredAt","Outcome","Detail") VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING "CourtEventID"',
            (cid, req.court_id, et, req.scheduled_at, req.occurred_at, req.outcome, Json(detail)))
        ceid = int(cur.fetchone()[0])
    audit.record(audit.Action.CASE_EVENT, "court_event", ceid, actor=req.actor, conn=conn,
                 detail={"case_id": cid, "event_type": et})
    return ceid


def _add_bail(conn, cid: int, req: S.BailInput, role: Optional[str]) -> int:
    _require_case(conn, cid)
    _require_procedural_write(conn, cid)
    if req.status not in BAIL_STATUSES:
        raise CaseworkValidationError(f"Unknown bail status '{req.status}'.")
    if req.court_id is not None and _court_name(conn, req.court_id) is None:
        raise CaseworkValidationError(f"Court {req.court_id} not found.")
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "BailEvent" ("CaseMasterID","CanonicalPersonID","BailType","Status",'
            '"DecidedAt","CourtID","Detail") VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING "BailEventID"',
            (cid, req.canonical_person_id, req.bail_type, req.status, req.decided_at,
             req.court_id, Json(req.detail or {})))
        bid = int(cur.fetchone()[0])
    audit.record(audit.Action.CASE_EVENT, "bail_event", bid, actor=req.actor, conn=conn,
                 detail={"case_id": cid, "status": req.status})
    return bid


def _add_disposition(conn, cid: int, req: S.DispositionInput, role: Optional[str]) -> int:
    _require_case(conn, cid)
    _require_procedural_write(conn, cid)
    if req.disposition_type not in DISPOSITION_TYPES:
        raise CaseworkValidationError(f"Unknown disposition type '{req.disposition_type}'.")
    if req.disposition_type in DISPOSITION_NEEDS_JUDGMENT:
        court_types = _court_prior_types(conn, cid)
        if "judgment" not in court_types:
            raise CaseworkValidationError(
                f"A '{req.disposition_type}' disposition requires a prior recorded judgment.")
    if req.court_event_id is not None:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "CourtEvent" WHERE "CourtEventID"=%s AND "CaseMasterID"=%s',
                        (req.court_event_id, cid))
            if cur.fetchone() is None:
                raise CaseworkValidationError(f"Court event {req.court_event_id} not found on this case.")
    is_final = req.is_final if req.is_final is not None else (req.disposition_type in FINAL_DISPOSITION_TYPES)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "CaseDisposition" ("CaseMasterID","DispositionType","DispositionDate",'
            '"CourtEventID","IsFinal","Detail") VALUES (%s,%s,%s,%s,%s,%s) RETURNING "CaseDispositionID"',
            (cid, req.disposition_type, req.disposition_date, req.court_event_id, is_final,
             Json(req.detail or {})))
        did = int(cur.fetchone()[0])
    audit.record(audit.Action.CASE_EVENT, "case_disposition", did, actor=req.actor, conn=conn,
                 detail={"case_id": cid, "type": req.disposition_type, "final": is_final})
    return did


def _has_final_event(conn, cid: int) -> bool:
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "CaseDisposition" WHERE "CaseMasterID"=%s AND "IsFinal"=TRUE LIMIT 1', (cid,))
        if cur.fetchone():
            return True
        cur.execute("SELECT 1 FROM \"CourtEvent\" WHERE \"CaseMasterID\"=%s AND \"EventType\"='judgment' LIMIT 1", (cid,))
        return cur.fetchone() is not None


def _terminal_case_event_id(conn, cid: int) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseEventID" FROM "CaseEvent" WHERE "CaseMasterID"=%s '
                    'AND "ToStatus" = ANY(%s) ORDER BY "SequenceNo" DESC LIMIT 1',
                    (cid, list(TERMINAL_STATUSES)))
        r = cur.fetchone()
    return int(r[0]) if r else None


def _add_outcome(conn, cid: int, req: S.OutcomeInput, role: Optional[str]) -> int:
    _require_case(conn, cid)
    _require_procedural_write(conn, cid)
    if not _has_final_event(conn, cid):
        raise CaseworkConflict(
            "No verified final event yet (a final disposition or a judgment). "
            "An outcome observation cannot be recorded before a case is finally concluded.")
    observed_at = req.observed_at or _now_iso()
    if req.observation_window_end and observed_at < req.observation_window_end:
        raise CaseworkValidationError(
            "Observed date must be on/after the observation window end (no label leakage).")
    src = _terminal_case_event_id(conn, cid)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "OutcomeObservation" ("CaseMasterID","ObservationType","ObservedAt",'
            '"ObservationWindowStart","ObservationWindowEnd","Verified","SourceEventID","Detail") '
            'VALUES (%s,%s,%s,%s,%s,TRUE,%s,%s) RETURNING "OutcomeObservationID"',
            (cid, req.observation_type, observed_at, req.observation_window_start,
             req.observation_window_end, src, Json(req.detail or {})))
        oid = int(cur.fetchone()[0])
    audit.record(audit.Action.CASE_EVENT, "outcome_observation", oid, actor=req.actor, conn=conn,
                 detail={"case_id": cid, "type": req.observation_type})
    return oid


def _court_events(conn, cid: int) -> list[S.CourtEventOut]:
    with conn.cursor() as cur:
        cur.execute('SELECT "CourtEventID","CaseMasterID","CourtID","EventType","ScheduledAt",'
                    '"OccurredAt","Outcome","Detail","CreatedAt" FROM "CourtEvent" '
                    'WHERE "CaseMasterID"=%s ORDER BY COALESCE("OccurredAt","ScheduledAt","CreatedAt"), '
                    '"CourtEventID"', (cid,))
        rows = cur.fetchall()
    out: list[S.CourtEventOut] = []
    for r in rows:
        detail = r[7] if isinstance(r[7], dict) else {}
        proxy = detail.get("reference_mapping") == "proxy"
        sourced_label = detail.get("public_court_label") or detail.get("reported_court_label")
        court_name = sourced_label if proxy else _court_name(conn, r[2])
        reference_kind = (
            "public_source" if proxy and sourced_label
            else "unasserted" if proxy
            else "operational_reference"
        )
        out.append(S.CourtEventOut(
            court_event_id=int(r[0]), case_master_id=int(r[1]), court_id=r[2],
            court_name=court_name, court_reference_kind=reference_kind,
            event_type=r[3], scheduled_at=_s(r[4]), occurred_at=_s(r[5]),
            outcome=r[6], detail=detail, created_at=_s(r[8])))
    return out


def _bail_events(conn, cid: int) -> list[S.BailOut]:
    with conn.cursor() as cur:
        cur.execute('SELECT "BailEventID","CaseMasterID","CanonicalPersonID","BailType","Status",'
                    '"DecidedAt","CourtID","Detail","CreatedAt" FROM "BailEvent" '
                    'WHERE "CaseMasterID"=%s ORDER BY "BailEventID"', (cid,))
        rows = cur.fetchall()
    out = []
    for r in rows:
        _, label = _person_label(conn, r[2])
        out.append(S.BailOut(
            bail_event_id=int(r[0]), case_master_id=int(r[1]), canonical_person_id=r[2],
            person_label=label, bail_type=r[3], status=r[4], decided_at=_s(r[5]),
            court_id=r[6], detail=r[7] or {}, created_at=_s(r[8])))
    return out


def _dispositions(conn, cid: int) -> list[S.DispositionOut]:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseDispositionID","CaseMasterID","DispositionType","DispositionDate",'
                    '"CourtEventID","IsFinal","Detail","CreatedAt" FROM "CaseDisposition" '
                    'WHERE "CaseMasterID"=%s ORDER BY "CaseDispositionID"', (cid,))
        rows = cur.fetchall()
    return [S.DispositionOut(
        case_disposition_id=int(r[0]), case_master_id=int(r[1]), disposition_type=r[2],
        disposition_date=_s(r[3]), court_event_id=r[4], is_final=bool(r[5]), detail=r[6] or {},
        created_at=_s(r[7])) for r in rows]


def _outcomes(conn, cid: int) -> list[S.OutcomeOut]:
    with conn.cursor() as cur:
        cur.execute('SELECT "OutcomeObservationID","CaseMasterID","ObservationType","ObservedAt",'
                    '"ObservationWindowStart","ObservationWindowEnd","Verified","SourceEventID","Detail","CreatedAt" '
                    'FROM "OutcomeObservation" WHERE "CaseMasterID"=%s ORDER BY "OutcomeObservationID"', (cid,))
        rows = cur.fetchall()
    return [S.OutcomeOut(
        outcome_observation_id=int(r[0]), case_master_id=int(r[1]), observation_type=r[2],
        observed_at=_s(r[3]), observation_window_start=_s(r[4]), observation_window_end=_s(r[5]),
        verified=bool(r[6]), source_event_id=r[7], detail=r[8] or {}, created_at=_s(r[9])) for r in rows]


# ---------------------------------------------------------------------------
# Case category + status derivation
# ---------------------------------------------------------------------------
def _legacy_category(conn, cid: int) -> Optional[str]:
    with conn.cursor() as cur:
        cur.execute('SELECT cc."LookupValue" FROM "CaseMaster" cm '
                    'JOIN "CaseCategory" cc ON cc."CaseCategoryID"=cm."CaseCategoryID" '
                    'WHERE cm."CaseMasterID"=%s', (cid,))
        r = cur.fetchone()
    return r[0] if r else None


def _legacy_status_name(conn, cid: int) -> Optional[str]:
    with conn.cursor() as cur:
        cur.execute('SELECT st."CaseStatusName" FROM "CaseMaster" cm '
                    'JOIN "CaseStatusMaster" st ON st."CaseStatusID"=cm."CaseStatusID" '
                    'WHERE cm."CaseMasterID"=%s', (cid,))
        r = cur.fetchone()
    return r[0] if r else None


def _current_version(conn, cid: int):
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseVersionID","CaseCategoryCode","StatusCode",'
                    '"SnapshotAttributes" FROM "CaseVersion" '
                    'WHERE "CaseMasterID"=%s AND "IsCurrent" '
                    'ORDER BY "VersionNo" DESC LIMIT 1', (cid,))
        return cur.fetchone()


def _prior_event_types(conn, cid: int) -> list[str]:
    with conn.cursor() as cur:
        cur.execute('SELECT "EventType" FROM "CaseEvent" WHERE "CaseMasterID"=%s ORDER BY "SequenceNo"', (cid,))
        return [r[0] for r in cur.fetchall()]


def _lifecycle_view(conn, cid: int) -> S.CourtLifecycleView:
    _require_case(conn, cid)
    cv = _current_version(conn, cid)
    read_only = False
    read_only_reason = None
    if cv is not None:
        category, current_status = cv[1], cv[2]
        has_version = True
        attrs = cv[3] if isinstance(cv[3], dict) else {}
        read_only = attrs.get("record_origin") == "public_source_curated"
        if read_only:
            read_only_reason = (
                "Public-source curated procedure is presentation-only and can be "
                "updated only through a reviewed source-qualified version."
            )
    else:
        category = _legacy_category(conn, cid) or "FIR"
        legacy_name = _legacy_status_name(conn, cid)
        current_status = LEGACY_TO_STATUS.get(legacy_name or "", wf.S_UNDER_INVESTIGATION)
        has_version = False
    legacy_status = wf.STATUS_TO_LEGACY.get(current_status)
    priors = _prior_event_types(conn, cid)
    # Source-curated procedural claims are read-only. Other cases expose allowed
    # transitions from the seeded state machine for their current status.
    transitions = []
    if not read_only:
        for t in wf.load_transitions(conn, category):
            if t["from_status"] in (None, "", current_status):
                transitions.append(S.TransitionMeta(
                    event_type=t["event_type"], label=wf.EVENT_LABELS.get(t["event_type"], t["event_type"]),
                    from_status=t["from_status"], to_status=t["to_status"],
                    requires_prior_event=t["requires_prior_event"], is_terminal=bool(t["is_terminal"]),
                    description=t["description"]))
    has_final = _has_final_event(conn, cid)
    return S.CourtLifecycleView(
        case_master_id=cid, category=category, current_status=current_status,
        current_status_label=wf.STATUS_LABELS.get(current_status), legacy_status=legacy_status,
        has_case_version=has_version, read_only=read_only, read_only_reason=read_only_reason,
        prior_event_types=priors, allowed_transitions=transitions,
        court_events=_court_events(conn, cid), bail_events=_bail_events(conn, cid),
        dispositions=_dispositions(conn, cid), outcomes=_outcomes(conn, cid),
        has_final_disposition=has_final, can_record_outcome=(has_final and not read_only))


# ---------------------------------------------------------------------------
# Lifecycle events (bootstrap a CaseVersion for legacy cases, then reuse intake)
# ---------------------------------------------------------------------------
def _bootstrap_kind(category: str) -> wf.CaseKind:
    for name in wf.CATEGORY_TO_KINDS.get(category, []):
        if name != "missing_person":
            return wf.CASE_KINDS[name]
    return wf.CASE_KINDS["fir_standard"]


def _ensure_case_version(conn, cid: int) -> bool:
    """Ensure an IsCurrent CaseVersion exists so lifecycle events can be applied.
    Legacy cases (no version) get a bootstrap version derived from their legacy
    category/status/coords PLUS an initial lifecycle event (so later transitions
    have their prerequisite history). Returns True iff a version was created."""
    if _current_version(conn, cid) is not None:
        return False
    category = _legacy_category(conn, cid) or "FIR"
    ck = _bootstrap_kind(category)
    current_status = LEGACY_TO_STATUS.get(_legacy_status_name(conn, cid) or "", ck.initial_status)
    with conn.cursor() as cur:
        cur.execute('SELECT "latitude","longitude","PoliceStationID" FROM "CaseMaster" WHERE "CaseMasterID"=%s', (cid,))
        lat, lon, unit = cur.fetchone()
        district = None
        if unit is not None:
            cur.execute('SELECT "DistrictID" FROM "Unit" WHERE "UnitID"=%s', (unit,))
            dr = cur.fetchone()
            district = dr[0] if dr else None
        cur.execute(
            'INSERT INTO "CaseVersion" ("CaseMasterID","VersionNo","CaseCategoryCode","StatusCode",'
            '"IsCurrent","IncidentLatitude","IncidentLongitude","AssignedDistrictID","AssignedUnitID",'
            '"SnapshotAttributes","ChangeReason","Actor") '
            'VALUES (%s,1,%s,%s,TRUE,%s,%s,%s,%s,%s,%s,%s)',
            (cid, category, current_status, lat, lon, district, unit,
             Json({"bootstrapped": True, "case_kind": ck.name}), "phase7_lifecycle_bootstrap", "phase7"))
        # seed the initial event only if the case has no lifecycle events yet, so
        # prerequisite-gated transitions (e.g. investigation before chargesheet)
        # have a consistent starting point.
        cur.execute('SELECT 1 FROM "CaseEvent" WHERE "CaseMasterID"=%s LIMIT 1', (cid,))
        if cur.fetchone() is None:
            cur.execute(
                'INSERT INTO "CaseEvent" ("CaseMasterID","EventType","EventCategory","SequenceNo",'
                '"OccurredAt","FromStatus","ToStatus","Payload","ActorRole") '
                'VALUES (%s,%s,\'lifecycle\',1,now(),NULL,%s,%s,%s)',
                (cid, ck.initial_event, ck.initial_status,
                 Json({"bootstrapped": True}), "phase7"))
    return True


def _add_lifecycle_event(conn, cid: int, event_type: str, occurred_at: Optional[str],
                         actor_role: Optional[str], payload: dict) -> S.LifecycleEventResult:
    _require_case(conn, cid)
    _require_procedural_write(conn, cid)
    bootstrapped = _ensure_case_version(conn, cid)
    try:
        res = intake_service._add_case_event(conn, cid, event_type, occurred_at, actor_role, payload)
    except intake_service.IntakeConflict as exc:
        raise CaseworkConflict(str(exc))
    except intake_service.IntakeNotFound as exc:
        raise CaseworkNotFound(str(exc))
    return S.LifecycleEventResult(
        case_master_id=cid, case_event_id=res.case_event_id, from_status=res.from_status,
        to_status=res.to_status, is_terminal=res.is_terminal, legacy_status=res.legacy_status,
        bootstrapped_version=bootstrapped)


# ===========================================================================
# TIMELINE
# ===========================================================================
def _timeline(conn, cid: int) -> S.TimelineResponse:
    _require_case(conn, cid)
    entries: list[S.TimelineEntry] = []
    event_backed = False
    case_event_types: set[str] = set()
    case_event_keys: set[tuple[str, Optional[str]]] = set()
    milestone_counts: Counter[tuple[str, Optional[str]]] = Counter()
    with conn.cursor() as cur:
        # 1. append-only lifecycle events (CaseEvent). A curated event may carry
        # a source-qualified display label in Payload; never infer stronger text.
        cur.execute(
            'SELECT "CaseEventID","EventType","OccurredAt","ToStatus","Payload" '
            'FROM "CaseEvent" WHERE "CaseMasterID"=%s ORDER BY "SequenceNo"',
            (cid,),
        )
        for r in cur.fetchall():
            event_backed = True
            payload = r[4] if isinstance(r[4], dict) else {}
            event_date = _s(r[2])
            case_event_types.add(r[1])
            key = (r[1], event_date[:10] if event_date else None)
            case_event_keys.add(key)
            milestone_counts[key] += 1
            entries.append(S.TimelineEntry(
                date=event_date, kind="lifecycle", type=r[1],
                label=payload.get("display_label") or wf.EVENT_LABELS.get(r[1], r[1]),
                detail=(payload.get("display_detail")
                        or (wf.STATUS_LABELS.get(r[3]) if r[3] else None)),
                ref_id=int(r[0])))
        # 2. court events. Suppress exact type/day duplicates already represented
        # by a CaseEvent while retaining court-only procedural milestones.
        cur.execute(
            'SELECT "CourtEventID","EventType","OccurredAt","ScheduledAt","Outcome","Detail" '
            'FROM "CourtEvent" WHERE "CaseMasterID"=%s', (cid,))
        for r in cur.fetchall():
            event_backed = True
            event_date = _s(r[2] or r[3])
            if (r[1], event_date[:10] if event_date else None) in case_event_keys:
                continue
            detail = r[5] if isinstance(r[5], dict) else {}
            entries.append(S.TimelineEntry(
                date=event_date, kind="court", type=r[1],
                label=detail.get("display_label") or r[1].replace("_", " ").title(),
                detail=r[4], ref_id=int(r[0])))
        # 3. bail decisions (including person labels). Cancellation/set-aside
        # milestones that do not fit BailEvent.Status remain CourtEvents.
        cur.execute(
            'SELECT b."BailEventID",b."BailType",b."Status",b."DecidedAt",'
            'COALESCE(p."DisplayLabel",p."PublicRef") '
            'FROM "BailEvent" b LEFT JOIN "CanonicalPerson" p '
            'ON p."CanonicalPersonID"=b."CanonicalPersonID" '
            'WHERE b."CaseMasterID"=%s', (cid,))
        for r in cur.fetchall():
            event_backed = True
            person = r[4] or "Accused"
            entries.append(S.TimelineEntry(
                date=_s(r[3]), kind="bail", type=r[1] or "bail",
                label=f"{person}: {(r[1] or 'bail').replace('_', ' ')}",
                detail=r[2], ref_id=int(r[0])))
        # 4. statements
        cur.execute('SELECT "StatementID","StatementType","RecordedAt" FROM "Statement" '
                    'WHERE "CaseMasterID"=%s', (cid,))
        for r in cur.fetchall():
            entries.append(S.TimelineEntry(
                date=_s(r[2]), kind="statement", type=r[1],
                label=f"{r[1].title()} statement", detail=None, ref_id=int(r[0])))
        # 5. seizures
        cur.execute('SELECT "SeizureID","SeizureType","SeizedAt" FROM "Seizure" WHERE "CaseMasterID"=%s', (cid,))
        for r in cur.fetchall():
            entries.append(S.TimelineEntry(
                date=_s(r[2]), kind="seizure", type=r[1], label="Seizure", detail=None, ref_id=int(r[0])))
        # 6. dispositions
        cur.execute('SELECT "CaseDispositionID","DispositionType","DispositionDate","IsFinal" '
                    'FROM "CaseDisposition" WHERE "CaseMasterID"=%s', (cid,))
        for r in cur.fetchall():
            entries.append(S.TimelineEntry(
                date=_s(r[2]), kind="disposition", type=r[1],
                label=r[1].replace("_", " ").title(), detail=("final" if r[3] else None), ref_id=int(r[0])))
        # 7. outcomes
        cur.execute('SELECT "OutcomeObservationID","ObservationType","ObservedAt" FROM "OutcomeObservation" '
                    'WHERE "CaseMasterID"=%s', (cid,))
        for r in cur.fetchall():
            entries.append(S.TimelineEntry(
                date=_s(r[2]), kind="outcome", type=r[1], label="Verified outcome", detail=None, ref_id=int(r[0])))
        # 8. derived base dates so pre-v2 and partially migrated cases remain
        # useful. Reconcile per milestone/day instead of using an all-or-nothing
        # event-backed gate, which used to hide unmatched arrest/chargesheet rows.
        cur.execute('SELECT "CrimeRegisteredDate","CrimeNo" FROM "CaseMaster" WHERE "CaseMasterID"=%s', (cid,))
        cm = cur.fetchone()
        if cm and cm[0] and "registered" not in case_event_types:
            entries.append(S.TimelineEntry(date=_s(cm[0]), kind="derived", type="registered",
                                           label="FIR registered", detail=cm[1]))
        cur.execute('SELECT "ArrestSurrenderDate","ArrestSurrenderTypeID" '
                    'FROM "ArrestSurrender" WHERE "CaseMasterID"=%s '
                    'AND "ArrestSurrenderDate" IS NOT NULL '
                    'ORDER BY "ArrestSurrenderDate","ArrestSurrenderID" LIMIT 100', (cid,))
        for r in cur.fetchall():
            date = _s(r[0])
            day = date[:10] if date else None
            expected_type = "surrender" if r[1] == 2 else "arrest"
            key = (expected_type, day)
            if milestone_counts[key] > 0:
                milestone_counts[key] -= 1
                continue
            entries.append(S.TimelineEntry(date=date, kind="derived", type=expected_type,
                                           label="Arrest / surrender", detail=None))
        cur.execute('SELECT "csdate","cstype" FROM "ChargesheetDetails" '
                    'WHERE "CaseMasterID"=%s AND "csdate" IS NOT NULL '
                    'ORDER BY "csdate","CSID" LIMIT 100', (cid,))
        for r in cur.fetchall():
            date = _s(r[0])
            key = ("chargesheet_filed", date[:10] if date else None)
            if milestone_counts[key] > 0:
                milestone_counts[key] -= 1
                continue
            entries.append(S.TimelineEntry(date=date, kind="derived", type="chargesheet",
                                           label="Chargesheet / final report", detail=_s(r[1])))
    entries.sort(key=lambda e: (e.date is None, e.date or ""))
    return S.TimelineResponse(case_master_id=cid, count=len(entries),
                              event_backed=event_backed, entries=entries[:250])


# ===========================================================================
# Lookups
# ===========================================================================
def _lv(v: str) -> dict:
    return {"value": v, "label": v.replace("_", " ").title()}


def lookups() -> S.CaseworkLookups:
    # The casework vocabularies are static (enforced in code). The court list is
    # operational reference data served from the deployed store; when AWS RDS is
    # absent (deployed AppSail runs without DATABASE_URL) it degrades to an empty
    # list rather than failing the whole lookups endpoint (Prompt 21 §B.5).
    courts: list[dict] = []
    try:
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT "CourtID","CourtName" FROM "Court" WHERE "Active" ORDER BY "CourtName" LIMIT 500')
                courts = [{"id": int(r[0]), "name": r[1]} for r in cur.fetchall()]
    except Exception:  # noqa: BLE001 — reference read is best-effort without RDS
        courts = []
    return S.CaseworkLookups(
        statement_types=[_lv(x) for x in STATEMENT_TYPES],
        property_item_types=[_lv(x) for x in PROPERTY_ITEM_TYPES],
        property_statuses=[_lv(x) for x in PROPERTY_STATUSES],
        court_event_types=[_lv(x) for x in COURT_EVENT_TYPES],
        bail_statuses=[_lv(x) for x in BAIL_STATUSES],
        disposition_types=[_lv(x) for x in DISPOSITION_TYPES],
        lab_test_types=[_lv(x) for x in LAB_TEST_TYPES],
        lab_statuses=[_lv(x) for x in LAB_STATUSES],
        access_classifications=[_lv(x) for x in ACCESS_CLASSIFICATIONS],
        courts=courts)


# ===========================================================================
# Public API (open connections; rw_conn commits on clean exit)
# ===========================================================================
# --- statements ---
def create_statement(cid: int, req: S.StatementCreate, role: Optional[str]) -> S.StatementOut:
    with db.rw_conn() as conn:
        sid = _create_statement(conn, cid, req, role)
        return _serialize_statement(conn, sid, role)


def list_statements(cid: int, role: Optional[str]) -> S.StatementListResponse:
    with db.ro_conn() as conn:
        return _list_statements(conn, cid, role)


def get_statement(sid: int, role: Optional[str]) -> S.StatementOut:
    with db.ro_conn() as conn:
        return _serialize_statement(conn, sid, role)


def correct_statement(sid: int, req: S.StatementCorrection, role: Optional[str]) -> S.StatementOut:
    with db.rw_conn() as conn:
        _correct_statement(conn, sid, req, role)
        return _serialize_statement(conn, sid, role)


def review_statement(sid: int, req: S.StatementReview, role: Optional[str]) -> S.StatementOut:
    with db.rw_conn() as conn:
        _review_statement(conn, sid, req)
        return _serialize_statement(conn, sid, role)


# --- property / seizure ---
def create_seizure(cid: int, req: S.SeizureCreate, role: Optional[str]) -> S.SeizureListResponse:
    with db.rw_conn() as conn:
        _create_seizure(conn, cid, req, role)
        return _list_seizures(conn, cid)


def list_seizures(cid: int) -> S.SeizureListResponse:
    with db.ro_conn() as conn:
        return _list_seizures(conn, cid)


def add_property_item(cid: int, seizure_id: Optional[int], p: S.PropertyItemInput,
                      role: Optional[str]) -> S.PropertyItemOut:
    with db.rw_conn() as conn:
        _require_case(conn, cid)
        _require_procedural_write(conn, cid)
        if seizure_id is not None:
            with conn.cursor() as cur:
                cur.execute('SELECT 1 FROM "Seizure" WHERE "SeizureID"=%s AND "CaseMasterID"=%s',
                            (seizure_id, cid))
                if cur.fetchone() is None:
                    raise CaseworkValidationError(f"Seizure {seizure_id} not found on this case.")
        pid = _insert_property_item(conn, cid, seizure_id, p)
        audit.record(audit.Action.CREATE, "property_item", pid, conn=conn, detail={"case_id": cid})
        return _serialize_property_item(conn, _fetch_property_item(conn, pid))


def change_property_status(pid: int, req: S.PropertyStatusChange) -> S.PropertyItemOut:
    with db.rw_conn() as conn:
        _change_property_status(conn, pid, req)
        return _serialize_property_item(conn, _fetch_property_item(conn, pid))


# --- lab ---
def create_lab(cid: int, req: S.LabResultInput, role: Optional[str]) -> S.LabResultOut:
    with db.rw_conn() as conn:
        lid = _create_lab(conn, cid, req, role)
        with conn.cursor() as cur:
            cur.execute(f'SELECT {_LAB_COLS} FROM "LabResult" WHERE "LabResultID"=%s', (lid,))
            row = cur.fetchone()
        return _serialize_lab(conn, row, role)


def list_labs(cid: int, role: Optional[str]) -> S.LabResultListResponse:
    with db.ro_conn() as conn:
        return _list_labs(conn, cid, role)


def update_lab(lid: int, req: S.LabResultUpdate, role: Optional[str]) -> S.LabResultOut:
    with db.rw_conn() as conn:
        _update_lab(conn, lid, req)
        with conn.cursor() as cur:
            cur.execute(f'SELECT {_LAB_COLS} FROM "LabResult" WHERE "LabResultID"=%s', (lid,))
            row = cur.fetchone()
        return _serialize_lab(conn, row, role)


# --- court / bail / disposition / outcome / lifecycle ---
def court_lifecycle(cid: int) -> S.CourtLifecycleView:
    with db.ro_conn() as conn:
        return _lifecycle_view(conn, cid)


def add_court_event(cid: int, req: S.CourtEventInput, role: Optional[str]) -> S.CourtLifecycleView:
    with db.rw_conn() as conn:
        _add_court_event(conn, cid, req, role)
        return _lifecycle_view(conn, cid)


def add_bail(cid: int, req: S.BailInput, role: Optional[str]) -> S.CourtLifecycleView:
    with db.rw_conn() as conn:
        _add_bail(conn, cid, req, role)
        return _lifecycle_view(conn, cid)


def add_disposition(cid: int, req: S.DispositionInput, role: Optional[str]) -> S.CourtLifecycleView:
    with db.rw_conn() as conn:
        _add_disposition(conn, cid, req, role)
        return _lifecycle_view(conn, cid)


def add_outcome(cid: int, req: S.OutcomeInput, role: Optional[str]) -> S.CourtLifecycleView:
    with db.rw_conn() as conn:
        _add_outcome(conn, cid, req, role)
        return _lifecycle_view(conn, cid)


def add_lifecycle_event(cid: int, req: S.LifecycleEventInput, role: Optional[str]) -> S.LifecycleEventResult:
    with db.rw_conn() as conn:
        return _add_lifecycle_event(conn, cid, req.event_type, req.occurred_at,
                                    req.actor_role or role, req.payload)


# --- timeline ---
def timeline(cid: int) -> S.TimelineResponse:
    with db.ro_conn() as conn:
        return _timeline(conn, cid)


# --------------------------------------------------------------------------- #
# Scoped "next hearing" aggregate                                             #
# --------------------------------------------------------------------------- #
_HEARING_LIST_CAP = 25


def next_hearings(*, district_ids=None, unit_id=None, limit: int = _HEARING_LIST_CAP) -> dict:
    """The soonest scheduled hearings in the caller's scope.

    Backs the "Next court date" KPI, which shipped in an honest `pending` state
    because no hearing in the corpus was scheduled-but-not-yet-heard: ScheduledAt
    was NULL on every row and every row carried an OccurredAt. Migration 036 (and
    datagen, for freshly built corpora) writes the adjourned-to date for cases
    awaiting trial, which is the population selected here.

    ``ScheduledAt IS NOT NULL AND OccurredAt IS NULL`` is the definition of
    "still to come". Every historical row has the opposite pair, so the two
    populations cannot be confused.

    DAYS ARE COUNTED FROM THE CORPUS AS-OF DATE, NOT wall-clock today. The dataset
    is synthetic and ends before today, so counting from today would report every
    hearing as overdue by however long the demo has been running. ``as_of`` and
    ``data_age_days`` are returned so the caller can say what the number is
    relative to — the same contract /performance and /outcomes use.
    """
    scope_sql: list[str] = []
    params: list = []
    if district_ids is not None:
        if not district_ids:
            # Entitled to nothing. An impossible predicate, not a skipped filter:
            # treating empty as "no filter" is what leaks every district to an
            # unposted seat.
            scope_sql.append("FALSE")
        else:
            scope_sql.append('u."DistrictID" = ANY(%s)')
            params.append([int(d) for d in district_ids])
    if unit_id is not None:
        scope_sql.append('cm."PoliceStationID" = %s')
        params.append(int(unit_id))
    where = (" AND " + " AND ".join(scope_sql)) if scope_sql else ""

    with db.ro_conn() as conn, conn.cursor() as cur:
        # The corpus reference point: the last thing that actually happened in
        # court. Read once and reported, so "in 14 days" is anchored to something
        # the caller can see rather than to an unstated assumption.
        cur.execute('SELECT max("OccurredAt")::date FROM "CourtEvent" '
                    'WHERE "OccurredAt" IS NOT NULL')
        row = cur.fetchone()
        as_of = row[0] if row and row[0] else None

        cur.execute(
            'SELECT count(*) AS pending, '
            '       min(ce."ScheduledAt")::date AS soonest, '
            '       count(DISTINCT ce."CaseMasterID") AS cases '
            '  FROM "CourtEvent" ce '
            '  JOIN "CaseMaster" cm ON cm."CaseMasterID" = ce."CaseMasterID" '
            '  JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
            ' WHERE ce."OccurredAt" IS NULL AND ce."ScheduledAt" IS NOT NULL'
            + where,
            params)
        agg = cur.fetchone()
        pending, soonest, cases_n = int(agg[0] or 0), agg[1], int(agg[2] or 0)

        hearings = []
        if pending:
            cur.execute(
                'SELECT ce."CourtEventID", ce."CaseMasterID", cm."CaseNo", '
                '       ce."ScheduledAt"::date, u."UnitID", u."UnitName", '
                '       d."DistrictName", ct."CourtName" '
                '  FROM "CourtEvent" ce '
                '  JOIN "CaseMaster" cm ON cm."CaseMasterID" = ce."CaseMasterID" '
                '  JOIN "Unit" u ON u."UnitID" = cm."PoliceStationID" '
                '  LEFT JOIN "District" d ON d."DistrictID" = u."DistrictID" '
                '  LEFT JOIN "Court" ct ON ct."CourtID" = ce."CourtID" '
                ' WHERE ce."OccurredAt" IS NULL AND ce."ScheduledAt" IS NOT NULL'
                + where +
                ' ORDER BY ce."ScheduledAt" ASC LIMIT %s',
                params + [int(limit)])
            for r in cur.fetchall():
                sched = r[3]
                hearings.append({
                    "court_event_id": int(r[0]),
                    "case_id": int(r[1]),
                    "case_number": r[2],
                    "scheduled_on": sched.isoformat() if sched else None,
                    "days_away": (sched - as_of).days if (sched and as_of) else None,
                    "unit_id": int(r[4]) if r[4] is not None else None,
                    "unit_name": r[5],
                    "district_name": r[6],
                    "court_name": r[7],
                })

    days_to_next = (soonest - as_of).days if (soonest and as_of) else None
    today = date.today()
    return {
        "scope": {"district_ids": district_ids, "unit_id": unit_id},
        "as_of": as_of.isoformat() if as_of else None,
        "data_age_days": (today - as_of).days if as_of else None,
        # None, not 0, when nothing is listed: "no hearing scheduled" and "a hearing
        # today" are different statements and must not render the same.
        "days_to_next_hearing": days_to_next,
        "next_hearing_on": soonest.isoformat() if soonest else None,
        "pending_hearings": pending,
        "cases_awaiting_hearing": cases_n,
        "hearings": hearings,
        "empty": pending == 0,
        "limitations": [
            "Synthetic hackathon data.",
            "Days are counted from the corpus as-of date, not today, because the "
            "dataset ends before the current date.",
            "Covers cases with an adjourned-to date on record; a case awaiting "
            "trial with no listed date does not appear.",
        ],
        "dataset": "synthetic",
    }
