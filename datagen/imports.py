"""Phase 8 datagen: golden template-driven import fixtures.

A regenerated synthetic DB should show the import pipeline end-to-end. The
template registry itself is seeded by migration 015 (reference data), so this
module runs as a LOADER POST-STEP (against a live connection) that creates a few
golden STAGED import batches — a source file uploaded as evidence, a template
version bound, and a mix of valid / rejected / duplicate staging rows — so the
import inbox and dry-run report have realistic demo content. Reviewers commit
them through the API/UI (the commit engine lives in app/imports, not duplicated
here).

Sample CSVs are also exported so a demo operator can paste a known-good file
into the import wizard.
"""
from __future__ import annotations

from psycopg2.extras import Json

# Small, unmistakably-synthetic sample files per template (structured; no OCR).
SAMPLE_CSV = {
    "cdr_call_events": (
        "caller_msisdn,callee_msisdn,event_time,duration_sec,call_type\n"
        "SYN-MSISDN-0000000001,SYN-MSISDN-0000000002,2025-03-01 09:15:00,142,call\n"
        "SYN-MSISDN-0000000001,SYN-MSISDN-0000000003,2025-03-01 11:40:00,63,call\n"
        "SYN-MSISDN-0000000002,SYN-MSISDN-0000000001,2025-03-02 18:05:00,300,call\n"
    ),
    "bank_transactions": (
        "from_account,to_account,amount,txn_time,channel,ref_no\n"
        "SYN-ACCT-0001,SYN-ACCT-0002,48000,2025-03-01 10:00:00,imps,SYN-REF-1\n"
        "SYN-ACCT-0003,SYN-ACCT-0002,47000,2025-03-01 12:30:00,imps,SYN-REF-2\n"
        "SYN-ACCT-0004,SYN-ACCT-0002,46500,2025-03-02 09:10:00,imps,SYN-REF-3\n"
    ),
    "wallet_upi": (
        "payer_vpa,payee_vpa,amount,txn_time,channel,rrn\n"
        "syn-payer@synbank,syn-payee@synbank,2500,2025-03-03 08:00:00,upi,SYN-RRN-1\n"
    ),
}


def _template_version(conn, code: str, version: str = "v1"):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT v."ImportTemplateVersionID", t."Domain", t."TargetTable" '
            'FROM "ImportTemplateVersion" v '
            'JOIN "ImportTemplate" t ON t."ImportTemplateID"=v."ImportTemplateID" '
            'WHERE t."Code"=%s AND v."Version"=%s', (code, version))
        return cur.fetchone()


def _source_system(conn, code: str):
    with conn.cursor() as cur:
        cur.execute('SELECT "SourceSystemID" FROM "SourceSystem" WHERE "Code"=%s', (code,))
        r = cur.fetchone()
        return int(r[0]) if r else None


def _seed_one(conn, code: str, staging: list, log=print) -> None:
    """Create one golden STAGED import batch with the given staging rows.

    ``staging`` is a list of (row_number, mapped_dict, status, reject_reason).
    """
    tv = _template_version(conn, code)
    if tv is None:
        log(f"  skip import demo '{code}': template not found")
        return
    tvid, domain, _target = int(tv[0]), tv[1], tv[2]
    financial = domain in ("bank_txn", "account_kyc", "wallet_upi")
    ssid = _source_system(conn, "FINANCIAL_IMPORT" if financial else "DIGITAL_IMPORT")
    valid = sum(1 for r in staging if r[2] == "valid")
    rejected = sum(1 for r in staging if r[2] == "rejected")
    duplicate = sum(1 for r in staging if r[2] == "duplicate")
    totals = {"parsed": len(staging), "valid": valid, "rejected": rejected, "duplicate": duplicate}

    with conn.cursor() as cur:
        # source file uploaded as evidence
        cur.execute(
            'INSERT INTO "EvidenceItem" ("SourceSystemID","EvidenceType","Category","Title",'
            '"State","ManualMetadata","IsSynthetic") VALUES (%s,%s,%s,%s,%s,%s,TRUE) '
            'RETURNING "EvidenceItemID"',
            (ssid, "financial_dataset" if financial else "digital_export", domain,
             f"{code} golden import sample", "available",
             Json({"import_template": code, "golden": True})))
        eid = int(cur.fetchone()[0])
        cur.execute(
            'INSERT INTO "IngestionJob" ("SourceSystemID","JobKind","Status","DryRun","Totals") '
            'VALUES (%s,%s,%s,TRUE,%s) RETURNING "IngestionJobID"',
            (ssid, "import", "dry_run", Json(totals)))
        job_id = int(cur.fetchone()[0])
        cur.execute(
            'INSERT INTO "ImportBatch" ("IngestionJobID","ImportTemplateVersionID","EvidenceItemID",'
            '"Domain","SourceFileName","SourceFormat","Status","DryRun","Totals","CreatedByActor") '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s) RETURNING "ImportBatchID"',
            (job_id, tvid, eid, domain, f"{code}.csv", "csv", "staged", Json(totals), "io.ramesh"))
        batch_id = int(cur.fetchone()[0])
        for row_no, mapped, status, reject in staging:
            cur.execute(
                'INSERT INTO "ImportStagingRow" ("ImportBatchID","RowNumber","MappedValues",'
                '"Status","RejectReason") VALUES (%s,%s,%s,%s,%s)',
                (batch_id, row_no, Json(mapped), status, reject))
    log(f"  import demo '{code}': batch {batch_id} staged ({totals})")


def seed_import_demo(conn, log=print) -> None:
    """Seed a couple of golden STAGED import batches (CDR + bank), each with a
    mix of valid / rejected / duplicate rows, if the Phase-8 tables exist."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.\"ImportBatch\"')")
        if cur.fetchone()[0] is None:
            log("  import demo skipped (migration 015 not applied)")
            return

    _seed_one(conn, "cdr_call_events", [
        (1, {"endpoint_a": "SYN-MSISDN-0000000001", "endpoint_b": "SYN-MSISDN-0000000002",
             "occurred_at": "2025-03-01T09:15:00", "duration_sec": 142, "comm_type": "call"}, "valid", None),
        (2, {"endpoint_a": "SYN-MSISDN-0000000001", "endpoint_b": "SYN-MSISDN-0000000003",
             "occurred_at": "2025-03-01T11:40:00", "duration_sec": 63, "comm_type": "call"}, "valid", None),
        (3, {"endpoint_a": "SYN-MSISDN-0000000003", "endpoint_b": None,
             "occurred_at": "2025-03-01T12:00:00", "comm_type": "call"}, "rejected",
         "endpoint_b: required (source column 'callee_msisdn')"),
    ], log=log)

    _seed_one(conn, "bank_transactions", [
        (1, {"source_account_no": "SYN-ACCT-0001", "destination_account_no": "SYN-ACCT-0002",
             "amount": 48000, "txn_timestamp": "2025-03-01T10:00:00", "channel": "imps"}, "valid", None),
        (2, {"source_account_no": "SYN-ACCT-0003", "destination_account_no": "SYN-ACCT-0002",
             "amount": 47000, "txn_timestamp": "2025-03-01T12:30:00", "channel": "imps"}, "valid", None),
        (3, {"source_account_no": "SYN-ACCT-0001", "destination_account_no": "SYN-ACCT-0002",
             "amount": 48000, "txn_timestamp": "2025-03-01T10:00:00", "channel": "imps"}, "duplicate",
         "duplicate of an earlier/committed row"),
    ], log=log)
    conn.commit()
