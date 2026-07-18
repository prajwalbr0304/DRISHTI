"""Import service — the Phase-8 pipeline.

Design mirrors intake/casework: internal ``_fn(conn, ...)`` helpers do the work on
an OPEN connection and never commit (so tests drive the full create->commit->
rollback path inside the rw_rollback fixture and discard it); public wrappers open
db.rw_conn()/ro_conn().

Pipeline: upload source file as evidence -> select template version -> parse into
STAGING only -> dry-run report -> approve commit -> one SourceRecord per canonical
row -> resolve phones/accounts/devices as CANDIDATE entity links (never
auto-confirmed). Idempotent (IdempotencyKey), retry-safe, partial errors,
rollback and supersession.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from psycopg2.extras import Json

from .. import audit, db
from . import parse as P
from . import templates as T


# ---------------------------------------------------------------------------
# Typed errors (router translates to HTTP)
# ---------------------------------------------------------------------------
class ImportError(Exception):
    pass


class ImportNotFound(ImportError):
    pass


class ImportConflict(ImportError):
    pass


class ImportValidationError(ImportError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s(v) -> Optional[str]:
    return str(v) if v is not None else None


# Digital target tables carry a physical ImportBatchID column (migration 015);
# financial ones do too. Used for rollback + provenance.
_BATCH_COLUMN_TABLES = (
    "CommunicationEvent", "LocationObservation", "DeviceArtifact", "Device",
    "FinancialTransaction", "FinancialAccount", "EvidenceEntityLink",
)


# ---------------------------------------------------------------------------
# Reference lookups
# ---------------------------------------------------------------------------
def _source_system_id(conn, code: str) -> Optional[int]:
    with conn.cursor() as cur:
        cur.execute('SELECT "SourceSystemID" FROM "SourceSystem" WHERE "Code"=%s', (code,))
        r = cur.fetchone()
    return int(r[0]) if r else None


def _domain_source_system(conn, domain: str) -> Optional[int]:
    financial = {"bank_txn", "account_kyc", "wallet_upi"}
    code = "FINANCIAL_IMPORT" if domain in financial else "DIGITAL_IMPORT"
    return _source_system_id(conn, code) or _source_system_id(conn, "CSV_IMPORT")


def _template_version(conn, tvid: int) -> Optional[dict]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT v."ImportTemplateVersionID", v."Version", v."Status", v."ColumnMapping",'
            ' v."RequiredColumns", v."DedupeKeys", t."ImportTemplateID", t."Code", t."Domain",'
            ' t."TargetTable" '
            'FROM "ImportTemplateVersion" v '
            'JOIN "ImportTemplate" t ON t."ImportTemplateID"=v."ImportTemplateID" '
            'WHERE v."ImportTemplateVersionID"=%s', (tvid,))
        r = cur.fetchone()
    if not r:
        return None
    return {"tvid": int(r[0]), "version": r[1], "status": r[2], "mapping": r[3] or {},
            "required": r[4] or [], "dedupe_keys": r[5] or [], "template_id": int(r[6]),
            "code": r[7], "domain": r[8], "target_table": r[9]}


# ---------------------------------------------------------------------------
# Templates (read)
# ---------------------------------------------------------------------------
def list_templates() -> dict:
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "ImportTemplateID","Code","Name","Domain","TargetTable","Description" '
                'FROM "ImportTemplate" ORDER BY "Domain","Code"')
            tpls = cur.fetchall()
            cur.execute(
                'SELECT "ImportTemplateVersionID","ImportTemplateID","Version","Status",'
                '"ColumnMapping","RequiredColumns","DedupeKeys","Notes" '
                'FROM "ImportTemplateVersion" ORDER BY "ImportTemplateID","Version"')
            vers = cur.fetchall()
    by_tpl: dict[int, list] = {}
    for v in vers:
        by_tpl.setdefault(int(v[1]), []).append({
            "import_template_version_id": int(v[0]), "version": v[2], "status": v[3],
            "target_table": (v[4] or {}).get("target_table"),
            "fields": (v[4] or {}).get("fields", []),
            "required_columns": v[5] or [], "dedupe_keys": v[6] or [], "notes": v[7]})
    templates = []
    for t in tpls:
        templates.append({
            "import_template_id": int(t[0]), "code": t[1], "name": t[2], "domain": t[3],
            "target_table": t[4], "description": t[5],
            "versions": by_tpl.get(int(t[0]), [])})
    return {"count": len(templates), "templates": templates}


# ---------------------------------------------------------------------------
# Batch serialise
# ---------------------------------------------------------------------------
_BATCH_COLS = (
    'b."ImportBatchID", b."IngestionJobID", b."ImportTemplateVersionID", b."Domain",'
    ' b."CaseMasterID", b."EvidenceItemID", b."SourceFileName", b."SourceFormat",'
    ' b."Status", b."DryRun", b."Totals", b."ErrorSummary", b."MappingResolved",'
    ' b."SupersededByImportBatchID", b."CreatedByActor", b."ApprovedByActor",'
    ' b."CommittedAt", b."CreatedAt", t."Code", v."Version", t."TargetTable"'
)


def _serialize_batch(conn, batch_id: int, include_rows: int = 10) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT {_BATCH_COLS} FROM "ImportBatch" b '
            'JOIN "ImportTemplateVersion" v ON v."ImportTemplateVersionID"=b."ImportTemplateVersionID" '
            'JOIN "ImportTemplate" t ON t."ImportTemplateID"=v."ImportTemplateID" '
            'WHERE b."ImportBatchID"=%s', (batch_id,))
        r = cur.fetchone()
    if not r:
        raise ImportNotFound(f"Import batch {batch_id} not found.")
    batch = {
        "import_batch_id": int(r[0]), "ingestion_job_id": r[1],
        "import_template_version_id": int(r[2]), "domain": r[3], "case_master_id": r[4],
        "evidence_item_id": r[5], "source_file_name": r[6], "source_format": r[7],
        "status": r[8], "dry_run": bool(r[9]), "totals": r[10] or {},
        "error_summary": r[11] or {}, "mapping": r[12] or {},
        "superseded_by_import_batch_id": r[13], "created_by_actor": r[14],
        "approved_by_actor": r[15], "committed_at": _s(r[16]), "created_at": _s(r[17]),
        "template_code": r[18], "template_version": r[19], "target_table": r[20],
        "sample_rows": [],
    }
    if include_rows:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "ImportStagingRowID","RowNumber","Status","RejectReason","MappedValues",'
                '"CanonicalTargetTable","CanonicalTargetID" FROM "ImportStagingRow" '
                'WHERE "ImportBatchID"=%s ORDER BY "RowNumber" LIMIT %s', (batch_id, include_rows))
            batch["sample_rows"] = [{
                "import_staging_row_id": int(x[0]), "row_number": x[1], "status": x[2],
                "reject_reason": x[3], "mapped": x[4] or {},
                "canonical_target_table": x[5], "canonical_target_id": x[6]}
                for x in cur.fetchall()]
    return batch


# ---------------------------------------------------------------------------
# Create batch (parse -> stage -> dry-run)
# ---------------------------------------------------------------------------
def _committed_hashes(conn, target_table: str) -> set[str]:
    """RowHashes already committed for this target table (cross-batch dedupe)."""
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "RowHash" FROM "ImportStagingRow" '
            'WHERE "Status"=\'committed\' AND "CanonicalTargetTable"=%s', (target_table,))
        return {r[0] for r in cur.fetchall() if r[0]}


def _ensure_evidence_item(conn, tv: dict, req_evidence_id: Optional[int],
                          case_id: Optional[int], file_name: Optional[str],
                          sha256: str, size_bytes: int, actor: Optional[str]) -> Optional[int]:
    """Link an existing evidence item, or create a lightweight one representing
    the uploaded structured source file (step 1: 'upload source file as evidence')."""
    if req_evidence_id:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "EvidenceItem" WHERE "EvidenceItemID"=%s', (req_evidence_id,))
            if cur.fetchone() is None:
                raise ImportValidationError(f"Evidence item {req_evidence_id} not found.")
        return req_evidence_id
    financial = tv["domain"] in ("bank_txn", "account_kyc", "wallet_upi")
    etype = "financial_dataset" if financial else "digital_export"
    ssid = _domain_source_system(conn, tv["domain"])
    title = f"{tv['code']} import — {file_name or 'structured file'}"
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "EvidenceItem" ("CaseMasterID","SourceSystemID","EvidenceType","Category",'
            '"Title","SyntheticReference","Tags","UploaderActor","State","ManualMetadata","IsSynthetic") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING "EvidenceItemID"',
            (case_id, ssid, etype, tv["domain"], title,
             "SYN-IMP-" + sha256[:12].upper(), ["import", tv["domain"]], actor, "available",
             Json({"import_template": tv["code"], "file_name": file_name,
                   "sha256": sha256, "size_bytes": size_bytes})))
        eid = int(cur.fetchone()[0])
        cur.execute(
            'INSERT INTO "EvidenceObject" ("EvidenceItemID","StorageStatus","FileName","MimeType",'
            '"SizeBytes","Sha256","ManualProvenance") VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (eid, "fixture_pending_cloud_upload", file_name,
             "text/csv" if (file_name or "").endswith(".csv") else "application/json",
             size_bytes, sha256, Json({"import": True})))
        cur.execute(
            'INSERT INTO "EvidenceActivityEvent" ("EvidenceItemID","EventType","Actor","Detail") '
            'VALUES (%s,%s,%s,%s)', (eid, "created", actor, Json({"source": "digital_import"})))
    return eid


def _create_batch(conn, req, actor: Optional[str]) -> int:
    tv = _template_version(conn, req.import_template_version_id)
    if tv is None:
        raise ImportNotFound(f"Import template version {req.import_template_version_id} not found.")
    if tv["status"] != "approved":
        raise ImportValidationError(
            f"Template version '{tv['code']}@{tv['version']}' is '{tv['status']}', not approved.")

    # idempotent retry: same key -> return the existing batch
    if req.idempotency_key:
        with conn.cursor() as cur:
            cur.execute('SELECT "ImportBatchID" FROM "ImportBatch" WHERE "IdempotencyKey"=%s',
                        (req.idempotency_key,))
            r = cur.fetchone()
        if r:
            return int(r[0])

    try:
        raw_rows = P.parse_content(req.content, req.source_format)
    except P.ParseError as exc:
        raise ImportValidationError(str(exc))
    if not raw_rows:
        raise ImportValidationError("Source file parsed to zero rows.")

    mapping = P.effective_mapping(tv["mapping"], req.mapping_override)
    target = T.target_table(mapping, tv["target_table"])
    seen = _committed_hashes(conn, target)
    try:
        report = P.map_and_validate(raw_rows, mapping, tv["dedupe_keys"], seen_hashes=seen)
    except P.ParseError as exc:
        raise ImportValidationError(str(exc))

    sha256 = hashlib.sha256(req.content.encode("utf-8")).hexdigest()
    size_bytes = len(req.content.encode("utf-8"))
    evidence_id = _ensure_evidence_item(
        conn, tv, req.evidence_item_id, req.case_master_id, req.source_file_name,
        sha256, size_bytes, actor)

    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "IngestionJob" ("SourceSystemID","JobKind","IdempotencyKey","Status","DryRun","Totals") '
            'VALUES (%s,%s,%s,%s,%s,%s) RETURNING "IngestionJobID"',
            (_domain_source_system(conn, tv["domain"]), "import", req.idempotency_key,
             "dry_run", True, Json(report["totals"])))
        job_id = int(cur.fetchone()[0])
        cur.execute(
            'INSERT INTO "ImportBatch" ("IngestionJobID","ImportTemplateVersionID","EvidenceItemID",'
            '"CaseMasterID","Domain","SourceFileName","SourceFormat","SourceSha256","IdempotencyKey",'
            '"Status","DryRun","MappingResolved","Totals","ErrorSummary","CreatedByActor") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING "ImportBatchID"',
            (job_id, tv["tvid"], evidence_id, req.case_master_id, tv["domain"],
             req.source_file_name, req.source_format, sha256, req.idempotency_key,
             "staged", True, Json(mapping), Json(report["totals"]),
             Json(report["error_summary"]), actor))
        batch_id = int(cur.fetchone()[0])

        rows_params = [
            (batch_id, r["row_number"], Json(r["raw"]), Json(r["mapped"]), r["row_hash"],
             r["status"] if r["status"] != "valid" else "valid", r["reject_reason"])
            for r in report["rows"]]
        cur.executemany(
            'INSERT INTO "ImportStagingRow" ("ImportBatchID","RowNumber","RawValues","MappedValues",'
            '"RowHash","Status","RejectReason") VALUES (%s,%s,%s,%s,%s,%s,%s)', rows_params)

    audit.record(audit.Action.IMPORT, "import_batch", batch_id, actor=actor, conn=conn,
                 detail={"template": tv["code"], "version": tv["version"], "domain": tv["domain"],
                         "totals": report["totals"], "dry_run": True})
    return batch_id


# ---------------------------------------------------------------------------
# Entity / account / device resolution (CANDIDATE only — never auto-confirmed)
# ---------------------------------------------------------------------------
def _resolve_entity(conn, kind: str, token: str, label: Optional[str]) -> int:
    ref = "SYN-IMP-" + kind[:3].upper() + "-" + hashlib.sha1(token.encode("utf-8")).hexdigest()[:14]
    with conn.cursor() as cur:
        cur.execute('SELECT "CanonicalEntityID" FROM "CanonicalEntity" WHERE "PublicRef"=%s', (ref,))
        r = cur.fetchone()
        if r:
            return int(r[0])
        cur.execute(
            'INSERT INTO "CanonicalEntity" ("EntityKind","PublicRef","Label","Attributes","IsSynthetic") '
            'VALUES (%s,%s,%s,%s,TRUE) RETURNING "CanonicalEntityID"',
            (kind, ref, label or token, Json({"import_token": token})))
        return int(cur.fetchone()[0])


def _candidate_link(conn, evidence_item_id: Optional[int], entity_id: int, link_type: str,
                    source_record_id: Optional[int], batch_id: int) -> bool:
    """Create a CANDIDATE evidence->entity link (reviewed later). Returns True if new."""
    if not evidence_item_id:
        return False
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "EvidenceEntityLink" ("EvidenceItemID","CanonicalEntityID","LinkType",'
            '"Confidence","ReviewStatus","SourceRecordID","ImportBatchID") '
            'VALUES (%s,%s,%s,%s,\'candidate\',%s,%s) '
            'ON CONFLICT ("EvidenceItemID","CanonicalEntityID","LinkType") DO NOTHING '
            'RETURNING "EvidenceEntityLinkID"',
            (evidence_item_id, entity_id, link_type, 0.5, source_record_id, batch_id))
        return cur.fetchone() is not None


def _resolve_account(conn, account_no: str, batch_id: int, source_record_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "AccountID" FROM "FinancialAccount" WHERE "AccountNo"=%s '
                    'ORDER BY "AccountID" LIMIT 1', (account_no,))
        r = cur.fetchone()
        if r:
            return int(r[0])
        cur.execute(
            'INSERT INTO "FinancialAccount" ("AccountNo","AccountType","Currency","ImportBatchID",'
            '"SourceRecordID","IsSynthetic","Attributes") VALUES (%s,%s,%s,%s,%s,TRUE,%s) '
            'RETURNING "AccountID"',
            (account_no, "unknown", "INR", batch_id, source_record_id,
             Json({"created_by_import": True})))
        return int(cur.fetchone()[0])


def _resolve_device(conn, identifier: str, case_id: Optional[int], batch_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "DeviceID" FROM "Device" WHERE "SyntheticIdentifier"=%s '
                    'ORDER BY "DeviceID" LIMIT 1', (identifier,))
        r = cur.fetchone()
        if r:
            return int(r[0])
        cur.execute(
            'INSERT INTO "Device" ("DeviceType","SyntheticIdentifier","Label","CaseMasterID","ImportBatchID") '
            'VALUES (%s,%s,%s,%s,%s) RETURNING "DeviceID"',
            ("mobile", identifier, f"Imported device {identifier[:24]}", case_id, batch_id))
        return int(cur.fetchone()[0])


def _resolve_district(conn, lon: float, lat: float) -> Optional[int]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT b."DistrictID" FROM "JurisdictionBoundary" b '
                'WHERE b."Level"=\'district\' AND b."IsCurrent" '
                'AND ST_Contains(b."geom", ST_SetSRID(ST_MakePoint(%s,%s),4326)) LIMIT 1',
                (lon, lat))
            r = cur.fetchone()
        return int(r[0]) if r else None
    except Exception:  # noqa: BLE001 — geometry optional, never block a commit
        return None


# ---------------------------------------------------------------------------
# Canonical insert per target table (returns canonical id, +candidate link count)
# ---------------------------------------------------------------------------
def _insert_canonical(conn, ctx: dict, mapped: dict, source_record_id: int) -> tuple[str, int, int]:
    """Insert one canonical row. Returns (target_table, canonical_id, candidate_links)."""
    target = ctx["target_table"]
    batch_id = ctx["batch_id"]
    evidence_id = ctx["evidence_item_id"]
    case_id = ctx["case_master_id"]
    domain = ctx["domain"]
    links = 0

    if target == "CommunicationEvent":
        kind = T.DOMAIN_ENTITY_KIND.get(domain)   # phone for cdr/chat; None for ip
        ep_a = mapped.get("endpoint_a")
        ep_b = mapped.get("endpoint_b")
        ent_a = ent_b = None
        if kind and ep_a:
            ent_a = _resolve_entity(conn, kind, str(ep_a), str(ep_a))
            links += 1 if _candidate_link(conn, evidence_id, ent_a, "communication_endpoint",
                                          source_record_id, batch_id) else 0
        if kind and ep_b:
            ent_b = _resolve_entity(conn, kind, str(ep_b), str(ep_b))
            links += 1 if _candidate_link(conn, evidence_id, ent_b, "communication_endpoint",
                                          source_record_id, batch_id) else 0
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "CommunicationEvent" ("CaseMasterID","FromCanonicalEntityID",'
                '"ToCanonicalEntityID","CommType","OccurredAt","DurationSec","SyntheticEndpointA",'
                '"SyntheticEndpointB","ReviewStatus","SourceRecordID","ImportBatchID") '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,\'candidate\',%s,%s) RETURNING "CommunicationEventID"',
                (case_id, ent_a, ent_b, mapped.get("comm_type") or "call",
                 mapped.get("occurred_at"), mapped.get("duration_sec"),
                 _s(ep_a), _s(ep_b), source_record_id, batch_id))
            return target, int(cur.fetchone()[0]), links

    if target == "DeviceArtifact":
        dev_id = _resolve_device(conn, str(mapped.get("device_identifier")), case_id, batch_id)
        ent = _resolve_entity(conn, "device", str(mapped.get("device_identifier")),
                              str(mapped.get("device_identifier")))
        links += 1 if _candidate_link(conn, evidence_id, ent, "device_owner",
                                      source_record_id, batch_id) else 0
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "DeviceArtifact" ("DeviceID","ArtifactType","SyntheticReference",'
                '"Detail","EvidenceItemID","ImportBatchID") VALUES (%s,%s,%s,%s,%s,%s) '
                'RETURNING "DeviceArtifactID"',
                (dev_id, mapped.get("artifact_type") or "artifact", mapped.get("reference"),
                 Json({"source_record_id": source_record_id}), evidence_id, batch_id))
            return target, int(cur.fetchone()[0]), links

    if target == "LocationObservation":
        lon = mapped.get("longitude")
        lat = mapped.get("latitude")
        ent = None
        entity_ref = mapped.get("entity_ref")
        if entity_ref:
            with conn.cursor() as cur:
                cur.execute('SELECT "CanonicalEntityID" FROM "CanonicalEntity" WHERE "PublicRef"=%s',
                            (str(entity_ref),))
                r = cur.fetchone()
                ent = int(r[0]) if r else None
        district_id = _resolve_district(conn, lon, lat) if (lon is not None and lat is not None) else None
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "LocationObservation" ("CanonicalEntityID","CaseMasterID","ObservedAt",'
                '"geom","DistrictID","Source","SourceRecordID","ImportBatchID") '
                'VALUES (%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),4326),%s,%s,%s,%s) '
                'RETURNING "LocationObservationID"',
                (ent, case_id, mapped.get("observed_at"), lon, lat, district_id,
                 "structured_import", source_record_id, batch_id))
            return target, int(cur.fetchone()[0]), links

    if target == "FinancialTransaction":
        src_acct = _resolve_account(conn, str(mapped.get("source_account_no")), batch_id, source_record_id)
        dst_acct = _resolve_account(conn, str(mapped.get("destination_account_no")), batch_id, source_record_id)
        for acct_no, acct_id in ((mapped.get("source_account_no"), src_acct),
                                 (mapped.get("destination_account_no"), dst_acct)):
            ent = _resolve_entity(conn, "account", str(acct_no), str(acct_no))
            links += 1 if _candidate_link(conn, evidence_id, ent, "account_holder",
                                          source_record_id, batch_id) else 0
        channel = mapped.get("channel")
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "FinancialTransaction" ("SourceAccountID","DestinationAccountID","Amount",'
                '"TxnTimestamp","Channel","NormalizedChannel","Currency","SyntheticReference",'
                '"ReviewStatus","EvidenceCaseID","SourceRecordID","ImportBatchID","IsSynthetic","Properties") '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,\'candidate\',%s,%s,%s,TRUE,%s) RETURNING "TransactionID"',
                (src_acct, dst_acct, mapped.get("amount"), mapped.get("txn_timestamp"),
                 channel, T.normalize_channel(channel), mapped.get("currency") or "INR",
                 mapped.get("reference"), case_id, source_record_id, batch_id,
                 Json({"source_record_id": source_record_id, "import": True})))
            txn_id = int(cur.fetchone()[0])
            if case_id:
                cur.execute(
                    'INSERT INTO "TransactionLink" ("TransactionID","CaseMasterID","LinkType",'
                    '"Confidence","ReviewStatus","SourceRecordID") '
                    'VALUES (%s,%s,%s,%s,\'candidate\',%s) '
                    'ON CONFLICT ("TransactionID","CaseMasterID") DO NOTHING',
                    (txn_id, case_id, "imported", 0.5, source_record_id))
        return target, txn_id, links

    if target == "FinancialAccount":
        acct_no = str(mapped.get("account_no"))
        atype = (mapped.get("account_type") or "unknown").lower()
        valid_types = {"savings", "current", "wallet", "mule", "business", "unknown"}
        if atype not in valid_types:
            atype = "unknown"
        with conn.cursor() as cur:
            cur.execute('SELECT "AccountID" FROM "FinancialAccount" WHERE "AccountNo"=%s '
                        'ORDER BY "AccountID" LIMIT 1', (acct_no,))
            r = cur.fetchone()
            if r:
                acct_id = int(r[0])
                cur.execute(
                    'UPDATE "FinancialAccount" SET "AccountType"=%s::account_type_enum,"HolderName"=%s,'
                    '"Bank"=%s,"IFSC"=%s,"Currency"=%s,"SyntheticReference"=%s,"KycDetail"=%s,'
                    '"ImportBatchID"=%s,"SourceRecordID"=%s,"Version"="Version"+1 WHERE "AccountID"=%s',
                    (atype, mapped.get("holder_name"), mapped.get("bank"), mapped.get("ifsc"),
                     mapped.get("currency") or "INR", mapped.get("kyc_reference"),
                     Json({"kyc_reference": mapped.get("kyc_reference")}), batch_id,
                     source_record_id, acct_id))
            else:
                cur.execute(
                    'INSERT INTO "FinancialAccount" ("AccountNo","AccountType","HolderName","Bank",'
                    '"IFSC","Currency","SyntheticReference","KycDetail","ImportBatchID","SourceRecordID",'
                    '"IsSynthetic") VALUES (%s,%s::account_type_enum,%s,%s,%s,%s,%s,%s,%s,%s,TRUE) '
                    'RETURNING "AccountID"',
                    (acct_no, atype, mapped.get("holder_name"), mapped.get("bank"),
                     mapped.get("ifsc"), mapped.get("currency") or "INR",
                     mapped.get("kyc_reference"), Json({"kyc_reference": mapped.get("kyc_reference")}),
                     batch_id, source_record_id))
                acct_id = int(cur.fetchone()[0])
        ent = _resolve_entity(conn, "account", acct_no, mapped.get("holder_name") or acct_no)
        links += 1 if _candidate_link(conn, evidence_id, ent, "account_holder",
                                      source_record_id, batch_id) else 0
        return target, acct_id, links

    raise ImportValidationError(f"Unsupported target table '{target}'.")


# ---------------------------------------------------------------------------
# Commit (approve) — provenance + candidate resolution, idempotent, partial
# ---------------------------------------------------------------------------
def _load_batch(conn, batch_id: int) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT b."ImportBatchID",b."Status",b."Domain",b."CaseMasterID",b."EvidenceItemID",'
            'b."IngestionJobID",b."Totals",t."TargetTable" FROM "ImportBatch" b '
            'JOIN "ImportTemplateVersion" v ON v."ImportTemplateVersionID"=b."ImportTemplateVersionID" '
            'JOIN "ImportTemplate" t ON t."ImportTemplateID"=v."ImportTemplateID" '
            'WHERE b."ImportBatchID"=%s', (batch_id,))
        r = cur.fetchone()
    if not r:
        raise ImportNotFound(f"Import batch {batch_id} not found.")
    return {"batch_id": int(r[0]), "status": r[1], "domain": r[2], "case_master_id": r[3],
            "evidence_item_id": r[4], "ingestion_job_id": r[5], "totals": r[6] or {},
            "target_table": r[7]}


def _commit_batch(conn, batch_id: int, actor: Optional[str]) -> dict:
    b = _load_batch(conn, batch_id)
    if b["status"] in ("committed", "partial"):
        # idempotent replay: already committed (fully or partially), do nothing
        t = b["totals"]
        return {"import_batch_id": batch_id, "status": b["status"], "target_table": b["target_table"],
                "committed": int(t.get("committed", t.get("valid", 0))), "rejected": int(t.get("rejected", 0)),
                "duplicate": int(t.get("duplicate", 0)), "source_records_created": 0,
                "canonical_rows_created": 0, "candidate_entity_links": 0, "idempotent_replay": True}
    if b["status"] in ("rolled_back", "superseded", "failed"):
        raise ImportConflict(f"Batch is '{b['status']}' and cannot be committed.")

    with conn.cursor() as cur:
        cur.execute(
            'SELECT "ImportStagingRowID","MappedValues" FROM "ImportStagingRow" '
            'WHERE "ImportBatchID"=%s AND "Status"=%s ORDER BY "RowNumber"',
            (batch_id, "valid"))
        valid_rows = cur.fetchall()
        cur.execute('SELECT count(*) FROM "ImportStagingRow" WHERE "ImportBatchID"=%s '
                    "AND \"Status\" IN ('rejected','duplicate')", (batch_id,))
        bad = int(cur.fetchone()[0])

    if not valid_rows and bad == 0:
        raise ImportConflict("Batch has no rows to commit.")

    ctx = {"batch_id": batch_id, "target_table": b["target_table"], "domain": b["domain"],
           "case_master_id": b["case_master_id"], "evidence_item_id": b["evidence_item_id"]}
    ssid = _domain_source_system(conn, b["domain"])
    committed = src_created = link_created = 0
    for srow_id, mapped in valid_rows:
        mapped = mapped or {}
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "SourceRecord" ("SourceSystemID","RecordKind","Payload","Status") '
                'VALUES (%s,%s,%s,\'committed\') RETURNING "SourceRecordID"',
                (ssid, "import_row", Json(mapped)))
            source_record_id = int(cur.fetchone()[0])
        src_created += 1
        target, canonical_id, links = _insert_canonical(conn, ctx, mapped, source_record_id)
        link_created += links
        committed += 1
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE "ImportStagingRow" SET "Status"=\'committed\',"CanonicalTargetTable"=%s,'
                '"CanonicalTargetID"=%s,"SourceRecordID"=%s WHERE "ImportStagingRowID"=%s',
                (target, canonical_id, source_record_id, srow_id))

    final_status = "committed" if bad == 0 else "partial"
    totals = dict(b["totals"])
    totals["committed"] = committed
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE "ImportBatch" SET "Status"=%s,"DryRun"=FALSE,"ApprovedByActor"=%s,'
            '"CommittedAt"=now(),"Totals"=%s WHERE "ImportBatchID"=%s',
            (final_status, actor, Json(totals), batch_id))
        if b["ingestion_job_id"]:
            cur.execute('UPDATE "IngestionJob" SET "Status"=%s,"DryRun"=FALSE,"FinishedAt"=now(),'
                        '"Totals"=%s WHERE "IngestionJobID"=%s',
                        ("committed" if bad == 0 else "partial", Json(totals), b["ingestion_job_id"]))
    audit.record(audit.Action.IMPORT, "import_batch", batch_id, actor=actor, conn=conn,
                 detail={"action": "commit", "committed": committed, "status": final_status,
                         "target": b["target_table"]})
    return {"import_batch_id": batch_id, "status": final_status, "target_table": b["target_table"],
            "committed": committed, "rejected": int(totals.get("rejected", 0)),
            "duplicate": int(totals.get("duplicate", 0)), "source_records_created": src_created,
            "canonical_rows_created": committed, "candidate_entity_links": link_created,
            "idempotent_replay": False}


# ---------------------------------------------------------------------------
# Rollback (delete canonical rows created by a committed batch)
# ---------------------------------------------------------------------------
def _rollback_batch(conn, batch_id: int, actor: Optional[str], reason: Optional[str]) -> dict:
    b = _load_batch(conn, batch_id)
    if b["status"] not in ("committed", "partial"):
        raise ImportConflict(f"Only a committed/partial batch can be rolled back (is '{b['status']}').")

    deleted = 0
    with conn.cursor() as cur:
        # children before parents; FinancialAccount only if no remaining txn references it
        cur.execute('DELETE FROM "EvidenceEntityLink" WHERE "ImportBatchID"=%s', (batch_id,))
        cur.execute('DELETE FROM "TransactionLink" WHERE "TransactionID" IN '
                    '(SELECT "TransactionID" FROM "FinancialTransaction" WHERE "ImportBatchID"=%s)',
                    (batch_id,))
        for tbl, pk in (("CommunicationEvent", "CommunicationEventID"),
                        ("LocationObservation", "LocationObservationID"),
                        ("DeviceArtifact", "DeviceArtifactID"),
                        ("FinancialTransaction", "TransactionID")):
            cur.execute(f'DELETE FROM "{tbl}" WHERE "ImportBatchID"=%s', (batch_id,))
            deleted += cur.rowcount
        # devices created by this batch with no remaining artifacts
        cur.execute('DELETE FROM "Device" d WHERE d."ImportBatchID"=%s AND NOT EXISTS '
                    '(SELECT 1 FROM "DeviceArtifact" a WHERE a."DeviceID"=d."DeviceID")', (batch_id,))
        deleted += cur.rowcount
        # accounts created by this batch with no remaining transactions
        cur.execute('DELETE FROM "FinancialAccount" a WHERE a."ImportBatchID"=%s AND NOT EXISTS '
                    '(SELECT 1 FROM "FinancialTransaction" t WHERE t."SourceAccountID"=a."AccountID" '
                    'OR t."DestinationAccountID"=a."AccountID")', (batch_id,))
        deleted += cur.rowcount
        # retract this batch's source records
        cur.execute('UPDATE "SourceRecord" SET "Status"=\'retracted\' WHERE "SourceRecordID" IN '
                    '(SELECT "SourceRecordID" FROM "ImportStagingRow" WHERE "ImportBatchID"=%s '
                    'AND "SourceRecordID" IS NOT NULL)', (batch_id,))
        retracted = cur.rowcount
        # reset staging rows so they could be re-committed
        cur.execute('UPDATE "ImportStagingRow" SET "Status"=\'valid\',"CanonicalTargetID"=NULL,'
                    '"SourceRecordID"=NULL WHERE "ImportBatchID"=%s AND "Status"=\'committed\'',
                    (batch_id,))
        cur.execute('UPDATE "ImportBatch" SET "Status"=\'rolled_back\',"DryRun"=TRUE WHERE "ImportBatchID"=%s',
                    (batch_id,))
    audit.record(audit.Action.IMPORT, "import_batch", batch_id, actor=actor, conn=conn,
                 detail={"action": "rollback", "deleted": deleted, "reason": reason})
    return {"import_batch_id": batch_id, "status": "rolled_back",
            "canonical_rows_deleted": deleted, "source_records_retracted": retracted}


def _supersede_batch(conn, old_batch_id: int, req, actor: Optional[str]) -> int:
    b = _load_batch(conn, old_batch_id)
    with conn.cursor() as cur:
        cur.execute('SELECT "ImportTemplateVersionID","CaseMasterID","EvidenceItemID" '
                    'FROM "ImportBatch" WHERE "ImportBatchID"=%s', (old_batch_id,))
        r = cur.fetchone()
    tvid, case_id, _ev = int(r[0]), r[1], r[2]

    # build the replacement batch from the new content
    class _R:
        pass
    nr = _R()
    nr.import_template_version_id = tvid
    nr.content = req.content
    nr.source_format = req.source_format
    nr.source_file_name = req.source_file_name
    nr.source_sha256 = None
    nr.case_master_id = case_id
    nr.evidence_item_id = None
    nr.mapping_override = req.mapping_override
    nr.idempotency_key = None
    nr.created_by_actor = actor
    new_id = _create_batch(conn, nr, actor)

    # roll back the old batch's canonical rows if it was committed
    if b["status"] in ("committed", "partial"):
        _rollback_batch(conn, old_batch_id, actor, reason="superseded")
    with conn.cursor() as cur:
        cur.execute('UPDATE "ImportBatch" SET "Status"=\'superseded\','
                    '"SupersededByImportBatchID"=%s WHERE "ImportBatchID"=%s', (new_id, old_batch_id))
    audit.record(audit.Action.IMPORT, "import_batch", old_batch_id, actor=actor, conn=conn,
                 detail={"action": "supersede", "superseded_by": new_id})
    return new_id


# ===========================================================================
# Public wrappers
# ===========================================================================
def create_batch(req, actor: Optional[str] = None) -> dict:
    with db.rw_conn() as conn:
        bid = _create_batch(conn, req, actor or req.created_by_actor)
        return _serialize_batch(conn, bid)


def get_batch(batch_id: int) -> dict:
    with db.ro_conn() as conn:
        return _serialize_batch(conn, batch_id, include_rows=20)


def commit_batch(batch_id: int, actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        return _commit_batch(conn, batch_id, actor)


def rollback_batch(batch_id: int, actor: Optional[str], reason: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        return _rollback_batch(conn, batch_id, actor, reason)


def supersede_batch(batch_id: int, req, actor: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        new_id = _supersede_batch(conn, batch_id, req, actor)
        return _serialize_batch(conn, new_id)


def list_batches(status: Optional[str], domain: Optional[str], case_id: Optional[int],
                 page: int, page_size: int) -> dict:
    clauses, params = [], []
    if status:
        clauses.append('b."Status"=%s'); params.append(status)
    if domain:
        clauses.append('b."Domain"=%s'); params.append(domain)
    if case_id:
        clauses.append('b."CaseMasterID"=%s'); params.append(case_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "ImportBatch" b{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT b."ImportBatchID",b."Domain",t."Code",b."Status",b."DryRun",'
                f'b."CaseMasterID",b."Totals",b."CreatedByActor",b."CreatedAt" '
                f'FROM "ImportBatch" b '
                f'JOIN "ImportTemplateVersion" v ON v."ImportTemplateVersionID"=b."ImportTemplateVersionID" '
                f'JOIN "ImportTemplate" t ON t."ImportTemplateID"=v."ImportTemplateID"{where} '
                f'ORDER BY b."ImportBatchID" DESC LIMIT %s OFFSET %s', params + [page_size, offset])
            items = [{
                "import_batch_id": int(x[0]), "domain": x[1], "template_code": x[2],
                "status": x[3], "dry_run": bool(x[4]), "case_master_id": x[5],
                "totals": x[6] or {}, "created_by_actor": x[7], "created_at": _s(x[8])}
                for x in cur.fetchall()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def list_staging_rows(batch_id: int, status: Optional[str], page: int, page_size: int) -> dict:
    clauses = ['"ImportBatchID"=%s']
    params: list[Any] = [batch_id]
    if status:
        clauses.append('"Status"=%s'); params.append(status)
    where = " WHERE " + " AND ".join(clauses)
    offset = (page - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM "ImportBatch" WHERE "ImportBatchID"=%s', (batch_id,))
            if cur.fetchone() is None:
                raise ImportNotFound(f"Import batch {batch_id} not found.")
            cur.execute(f'SELECT count(*) FROM "ImportStagingRow"{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT "ImportStagingRowID","RowNumber","Status","RejectReason","MappedValues",'
                f'"CanonicalTargetTable","CanonicalTargetID" FROM "ImportStagingRow"{where} '
                f'ORDER BY "RowNumber" LIMIT %s OFFSET %s', params + [page_size, offset])
            items = [{
                "import_staging_row_id": int(x[0]), "row_number": x[1], "status": x[2],
                "reject_reason": x[3], "mapped": x[4] or {}, "canonical_target_table": x[5],
                "canonical_target_id": x[6]} for x in cur.fetchall()]
    return {"import_batch_id": batch_id, "total": total, "page": page, "page_size": page_size,
            "status_filter": status, "items": items}


# ---------------------------------------------------------------------------
# Reviewed entity-link queue
# ---------------------------------------------------------------------------
def entity_link_queue(review_status: Optional[str], page: int, page_size: int) -> dict:
    clauses, params = [], []
    if review_status:
        clauses.append('"ReviewStatus"=%s'); params.append(review_status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "vw_entity_link_queue"{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT "EvidenceEntityLinkID","EvidenceItemID","EvidenceTitle","CanonicalEntityID",'
                f'"EntityKind","EntityLabel","EntityRef","LinkType","Confidence","ReviewStatus",'
                f'"ReviewedByActor","ReviewedAt","SourceRecordID","ImportBatchID","CaseMasterID" '
                f'FROM "vw_entity_link_queue"{where} '
                f'ORDER BY "EvidenceEntityLinkID" DESC LIMIT %s OFFSET %s', params + [page_size, offset])
            items = [{
                "evidence_entity_link_id": int(x[0]), "evidence_item_id": x[1],
                "evidence_title": x[2], "canonical_entity_id": int(x[3]), "entity_kind": x[4],
                "entity_label": x[5], "entity_ref": x[6], "link_type": x[7],
                "confidence": float(x[8]) if x[8] is not None else None, "review_status": x[9],
                "reviewed_by_actor": x[10], "reviewed_at": _s(x[11]), "source_record_id": x[12],
                "import_batch_id": x[13], "case_master_id": x[14]} for x in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size,
            "review_status": review_status, "items": items}


def _review_entity_link(conn, link_id: int, decision: str, actor: Optional[str], note: Optional[str]) -> dict:
    with conn.cursor() as cur:
        cur.execute('SELECT "ReviewStatus" FROM "EvidenceEntityLink" WHERE "EvidenceEntityLinkID"=%s',
                    (link_id,))
        r = cur.fetchone()
        if r is None:
            raise ImportNotFound(f"Entity link {link_id} not found.")
        new_status = "reviewed" if decision == "accept" else "rejected"
        cur.execute(
            'UPDATE "EvidenceEntityLink" SET "ReviewStatus"=%s,"ReviewedByActor"=%s,"ReviewedAt"=now() '
            'WHERE "EvidenceEntityLinkID"=%s', (new_status, actor, link_id))
    audit.record(audit.Action.ENTITY_CHANGE, "evidence_entity_link", link_id, actor=actor, conn=conn,
                 detail={"decision": decision, "new_status": new_status, "note": note})
    return {"evidence_entity_link_id": link_id, "review_status": new_status}


def review_entity_link(link_id: int, decision: str, actor: Optional[str], note: Optional[str]) -> dict:
    with db.rw_conn() as conn:
        return _review_entity_link(conn, link_id, decision, actor, note)


# ---------------------------------------------------------------------------
# Account / transaction views
# ---------------------------------------------------------------------------
def list_accounts(flagged: Optional[bool], review_status: Optional[str],
                  page: int, page_size: int) -> dict:
    clauses, params = [], []
    if flagged is not None:
        clauses.append('"IsFlagged"=%s'); params.append(flagged)
    if review_status:
        clauses.append('"OwnerReviewStatus"=%s'); params.append(review_status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "FinancialAccount"{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT "AccountID","AccountNo","AccountType","HolderName","Bank","IFSC","Currency",'
                f'"IsFlagged","OwnerCanonicalPersonID","OwnerReviewStatus","ImportBatchID" '
                f'FROM "FinancialAccount"{where} ORDER BY "AccountID" DESC LIMIT %s OFFSET %s',
                params + [page_size, offset])
            items = [{
                "account_id": int(x[0]), "account_no": x[1], "account_type": x[2],
                "holder_name": x[3], "bank": x[4], "ifsc": x[5], "currency": x[6],
                "is_flagged": bool(x[7]), "owner_canonical_person_id": x[8],
                "owner_review_status": x[9], "import_batch_id": x[10]} for x in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def list_transactions(account_id: Optional[int], flagged: Optional[bool], case_id: Optional[int],
                      page: int, page_size: int) -> dict:
    clauses, params = [], []
    if account_id:
        clauses.append('("SourceAccountID"=%s OR "DestinationAccountID"=%s)')
        params.extend([account_id, account_id])
    if flagged is not None:
        clauses.append('"IsFlagged"=%s'); params.append(flagged)
    if case_id:
        clauses.append('"EvidenceCaseID"=%s'); params.append(case_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * page_size
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "FinancialTransaction"{where}', params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT "TransactionID","SourceAccountID","DestinationAccountID","Amount","Currency",'
                f'"TxnTimestamp"::text,"Channel","NormalizedChannel","IsFlagged","FlagReason",'
                f'"ReviewStatus","EvidenceCaseID","ImportBatchID","SyntheticReference" '
                f'FROM "FinancialTransaction"{where} ORDER BY "TxnTimestamp" DESC NULLS LAST '
                f'LIMIT %s OFFSET %s', params + [page_size, offset])
            items = [{
                "transaction_id": int(x[0]), "source_account_id": int(x[1]),
                "destination_account_id": int(x[2]), "amount": float(x[3]), "currency": x[4],
                "txn_timestamp": x[5], "channel": x[6], "normalized_channel": x[7],
                "is_flagged": bool(x[8]), "flag_reason": x[9], "review_status": x[10],
                "evidence_case_id": x[11], "import_batch_id": x[12], "synthetic_reference": x[13]}
                for x in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ---------------------------------------------------------------------------
# CDR / device timeline + aggregates
# ---------------------------------------------------------------------------
def cdr_timeline(case_id: Optional[int], entity_id: Optional[int], limit: int = 500) -> dict:
    if (case_id is None) == (entity_id is None):
        raise ImportValidationError("Provide exactly one of case_id or entity_id.")
    scope = "case" if case_id is not None else "entity"
    scope_id = case_id if case_id is not None else entity_id
    if scope == "case":
        pred = '"CaseMasterID"=%s'
        args = [case_id]
    else:
        pred = '("FromCanonicalEntityID"=%s OR "ToCanonicalEntityID"=%s)'
        args = [entity_id, entity_id]
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "CommunicationEvent" WHERE {pred}', args)
            total = int(cur.fetchone()[0])
            cur.execute(f'SELECT "CommType", count(*) FROM "CommunicationEvent" WHERE {pred} '
                        'GROUP BY "CommType"', args)
            by_type = {r[0]: int(r[1]) for r in cur.fetchall()}
            cur.execute(f'SELECT to_char("OccurredAt",\'YYYY-MM-DD\') d, count(*) '
                        f'FROM "CommunicationEvent" WHERE {pred} AND "OccurredAt" IS NOT NULL '
                        'GROUP BY d ORDER BY d', args)
            by_day = {r[0]: int(r[1]) for r in cur.fetchall()}
            cur.execute(
                f'SELECT ep, count(*) c FROM (SELECT "SyntheticEndpointA" ep FROM "CommunicationEvent" '
                f'WHERE {pred} UNION ALL SELECT "SyntheticEndpointB" FROM "CommunicationEvent" WHERE {pred}) s '
                'WHERE ep IS NOT NULL GROUP BY ep ORDER BY c DESC LIMIT 10', args + args)
            top_endpoints = [{"endpoint": r[0], "count": int(r[1])} for r in cur.fetchall()]
            cur.execute(
                f'SELECT "CommunicationEventID","CommType","OccurredAt"::text,"DurationSec",'
                f'"SyntheticEndpointA","SyntheticEndpointB","ReviewStatus","CaseMasterID","ImportBatchID" '
                f'FROM "CommunicationEvent" WHERE {pred} ORDER BY "OccurredAt" DESC NULLS LAST LIMIT %s',
                args + [limit])
            events = [{
                "communication_event_id": int(x[0]), "comm_type": x[1], "occurred_at": x[2],
                "duration_sec": x[3], "endpoint_a": x[4], "endpoint_b": x[5],
                "review_status": x[6], "case_master_id": x[7], "import_batch_id": x[8]}
                for x in cur.fetchall()]
    return {"scope": scope, "scope_id": scope_id, "total": total, "by_type": by_type,
            "by_day": by_day, "top_endpoints": top_endpoints, "events": events}


def list_devices(case_id: Optional[int], entity_id: Optional[int]) -> dict:
    if (case_id is None) == (entity_id is None):
        raise ImportValidationError("Provide exactly one of case_id or entity_id.")
    scope = "case" if case_id is not None else "entity"
    scope_id = case_id if case_id is not None else entity_id
    pred = '"CaseMasterID"=%s' if scope == "case" else '"CanonicalEntityID"=%s'
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT "DeviceID","DeviceType","SyntheticIdentifier","Label","CaseMasterID","ImportBatchID" '
                f'FROM "Device" WHERE {pred} ORDER BY "DeviceID" DESC LIMIT 200', (scope_id,))
            devs = cur.fetchall()
            device_ids = [int(d[0]) for d in devs]
            artifacts_by_dev: dict[int, list] = {}
            if device_ids:
                cur.execute(
                    'SELECT "DeviceID","DeviceArtifactID","ArtifactType","SyntheticReference","ImportBatchID" '
                    'FROM "DeviceArtifact" WHERE "DeviceID" = ANY(%s) ORDER BY "DeviceArtifactID"',
                    (device_ids,))
                for a in cur.fetchall():
                    artifacts_by_dev.setdefault(int(a[0]), []).append({
                        "device_artifact_id": int(a[1]), "artifact_type": a[2],
                        "synthetic_reference": a[3], "import_batch_id": a[4]})
    devices = [{
        "device_id": int(d[0]), "device_type": d[1], "synthetic_identifier": d[2],
        "label": d[3], "case_master_id": d[4], "import_batch_id": d[5],
        "artifacts": artifacts_by_dev.get(int(d[0]), [])} for d in devs]
    return {"scope": scope, "scope_id": scope_id, "count": len(devices), "devices": devices}
