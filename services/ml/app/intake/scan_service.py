"""Scanned-FIR intake service: OCR -> parse -> resolve -> reviewed draft.

Pipeline
--------
1. ``run_scan_ocr``      bytes -> Zia OCR -> ``extract_fir`` -> ``resolve_extraction``
                         -> one ``IntakeScan`` row (+ one ``IntakeScanField`` per
                         proposed field). Creates NO draft and NO case.
2. officer reviews       the SPA shows the proposal beside the recognised text.
3. ``apply_scan_to_draft`` the values the officer ACCEPTED become an ``IntakeDraft``
                         via the ordinary ``service._create_draft`` path, so the
                         scanned lane and the manual lane converge on one draft,
                         one validator and one approval gate.

What this module deliberately does not do
-----------------------------------------
It never writes a canonical row. ``CaseMaster`` is still created only by
``service._approve``, driven by a human. So the worst case for a bad OCR read is a
draft an officer corrects or discards — never a wrong registered FIR.

Byte handling
-------------
The scanned page is hashed (SHA-256) so an approved FIR is always traceable to the
exact image it was read from. Retaining the image itself is best-effort: if an
evidence object store is configured the bytes are written there through a
short-lived pre-signed PUT (reusing the evidence gateway rather than adding a
second storage path); if not, the manifest is kept hash-only and the response says
so. Zia itself does not retain uploaded files.
"""
from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from psycopg2.extras import Json

from .. import audit, db
from ..config import get_settings
from .. import zia_ocr as ocr_mod
from . import service as draft_service
from . import workflow as wf
from .extract import ExtractionResult, extract_fir, template_spec
from .resolve import resolve_extraction
from .schemas import (CreateDraftRequest, DraftPayload, PartyInput, ScanApplyRequest,
                      ScanApplyResult, ScanExtractedField, ScanFieldProvenance,
                      ScanProposedParty, ScanProvenanceResponse, ScanQueueItem,
                      ScanQueueResponse, ScanResponse, ScanUnresolvedLookup)
from .service import IntakeConflict, IntakeNotFound, IntakeValidationError

# Re-exported so the router can translate scan errors with the intake mapping.
__all__ = [
    "run_scan_ocr", "get_scan", "apply_scan_to_draft", "scan_provenance",
    "list_scan_queue", "discard_scan", "scan_template", "scan_capability",
]

_STORE_TIMEOUT_S = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s(v) -> Optional[str]:
    return str(v) if v is not None else None


