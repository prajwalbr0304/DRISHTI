"""Intake service — draft lifecycle, validation, canonicalisation, case events.

Design for testability + safety:
  * Internal ``_fn(conn, ...)`` helpers do the work on an OPEN connection and
    never commit, so tests can drive the full create -> validate -> submit ->
    approve path inside a transaction and ROLL BACK (no mutation of the
    over-quota live synthetic DB).
  * Public functions open app.db.rw_conn()/ro_conn() and delegate; rw_conn
    commits on clean exit.

On approval a draft is canonicalised in ONE transaction into:
  CaseMaster (+ 18-digit CrimeNo) + CaseSource + CaseVersion (canonical incident
  coords) + initial CaseEvent + CasePartyRole rows (each backed by a stable
  CanonicalPerson/CanonicalOrganisation, with legacy Accused/Victim/Complainant
  rows kept in sync for the existing Case File) + ActSectionAssociation.
Invalid/incomplete drafts never reach these canonical tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from psycopg2 import errors as pg_errors
from psycopg2.extras import Json

from .. import audit, db
from . import workflow as wf
from .schemas import (ApprovalResult, CaseEventResponse, CreateDraftRequest,
                      DraftActivity, DraftListResponse, DraftPayload, DraftResponse,
                      DuplicateCandidate, DuplicateCheckResponse, JurisdictionInfo,
                      PartyInput, PartyOut, UpdateDraftRequest, ValidationIssue,
                      ValidationResponse)


# ---------------------------------------------------------------------------
# Typed errors (router translates to HTTP)
# ---------------------------------------------------------------------------
class IntakeError(Exception):
    pass


class IntakeNotFound(IntakeError):
    pass


class IntakeConflict(IntakeError):
    pass


class IntakeValidationError(IntakeError):
    def __init__(self, message: str, validation: Optional[dict] = None):
        super().__init__(message)
        self.validation = validation


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s(v) -> Optional[str]:
    return str(v) if v is not None else None


# ---------------------------------------------------------------------------
# Reference id helpers
# ---------------------------------------------------------------------------
def _source_system_id(conn, code: str) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "SourceSystemID" FROM "SourceSystem" WHERE "Code"=%s', (code,))
        r = cur.fetchone()
    return int(r[0]) if r else None


def _category_id(conn, category_code: str) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseCategoryID" FROM "CaseCategory" WHERE "LookupValue"=%s', (category_code,))
        r = cur.fetchone()
    return int(r[0]) if r else None


def _status_id(conn, status_name: str) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseStatusID" FROM "CaseStatusMaster" WHERE "CaseStatusName"=%s', (status_name,))
        r = cur.fetchone()
    return int(r[0]) if r else None


def _unit_district(conn, unit_id: int) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "DistrictID" FROM "Unit" WHERE "UnitID"=%s', (unit_id,))
        r = cur.fetchone()
    return int(r[0]) if r and r[0] is not None else None


def _exists(conn, table: str, pk_col: str, pk_val) -> bool:
    with conn.cursor() as cur:
        cur.execute(f'SELECT 1 FROM "{table}" WHERE "{pk_col}"=%s', (pk_val,))
        return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Draft load / serialise
# ---------------------------------------------------------------------------
_DRAFT_COLS = (
    '"IntakeDraftID","DraftKey","Status","CaseKind","CaseCategoryCode",'
    '"SourceSystemID","SourceRecordID","IngestionJobID","CaseMasterID",'
    '"Payload","ValidationState","RevisionNo","CreatedByActor","SubmittedByActor",'
    '"ReviewedByActor","ReviewNote","ReturnReason","CreatedAt","UpdatedAt",'
    '"SubmittedAt","ReviewedAt"'
)


def _draft_row(conn, draft_key: str) -> Optional[tuple]:
    with conn.cursor() as cur:
        cur.execute(f'SELECT {_DRAFT_COLS} FROM "IntakeDraft" WHERE "DraftKey"=%s', (draft_key,))
        return cur.fetchone()


def _draft_id(conn, draft_key: str) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "IntakeDraftID" FROM "IntakeDraft" WHERE "DraftKey"=%s', (draft_key,))
        r = cur.fetchone()
    return int(r[0]) if r else None


def _parties(conn, draft_id: int) -> list[PartyOut]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "IntakeDraftPartyID","RoleType","PartyNature","CanonicalPersonID",'
            '"CanonicalOrganisationID","IsUnknownParty","DisplayName","Attributes","SequenceNo" '
            'FROM "IntakeDraftParty" WHERE "IntakeDraftID"=%s ORDER BY "IntakeDraftPartyID"',
            (draft_id,))
        rows = cur.fetchall()
    return [
        PartyOut(
            intake_draft_party_id=int(r[0]), role_type=r[1], party_nature=r[2],
            canonical_person_id=r[3], canonical_organisation_id=r[4],
            is_unknown=bool(r[5]), display_name=r[6], attributes=r[7] or {},
            sequence_no=r[8])
        for r in rows
    ]


def _crime_no_for_case(conn, case_master_id: Optional[int]) -> Optional[str]:
    if not case_master_id:
        return None
    with conn.cursor() as cur:
        cur.execute('SELECT "CrimeNo" FROM "CaseMaster" WHERE "CaseMasterID"=%s', (case_master_id,))
        r = cur.fetchone()
    return r[0] if r else None


def _serialize_draft(conn, draft_key: str) -> DraftResponse:
    row = _draft_row(conn, draft_key)
    if row is None:
        raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
    (draft_id, dkey, status, kind, category, ssid, srid, jobid, case_id, payload,
     vstate, rev, cby, sby, rby, rnote, rreason, cat_created, cat_updated,
     cat_submitted, cat_reviewed) = row
    payload = payload or {}
    validation = None
    if vstate:
        try:
            validation = ValidationResponse(**vstate)
        except Exception:  # noqa: BLE001 — tolerate older/partial snapshots
            validation = None
    return DraftResponse(
        intake_draft_id=int(draft_id), draft_key=dkey, status=status,
        case_kind=kind, case_category_code=category,
        source_system_id=ssid, source_record_id=srid, ingestion_job_id=jobid,
        case_master_id=case_id, crime_no=_crime_no_for_case(conn, case_id),
        revision_no=int(rev), created_by_actor=cby, submitted_by_actor=sby,
        reviewed_by_actor=rby, review_note=rnote, return_reason=rreason,
        payload=DraftPayload(**payload), parties=_parties(conn, int(draft_id)),
        validation=validation,
        created_at=_s(cat_created), updated_at=_s(cat_updated),
        submitted_at=_s(cat_submitted), reviewed_at=_s(cat_reviewed))


def _activity(conn, draft_id: int, event_type: str, actor: Optional[str], detail: dict):
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "IntakeDraftActivity" ("IntakeDraftID","EventType","Actor","Detail") '
            'VALUES (%s,%s,%s,%s)', (draft_id, event_type, actor, Json(detail)))


# ---------------------------------------------------------------------------
# Create / update
# ---------------------------------------------------------------------------
def _validate_kind(kind: str) -> wf.CaseKind:
    if kind not in wf.CASE_KINDS:
        raise IntakeValidationError(f"Unknown case kind '{kind}'.")
    return wf.CASE_KINDS[kind]


def _insert_party(conn, draft_id: int, kind: str, p: PartyInput) -> int:
    if p.role_type not in wf.PARTY_ROLES:
        raise IntakeValidationError(f"Unknown party role '{p.role_type}'.")
    if not wf.is_party_role_allowed(kind, p.role_type):
        raise IntakeValidationError(
            f"Role '{p.role_type}' is not permitted for a {wf.CASE_KINDS[kind].label} case.")
    if not (p.canonical_person_id or p.canonical_organisation_id or p.is_unknown
            or (p.display_name and p.display_name.strip())):
        raise IntakeValidationError(
            "A party must link an identity, be marked unknown, or carry a name.")
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "IntakeDraftParty" ("IntakeDraftID","RoleType","PartyNature",'
            '"CanonicalPersonID","CanonicalOrganisationID","IsUnknownParty","DisplayName",'
            '"Attributes","SequenceNo") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) '
            'RETURNING "IntakeDraftPartyID"',
            (draft_id, p.role_type, p.party_nature, p.canonical_person_id,
             p.canonical_organisation_id, p.is_unknown,
             (p.display_name.strip() if p.display_name else None),
             Json(p.attributes or {}), p.sequence_no))
        return int(cur.fetchone()[0])


def _create_draft(conn, req: CreateDraftRequest) -> str:
    ck = _validate_kind(req.case_kind)
    category = ck.category  # kind determines category (avoids inconsistency)

    if req.idempotency_key:
        with conn.cursor() as cur:
            cur.execute('SELECT "DraftKey" FROM "IntakeDraft" WHERE "IdempotencyKey"=%s',
                        (req.idempotency_key,))
            r = cur.fetchone()
        if r:
            return r[0]

    source_code = req.payload.source.source_system_code or "FIR_FORM"
    ssid = _source_system_id(conn, source_code) or _source_system_id(conn, "FIR_FORM")
    external_ref = req.payload.source.external_source_id
    payload_dict = req.payload.model_dump()

    with conn.cursor() as cur:
        # idempotent ingestion job
        cur.execute(
            'INSERT INTO "IngestionJob" ("SourceSystemID","JobKind","IdempotencyKey","Status","DryRun") '
            'VALUES (%s,%s,%s,%s,%s) RETURNING "IngestionJobID"',
            (ssid, "form_submit", req.idempotency_key, "pending", False))
        job_id = int(cur.fetchone()[0])
        # staging source record (provenance)
        cur.execute(
            'INSERT INTO "SourceRecord" ("SourceSystemID","ExternalRef","RecordKind","Payload","Status") '
            'VALUES (%s,%s,%s,%s,%s) RETURNING "SourceRecordID"',
            (ssid, external_ref, "case", Json(payload_dict), "staged"))
        source_record_id = int(cur.fetchone()[0])

        draft_key = "DR-" + uuid.uuid4().hex[:12].upper()
        cur.execute(
            'INSERT INTO "IntakeDraft" ("DraftKey","IdempotencyKey","SourceSystemID",'
            '"SourceRecordID","IngestionJobID","CaseKind","CaseCategoryCode","Status",'
            '"Payload","CreatedByActor") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
            'RETURNING "IntakeDraftID"',
            (draft_key, req.idempotency_key, ssid, source_record_id, job_id,
             ck.name, category, "draft", Json(payload_dict), req.created_by_actor))
        draft_id = int(cur.fetchone()[0])

    for p in req.parties:
        _insert_party(conn, draft_id, ck.name, p)
    _activity(conn, draft_id, "created", req.created_by_actor,
              {"case_kind": ck.name, "category": category})
    audit.record(audit.Action.INTAKE_CREATE, "intake_draft", draft_key,
                 actor=req.created_by_actor, conn=conn,
                 detail={"case_kind": ck.name, "category": category})
    return draft_key


def _update_draft(conn, draft_key: str, req: UpdateDraftRequest) -> None:
    row = _draft_row(conn, draft_key)
    if row is None:
        raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
    draft_id, _, status, kind = int(row[0]), row[1], row[2], row[3]
    source_record_id, rev = row[6], int(row[11])
    if status not in ("draft", "returned_for_correction"):
        raise IntakeConflict(f"Draft is '{status}' and can no longer be edited.")
    if req.expected_revision_no is not None and req.expected_revision_no != rev:
        raise IntakeConflict(
            f"Draft was modified elsewhere (expected revision {req.expected_revision_no}, "
            f"found {rev}). Reload before saving.")

    new_kind = kind
    if req.case_kind and req.case_kind != kind:
        new_kind = _validate_kind(req.case_kind).name
    new_category = wf.CASE_KINDS[new_kind].category

    sets = ['"RevisionNo" = "RevisionNo" + 1', '"CaseKind" = %s', '"CaseCategoryCode" = %s']
    params: list[Any] = [new_kind, new_category]
    payload_dict = None
    if req.payload is not None:
        payload_dict = req.payload.model_dump()
        sets.append('"Payload" = %s')
        params.append(Json(payload_dict))
    params.append(draft_key)

    with conn.cursor() as cur:
        cur.execute(f'UPDATE "IntakeDraft" SET {", ".join(sets)} WHERE "DraftKey"=%s', params)
        if payload_dict is not None and source_record_id is not None:
            cur.execute('UPDATE "SourceRecord" SET "Payload"=%s WHERE "SourceRecordID"=%s',
                        (Json(payload_dict), source_record_id))
    _activity(conn, draft_id, "autosaved" if req.autosave else "updated", req.actor,
              {"revision_from": rev})


# ---------------------------------------------------------------------------
# Jurisdiction / geo
# ---------------------------------------------------------------------------
def _jurisdiction(conn, lat: Optional[float], lon: Optional[float],
                  assigned_district_id: Optional[int]) -> JurisdictionInfo:
    if lat is None or lon is None:
        return JurisdictionInfo(has_point=False)
    info = JurisdictionInfo(has_point=True, latitude=lat, longitude=lon)
    with conn.cursor() as cur:
        cur.execute("SELECT fn_point_in_state(%s::double precision, %s::double precision)", (lon, lat))
        info.in_state = bool(cur.fetchone()[0])
        cur.execute(
            'SELECT b."DistrictID", d."DistrictName" FROM "JurisdictionBoundary" b '
            'JOIN "District" d ON d."DistrictID" = b."DistrictID" '
            'WHERE b."Level"=\'district\' AND b."IsCurrent" '
            'AND ST_Contains(b."geom", ST_SetSRID(ST_MakePoint(%s,%s),4326)) LIMIT 1',
            (lon, lat))
        r = cur.fetchone()
        if r:
            info.resolved_district_id, info.resolved_district_name = int(r[0]), r[1]
        if assigned_district_id:
            cur.execute(
                "SELECT fn_point_in_district(%s, %s::double precision, %s::double precision)",
                (assigned_district_id, lon, lat))
            info.in_assigned_district = bool(cur.fetchone()[0])
        # nearest station hint (KNN on UnitLocation)
        cur.execute(
            'SELECT ul."UnitID", u."UnitName" FROM "UnitLocation" ul '
            'JOIN "Unit" u ON u."UnitID" = ul."UnitID" WHERE ul."IsCurrent" '
            'ORDER BY ul."geom" <-> ST_SetSRID(ST_MakePoint(%s,%s),4326) LIMIT 1',
            (lon, lat))
        r = cur.fetchone()
        if r:
            info.nearest_unit_id, info.nearest_unit_name = int(r[0]), r[1]
    if info.in_state is False:
        info.note = "Incident point is outside the Karnataka state boundary."
    elif assigned_district_id and info.in_assigned_district is False:
        info.note = "Incident point is outside the assigned district (jurisdiction mismatch)."
    return info


def resolve_jurisdiction(lat: Optional[float], lon: Optional[float],
                         assigned_district_id: Optional[int]) -> JurisdictionInfo:
    with db.ro_conn() as conn:
        return _jurisdiction(conn, lat, lon, assigned_district_id)


# ---------------------------------------------------------------------------
# Duplicate / source-key detection
# ---------------------------------------------------------------------------
def _duplicate_candidates(conn, payload: DraftPayload, self_case_id: Optional[int] = None) -> list[DuplicateCandidate]:
    out: list[DuplicateCandidate] = []
    external = (payload.source.external_source_id or "").strip()
    with conn.cursor() as cur:
        if external:
            cur.execute(
                'SELECT cs."CaseMasterID", cm."CrimeNo", cs."ExternalRef" FROM "CaseSource" cs '
                'JOIN "CaseMaster" cm ON cm."CaseMasterID" = cs."CaseMasterID" '
                'WHERE cs."ExternalRef" = %s LIMIT 5', (external,))
            for r in cur.fetchall():
                out.append(DuplicateCandidate(
                    kind="case", id=int(r[0]), crime_no=r[1], external_ref=r[2],
                    reason="Same external source id already registered", match_score=1.0))
            cur.execute(
                'SELECT "SourceRecordID","ExternalRef","Status" FROM "SourceRecord" '
                'WHERE "ExternalRef" = %s AND "Status" = \'committed\' LIMIT 5', (external,))
            for r in cur.fetchall():
                out.append(DuplicateCandidate(
                    kind="source", id=int(r[0]), external_ref=r[1],
                    reason="A committed source record already uses this external id",
                    match_score=0.9, detail=r[2]))
        # soft heuristic: same station + same registration date
        station = payload.registration.station_id
        reg_date = payload.registration.registration_date
        if station and reg_date:
            cur.execute(
                'SELECT "CaseMasterID","CrimeNo" FROM "CaseMaster" '
                'WHERE "PoliceStationID" = %s AND "CrimeRegisteredDate" = %s '
                'ORDER BY "CaseMasterID" DESC LIMIT 5', (station, reg_date))
            for r in cur.fetchall():
                if self_case_id and int(r[0]) == self_case_id:
                    continue
                out.append(DuplicateCandidate(
                    kind="case", id=int(r[0]), crime_no=r[1],
                    reason="Same station and registration date (review for duplication)",
                    match_score=0.35))
    return out


def duplicate_check(external_source_id: Optional[str] = None,
                    draft_key: Optional[str] = None) -> DuplicateCheckResponse:
    with db.ro_conn() as conn:
        if draft_key:
            row = _draft_row(conn, draft_key)
            if row is None:
                raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
            payload = DraftPayload(**(row[9] or {}))
        else:
            payload = DraftPayload()
            payload.source.external_source_id = external_source_id
        cands = _duplicate_candidates(conn, payload)
    return DuplicateCheckResponse(
        external_source_id=external_source_id or payload.source.external_source_id,
        candidates=cands)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _validate(conn, draft_key: str, persist: bool = True) -> ValidationResponse:
    row = _draft_row(conn, draft_key)
    if row is None:
        raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
    draft_id = int(row[0])
    kind = row[3]
    payload = DraftPayload(**(row[9] or {}))
    parties = _parties(conn, draft_id)
    ck = wf.CASE_KINDS.get(kind)

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    def err(field, code, msg):
        errors.append(ValidationIssue(field=field, code=code, message=msg, severity="error"))

    def warn(field, code, msg):
        warnings.append(ValidationIssue(field=field, code=code, message=msg, severity="warning"))

    if ck is None:
        err("case_kind", "unknown_kind", f"Unknown case kind '{kind}'.")
        return ValidationResponse(ok=False, can_submit=False, errors=errors, warnings=warnings,
                                  validated_at=_now_iso())

    reg = payload.registration
    inc = payload.incident
    cls = payload.classification
    nar = payload.narrative
    src = payload.source

    # --- registration ---
    if not reg.registration_date:
        err("registration.registration_date", "required", "Registration date is required.")
    if not reg.station_id:
        err("registration.station_id", "required", "Registering police station is required.")
    elif not _exists(conn, "Unit", "UnitID", reg.station_id):
        err("registration.station_id", "not_found", "Selected police station does not exist.")
    if not reg.registering_officer_id:
        err("registration.registering_officer_id", "required", "Registering officer is required.")
    elif not _exists(conn, "Employee", "EmployeeID", reg.registering_officer_id):
        err("registration.registering_officer_id", "not_found", "Selected officer does not exist.")
    if reg.assigned_io_id and not _exists(conn, "Employee", "EmployeeID", reg.assigned_io_id):
        err("registration.assigned_io_id", "not_found", "Assigned IO does not exist.")
    if not reg.assigned_io_id:
        warn("registration.assigned_io_id", "recommended", "No investigating officer assigned yet.")

    # --- classification ---
    if not cls.major_head_id:
        err("classification.major_head_id", "required", "Major crime head is required.")
    elif not _exists(conn, "CrimeHead", "CrimeHeadID", cls.major_head_id):
        err("classification.major_head_id", "not_found", "Selected crime head does not exist.")
    if not cls.minor_head_id:
        warn("classification.minor_head_id", "recommended", "No crime sub-head selected.")
    if not cls.gravity_id:
        warn("classification.gravity_id", "recommended", "Gravity of offence not set.")
    # acts/sections existence + belonging
    for i, as_ in enumerate(cls.acts_sections):
        if not _exists(conn, "Act", "ActCode", as_.act_code):
            err(f"classification.acts_sections[{i}].act_code", "not_found",
                f"Act '{as_.act_code}' does not exist.")
        with conn.cursor() as cur:
            cur.execute('SELECT "ActCode" FROM "Section" WHERE "SectionCode"=%s', (as_.section_code,))
            srow = cur.fetchone()
        if srow is None:
            err(f"classification.acts_sections[{i}].section_code", "not_found",
                f"Section '{as_.section_code}' does not exist.")
        elif srow[0] != as_.act_code:
            warn(f"classification.acts_sections[{i}]", "act_section_mismatch",
                 f"Section '{as_.section_code}' belongs to act '{srow[0]}', not '{as_.act_code}'.")
    if not cls.acts_sections and ck.name in ("fir_standard", "zero_fir"):
        warn("classification.acts_sections", "recommended", "No acts/sections applied yet.")

    # --- incident temporal + spatial ---
    if inc.incident_from and inc.incident_to and inc.incident_to < inc.incident_from:
        err("incident.incident_to", "temporal_order", "Incident 'to' is before 'from'.")
    if inc.info_received_at and inc.incident_from and inc.info_received_at < inc.incident_from:
        warn("incident.info_received_at", "temporal_order",
             "Information received before the incident window began.")
    juris = _jurisdiction(conn, inc.latitude, inc.longitude,
                          reg.district_id or (_unit_district(conn, reg.station_id) if reg.station_id else None))
    if juris.has_point:
        if juris.in_state is False:
            err("incident.location", "out_of_state",
                "Incident coordinates are outside the Karnataka state boundary.")
        elif juris.in_assigned_district is False:
            # Phase 9: an out-of-assigned-district incident BLOCKS canonical submit
            # unless a supervisory override reason is recorded. The clean fix is to
            # reassign the registering district to the detected one (juris.resolved_district_*).
            detected = (f" (detected district: {juris.resolved_district_name})"
                        if juris.resolved_district_name else "")
            if (inc.jurisdiction_override_reason or "").strip():
                warn("incident.location", "jurisdiction_override",
                     f"Jurisdiction mismatch overridden{detected}: "
                     f"{inc.jurisdiction_override_reason.strip()}")
            else:
                err("incident.location", "jurisdiction_mismatch",
                    f"Incident coordinates are outside the assigned district{detected}. "
                    "Reassign the registering district to the detected one, or record a "
                    "supervisory override reason before submitting.")
    else:
        warn("incident.location", "recommended", "No incident location pinned on the map.")

    # --- narrative ---
    if not nar.brief_facts or not nar.brief_facts.strip():
        err("narrative.brief_facts", "required", "Brief facts of the case are required.")
    elif len(nar.brief_facts.strip()) < 20:
        warn("narrative.brief_facts", "too_short", "Brief facts look very short.")

    # --- parties ---
    role_counts: dict[str, int] = {}
    for p in parties:
        role_counts[p.role_type] = role_counts.get(p.role_type, 0) + 1
        if not wf.is_party_role_allowed(kind, p.role_type):
            err("people", "role_not_allowed",
                f"Role '{p.role_type}' is not permitted for a {ck.label} case.")
    if not (role_counts.get("complainant") or role_counts.get("informant")):
        err("people", "reporter_required",
            "At least one complainant or informant is required.")
    if ck.allow_accused and not role_counts.get("accused"):
        warn("people", "no_accused", "No accused/suspect recorded yet.")

    # --- category-specific ---
    if ck.name == "zero_fir":
        if not src.originating_unit_id:
            warn("source.originating_unit_id", "recommended",
                 "Zero FIR: originating unit not recorded.")
        if not src.receiving_unit_id:
            warn("source.receiving_unit_id", "recommended",
                 "Zero FIR: receiving jurisdiction unit not recorded.")
    if ck.name == "missing_person":
        cs = cls.category_specific or {}
        if not (cs.get("last_seen_at") or cs.get("last_seen_location")):
            warn("classification.category_specific", "recommended",
                 "Missing person: last-seen time/location not recorded.")
    if ck.name == "udr":
        cs = cls.category_specific or {}
        if not cs.get("apparent_cause"):
            warn("classification.category_specific", "recommended",
                 "UDR: apparent cause of death not recorded.")

    dupes = _duplicate_candidates(conn, payload)
    ok = len(errors) == 0
    result = ValidationResponse(
        ok=ok, can_submit=ok, errors=errors, warnings=warnings,
        jurisdiction=juris, duplicate_candidates=dupes, validated_at=_now_iso())

    if persist:
        with conn.cursor() as cur:
            cur.execute('UPDATE "IntakeDraft" SET "ValidationState"=%s WHERE "IntakeDraftID"=%s',
                        (Json(result.model_dump()), draft_id))
        _activity(conn, draft_id, "validated", None,
                  {"ok": ok, "errors": len(errors), "warnings": len(warnings)})
    return result


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------
def _submit(conn, draft_key: str, actor: Optional[str]) -> ValidationResponse:
    row = _draft_row(conn, draft_key)
    if row is None:
        raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
    draft_id, status = int(row[0]), row[2]
    if status not in ("draft", "returned_for_correction"):
        raise IntakeConflict(f"Only a draft can be submitted (current status: '{status}').")
    validation = _validate(conn, draft_key, persist=True)
    if not validation.can_submit:
        raise IntakeValidationError(
            "Draft has blocking validation errors and cannot be submitted.",
            validation=validation.model_dump())
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE "IntakeDraft" SET "Status"=\'submitted\', "SubmittedByActor"=%s, '
            '"SubmittedAt"=now(), "RevisionNo"="RevisionNo"+1 WHERE "IntakeDraftID"=%s',
            (actor, draft_id))
    _activity(conn, draft_id, "submitted", actor, {})
    audit.record(audit.Action.INTAKE_SUBMIT, "intake_draft", draft_key,
                 actor=actor, conn=conn)
    return validation


# ---------------------------------------------------------------------------
# Canonicalisation on approval
# ---------------------------------------------------------------------------
def _new_canonical_person(conn, display_name: Optional[str], attributes: dict) -> int:
    ref = "SYN-PERSON-" + uuid.uuid4().hex[:12].upper()
    gender = attributes.get("gender_id")
    birth_year = attributes.get("approx_birth_year")
    is_juv = bool(attributes.get("is_juvenile", False))
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "CanonicalPerson" ("PublicRef","DisplayLabel","PrimaryGenderID",'
            '"ApproxBirthYear","IsJuvenile","Attributes","IsSynthetic") '
            'VALUES (%s,%s,%s,%s,%s,%s,TRUE) RETURNING "CanonicalPersonID"',
            (ref, display_name, gender, birth_year, is_juv, Json(attributes or {})))
        return int(cur.fetchone()[0])


def _new_canonical_org(conn, name: str, attributes: dict) -> int:
    ref = "SYN-ORG-" + uuid.uuid4().hex[:12].upper()
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "CanonicalOrganisation" ("PublicRef","Name","OrgType","Attributes","IsSynthetic") '
            'VALUES (%s,%s,%s,%s,TRUE) RETURNING "CanonicalOrganisationID"',
            (ref, name, attributes.get("org_type"), Json(attributes or {})))
        return int(cur.fetchone()[0])


def _next_crime_no(conn, category_code: str, district_id: int, unit_id: int, year: int) -> str:
    cat = wf.CATEGORY_CRIMENO_CODE.get(category_code, 1)
    prefix = f"{cat:d}{district_id:04d}{unit_id:04d}{year:04d}"  # 13 digits
    with conn.cursor() as cur:
        cur.execute('SELECT "CrimeNo" FROM "CaseMaster" WHERE "CrimeNo" LIKE %s '
                    'ORDER BY "CrimeNo" DESC LIMIT 1', (prefix + "%",))
        r = cur.fetchone()
    serial = (int(r[0][-5:]) + 1) if r else 1
    return f"{prefix}{serial:05d}"


def _insert_legacy_person(conn, role: str, case_id: int, canonical_id: Optional[int],
                          display_name: Optional[str], attributes: dict, seq: int) -> tuple[Optional[str], Optional[int]]:
    """Insert the legacy child row for accused/victim/complainant so the existing
    Case File keeps working. Returns (legacy_table, legacy_row_id)."""
    name = (display_name or "Unknown").strip() or "Unknown"
    age = attributes.get("age")
    gender = attributes.get("gender_id")
    with conn.cursor() as cur:
        if role == "accused":
            cur.execute(
                'INSERT INTO "Accused" ("CaseMasterID","AccusedName","AgeYear","GenderID",'
                '"PersonID","CanonicalPersonID") VALUES (%s,%s,%s,%s,%s,%s) '
                'RETURNING "AccusedMasterID"',
                (case_id, name, age, gender, f"A{seq}", canonical_id))
            return "Accused", int(cur.fetchone()[0])
        if role == "victim":
            cur.execute(
                'INSERT INTO "Victim" ("CaseMasterID","VictimName","AgeYear","GenderID","CanonicalPersonID") '
                'VALUES (%s,%s,%s,%s,%s) RETURNING "VictimMasterID"',
                (case_id, name, age, gender, canonical_id))
            return "Victim", int(cur.fetchone()[0])
        if role == "complainant":
            cur.execute(
                'INSERT INTO "ComplainantDetails" ("CaseMasterID","ComplainantName","AgeYear",'
                '"GenderID","CanonicalPersonID") VALUES (%s,%s,%s,%s,%s) RETURNING "ComplainantID"',
                (case_id, name, age, gender, canonical_id))
            return "ComplainantDetails", int(cur.fetchone()[0])
    return None, None


def _approve(conn, draft_key: str, actor: Optional[str]) -> ApprovalResult:
    row = _draft_row(conn, draft_key)
    if row is None:
        raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
    draft_id, status, kind, category = int(row[0]), row[2], row[3], row[4]
    source_system_id, source_record_id, ingestion_job_id = row[5], row[6], row[7]
    if status not in ("submitted", "under_review"):
        raise IntakeConflict(f"Only a submitted draft can be approved (current status: '{status}').")

    validation = _validate(conn, draft_key, persist=True)
    if not validation.ok:
        raise IntakeValidationError(
            "Draft has blocking validation errors and cannot be approved.",
            validation=validation.model_dump())

    payload = DraftPayload(**(row[9] or {}))
    parties = _parties(conn, draft_id)
    ck = wf.CASE_KINDS[kind]
    reg, inc, cls, nar = payload.registration, payload.incident, payload.classification, payload.narrative

    district_id = reg.district_id or _unit_district(conn, reg.station_id)
    if district_id is None:
        raise IntakeConflict("Cannot resolve the district for the selected station.")
    year = int((reg.registration_date or _now_iso())[:4])
    category_id = _category_id(conn, category)
    if category_id is None:
        raise IntakeConflict(f"Case category '{category}' is not configured.")
    legacy_status = wf.STATUS_TO_LEGACY.get(ck.initial_status)
    status_id = _status_id(conn, legacy_status) if legacy_status else None

    # --- CaseMaster (retry a fresh serial on CrimeNo uniqueness via savepoint,
    #     so a rare collision never aborts the whole approval transaction) ---
    case_id = None
    crime_no = None
    for attempt in range(6):
        crime_no = _next_crime_no(conn, category, district_id, reg.station_id, year)
        try:
            with conn.cursor() as cur:
                cur.execute("SAVEPOINT sp_crimeno")
                cur.execute(
                    'INSERT INTO "CaseMaster" ("CrimeNo","CrimeRegisteredDate","PolicePersonID",'
                    '"PoliceStationID","CaseCategoryID","GravityOffenceID","CrimeMajorHeadID",'
                    '"CrimeMinorHeadID","CaseStatusID","IncidentFromDate","IncidentToDate",'
                    '"InfoReceivedPSDate","latitude","longitude","BriefFacts") '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "CaseMasterID"',
                    (crime_no, reg.registration_date, reg.registering_officer_id, reg.station_id,
                     category_id, cls.gravity_id, cls.major_head_id, cls.minor_head_id, status_id,
                     inc.incident_from, inc.incident_to, inc.info_received_at,
                     inc.latitude, inc.longitude, (nar.brief_facts or "").strip() or None))
                case_id = int(cur.fetchone()[0])
                cur.execute("RELEASE SAVEPOINT sp_crimeno")
            break
        except pg_errors.UniqueViolation:
            with conn.cursor() as cur:
                cur.execute("ROLLBACK TO SAVEPOINT sp_crimeno")
            case_id = None
            continue
    if case_id is None:
        raise IntakeConflict("Could not allocate a unique CrimeNo after several attempts.")

    with conn.cursor() as cur:
        # --- CaseSource (provenance) ---
        cur.execute(
            'INSERT INTO "CaseSource" ("CaseMasterID","SourceSystemID","SourceRecordID",'
            '"ExternalRef","IngestionMethod") VALUES (%s,%s,%s,%s,%s)',
            (case_id, source_system_id, source_record_id, payload.source.external_source_id,
             payload.source.source_method))
        # --- CaseVersion (canonical incident coords + status) ---
        snapshot = payload.model_dump()
        snapshot["case_kind"] = kind
        cur.execute(
            'INSERT INTO "CaseVersion" ("CaseMasterID","VersionNo","CaseCategoryCode","StatusCode",'
            '"IsCurrent","IncidentLatitude","IncidentLongitude","AssignedDistrictID","AssignedUnitID",'
            '"SnapshotAttributes","ChangeReason","Actor") '
            'VALUES (%s,1,%s,%s,TRUE,%s,%s,%s,%s,%s,%s,%s) RETURNING "CaseVersionID"',
            (case_id, category, ck.initial_status, inc.latitude, inc.longitude,
             district_id, reg.station_id, Json(snapshot), "intake_approved", actor))
        case_version_id = int(cur.fetchone()[0])
        # --- initial CaseEvent ---
        cur.execute(
            'INSERT INTO "CaseEvent" ("CaseMasterID","EventType","EventCategory","SequenceNo",'
            '"OccurredAt","FromStatus","ToStatus","Payload","ActorRole") '
            'VALUES (%s,%s,\'lifecycle\',1,%s,NULL,%s,%s,%s) RETURNING "CaseEventID"',
            (case_id, ck.initial_event, reg.registration_date, ck.initial_status,
             Json({"crime_no": crime_no, "category": category, "kind": kind}), actor))
        case_event_id = int(cur.fetchone()[0])
        # --- Phase 9: audited jurisdiction override (an out-of-assigned-district
        #     incident submitted with a supervisory reason). No silent move — the
        #     override is recorded as an accepted DataQualityIssue + a
        #     JurisdictionReassignment(action='override') trail. ---
        if ((inc.jurisdiction_override_reason or "").strip()
                and validation.jurisdiction.in_assigned_district is False):
            resolved_did = validation.jurisdiction.resolved_district_id
            cur.execute(
                'INSERT INTO "DataQualityIssue" ("IssueType","Severity","CaseMasterID","Detail",'
                '"Status","ResolvedByActor","ResolvedAt") VALUES (%s,%s,%s,%s,\'accepted\',%s,now()) '
                'RETURNING "DataQualityIssueID"',
                ("invalid_jurisdiction_district", "error", case_id,
                 Json({"override_reason": inc.jurisdiction_override_reason.strip(),
                       "assigned_district_id": district_id, "resolved_district_id": resolved_did}),
                 actor))
            dq_id = int(cur.fetchone()[0])
            cur.execute(
                'INSERT INTO "JurisdictionReassignment" ("CaseMasterID","FromCaseVersionID",'
                '"ToCaseVersionID","Action","FromDistrictID","ToDistrictID","Reason","ReviewerActor",'
                '"SourceRecordID","DataQualityIssueID","BeforeState","AfterState") '
                'VALUES (%s,%s,%s,\'override\',%s,%s,%s,%s,%s,%s,%s,%s)',
                (case_id, case_version_id, case_version_id, district_id, district_id,
                 inc.jurisdiction_override_reason.strip(), actor, source_record_id, dq_id,
                 Json({"district_id": district_id}),
                 Json({"district_id": district_id, "action": "override",
                       "resolved_district_id": resolved_did})))

    # --- parties -> CanonicalPerson/Org + CasePartyRole (+legacy child rows) ---
    role_seq: dict[str, int] = {}
    party_role_ids: list[int] = []
    canonical_person_ids: list[int] = []
    for p in parties:
        role_seq[p.role_type] = role_seq.get(p.role_type, 0) + 1
        seq = p.sequence_no or role_seq[p.role_type]
        cp_id = p.canonical_person_id
        co_id = p.canonical_organisation_id
        is_unknown = p.is_unknown
        if p.party_nature == "organisation" and not co_id and not is_unknown:
            co_id = _new_canonical_org(conn, (p.display_name or "Unknown organisation"), p.attributes or {})
        elif not cp_id and not co_id and not is_unknown:
            cp_id = _new_canonical_person(conn, p.display_name, p.attributes or {})
        if cp_id:
            canonical_person_ids.append(cp_id)
        legacy_table, legacy_id = (None, None)
        if p.role_type in ("accused", "victim", "complainant") and not is_unknown:
            legacy_table, legacy_id = _insert_legacy_person(
                conn, p.role_type, case_id, cp_id, p.display_name, p.attributes or {}, seq)
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "CasePartyRole" ("CaseMasterID","CanonicalPersonID","CanonicalOrganisationID",'
                '"RoleType","IsUnknownParty","LegacyRefTable","LegacyRefID","PartyLabel","SequenceNo","Provenance") '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "CasePartyRoleID"',
                (case_id, cp_id, co_id, p.role_type, is_unknown, legacy_table, legacy_id,
                 p.display_name, seq, Json({"source": "intake", "draft_key": draft_key})))
            party_role_ids.append(int(cur.fetchone()[0]))

    # --- acts/sections ---
    with conn.cursor() as cur:
        for order, as_ in enumerate(cls.acts_sections, start=1):
            cur.execute(
                'INSERT INTO "ActSectionAssociation" ("CaseMasterID","ActID","SectionID",'
                '"ActOrderID","SectionOrderID") VALUES (%s,%s,%s,%s,%s) '
                'ON CONFLICT ("CaseMasterID","ActID","SectionID") DO NOTHING',
                (case_id, as_.act_code, as_.section_code, order, order))
        # --- mark provenance committed ---
        if source_record_id:
            cur.execute('UPDATE "SourceRecord" SET "Status"=\'committed\' WHERE "SourceRecordID"=%s',
                        (source_record_id,))
        if ingestion_job_id:
            cur.execute('UPDATE "IngestionJob" SET "Status"=\'committed\', "FinishedAt"=now() '
                        'WHERE "IngestionJobID"=%s', (ingestion_job_id,))
        # --- close out the draft ---
        cur.execute(
            'UPDATE "IntakeDraft" SET "Status"=\'approved\', "CaseMasterID"=%s, '
            '"ReviewedByActor"=%s, "ReviewedAt"=now(), "RevisionNo"="RevisionNo"+1 '
            'WHERE "IntakeDraftID"=%s', (case_id, actor, draft_id))
    _activity(conn, draft_id, "approved", actor,
              {"case_master_id": case_id, "crime_no": crime_no})
    audit.record(audit.Action.INTAKE_APPROVE, "case", case_id, actor=actor, conn=conn,
                 detail={"draft_key": draft_key, "crime_no": crime_no, "category": category})

    draft = _serialize_draft(conn, draft_key)
    return ApprovalResult(
        draft=draft, case_master_id=case_id, case_version_id=case_version_id,
        case_event_id=case_event_id, crime_no=crime_no,
        case_party_role_ids=party_role_ids, canonical_person_ids=canonical_person_ids)


def _review(conn, draft_key: str, action: str, actor: Optional[str], note: Optional[str]):
    if action == "approve":
        return _approve(conn, draft_key, actor)
    row = _draft_row(conn, draft_key)
    if row is None:
        raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
    draft_id, status = int(row[0]), row[2]
    if status not in ("submitted", "under_review"):
        raise IntakeConflict(f"Only a submitted draft can be reviewed (current status: '{status}').")
    if action == "reject":
        with conn.cursor() as cur:
            cur.execute('UPDATE "IntakeDraft" SET "Status"=\'rejected\', "ReviewedByActor"=%s, '
                        '"ReviewNote"=%s, "ReviewedAt"=now() WHERE "IntakeDraftID"=%s',
                        (actor, note, draft_id))
            if row[6]:
                cur.execute('UPDATE "SourceRecord" SET "Status"=\'rejected\' WHERE "SourceRecordID"=%s', (row[6],))
        _activity(conn, draft_id, "rejected", actor, {"note": note})
        audit.record(audit.Action.INTAKE_REJECT, "intake_draft", draft_key,
                     actor=actor, conn=conn)
    elif action == "return":
        with conn.cursor() as cur:
            cur.execute('UPDATE "IntakeDraft" SET "Status"=\'returned_for_correction\', '
                        '"ReviewedByActor"=%s, "ReturnReason"=%s, "ReviewedAt"=now() '
                        'WHERE "IntakeDraftID"=%s', (actor, note, draft_id))
        _activity(conn, draft_id, "returned_for_correction", actor, {"reason": note})
        audit.record(audit.Action.INTAKE_RETURN, "intake_draft", draft_key,
                     actor=actor, conn=conn)
    else:
        raise IntakeValidationError(f"Unknown review action '{action}'.")
    return _serialize_draft(conn, draft_key)


# ---------------------------------------------------------------------------
# Workflow-gated case events (on an already-approved case)
# ---------------------------------------------------------------------------
def _infer_kind(conn, case_id: int, category: str, snapshot: dict) -> str:
    if snapshot and snapshot.get("case_kind") in wf.CASE_KINDS:
        return snapshot["case_kind"]
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "CaseEvent" WHERE "CaseMasterID"=%s AND "EventType"=%s LIMIT 1',
                    (case_id, wf.E_MISSING_REPORTED))
        if cur.fetchone():
            return "missing_person"
    for name, ck in wf.CASE_KINDS.items():
        if ck.category == category and name != "missing_person":
            return name
    return "fir_standard"


def _add_case_event(conn, case_master_id: int, event_type: str,
                    occurred_at: Optional[str], actor_role: Optional[str],
                    payload: dict) -> CaseEventResponse:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "CaseVersionID","CaseCategoryCode","StatusCode","SnapshotAttributes" '
            'FROM "CaseVersion" WHERE "CaseMasterID"=%s AND "IsCurrent" LIMIT 1', (case_master_id,))
        cv = cur.fetchone()
    if cv is None:
        raise IntakeNotFound(f"No current CaseVersion for case {case_master_id}.")
    case_version_id, category, from_status, snapshot = int(cv[0]), cv[1], cv[2], (cv[3] or {})
    if snapshot.get("record_origin") == "public_source_curated":
        raise IntakeConflict(
            "Public-source curated procedure is read-only; update the reviewed "
            "source-qualified snapshot rather than applying an operational lifecycle action."
        )
    kind = _infer_kind(conn, case_master_id, category, snapshot)

    with conn.cursor() as cur:
        cur.execute('SELECT "EventType" FROM "CaseEvent" WHERE "CaseMasterID"=%s ORDER BY "SequenceNo"',
                    (case_master_id,))
        prior = [r[0] for r in cur.fetchall()]

    res = wf.validate_event(conn, kind=kind, category=category, event_type=event_type,
                            from_status=from_status, prior_event_types=prior)
    if not res.ok:
        raise IntakeConflict(res.error or "Invalid lifecycle transition.")

    with conn.cursor() as cur:
        cur.execute('SELECT COALESCE(MAX("SequenceNo"),0)+1 FROM "CaseEvent" WHERE "CaseMasterID"=%s',
                    (case_master_id,))
        seq = int(cur.fetchone()[0])
        cur.execute(
            'INSERT INTO "CaseEvent" ("CaseMasterID","EventType","EventCategory","SequenceNo",'
            '"OccurredAt","FromStatus","ToStatus","Payload","ActorRole") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "CaseEventID"',
            (case_master_id, event_type, "lifecycle", seq, occurred_at, from_status,
             res.to_status, Json(payload or {}), actor_role))
        case_event_id = int(cur.fetchone()[0])
        # advance the current CaseVersion status
        cur.execute('UPDATE "CaseVersion" SET "StatusCode"=%s WHERE "CaseVersionID"=%s',
                    (res.to_status, case_version_id))
    legacy = wf.STATUS_TO_LEGACY.get(res.to_status)
    if legacy:
        sid = _status_id(conn, legacy)
        if sid:
            with conn.cursor() as cur:
                cur.execute('UPDATE "CaseMaster" SET "CaseStatusID"=%s WHERE "CaseMasterID"=%s',
                            (sid, case_master_id))
    audit.record(audit.Action.CASE_EVENT, "case", case_master_id,
                 actor=actor_role, conn=conn,
                 detail={"event_type": event_type, "to_status": res.to_status})
    return CaseEventResponse(
        case_master_id=case_master_id, case_event_id=case_event_id,
        from_status=from_status, to_status=res.to_status, is_terminal=res.is_terminal,
        legacy_status=legacy)


# ===========================================================================
# Public API (open connections; rw_conn commits on clean exit)
# ===========================================================================
def create_draft(req: CreateDraftRequest) -> DraftResponse:
    with db.rw_conn() as conn:
        key = _create_draft(conn, req)
        draft = _serialize_draft(conn, key)
    return draft


def get_draft(draft_key: str) -> DraftResponse:
    with db.ro_conn() as conn:
        return _serialize_draft(conn, draft_key)


def update_draft(draft_key: str, req: UpdateDraftRequest) -> DraftResponse:
    with db.rw_conn() as conn:
        _update_draft(conn, draft_key, req)
        return _serialize_draft(conn, draft_key)


def add_party(draft_key: str, party: PartyInput, actor: Optional[str] = None) -> DraftResponse:
    with db.rw_conn() as conn:
        row = _draft_row(conn, draft_key)
        if row is None:
            raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
        if row[2] not in ("draft", "returned_for_correction"):
            raise IntakeConflict(f"Draft is '{row[2]}' and can no longer be edited.")
        pid = _insert_party(conn, int(row[0]), row[3], party)
        _activity(conn, int(row[0]), "party_added", actor,
                  {"party_id": pid, "role": party.role_type})
        return _serialize_draft(conn, draft_key)


def update_party(draft_key: str, party_id: int, patch: PartyInput, actor: Optional[str] = None) -> DraftResponse:
    with db.rw_conn() as conn:
        row = _draft_row(conn, draft_key)
        if row is None:
            raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
        draft_id, kind = int(row[0]), row[3]
        if row[2] not in ("draft", "returned_for_correction"):
            raise IntakeConflict(f"Draft is '{row[2]}' and can no longer be edited.")
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "IntakeDraftParty" WHERE "IntakeDraftPartyID"=%s AND "IntakeDraftID"=%s',
                        (party_id, draft_id))
            if cur.fetchone() is None:
                raise IntakeNotFound(f"Party {party_id} not found on this draft.")
        if not wf.is_party_role_allowed(kind, patch.role_type):
            raise IntakeValidationError(
                f"Role '{patch.role_type}' is not permitted for a {wf.CASE_KINDS[kind].label} case.")
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE "IntakeDraftParty" SET "RoleType"=%s,"PartyNature"=%s,"CanonicalPersonID"=%s,'
                '"CanonicalOrganisationID"=%s,"IsUnknownParty"=%s,"DisplayName"=%s,"Attributes"=%s,'
                '"SequenceNo"=%s WHERE "IntakeDraftPartyID"=%s',
                (patch.role_type, patch.party_nature, patch.canonical_person_id,
                 patch.canonical_organisation_id, patch.is_unknown,
                 (patch.display_name.strip() if patch.display_name else None),
                 Json(patch.attributes or {}), patch.sequence_no, party_id))
        _activity(conn, draft_id, "party_updated", actor, {"party_id": party_id})
        return _serialize_draft(conn, draft_key)


def remove_party(draft_key: str, party_id: int, actor: Optional[str] = None) -> DraftResponse:
    with db.rw_conn() as conn:
        row = _draft_row(conn, draft_key)
        if row is None:
            raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
        if row[2] not in ("draft", "returned_for_correction"):
            raise IntakeConflict(f"Draft is '{row[2]}' and can no longer be edited.")
        with conn.cursor() as cur:
            cur.execute('DELETE FROM "IntakeDraftParty" WHERE "IntakeDraftPartyID"=%s AND "IntakeDraftID"=%s',
                        (party_id, int(row[0])))
            if cur.rowcount == 0:
                raise IntakeNotFound(f"Party {party_id} not found on this draft.")
        _activity(conn, int(row[0]), "party_removed", actor, {"party_id": party_id})
        return _serialize_draft(conn, draft_key)


def validate_draft(draft_key: str) -> ValidationResponse:
    with db.rw_conn() as conn:
        return _validate(conn, draft_key, persist=True)


def submit_draft(draft_key: str, actor: Optional[str]) -> DraftResponse:
    with db.rw_conn() as conn:
        _submit(conn, draft_key, actor)
        return _serialize_draft(conn, draft_key)


def review_draft(draft_key: str, action: str, actor: Optional[str], note: Optional[str]):
    with db.rw_conn() as conn:
        return _review(conn, draft_key, action, actor, note)


def add_case_event(case_master_id: int, event_type: str, occurred_at: Optional[str],
                   actor_role: Optional[str], payload: dict) -> CaseEventResponse:
    with db.rw_conn() as conn:
        return _add_case_event(conn, case_master_id, event_type, occurred_at, actor_role, payload)


def list_drafts(status: Optional[str], case_kind: Optional[str], page: int, page_size: int) -> DraftListResponse:
    clauses, params = [], []
    if status:
        clauses.append('"Status" = %s'); params.append(status)
    if case_kind:
        clauses.append('"CaseKind" = %s'); params.append(case_kind)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "IntakeDraft"{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT "IntakeDraftID","DraftKey","CaseKind","CaseCategoryCode","Status",'
                f'"CaseMasterID","CreatedByActor","SubmittedByActor","ReviewedByActor",'
                f'"RevisionNo","PartyCount","ValidationOk","CrimeNo","CreatedAt","UpdatedAt","SubmittedAt" '
                f'FROM "vw_intake_inbox"{where} '
                f'ORDER BY "UpdatedAt" DESC LIMIT %s OFFSET %s', params + [page_size, offset])
            rows = cur.fetchall()
    items = [
        {
            "intake_draft_id": int(r[0]), "draft_key": r[1], "case_kind": r[2],
            "case_category_code": r[3], "status": r[4], "case_master_id": r[5],
            "created_by_actor": r[6], "submitted_by_actor": r[7], "reviewed_by_actor": r[8],
            "revision_no": int(r[9] or 0), "party_count": int(r[10] or 0),
            "validation_ok": r[11], "crime_no": r[12],
            "created_at": _s(r[13]), "updated_at": _s(r[14]), "submitted_at": _s(r[15]),
        }
        for r in rows
    ]
    return DraftListResponse(items=items, total=total, page=page, page_size=page_size)


def list_case_parties(case_master_id: int):
    """Canonical case parties (CasePartyRole resolved through canonical identity)."""
    from .schemas import CasePartyListResponse, CasePartyOut
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT r."CasePartyRoleID", r."RoleType", r."IsUnknownParty", r."PartyLabel",'
                ' r."SequenceNo", p."CanonicalPersonID", p."PublicRef", p."DisplayLabel",'
                ' o."CanonicalOrganisationID", o."PublicRef", o."Name",'
                ' r."LegacyRefTable", r."LegacyRefID" '
                'FROM "CasePartyRole" r '
                'LEFT JOIN "CanonicalPerson" p ON p."CanonicalPersonID" = r."CanonicalPersonID" '
                'LEFT JOIN "CanonicalOrganisation" o ON o."CanonicalOrganisationID" = r."CanonicalOrganisationID" '
                'WHERE r."CaseMasterID" = %s '
                'ORDER BY r."RoleType", r."SequenceNo" NULLS LAST, r."CasePartyRoleID"',
                (case_master_id,))
            rows = cur.fetchall()
    parties = [CasePartyOut(
        case_party_role_id=int(r[0]), role_type=r[1], is_unknown=bool(r[2]),
        party_label=r[3], sequence_no=r[4], canonical_person_id=r[5], person_ref=r[6],
        person_label=r[7], canonical_organisation_id=r[8], org_ref=r[9], org_name=r[10],
        legacy_ref_table=r[11], legacy_ref_id=r[12]) for r in rows]
    return CasePartyListResponse(case_master_id=case_master_id, count=len(parties), parties=parties)


def list_quality_issues(status: Optional[str], severity: Optional[str],
                        page: int, page_size: int):
    """Read-only staging data-quality queue (DataQualityIssue). Never mutates."""
    from .schemas import DataQualityIssueOut, DataQualityListResponse
    clauses, params = [], []
    if status:
        clauses.append('"Status" = %s'); params.append(status)
    if severity:
        clauses.append('"Severity" = %s'); params.append(severity)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "DataQualityIssue"{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute('SELECT "Severity", COUNT(*) FROM "DataQualityIssue" '
                        'GROUP BY "Severity"')
            by_sev = {r[0]: int(r[1]) for r in cur.fetchall()}
            cur.execute(
                f'SELECT "DataQualityIssueID","IssueType","Severity","Status","SourceRecordID",'
                f'"IngestionJobID","CaseMasterID","EvidenceItemID","Detail","ResolvedByActor",'
                f'"CreatedAt","ResolvedAt" FROM "DataQualityIssue"{where} '
                f'ORDER BY "CreatedAt" DESC, "DataQualityIssueID" DESC LIMIT %s OFFSET %s',
                params + [page_size, offset])
            rows = cur.fetchall()
    items = [DataQualityIssueOut(
        data_quality_issue_id=int(r[0]), issue_type=r[1], severity=r[2], status=r[3],
        source_record_id=r[4], ingestion_job_id=r[5], case_master_id=r[6],
        evidence_item_id=r[7], detail=r[8] or {}, resolved_by_actor=r[9],
        created_at=_s(r[10]), resolved_at=_s(r[11])) for r in rows]
    return DataQualityListResponse(items=items, total=total, by_severity=by_sev,
                                   page=page, page_size=page_size)


def draft_activity(draft_key: str) -> list[DraftActivity]:
    with db.ro_conn() as conn:
        did = _draft_id(conn, draft_key)
        if did is None:
            raise IntakeNotFound(f"Intake draft '{draft_key}' not found.")
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "IntakeDraftActivityID","EventType","Actor","Detail","CreatedAt" '
                'FROM "IntakeDraftActivity" WHERE "IntakeDraftID"=%s ORDER BY "IntakeDraftActivityID"',
                (did,))
            rows = cur.fetchall()
    return [DraftActivity(intake_draft_activity_id=int(r[0]), event_type=r[1], actor=r[2],
                          detail=r[3] or {}, created_at=_s(r[4])) for r in rows]
