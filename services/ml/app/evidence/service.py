"""Evidence service — draft metadata, S3 upload/complete, versions, activity,
links, correction, archive, download, synthetic reset, legacy migration.

Testability + safety (mirrors app/intake/service.py):
  * Internal ``_fn(conn, ...)`` helpers do the work on an OPEN connection and
    never commit, so tests drive the real SQL against the live schema then ROLL
    BACK (no mutation of the synthetic DB).
  * S3 is reached only through an injected ``S3Gateway`` — tests pass an
    in-memory fake, so no AWS calls happen in unit tests.
  * File bytes never enter PostgreSQL. Content is NEVER parsed (no OCR /
    extraction) and an upload NEVER triggers a prediction. The system generates
    only file name / MIME / size / SHA-256 from the uploaded object.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from psycopg2.extras import Json

from .. import audit, db
from ..config import get_settings
from . import s3
from .s3 import ObjectNotFound, S3Gateway
from .schemas import (ArchiveRequest, CompleteUploadRequest, CompleteUploadResponse,
                      CreateResponse, DownloadUrlResponse, EvidenceActivityOut,
                      EvidenceCaseLinkOut, EvidenceCreateRequest, EvidenceEntityLinkOut,
                      EvidenceItemOut, EvidenceListItem, EvidenceListResponse,
                      EvidenceMetadataUpdate, EvidenceObjectOut, EvidenceVersionOut,
                      LinkRequest, MigrateLegacyResponse, ResetResponse,
                      UploadUrlRequest, UploadUrlResponse)


# ---------------------------------------------------------------------------
# Typed errors (router -> HTTP)
# ---------------------------------------------------------------------------
class EvidenceError(Exception):
    pass


class EvidenceNotFound(EvidenceError):
    pass


class EvidenceConflict(EvidenceError):
    pass


class EvidenceValidationError(EvidenceError):
    def __init__(self, message: str, detail: Optional[dict] = None):
        super().__init__(message)
        self.detail = detail


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALLOWED_EVIDENCE_TYPES = {
    "document", "statement", "image", "video", "audio", "physical_exhibit",
    "property_item", "forensic_report", "digital_export", "financial_dataset",
    "court_document", "external_reference",
}
# Types that never carry an uploaded file (metadata / physical-world only).
NO_FILE_TYPES = {"external_reference", "physical_exhibit", "property_item"}
CONFIDENTIALITIES = {"demo_normal", "demo_restricted", "demo_sensitive"}
PREVIEWABLE_MIME = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf", "text/plain", "text/csv", "application/json",
}
_EVENT_CREATED = "created"
_EVENT_UPLOAD_URL = "upload_url_issued"
_EVENT_UPLOADED = "uploaded"
_EVENT_VERSION = "version_added"
_EVENT_META = "metadata_updated"
_EVENT_LINKED = "linked"
_EVENT_UNLINKED = "unlinked"
_EVENT_DOWNLOAD = "download"
_EVENT_ARCHIVED = "archived"
_EVENT_RESTORED = "restored"
_EVENT_FAILED = "failed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s(v) -> Optional[str]:
    return str(v) if v is not None else None


def _previewable(mime: Optional[str]) -> bool:
    return bool(mime and mime.lower() in PREVIEWABLE_MIME)


def _gw(gw: Optional[S3Gateway]) -> S3Gateway:
    return gw if gw is not None else s3.get_gateway()


# ---------------------------------------------------------------------------
# Reference helpers
# ---------------------------------------------------------------------------
def _source_system_id(conn, code: Optional[str]) -> Optional[int]:
    if not code:
        return None
    with conn.cursor() as cur:
        cur.execute('SELECT "SourceSystemID" FROM "SourceSystem" WHERE "Code"=%s', (code,))
        r = cur.fetchone()
    return int(r[0]) if r else None


def _case_exists(conn, case_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "CaseMaster" WHERE "CaseMasterID"=%s', (case_id,))
        return cur.fetchone() is not None


def _entity_exists(conn, entity_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "CanonicalEntity" WHERE "CanonicalEntityID"=%s', (entity_id,))
        return cur.fetchone() is not None


def _crime_no(conn, case_id: Optional[int]) -> Optional[str]:
    if not case_id:
        return None
    with conn.cursor() as cur:
        cur.execute(
            'SELECT COALESCE(NULLIF(cv.attrs #>> '
            "'{official_references,police_crime_no}', ''), cm.\"CrimeNo\") "
            'FROM "CaseMaster" cm LEFT JOIN LATERAL ('
            'SELECT cv0."SnapshotAttributes" AS attrs FROM "CaseVersion" cv0 '
            'WHERE cv0."CaseMasterID"=cm."CaseMasterID" AND cv0."IsCurrent"=TRUE '
            'ORDER BY cv0."VersionNo" DESC LIMIT 1) cv ON TRUE '
            'WHERE cm."CaseMasterID"=%s',
            (case_id,),
        )
        r = cur.fetchone()
    return r[0] if r else None


def _activity(conn, item_id: int, event_type: str, actor: Optional[str], detail: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "EvidenceActivityEvent" ("EvidenceItemID","EventType","Actor","Detail") '
            'VALUES (%s,%s,%s,%s)', (item_id, event_type, actor, Json(detail)))


def _validate_upload(file_name: str, mime_type: str, size_bytes: int) -> None:
    """Allow-list gate for file name / MIME / size (Contract §13, prompt2.md §5)."""
    s = get_settings()
    if size_bytes is None or size_bytes < 0:
        raise EvidenceValidationError("File size is missing or invalid.")
    if size_bytes == 0:
        raise EvidenceValidationError("Refusing to store an empty (0-byte) file.")
    if size_bytes > s.evidence_max_bytes:
        raise EvidenceValidationError(
            f"File is {size_bytes} bytes; the limit is {s.evidence_max_bytes} bytes.",
            detail={"code": "too_large", "max_bytes": s.evidence_max_bytes})
    ext = (file_name or "").rsplit(".", 1)[-1].lower() if "." in (file_name or "") else ""
    if ext not in s.evidence_allowed_ext_set():
        raise EvidenceValidationError(
            f"File extension '.{ext}' is not allowed.",
            detail={"code": "bad_extension", "allowed": sorted(s.evidence_allowed_ext_set())})
    if (mime_type or "").lower() not in s.evidence_allowed_mime_set():
        raise EvidenceValidationError(
            f"MIME type '{mime_type}' is not allowed.",
            detail={"code": "bad_mime", "allowed": sorted(s.evidence_allowed_mime_set())})


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
_ITEM_COLS = (
    '"EvidenceItemID","CaseMasterID","SourceSystemID","SourceRecordID","EvidenceType",'
    '"Category","Title","Description","SyntheticReference","Language","Tags","UploaderActor",'
    '"Confidentiality","State","ManualMetadata","CapturedAt","ReceivedAt","UploadedAt",'
    '"CreatedAt","UpdatedAt","IsSynthetic"'
)


def _item_row(conn, item_id: int) -> Optional[tuple]:
    with conn.cursor() as cur:
        cur.execute(f'SELECT {_ITEM_COLS} FROM "EvidenceItem" WHERE "EvidenceItemID"=%s', (item_id,))
        return cur.fetchone()


def _is_curated_reference(row: tuple) -> bool:
    metadata = row[14] if isinstance(row[14], dict) else {}
    return (
        row[20] is False
        and metadata.get("record_origin") == "public_source_curated"
        and metadata.get("metadata_only") is True
    )


def _require_mutable_reference(row: tuple, action: str) -> None:
    if _is_curated_reference(row):
        raise EvidenceConflict(
            "Public-source curated references are read-only. "
            f"Cannot {action}; add a separate sourced annotation instead."
        )


def _require_file_backed(row: tuple) -> None:
    metadata = row[14] if isinstance(row[14], dict) else {}
    if metadata.get("metadata_only") is True or metadata.get("file_backed") is False:
        raise EvidenceConflict(
            "This is a metadata-only external reference; no native file may be attached."
        )


def _objects(conn, item_id: int) -> list[EvidenceObjectOut]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EvidenceObjectID","VersionNo","IsCurrent","FileName","MimeType",'
            '"SizeBytes","Sha256","StorageStatus","StorageKey","CreatedAt" '
            'FROM "EvidenceObject" WHERE "EvidenceItemID"=%s ORDER BY "VersionNo" DESC, "EvidenceObjectID" DESC',
            (item_id,))
        rows = cur.fetchall()
    return [EvidenceObjectOut(
        evidence_object_id=int(r[0]), version_no=int(r[1]), is_current=bool(r[2]),
        file_name=r[3], mime_type=r[4], size_bytes=r[5], sha256=r[6],
        storage_status=r[7], storage_key=r[8], created_at=_s(r[9])) for r in rows]


def _versions(conn, item_id: int) -> list[EvidenceVersionOut]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EvidenceVersionID","VersionNo","EvidenceObjectID","ChangeReason",'
            '"CreatedByActor","CreatedAt" FROM "EvidenceVersion" WHERE "EvidenceItemID"=%s '
            'ORDER BY "VersionNo"', (item_id,))
        rows = cur.fetchall()
    return [EvidenceVersionOut(
        evidence_version_id=int(r[0]), version_no=int(r[1]), evidence_object_id=r[2],
        change_reason=r[3], created_by_actor=r[4], created_at=_s(r[5])) for r in rows]


def _case_links(conn, item_id: int) -> list[EvidenceCaseLinkOut]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT l."EvidenceCaseLinkID", l."CaseMasterID", cm."CrimeNo", l."LinkType", l."CreatedAt" '
            'FROM "EvidenceCaseLink" l LEFT JOIN "CaseMaster" cm ON cm."CaseMasterID"=l."CaseMasterID" '
            'WHERE l."EvidenceItemID"=%s ORDER BY l."EvidenceCaseLinkID"', (item_id,))
        rows = cur.fetchall()
    return [EvidenceCaseLinkOut(
        evidence_case_link_id=int(r[0]), case_master_id=int(r[1]), crime_no=r[2],
        link_type=r[3], created_at=_s(r[4])) for r in rows]


def _entity_links(conn, item_id: int) -> list[EvidenceEntityLinkOut]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT el."EvidenceEntityLinkID", el."CanonicalEntityID", ce."PublicRef", ce."Label",'
            ' el."LinkType", el."ReviewStatus", el."Confidence" '
            'FROM "EvidenceEntityLink" el '
            'LEFT JOIN "CanonicalEntity" ce ON ce."CanonicalEntityID"=el."CanonicalEntityID" '
            'WHERE el."EvidenceItemID"=%s ORDER BY el."EvidenceEntityLinkID"', (item_id,))
        rows = cur.fetchall()
    return [EvidenceEntityLinkOut(
        evidence_entity_link_id=int(r[0]), canonical_entity_id=int(r[1]), entity_ref=r[2],
        entity_label=r[3], link_type=r[4], review_status=r[5],
        confidence=(float(r[6]) if r[6] is not None else None)) for r in rows]


def _activity_list(conn, item_id: int) -> list[EvidenceActivityOut]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EvidenceActivityEventID","EventType","Actor","Detail","CreatedAt" '
            'FROM "EvidenceActivityEvent" WHERE "EvidenceItemID"=%s '
            'ORDER BY "EvidenceActivityEventID"', (item_id,))
        rows = cur.fetchall()
    return [EvidenceActivityOut(
        evidence_activity_event_id=int(r[0]), event_type=r[1], actor=r[2],
        detail=r[3] or {}, created_at=_s(r[4])) for r in rows]


def _serialize_item(conn, item_id: int) -> EvidenceItemOut:
    row = _item_row(conn, item_id)
    if row is None:
        raise EvidenceNotFound(f"Evidence item {item_id} not found.")
    (eid, case_id, ssid, _srid, etype, category, title, desc, ref, lang, tags,
     uploader, conf, state, meta, cap, recv, up, created, updated, is_synthetic) = row
    objects = _objects(conn, item_id)
    current = next((o for o in objects if o.is_current), None)
    return EvidenceItemOut(
        evidence_item_id=int(eid), case_master_id=case_id, crime_no=_crime_no(conn, case_id),
        source_system_id=ssid, evidence_type=etype, category=category, title=title,
        description=desc, synthetic_reference=ref, language=lang, tags=list(tags or []),
        uploader_actor=uploader, confidentiality=conf, state=state,
        is_synthetic=bool(is_synthetic), is_read_only=_is_curated_reference(row),
        manual_metadata=meta or {},
        captured_at=_s(cap), received_at=_s(recv), uploaded_at=_s(up),
        created_at=_s(created), updated_at=_s(updated),
        current_object=current, objects=objects, versions=_versions(conn, item_id),
        case_links=_case_links(conn, item_id), entity_links=_entity_links(conn, item_id),
        activity=_activity_list(conn, item_id),
        is_previewable=_previewable(current.mime_type) if current else False)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def _default_ref(conn) -> str:
    return "SYN-EV-UI-" + uuid.uuid4().hex[:10].upper()


def _create_item(conn, req: EvidenceCreateRequest) -> tuple[int, Optional[str]]:
    if req.evidence_type not in ALLOWED_EVIDENCE_TYPES:
        raise EvidenceValidationError(
            f"Unknown evidence type '{req.evidence_type}'.",
            detail={"allowed": sorted(ALLOWED_EVIDENCE_TYPES)})
    if req.confidentiality not in CONFIDENTIALITIES:
        raise EvidenceValidationError(
            f"Unknown confidentiality '{req.confidentiality}'.",
            detail={"allowed": sorted(CONFIDENTIALITIES)})
    if not req.title or not req.title.strip():
        raise EvidenceValidationError("Evidence title is required.")
    if req.case_id is not None and not _case_exists(conn, req.case_id):
        raise EvidenceValidationError(f"Case {req.case_id} does not exist.")
    if req.canonical_entity_id is not None and not _entity_exists(conn, req.canonical_entity_id):
        raise EvidenceValidationError(f"Canonical entity {req.canonical_entity_id} does not exist.")

    # Idempotency: reuse a prior item created with the same key.
    if req.idempotency_key:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "EvidenceItemID" FROM "EvidenceItem" '
                "WHERE \"ManualMetadata\"->>'idempotency_key' = %s LIMIT 1",
                (req.idempotency_key,))
            r = cur.fetchone()
        if r:
            return int(r[0]), None

    ssid = _source_system_id(conn, req.source_system_code)
    ref = (req.synthetic_reference or "").strip() or _default_ref(conn)
    # No-file evidence (external reference / physical-world) is 'available' at
    # once; file-backed evidence stays 'draft' until an upload completes.
    no_file = req.metadata_only or req.evidence_type in NO_FILE_TYPES
    state = "available" if no_file else "draft"
    tags = sorted({t.strip() for t in (req.tags or []) if t and t.strip()})
    meta: dict[str, Any] = {"manual": True, "entered_by": req.uploader_actor}
    if req.notes:
        meta["notes"] = req.notes
    if req.external_reference_url:
        meta["external_reference_url"] = req.external_reference_url
    if req.idempotency_key:
        meta["idempotency_key"] = req.idempotency_key
    if no_file:
        meta["metadata_only"] = True

    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "EvidenceItem" ("CaseMasterID","SourceSystemID","EvidenceType","Category",'
            '"Title","Description","SyntheticReference","Language","Tags","UploaderActor",'
            '"Confidentiality","State","ManualMetadata","CapturedAt","ReceivedAt","IsSynthetic") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING "EvidenceItemID"',
            (req.case_id, ssid, req.evidence_type, req.category, req.title.strip(),
             req.description, ref, req.language, tags, req.uploader_actor,
             req.confidentiality, state, Json(meta), req.captured_at, req.received_at))
        item_id = int(cur.fetchone()[0])
        if req.case_id is not None:
            cur.execute(
                'INSERT INTO "EvidenceCaseLink" ("EvidenceItemID","CaseMasterID","LinkType","CreatedByActor") '
                'VALUES (%s,%s,%s,%s) ON CONFLICT ("EvidenceItemID","CaseMasterID") DO NOTHING',
                (item_id, req.case_id, "evidence", req.uploader_actor))
        if req.canonical_entity_id is not None:
            cur.execute(
                'INSERT INTO "EvidenceEntityLink" ("EvidenceItemID","CanonicalEntityID","LinkType",'
                '"ReviewStatus") VALUES (%s,%s,%s,%s) '
                'ON CONFLICT ("EvidenceItemID","CanonicalEntityID","LinkType") DO NOTHING',
                (item_id, req.canonical_entity_id, "mentions", "reviewed"))
    _activity(conn, item_id, _EVENT_CREATED, req.uploader_actor,
              {"evidence_type": req.evidence_type, "case_id": req.case_id,
               "metadata_only": no_file})
    audit.record(audit.Action.CREATE, "evidence_item", item_id, actor=req.uploader_actor,
                 conn=conn, detail={"evidence_type": req.evidence_type, "case_id": req.case_id})
    return item_id, None


# ---------------------------------------------------------------------------
# Metadata correction
# ---------------------------------------------------------------------------
_EDITABLE = {
    "evidence_type": '"EvidenceType"', "category": '"Category"', "title": '"Title"',
    "description": '"Description"', "synthetic_reference": '"SyntheticReference"',
    "captured_at": '"CapturedAt"', "received_at": '"ReceivedAt"', "language": '"Language"',
    "confidentiality": '"Confidentiality"',
}


def _update_metadata(conn, item_id: int, patch: EvidenceMetadataUpdate) -> None:
    row = _item_row(conn, item_id)
    if row is None:
        raise EvidenceNotFound(f"Evidence item {item_id} not found.")
    _require_mutable_reference(row, "edit its source-qualified metadata")
    if row[13] == "archived":
        raise EvidenceConflict("Archived evidence cannot be edited. Restore it first.")
    if patch.evidence_type is not None and patch.evidence_type not in ALLOWED_EVIDENCE_TYPES:
        raise EvidenceValidationError(f"Unknown evidence type '{patch.evidence_type}'.")
    if patch.confidentiality is not None and patch.confidentiality not in CONFIDENTIALITIES:
        raise EvidenceValidationError(f"Unknown confidentiality '{patch.confidentiality}'.")
    if patch.title is not None and not patch.title.strip():
        raise EvidenceValidationError("Title cannot be blank.")

    sets, params, changed = [], [], {}
    for field_name, col in _EDITABLE.items():
        val = getattr(patch, field_name)
        if val is not None:
            v = val.strip() if isinstance(val, str) else val
            sets.append(f'{col} = %s')
            params.append(v)
            changed[field_name] = v
    if patch.tags is not None:
        tags = sorted({t.strip() for t in patch.tags if t and t.strip()})
        sets.append('"Tags" = %s')
        params.append(tags)
        changed["tags"] = tags
    if patch.notes is not None:
        sets.append('"ManualMetadata" = jsonb_set("ManualMetadata", \'{notes}\', %s::jsonb, true)')
        params.append(Json(patch.notes))
        changed["notes"] = True
    if not sets:
        raise EvidenceValidationError("No metadata fields supplied to correct.")
    params.append(item_id)
    with conn.cursor() as cur:
        cur.execute(f'UPDATE "EvidenceItem" SET {", ".join(sets)} WHERE "EvidenceItemID"=%s', params)
    _activity(conn, item_id, _EVENT_META, patch.actor,
              {"fields": sorted(changed.keys()), "change_reason": patch.change_reason})
    audit.record(audit.Action.UPDATE, "evidence_item", item_id, actor=patch.actor,
                 conn=conn, detail={"fields": sorted(changed.keys())})


# ---------------------------------------------------------------------------
# Upload URL + completion (S3)
# ---------------------------------------------------------------------------
def _next_version(conn, item_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT COALESCE(MAX("VersionNo"),0) FROM "EvidenceObject" WHERE "EvidenceItemID"=%s',
                    (item_id,))
        return int(cur.fetchone()[0]) + 1


def _issue_upload_url(conn, item_id: int, req: UploadUrlRequest, gw: S3Gateway) -> UploadUrlResponse:
    row = _item_row(conn, item_id)
    if row is None:
        raise EvidenceNotFound(f"Evidence item {item_id} not found.")
    _require_mutable_reference(row, "attach a file")
    _require_file_backed(row)
    if row[13] == "archived":
        raise EvidenceConflict("Archived evidence cannot receive a new upload.")
    _validate_upload(req.file_name, req.mime_type, req.size_bytes)
    case_id, ref = row[1], row[8]
    version_no = _next_version(conn, item_id)
    s = get_settings()
    key = s3.build_object_key(s.s3_evidence_prefix, case_id, ref or f"item-{item_id}",
                              version_no, req.file_name)
    presigned = gw.presign_put(key, s.s3_presign_expiry_s)
    with conn.cursor() as cur:
        cur.execute('UPDATE "EvidenceItem" SET "State"=\'uploading\' WHERE "EvidenceItemID"=%s '
                    "AND \"State\" <> 'archived'", (item_id,))
    _activity(conn, item_id, _EVENT_UPLOAD_URL, req.actor,
              {"version_no": version_no, "file_name": req.file_name,
               "size_bytes": req.size_bytes})
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=s.s3_presign_expiry_s)).isoformat()
    return UploadUrlResponse(
        evidence_item_id=item_id, version_no=version_no, storage_key=key,
        upload_url=presigned.url, method=presigned.method, headers=presigned.headers,
        expires_in=s.s3_presign_expiry_s, expires_at=expires_at, max_bytes=s.evidence_max_bytes)


def _mark_failed(conn, item_id: int, reason: str, actor: Optional[str]) -> None:
    with conn.cursor() as cur:
        cur.execute('UPDATE "EvidenceItem" SET "State"=\'failed\' WHERE "EvidenceItemID"=%s '
                    "AND \"State\" <> 'archived'", (item_id,))
    _activity(conn, item_id, _EVENT_FAILED, actor, {"reason": reason[:300]})


def _complete_upload(conn, item_id: int, req: CompleteUploadRequest,
                     gw: S3Gateway) -> CompleteUploadResponse:
    row = _item_row(conn, item_id)
    if row is None:
        raise EvidenceNotFound(f"Evidence item {item_id} not found.")
    _require_mutable_reference(row, "complete a file upload")
    _require_file_backed(row)
    if row[13] == "archived":
        raise EvidenceConflict("Archived evidence cannot be completed.")
    s = get_settings()
    # storage key must stay inside our prefix (never complete an arbitrary object)
    if not s3.key_in_prefix(req.storage_key, s.s3_evidence_prefix):
        raise EvidenceValidationError("Storage key is outside the evidence prefix.")
    _validate_upload(req.file_name, req.mime_type, req.size_bytes)

    # 1. object must exist + declared size must match what S3 stored
    try:
        head = gw.head(req.storage_key)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(conn, item_id, f"storage head failed: {type(exc).__name__}", req.actor)
        raise EvidenceValidationError("Could not verify the uploaded object in storage.")
    if not head.exists:
        _mark_failed(conn, item_id, "object missing after upload", req.actor)
        raise EvidenceValidationError(
            "Uploaded object was not found in storage (upload did not complete).",
            detail={"code": "missing_object"})
    if head.size is not None and int(head.size) != int(req.size_bytes):
        _mark_failed(conn, item_id, "size mismatch", req.actor)
        raise EvidenceValidationError(
            f"Stored object size ({head.size}) does not match the declared size "
            f"({req.size_bytes}) — the upload looks corrupt/partial.",
            detail={"code": "size_mismatch"})
    if head.size is not None and int(head.size) > s.evidence_max_bytes:
        _mark_failed(conn, item_id, "over size cap", req.actor)
        raise EvidenceValidationError("Stored object exceeds the size limit.")

    # 2. server-side SHA-256 verification (bounded read)
    computed = None
    if (head.size or 0) <= s.evidence_hash_verify_max_bytes:
        try:
            data = gw.get_bytes(req.storage_key, s.evidence_hash_verify_max_bytes)
        except ObjectNotFound:
            _mark_failed(conn, item_id, "object missing on read", req.actor)
            raise EvidenceValidationError("Uploaded object was not found in storage.")
        except Exception as exc:  # noqa: BLE001
            _mark_failed(conn, item_id, f"read failed: {type(exc).__name__}", req.actor)
            raise EvidenceValidationError("Could not read the uploaded object to verify its hash.")
        computed = hashlib.sha256(data).hexdigest()
        if req.sha256 and req.sha256.lower() != computed:
            _mark_failed(conn, item_id, "hash mismatch", req.actor)
            raise EvidenceValidationError(
                "Uploaded content hash does not match the declared SHA-256 "
                "(content may be corrupt).", detail={"code": "hash_mismatch"})
    sha = (computed or (req.sha256 or "").lower())
    if not sha:
        _mark_failed(conn, item_id, "no hash", req.actor)
        raise EvidenceValidationError("Could not determine a SHA-256 for the object.")

    # 3. duplicate-hash warning (non-blocking): same content already stored?
    with conn.cursor() as cur:
        cur.execute(
            'SELECT DISTINCT "EvidenceItemID" FROM "EvidenceObject" '
            'WHERE "Sha256"=%s AND "EvidenceItemID" <> %s LIMIT 5', (sha, item_id))
        dup_ids = [int(r[0]) for r in cur.fetchall()]
    dup_warning = (f"Identical content (same SHA-256) already exists on "
                   f"{len(dup_ids)} other evidence item(s).") if dup_ids else None

    version_no = req.version_no or _next_version(conn, item_id)
    with conn.cursor() as cur:
        # new version becomes current; demote the previous current object
        cur.execute('UPDATE "EvidenceObject" SET "IsCurrent"=FALSE WHERE "EvidenceItemID"=%s', (item_id,))
        cur.execute(
            'INSERT INTO "EvidenceObject" ("EvidenceItemID","StorageKey","StorageStatus","FileName",'
            '"MimeType","SizeBytes","Sha256","VersionNo","IsCurrent","ManualProvenance") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s) RETURNING "EvidenceObjectID"',
            (item_id, req.storage_key, "available", req.file_name, req.mime_type,
             int(head.size if head.size is not None else req.size_bytes), sha, version_no,
             Json({"manual_provenance": True, "hash_algo": "sha256",
                   "hash_verified": computed is not None})))
        object_id = int(cur.fetchone()[0])
        cur.execute(
            'INSERT INTO "EvidenceVersion" ("EvidenceItemID","VersionNo","EvidenceObjectID",'
            '"ChangeReason","CreatedByActor") VALUES (%s,%s,%s,%s,%s) '
            'ON CONFLICT ("EvidenceItemID","VersionNo") DO NOTHING',
            (item_id, version_no, object_id,
             req.change_reason or ("initial upload" if version_no == 1 else "file version replacement"),
             req.actor))
        cur.execute('UPDATE "EvidenceItem" SET "State"=\'available\', "UploadedAt"=now() '
                    'WHERE "EvidenceItemID"=%s', (item_id,))
    event = _EVENT_UPLOADED if version_no == 1 else _EVENT_VERSION
    _activity(conn, item_id, event, req.actor,
              {"version_no": version_no, "sha256": sha, "size_bytes": head.size,
               "file_name": req.file_name, "duplicate": bool(dup_ids)})
    audit.record(audit.Action.EVIDENCE_UPLOAD, "evidence_item", item_id, actor=req.actor,
                 conn=conn, detail={"version_no": version_no, "object_id": object_id,
                                    "size_bytes": head.size})
    item = _serialize_item(conn, item_id)
    return CompleteUploadResponse(
        item=item, evidence_object_id=object_id, version_no=version_no, sha256=sha,
        size_bytes=int(head.size if head.size is not None else req.size_bytes),
        duplicate_warning=dup_warning, duplicate_of_item_ids=dup_ids)


# ---------------------------------------------------------------------------
# Download URL
# ---------------------------------------------------------------------------
def _download_url(conn, item_id: int, version_no: Optional[int],
                  actor: Optional[str], gw: S3Gateway,
                  disposition: str = "attachment") -> DownloadUrlResponse:
    with conn.cursor() as cur:
        if version_no is not None:
            cur.execute(
                'SELECT "EvidenceObjectID","VersionNo","FileName","MimeType","StorageKey","StorageStatus" '
                'FROM "EvidenceObject" WHERE "EvidenceItemID"=%s AND "VersionNo"=%s', (item_id, version_no))
        else:
            cur.execute(
                'SELECT "EvidenceObjectID","VersionNo","FileName","MimeType","StorageKey","StorageStatus" '
                'FROM "EvidenceObject" WHERE "EvidenceItemID"=%s AND "IsCurrent" LIMIT 1', (item_id,))
        r = cur.fetchone()
    if r is None:
        if _item_row(conn, item_id) is None:
            raise EvidenceNotFound(f"Evidence item {item_id} not found.")
        raise EvidenceNotFound("No stored file for this evidence item/version.")
    object_id, ver, file_name, mime, key, storage_status = int(r[0]), int(r[1]), r[2], r[3], r[4], r[5]
    if not key or storage_status != "available":
        raise EvidenceConflict("This evidence object is not available for download.")
    s = get_settings()
    url = gw.presign_get(key, filename=file_name, content_type=mime,
                         expires_in=s.s3_presign_expiry_s, disposition=disposition)
    _activity(conn, item_id, _EVENT_DOWNLOAD, actor,
              {"version_no": ver, "object_id": object_id, "disposition": disposition})
    audit.record(audit.Action.EVIDENCE_DOWNLOAD, "evidence_item", item_id, actor=actor,
                 conn=conn, detail={"version_no": ver, "object_id": object_id})
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=s.s3_presign_expiry_s)).isoformat()
    return DownloadUrlResponse(
        evidence_item_id=item_id, evidence_object_id=object_id, version_no=ver,
        file_name=file_name, mime_type=mime, url=url,
        expires_in=s.s3_presign_expiry_s, expires_at=expires_at)


# ---------------------------------------------------------------------------
# Link / unlink / archive / restore
# ---------------------------------------------------------------------------
def _link(conn, item_id: int, req: LinkRequest) -> None:
    row = _item_row(conn, item_id)
    if row is None:
        raise EvidenceNotFound(f"Evidence item {item_id} not found.")
    _require_mutable_reference(row, "change its governed links")
    if not req.case_id and not req.canonical_entity_id:
        raise EvidenceValidationError("Provide a case_id or canonical_entity_id to link.")
    with conn.cursor() as cur:
        if req.case_id:
            if not _case_exists(conn, req.case_id):
                raise EvidenceValidationError(f"Case {req.case_id} does not exist.")
            cur.execute(
                'INSERT INTO "EvidenceCaseLink" ("EvidenceItemID","CaseMasterID","LinkType","CreatedByActor") '
                'VALUES (%s,%s,%s,%s) ON CONFLICT ("EvidenceItemID","CaseMasterID") DO NOTHING',
                (item_id, req.case_id, req.link_type or "evidence", req.actor))
        if req.canonical_entity_id:
            if not _entity_exists(conn, req.canonical_entity_id):
                raise EvidenceValidationError(f"Canonical entity {req.canonical_entity_id} does not exist.")
            cur.execute(
                'INSERT INTO "EvidenceEntityLink" ("EvidenceItemID","CanonicalEntityID","LinkType","ReviewStatus") '
                'VALUES (%s,%s,%s,%s) ON CONFLICT ("EvidenceItemID","CanonicalEntityID","LinkType") DO NOTHING',
                (item_id, req.canonical_entity_id, req.link_type or "mentions", "reviewed"))
    _activity(conn, item_id, _EVENT_LINKED, req.actor,
              {"case_id": req.case_id, "canonical_entity_id": req.canonical_entity_id})
    audit.record(audit.Action.ENTITY_CHANGE, "evidence_item", item_id, actor=req.actor,
                 conn=conn, detail={"link_case_id": req.case_id,
                                    "link_entity_id": req.canonical_entity_id})


def _unlink(conn, item_id: int, case_id: Optional[int], entity_id: Optional[int],
            actor: Optional[str]) -> None:
    row = _item_row(conn, item_id)
    if row is None:
        raise EvidenceNotFound(f"Evidence item {item_id} not found.")
    _require_mutable_reference(row, "change its governed links")
    if not case_id and not entity_id:
        raise EvidenceValidationError("Provide a case_id or canonical_entity_id to unlink.")
    with conn.cursor() as cur:
        if case_id:
            cur.execute('DELETE FROM "EvidenceCaseLink" WHERE "EvidenceItemID"=%s AND "CaseMasterID"=%s',
                        (item_id, case_id))
        if entity_id:
            cur.execute('DELETE FROM "EvidenceEntityLink" WHERE "EvidenceItemID"=%s AND "CanonicalEntityID"=%s',
                        (item_id, entity_id))
    _activity(conn, item_id, _EVENT_UNLINKED, actor,
              {"case_id": case_id, "canonical_entity_id": entity_id})
    audit.record(audit.Action.ENTITY_CHANGE, "evidence_item", item_id, actor=actor,
                 conn=conn, detail={"unlink_case_id": case_id, "unlink_entity_id": entity_id})


def _archive(conn, item_id: int, req: ArchiveRequest) -> None:
    row = _item_row(conn, item_id)
    if row is None:
        raise EvidenceNotFound(f"Evidence item {item_id} not found.")
    _require_mutable_reference(row, "archive it")
    if row[13] == "archived":
        raise EvidenceConflict("Evidence item is already archived.")
    with conn.cursor() as cur:
        cur.execute('UPDATE "EvidenceItem" SET "State"=\'archived\' WHERE "EvidenceItemID"=%s', (item_id,))
    _activity(conn, item_id, _EVENT_ARCHIVED, req.actor, {"reason": req.reason})
    audit.record(audit.Action.UPDATE, "evidence_item", item_id, actor=req.actor,
                 conn=conn, detail={"action": "archive"})


def _restore(conn, item_id: int, actor: Optional[str]) -> None:
    row = _item_row(conn, item_id)
    if row is None:
        raise EvidenceNotFound(f"Evidence item {item_id} not found.")
    _require_mutable_reference(row, "restore it")
    if row[13] != "archived":
        raise EvidenceConflict("Only an archived item can be restored.")
    # Restore to 'available' if it has a current object, else 'draft'.
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM "EvidenceObject" WHERE "EvidenceItemID"=%s AND "IsCurrent" LIMIT 1',
                    (item_id,))
        has_object = cur.fetchone() is not None
        new_state = "available" if (has_object or (row[14] or {}).get("metadata_only")) else "draft"
        cur.execute('UPDATE "EvidenceItem" SET "State"=%s WHERE "EvidenceItemID"=%s', (new_state, item_id))
    _activity(conn, item_id, _EVENT_RESTORED, actor, {"to_state": new_state})
    audit.record(audit.Action.UPDATE, "evidence_item", item_id, actor=actor,
                 conn=conn, detail={"action": "restore"})


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------
def _list(conn, *, case_id: Optional[int], evidence_type: Optional[str],
          state: Optional[str], q: Optional[str], page: int, page_size: int) -> EvidenceListResponse:
    clauses, params = [], []
    if case_id is not None:
        clauses.append('ei."CaseMasterID" = %s'); params.append(case_id)
    if evidence_type:
        clauses.append('ei."EvidenceType" = %s'); params.append(evidence_type)
    if state:
        clauses.append('ei."State" = %s'); params.append(state)
    if q and q.strip():
        clauses.append('(ei."Title" ILIKE %s OR ei."SyntheticReference" ILIKE %s)')
        like = f"%{q.strip()}%"; params += [like, like]
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "EvidenceItem" ei{where}', params)
        total = int(cur.fetchone()[0])
        # state histogram (same filter, minus state) for the UI tabs
        hist_clauses = [c for c in clauses if not c.startswith('ei."State"')]
        hist_params = [p for c, p in zip(clauses, params) if not c.startswith('ei."State"')] if False else None
        # simpler: recompute histogram with case/type/q filters only
        hclauses, hparams = [], []
        if case_id is not None:
            hclauses.append('"CaseMasterID" = %s'); hparams.append(case_id)
        if evidence_type:
            hclauses.append('"EvidenceType" = %s'); hparams.append(evidence_type)
        if q and q.strip():
            hclauses.append('("Title" ILIKE %s OR "SyntheticReference" ILIKE %s)')
            hparams += [f"%{q.strip()}%", f"%{q.strip()}%"]
        hwhere = (" WHERE " + " AND ".join(hclauses)) if hclauses else ""
        cur.execute(f'SELECT "State", COUNT(*) FROM "EvidenceItem"{hwhere} GROUP BY "State"', hparams)
        by_state = {r[0]: int(r[1]) for r in cur.fetchall()}
        cur.execute(
            f'SELECT ei."EvidenceItemID", ei."CaseMasterID", ei."EvidenceType", ei."Category",'
            f' ei."Title", ei."SyntheticReference", ei."State", ei."Language", ei."Tags",'
            f' ei."CapturedAt", ei."CreatedAt", ei."UpdatedAt", ss."Code",'
            f' obj."VersionNo", obj."Sha256", obj."FileName", obj."MimeType", obj."SizeBytes",'
            f' ei."IsSynthetic", ei."ManualMetadata" '
            f'FROM "EvidenceItem" ei '
            f'LEFT JOIN "SourceSystem" ss ON ss."SourceSystemID" = ei."SourceSystemID" '
            f'LEFT JOIN LATERAL (SELECT "VersionNo","Sha256","FileName","MimeType","SizeBytes" '
            f'  FROM "EvidenceObject" o WHERE o."EvidenceItemID"=ei."EvidenceItemID" AND o."IsCurrent" '
            f'  ORDER BY o."VersionNo" DESC LIMIT 1) obj ON TRUE'
            f'{where} ORDER BY ei."CreatedAt" DESC, ei."EvidenceItemID" DESC LIMIT %s OFFSET %s',
            params + [page_size, offset])
        rows = cur.fetchall()
    items = [EvidenceListItem(
        evidence_item_id=int(r[0]), case_master_id=r[1], evidence_type=r[2], category=r[3],
        title=r[4], synthetic_reference=r[5], state=r[6], language=r[7], tags=list(r[8] or []),
        captured_at=_s(r[9]), created_at=_s(r[10]), updated_at=_s(r[11]), source_label=r[12],
        version_no=r[13], sha256=r[14], file_name=r[15], mime_type=r[16], size_bytes=r[17],
        is_synthetic=bool(r[18]),
        is_read_only=(
            not bool(r[18]) and isinstance(r[19], dict)
            and r[19].get("record_origin") == "public_source_curated"
            and r[19].get("metadata_only") is True
        ))
        for r in rows]
    return EvidenceListResponse(items=items, total=total, page=page, page_size=page_size,
                                by_state=by_state)


# ---------------------------------------------------------------------------
# Legacy migration (CaseEvidence -> EvidenceItem)
# ---------------------------------------------------------------------------
_LEGACY_TYPE_MAP = {
    "note": "document", "attachment": "document", "statement": "statement",
    "seizure": "property_item", "exhibit": "physical_exhibit",
}


def _migrate_legacy(conn, case_id: Optional[int], actor: Optional[str]) -> MigrateLegacyResponse:
    # CaseEvidence may not exist / be empty; treat gracefully.
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.\"CaseEvidence\"')")
        if cur.fetchone()[0] is None:
            return MigrateLegacyResponse(scanned=0, migrated=0, skipped_existing=0)
        where, params = "", []
        if case_id is not None:
            where = ' WHERE "CaseMasterID" = %s'; params = [case_id]
        cur.execute(f'SELECT "EvidenceID","CaseMasterID","EvidenceType","Title","Description",'
                    f'"Reference","CreatedByRole","CreatedAt" FROM "CaseEvidence"{where} '
                    f'ORDER BY "EvidenceID"', params)
        legacy = cur.fetchall()

    scanned = len(legacy)
    migrated, skipped, ids = 0, 0, []
    for (leg_id, cmid, ltype, title, desc, ref, role, created) in legacy:
        marker = f"CaseEvidence:{leg_id}"
        with conn.cursor() as cur:
            cur.execute("SELECT \"EvidenceItemID\" FROM \"EvidenceItem\" "
                        "WHERE \"ManualMetadata\"->>'legacy_ref' = %s LIMIT 1", (marker,))
            if cur.fetchone():
                skipped += 1
                continue
            etype = _LEGACY_TYPE_MAP.get((ltype or "note").lower(), "document")
            meta = {"manual": True, "migrated_from": "CaseEvidence", "legacy_ref": marker,
                    "legacy_type": ltype, "legacy_reference": ref, "entered_by": role}
            cur.execute(
                'INSERT INTO "EvidenceItem" ("CaseMasterID","EvidenceType","Category","Title",'
                '"Description","SyntheticReference","Language","Tags","UploaderActor",'
                '"Confidentiality","State","ManualMetadata","IsSynthetic") '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING "EvidenceItemID"',
                (cmid, etype, "legacy", (title or "Untitled legacy evidence"), desc,
                 (ref or f"LEGACY-{leg_id}"), "en", ["legacy_migrated"], role,
                 "demo_normal", "available", Json(meta)))
            new_id = int(cur.fetchone()[0])
            if cmid is not None:
                cur.execute(
                    'INSERT INTO "EvidenceCaseLink" ("EvidenceItemID","CaseMasterID","LinkType","CreatedByActor") '
                    'VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING', (new_id, cmid, "evidence", role))
        _activity(conn, new_id, _EVENT_CREATED, actor,
                  {"migrated_from": "CaseEvidence", "legacy_ref": marker})
        migrated += 1
        ids.append(new_id)
    if migrated:
        audit.record(audit.Action.IMPORT, "evidence_item", None, actor=actor, conn=conn,
                     detail={"migrated_from": "CaseEvidence", "count": migrated})
    return MigrateLegacyResponse(scanned=scanned, migrated=migrated,
                                 skipped_existing=skipped, item_ids=ids)


# ---------------------------------------------------------------------------
# Synthetic-demo reset (admin only)
# ---------------------------------------------------------------------------
def _reset_case(conn, case_id: int, actor: Optional[str], gw: Optional[S3Gateway]) -> ResetResponse:
    # gather S3 keys to delete, then delete rows (cascade removes objects/versions/
    # activity/links). Only touches synthetic data for one case.
    with conn.cursor() as cur:
        cur.execute(
            'SELECT o."StorageKey" FROM "EvidenceObject" o '
            'JOIN "EvidenceItem" ei ON ei."EvidenceItemID"=o."EvidenceItemID" '
            'WHERE ei."CaseMasterID"=%s AND ei."IsSynthetic"=TRUE '
            'AND o."StorageKey" IS NOT NULL', (case_id,))
        keys = [r[0] for r in cur.fetchall()]

    deleted_objs = 0
    if gw is not None:
        for k in keys:
            if k and s3.key_in_prefix(k, get_settings().s3_evidence_prefix):
                try:
                    gw.delete(k)
                    deleted_objs += 1
                except Exception:  # noqa: BLE001 — best effort on synthetic demo objects
                    pass
    with conn.cursor() as cur:
        cur.execute('DELETE FROM "EvidenceItem" WHERE "CaseMasterID"=%s '
                    'AND "IsSynthetic"=TRUE', (case_id,))
        removed = cur.rowcount
    audit.record(audit.Action.DELETE, "evidence_case_reset", case_id, actor=actor, conn=conn,
                 detail={"items_deleted": removed, "objects_deleted": deleted_objs})
    return ResetResponse(case_master_id=case_id, items_deleted=int(removed),
                         objects_deleted_in_storage=deleted_objs, ok=True)


# ===========================================================================
# Public API (open connections; rw_conn commits on clean exit)
# ===========================================================================
def create_item(req: EvidenceCreateRequest) -> CreateResponse:
    with db.rw_conn() as conn:
        item_id, warn = _create_item(conn, req)
        item = _serialize_item(conn, item_id)
    return CreateResponse(item=item, duplicate_warning=warn)


def get_item(item_id: int) -> EvidenceItemOut:
    with db.ro_conn() as conn:
        return _serialize_item(conn, item_id)


def update_metadata(item_id: int, patch: EvidenceMetadataUpdate) -> EvidenceItemOut:
    with db.rw_conn() as conn:
        _update_metadata(conn, item_id, patch)
        return _serialize_item(conn, item_id)


def issue_upload_url(item_id: int, req: UploadUrlRequest,
                     gw: Optional[S3Gateway] = None) -> UploadUrlResponse:
    with db.rw_conn() as conn:
        return _issue_upload_url(conn, item_id, req, _gw(gw))


def complete_upload(item_id: int, req: CompleteUploadRequest,
                    gw: Optional[S3Gateway] = None) -> CompleteUploadResponse:
    with db.rw_conn() as conn:
        return _complete_upload(conn, item_id, req, _gw(gw))


def download_url(item_id: int, version_no: Optional[int], actor: Optional[str],
                 gw: Optional[S3Gateway] = None,
                 disposition: str = "attachment") -> DownloadUrlResponse:
    with db.rw_conn() as conn:
        return _download_url(conn, item_id, version_no, actor, _gw(gw), disposition)


def link(item_id: int, req: LinkRequest) -> EvidenceItemOut:
    with db.rw_conn() as conn:
        _link(conn, item_id, req)
        return _serialize_item(conn, item_id)


def unlink(item_id: int, case_id: Optional[int], entity_id: Optional[int],
           actor: Optional[str]) -> EvidenceItemOut:
    with db.rw_conn() as conn:
        _unlink(conn, item_id, case_id, entity_id, actor)
        return _serialize_item(conn, item_id)


def archive(item_id: int, req: ArchiveRequest) -> EvidenceItemOut:
    with db.rw_conn() as conn:
        _archive(conn, item_id, req)
        return _serialize_item(conn, item_id)


def restore(item_id: int, actor: Optional[str]) -> EvidenceItemOut:
    with db.rw_conn() as conn:
        _restore(conn, item_id, actor)
        return _serialize_item(conn, item_id)


def list_items(*, case_id: Optional[int], evidence_type: Optional[str], state: Optional[str],
               q: Optional[str], page: int, page_size: int) -> EvidenceListResponse:
    with db.ro_conn() as conn:
        return _list(conn, case_id=case_id, evidence_type=evidence_type, state=state,
                     q=q, page=page, page_size=page_size)


def migrate_legacy(case_id: Optional[int], actor: Optional[str]) -> MigrateLegacyResponse:
    with db.rw_conn() as conn:
        return _migrate_legacy(conn, case_id, actor)


def reset_case(case_id: int, actor: Optional[str],
               gw: Optional[S3Gateway] = None) -> ResetResponse:
    use_gw = gw
    if use_gw is None and get_settings().s3_configured():
        try:
            use_gw = s3.get_gateway()
        except Exception:  # noqa: BLE001
            use_gw = None
    with db.rw_conn() as conn:
        return _reset_case(conn, case_id, actor, use_gw)