# ---------------------------------------------------------------------------
# Optional retention of the scanned page
# ---------------------------------------------------------------------------
def _store_scan_bytes(content: bytes, *, scan_key: str, filename: str,
                      content_type: str) -> tuple[Optional[str], Optional[str]]:
    """Best-effort write of the scanned page to the evidence object store.

    Returns ``(storage_key, note)``. Reuses the evidence gateway's pre-signed PUT
    so Stratus and S3 both work with no new storage code path. A failure here is
    never fatal: the scan is still identifiable by its SHA-256, and the caller
    reports honestly that the image was not retained.
    """
    settings = get_settings()
    if not settings.storage_configured():
        return None, ("No evidence object store is configured, so the scanned image "
                      "was not retained. Its SHA-256 is recorded for traceability.")
    try:
        from ..evidence import s3 as evidence_s3
        gw = evidence_s3.get_gateway()
        safe_name = evidence_s3.sanitize_filename(filename, "scan")
        key = f"{settings.s3_evidence_prefix.strip('/')}/intake-scan/{scan_key}/{safe_name}"
        presigned = gw.presign_put(key, settings.s3_presign_expiry_s)
        req = urllib.request.Request(
            presigned.url, data=content, method="PUT",
            headers={"Content-Type": content_type or "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=_STORE_TIMEOUT_S) as resp:  # noqa: S310
            if resp.status not in (200, 201, 204):
                raise RuntimeError(f"unexpected status {resp.status}")
        return key, None
    except Exception as exc:  # noqa: BLE001 — retention is best-effort by design
        return None, (f"The scanned image could not be retained "
                      f"({type(exc).__name__}); its SHA-256 is recorded instead.")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _scan_row(conn, scan_key: str) -> Optional[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT s."IntakeScanID", s."ScanKey", s."Status", s."ReviewState",'
            ' s."Provider", s."ModelType", s."DetectedLanguage", s."OcrConfidence",'
            ' s."RawText", s."TemplateCode", s."TemplateMatched", s."ExtractedPayload",'
            ' s."FieldConfidence", s."UnresolvedFields", s."ExtractedParties",'
            ' s."FileName", s."MimeType", s."SizeBytes", s."Sha256", s."StorageKey",'
            ' s."IntakeDraftID", s."EvidenceItemID", s."CreatedByActor", s."CreatedAt",'
            ' d."DraftKey" '
            'FROM "IntakeScan" s LEFT JOIN "IntakeDraft" d '
            '  ON d."IntakeDraftID" = s."IntakeDraftID" '
            'WHERE s."ScanKey"=%s', (scan_key,))
        return cur.fetchone()


def _insert_scan(conn, *, scan_key: str, idempotency_key: Optional[str],
                 result: ExtractionResult, ocr: ocr_mod.OcrResult,
                 filename: str, content_type: str, size_bytes: int, sha256: str,
                 storage_key: Optional[str], actor: Optional[str],
                 case_kind: str) -> int:
    """Persist one OCR run. Fields go to IntakeScanField for per-field provenance."""
    with conn.cursor() as cur:
        cur.execute('SELECT "SourceSystemID" FROM "SourceSystem" WHERE "Code"=%s',
                    ("FIR_SCAN_OCR",))
        row = cur.fetchone()
        source_system_id = int(row[0]) if row else None

        payload_dict = dict(result.payload)
        payload_dict["__case_kind"] = case_kind
        cur.execute(
            'INSERT INTO "SourceRecord" ("SourceSystemID","ExternalRef","RecordKind",'
            '"Payload","Status") VALUES (%s,%s,%s,%s,%s) RETURNING "SourceRecordID"',
            (source_system_id, scan_key, "case", Json(payload_dict), "staged"))
        source_record_id = int(cur.fetchone()[0])

        cur.execute(
            'INSERT INTO "IntakeScan" ("ScanKey","IdempotencyKey","SourceSystemID",'
            '"SourceRecordID","StorageKey","FileName","MimeType","SizeBytes","Sha256",'
            '"Provider","ModelType","RequestedLanguages","DetectedLanguage",'
            '"OcrConfidence","RawText","TemplateCode","TemplateMatched",'
            '"ExtractedPayload","FieldConfidence","UnresolvedFields","ExtractedParties",'
            '"ReviewState","Status","CreatedByActor","OcrStartedAt","OcrFinishedAt") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'
            '%s,%s,%s,now(),now()) RETURNING "IntakeScanID"',
            (scan_key, idempotency_key, source_system_id, source_record_id,
             storage_key, filename, content_type, size_bytes, sha256,
             ocr.provider or "catalyst-zia-ocr", ocr.model_type or "OCR",
             list(ocr.requested_languages), result.language,
             None if ocr.confidence is None else round(ocr.confidence * 100, 3),
             result_text_for_storage(ocr.text), result.template_code,
             bool(result.template_matched),
             Json(result.payload), Json(result.field_confidence),
             Json([u.as_dict() for u in result.unresolved]),
             Json(result.parties),
             "pending_review", "extracted", actor))
        scan_id = int(cur.fetchone()[0])

        for f in result.fields:
            cur.execute(
                'INSERT INTO "IntakeScanField" ("IntakeScanID","FieldPath",'
                '"ExtractedText","ProposedValue","Confidence","Origin","WasEdited",'
                '"RequiresReview") VALUES (%s,%s,%s,%s,%s,%s,%s,%s) '
                'ON CONFLICT ("IntakeScanID","FieldPath") DO NOTHING',
                (scan_id, f.path, f.raw_text, Json(f.value),
                 round(min(max(f.confidence, 0.0), 1.0), 4), "ocr", False,
                 bool(f.requires_review)))
    return scan_id


def result_text_for_storage(text: str) -> str:
    """Bound retained OCR text so a pathological PDF cannot bloat a row."""
    return (text or "")[:get_settings().scan_ocr_max_text_chars]


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
def _scan_response(row: tuple, *, notes: Optional[list[str]] = None,
                   fields: Optional[list[ScanExtractedField]] = None) -> ScanResponse:
    (_scan_id, scan_key, status, review_state, provider, _model_type, language,
     ocr_conf, raw_text, template_code, template_matched, payload, field_conf,
     unresolved, parties, filename, _mime, size_bytes, sha256, _storage_key,
     _draft_id, _evidence_id, _actor, created_at, draft_key) = row

    conf = None if ocr_conf is None else float(ocr_conf) / 100.0
    threshold = get_settings().scan_ocr_low_confidence_threshold
    payload = payload or {}
    case_kind = (payload.pop("__case_kind", None)
                 if isinstance(payload, dict) else None) or "fir_standard"

    if fields is None:
        fields = [
            ScanExtractedField(field=path, value=None, confidence=float(score),
                               requires_review=float(score) < get_settings().scan_ocr_auto_fill_threshold,
                               auto_filled=float(score) >= get_settings().scan_ocr_auto_fill_threshold)
            for path, score in (field_conf or {}).items()
        ]

    return ScanResponse(
        scan_key=scan_key, status=status, review_state=review_state,
        provider=provider or "", template_code=template_code,
        template_matched=bool(template_matched),
        matched_label_count=len([f for f in fields if f.raw_text]) or len(fields),
        detected_language=language, ocr_confidence=conf,
        ocr_low_confidence=bool(conf is not None and conf < threshold),
        raw_text=raw_text or "",
        payload=DraftPayload(**(payload or {})), case_kind=case_kind,
        fields=fields,
        parties=[ScanProposedParty(**p) for p in (parties or [])],
        unresolved=[ScanUnresolvedLookup(**u) for u in (unresolved or [])],
        fields_needing_review=sum(1 for f in fields if f.requires_review),
        notes=notes or [],
        draft_key=draft_key, file_name=filename, size_bytes=size_bytes,
        sha256=sha256, created_at=_s(created_at))


def _fields_from_result(result: ExtractionResult) -> list[ScanExtractedField]:
    return [ScanExtractedField(**f.as_dict()) for f in result.fields]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _run_scan_ocr(conn, content: bytes, *, filename: str = "", content_type: str = "",
                  actor: Optional[str] = None, languages: Optional[list[str]] = None,
                  unit_id: Optional[int] = None,
                  idempotency_key: Optional[str] = None,
                  reference: Optional[dict] = None) -> ScanResponse:
    """OCR + parse + resolve + persist, on an OPEN connection (never commits).

    ``reference`` is injectable so a test can supply reference data instead of
    reading it from the database.
    """
    if not content:
        raise IntakeValidationError("No scan was uploaded.")

    engine = ocr_mod.get_zia_ocr()
    if not engine.available:
        # Fail closed with an actionable message; the manual lane still works.
        raise IntakeConflict(
            "Scanned-FIR reading is not enabled on this server. Enter the FIR "
            "manually, or ask an operator to enable the Catalyst Zia OCR path.")

    try:
        ocr_mod.validate_ocr_input(size_bytes=len(content), filename=filename,
                                   mime_type=content_type)
    except ocr_mod.ZiaOcrError as exc:
        raise IntakeValidationError(str(exc)) from exc

    sha256 = hashlib.sha256(content).hexdigest()
    scan_key = "SC-" + uuid.uuid4().hex[:12].upper()

    # Reuse an identical earlier run rather than paying for OCR twice.
    if idempotency_key:
        with conn.cursor() as cur:
            cur.execute('SELECT "ScanKey" FROM "IntakeScan" WHERE "IdempotencyKey"=%s',
                        (idempotency_key,))
            existing = cur.fetchone()
        if existing:
            prior = _scan_row(conn, existing[0])
            return _scan_response(prior, fields=_stored_fields(conn, int(prior[0])))

    try:
        ocr = engine.recognize(
            content, filename=filename, content_type=content_type,
            languages=languages or ocr_mod.default_languages())
    except ocr_mod.ZiaOcrUnavailable as exc:
        raise IntakeConflict(str(exc)) from exc
    except ocr_mod.ZiaOcrError as exc:
        raise IntakeValidationError(
            f"The scan could not be read. {exc} Try a clearer photograph, or "
            "enter the FIR manually.") from exc

    if not (ocr.text or "").strip():
        raise IntakeValidationError(
            "No text was recognised on this scan. Check the photograph is in "
            "focus and well lit, or enter the FIR manually.")

    result = extract_fir(ocr.text, ocr_confidence=ocr.confidence,
                         language=ocr.detected_language)
    result = resolve_extraction(result, reference=reference, unit_id=unit_id)

    storage_key, store_note = _store_scan_bytes(
        content, scan_key=scan_key, filename=filename or "scan",
        content_type=content_type)
    if store_note:
        result.notes.append(store_note)

    case_kind = result.case_kind or "fir_standard"
    if case_kind not in wf.CASE_KINDS:
        result.notes.append(
            f"Case type '{case_kind}' is not a recognised kind; using Standard FIR.")
        case_kind = "fir_standard"

    _insert_scan(conn, scan_key=scan_key, idempotency_key=idempotency_key,
                 result=result, ocr=ocr, filename=filename or "scan",
                 content_type=content_type, size_bytes=len(content),
                 sha256=sha256, storage_key=storage_key, actor=actor,
                 case_kind=case_kind)
    audit.record(audit.Action.INTAKE_CREATE, "intake_scan", scan_key,
                 actor=actor, conn=conn,
                 detail={"provider": ocr.provider, "sha256": sha256,
                         "language": result.language,
                         "template_matched": result.template_matched,
                         "fields_proposed": len(result.fields),
                         "creates_case": False})
    row = _scan_row(conn, scan_key)
    if row is None:  # pragma: no cover — insert then read in one transaction
        raise IntakeNotFound(f"Scan '{scan_key}' could not be read back.")
    return _scan_response(row, notes=result.notes, fields=_fields_from_result(result))


def run_scan_ocr(content: bytes, *, filename: str = "", content_type: str = "",
                 actor: Optional[str] = None, languages: Optional[list[str]] = None,
                 unit_id: Optional[int] = None,
                 idempotency_key: Optional[str] = None) -> ScanResponse:
    """OCR one scanned FIR page-set and return a reviewable proposal.

    Creates no draft and no case — the officer must accept the proposal first.
    """
    with db.rw_conn() as conn:
        return _run_scan_ocr(conn, content, filename=filename,
                             content_type=content_type, actor=actor,
                             languages=languages, unit_id=unit_id,
                             idempotency_key=idempotency_key)


def get_scan(scan_key: str) -> ScanResponse:
    with db.ro_conn() as conn:
        row = _scan_row(conn, scan_key)
        if row is None:
            raise IntakeNotFound(f"Scan '{scan_key}' not found.")
        fields = _stored_fields(conn, int(row[0]))
    return _scan_response(row, fields=fields)


def _stored_fields(conn, scan_id: int) -> list[ScanExtractedField]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "FieldPath","ExtractedText","ProposedValue","AcceptedValue",'
            '"Confidence","Origin","WasEdited","RequiresReview" '
            'FROM "IntakeScanField" WHERE "IntakeScanID"=%s ORDER BY "IntakeScanFieldID"',
            (scan_id,))
        rows = cur.fetchall()
    out: list[ScanExtractedField] = []
    for path, raw, proposed, accepted, conf, _origin, edited, needs in rows:
        out.append(ScanExtractedField(
            field=path, value=accepted if accepted is not None else proposed,
            raw_text=raw or "", confidence=float(conf or 0.0),
            requires_review=bool(needs), auto_filled=not bool(needs),
            note="Edited by the reviewing officer." if edited else None))
    return out


def _get_path(payload: dict, path: str) -> Any:
    section, _, key = path.partition(".")
    if not key:
        return None
    return (payload.get(section) or {}).get(key)


def _accepted_value_for(path: str, payload: dict,
                        parties: list[dict]) -> Any:
    """Find what the officer accepted for a proposed field path.

    Party pseudo-paths (``__complainant_name``) live on a party rather than the
    payload, so they are matched by role plus attribute.
    """
    if not path.startswith("__"):
        return _get_path(payload, path)
    if path == "__case_kind":
        return None            # handled separately from the draft's case_kind
    body = path[2:]
    role, _, attr = body.partition("_")
    for p in parties:
        if p.get("role_type") != role:
            continue
        if attr in ("name", ""):
            return p.get("display_name")
        return (p.get("attributes") or {}).get(attr)
    return None


def _apply_scan_to_draft(conn, scan_key: str, req: ScanApplyRequest) -> ScanApplyResult:
    """Turn a reviewed scan into an intake draft, on an OPEN connection.

    Never commits, so tests can drive the whole path inside a rolled-back
    transaction (same contract as the helpers in ``service.py``).

    The draft is created through the ordinary ``_create_draft`` path so the
    scanned lane inherits the manual lane's validation, review state machine and
    approval gate exactly. Per-field provenance records what OCR proposed versus
    what the officer accepted.
    """
    row = _scan_row(conn, scan_key)
    if row is None:
        raise IntakeNotFound(f"Scan '{scan_key}' not found.")
    scan_id, _key, status, _review, _prov, _mt, _lang, _conf, _raw, _tc, _tm, \
        stored_payload, _fc, _unres, stored_parties, _fn, _mime, _sz, _sha, \
        _sk, existing_draft_id, _ev, _actor, _created, existing_draft_key = row

    if existing_draft_id:
        raise IntakeConflict(
            f"Scan '{scan_key}' was already applied to draft "
            f"'{existing_draft_key}'. Open that draft instead.")
    if status == "discarded":
        raise IntakeConflict(f"Scan '{scan_key}' was discarded.")

    stored_payload = dict(stored_payload or {})
    proposed_kind = stored_payload.pop("__case_kind", None) or "fir_standard"

    # What the officer accepted wins; the machine proposal is the fallback.
    final_payload = (req.payload.model_dump() if req.payload is not None
                     else stored_payload)
    final_kind = req.case_kind or proposed_kind
    if final_kind not in wf.CASE_KINDS:
        raise IntakeValidationError(f"Unknown case kind '{final_kind}'.")

    if req.parties is not None:
        final_parties = [p.model_dump() for p in req.parties]
        party_inputs = list(req.parties)
    else:
        final_parties = [
            {k: v for k, v in p.items() if k != "confidence"}
            for p in (stored_parties or [])
        ]
        party_inputs = [PartyInput(**p) for p in final_parties]

    # Only keep proposed parties whose role the chosen kind actually permits
    # (a Missing Person case must not silently acquire an accused).
    allowed = set(wf.allowed_party_roles(final_kind))
    dropped = [p.role_type for p in party_inputs if p.role_type not in allowed]
    party_inputs = [p for p in party_inputs if p.role_type in allowed]

    payload_model = DraftPayload(**final_payload)
    # Record the true provenance of this draft: a scanned form, not a typed one.
    payload_model.source.source_system_code = "FIR_SCAN_OCR"
    if not payload_model.source.source_method:
        payload_model.source.source_method = "walk_in"

    draft_key = draft_service._create_draft(conn, CreateDraftRequest(
        case_kind=final_kind,
        idempotency_key=req.idempotency_key,
        created_by_actor=req.actor,
        payload=payload_model,
        parties=party_inputs))
    draft_id = draft_service._draft_id(conn, draft_key)

    # Per-field provenance: proposed vs accepted, and whether it was edited.
    edited_paths = set(req.edited_fields or [])
    accepted_payload = payload_model.model_dump()
    from_scan = edited = needs_review = 0
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "IntakeScanFieldID","FieldPath","ProposedValue","RequiresReview" '
            'FROM "IntakeScanField" WHERE "IntakeScanID"=%s', (scan_id,))
        for field_id, path, proposed, requires_review in cur.fetchall():
            accepted = _accepted_value_for(path, accepted_payload, final_parties)
            was_edited = (path in edited_paths) or (
                accepted is not None and proposed is not None
                and accepted != proposed)
            origin = "ocr_edited" if was_edited else "ocr"
            cur.execute(
                'UPDATE "IntakeScanField" SET "AcceptedValue"=%s,"Origin"=%s,'
                '"WasEdited"=%s WHERE "IntakeScanFieldID"=%s',
                (Json(accepted), origin, was_edited, field_id))
            from_scan += 1
            edited += 1 if was_edited else 0
            needs_review += 1 if requires_review and not was_edited else 0

        cur.execute(
            'UPDATE "IntakeScan" SET "IntakeDraftID"=%s,"Status"=%s,'
            '"ReviewState"=%s,"ReviewedByActor"=%s,"AppliedAt"=now() '
            'WHERE "IntakeScanID"=%s',
            (draft_id, "applied",
             "accepted_with_edits" if edited else "accepted_as_is",
             req.actor, scan_id))

    detail = {
        "scan_key": scan_key, "fields_from_scan": from_scan,
        "fields_edited": edited, "fields_needing_review": needs_review,
        "template_code": _tc,
        # psycopg2 hands NUMERIC back as Decimal; coerce so the audit row
        # stores a number rather than a stringified Decimal.
        "ocr_confidence": None if _conf is None else float(_conf),
    }
    if dropped:
        detail["parties_dropped_for_kind"] = dropped
    draft_service._activity(conn, draft_id, "scan_prefilled", req.actor, detail)
    audit.record(audit.Action.INTAKE_CREATE, "intake_draft", draft_key,
                 actor=req.actor, conn=conn,
                 detail={"prefilled_from_scan": scan_key, **detail})

    draft = draft_service._serialize_draft(conn, draft_key)
    return ScanApplyResult(scan_key=scan_key, draft=draft,
                           fields_from_scan=from_scan, fields_edited=edited,
                           fields_needing_review=needs_review)


def apply_scan_to_draft(scan_key: str, req: ScanApplyRequest) -> ScanApplyResult:
    """Public wrapper: opens a transaction that commits on clean exit."""
    with db.rw_conn() as conn:
        return _apply_scan_to_draft(conn, scan_key, req)


def scan_provenance(scan_key: str) -> ScanProvenanceResponse:
    """Per-field provenance for a scan: proposed, accepted, and what changed."""
    with db.ro_conn() as conn:
        row = _scan_row(conn, scan_key)
        if row is None:
            raise IntakeNotFound(f"Scan '{scan_key}' not found.")
        scan_id = int(row[0])
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "FieldPath","ExtractedText","ProposedValue","AcceptedValue",'
                '"Confidence","Origin","WasEdited","RequiresReview" '
                'FROM "IntakeScanField" WHERE "IntakeScanID"=%s '
                'ORDER BY "IntakeScanFieldID"', (scan_id,))
            rows = cur.fetchall()

    conf = None if row[7] is None else float(row[7]) / 100.0
    return ScanProvenanceResponse(
        scan_key=scan_key, draft_key=row[24], template_code=row[9],
        detected_language=row[6], ocr_confidence=conf, provider=row[4] or "",
        file_name=row[15], sha256=row[18], evidence_item_id=row[21],
        fields=[
            ScanFieldProvenance(
                field=r[0], extracted_text=r[1], proposed_value=r[2],
                accepted_value=r[3],
                confidence=None if r[4] is None else float(r[4]),
                origin=r[5], was_edited=bool(r[6]), requires_review=bool(r[7]))
            for r in rows
        ])


def _discard_scan(conn, scan_key: str, actor: Optional[str] = None) -> ScanResponse:
    """Discard an unapplied scan, on an OPEN connection (never commits)."""
    row = _scan_row(conn, scan_key)
    if row is None:
        raise IntakeNotFound(f"Scan '{scan_key}' not found.")
    if row[20]:
        raise IntakeConflict(
            "This scan was already applied to a draft; discard the draft instead.")
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE "IntakeScan" SET "Status"=%s,"ReviewState"=%s,'
            '"ReviewedByActor"=%s WHERE "ScanKey"=%s',
            ("discarded", "rejected", actor, scan_key))
    return _scan_response(_scan_row(conn, scan_key),
                          notes=["Scan discarded; nothing was saved to a case."])


def discard_scan(scan_key: str, actor: Optional[str] = None) -> ScanResponse:
    """Discard an unapplied scan (a misread page, or the wrong document)."""
    with db.rw_conn() as conn:
        return _discard_scan(conn, scan_key, actor)


def list_scan_queue(status: Optional[str] = None, review_state: Optional[str] = None,
                    page: int = 1, page_size: int = 25) -> ScanQueueResponse:
    """The scanned-FIR review queue (backs the admin extraction-queue panel)."""
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append('"Status" = %s')
        params.append(status)
    if review_state:
        clauses.append('"ReviewState" = %s')
        params.append(review_state)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = max(0, (max(1, page) - 1) * page_size)

    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "vw_intake_scan_queue"{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                'SELECT "ScanKey","Status","ReviewState","DetectedLanguage",'
                '"OcrConfidence","TemplateCode","TemplateMatched","FileName",'
                '"SizeBytes","CreatedByActor","CreatedAt","DraftKey","DraftStatus",'
                '"CaseKind","CaseMasterID","FieldCount","FieldsNeedingReview",'
                f'"FieldsEdited","UnresolvedCount" FROM "vw_intake_scan_queue"{where} '
                'ORDER BY "CreatedAt" DESC LIMIT %s OFFSET %s',
                (*params, page_size, offset))
            rows = cur.fetchall()

    items = [
        ScanQueueItem(
            scan_key=r[0], status=r[1], review_state=r[2], detected_language=r[3],
            ocr_confidence=None if r[4] is None else float(r[4]) / 100.0,
            template_code=r[5], template_matched=bool(r[6]), file_name=r[7],
            size_bytes=r[8], created_by_actor=r[9], created_at=_s(r[10]),
            draft_key=r[11], draft_status=r[12], case_kind=r[13],
            case_master_id=r[14], field_count=int(r[15] or 0),
            fields_needing_review=int(r[16] or 0), fields_edited=int(r[17] or 0),
            unresolved_count=int(r[18] or 0))
        for r in rows
    ]
    return ScanQueueResponse(items=items, total=total, page=max(1, page),
                             page_size=page_size, extraction_queue_present=True)


def scan_template() -> dict:
    """The printable intake-form contract (generated from the parser's table)."""
    return template_spec()


def scan_capability() -> dict:
    """Truthful OCR capability for the SPA."""
    return ocr_mod.ocr_capability_status()
