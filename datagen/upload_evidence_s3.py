#!/usr/bin/env python
"""Upload the already-digital golden-fixture evidence files to the private S3
bucket and reconcile their EvidenceObject metadata — DRISHTI Phase 5 datagen
integration.

What it does (idempotent + safe):
  1. Confirms the target DB is marked synthetic (read-only check) before any write.
  2. Reads datagen/fixtures/<run>/evidence_manifest.json.
  3. For each file present on disk: recomputes SHA-256 and asserts it matches the
     manifest (fixture self-integrity).
  4. Uploads the file to  <prefix>/fixtures/<run>/<ref>/<filename>  in the bucket.
  5. Re-reads the object (head + bounded get) and verifies the round-trip SHA-256
     equals the local hash (upload integrity).
  6. With --update-db: reconciles a still-'fixture_pending_cloud_upload'
     EvidenceObject row (matched by SHA-256, one per file) to StorageStatus
     'available' + the real s3:// key, sets its EvidenceItem to 'available', and
     appends an append-only 'uploaded' EvidenceActivityEvent.

No OCR/extraction. No file bytes in PostgreSQL. No secrets printed. Credentials
come from the environment / SSO profile / task role.

Usage (PowerShell):
    aws sso login --profile drishti
    python datagen/upload_evidence_s3.py --run golden-001 `
        --bucket <name> --region ap-south-1 --profile drishti --update-db

    # preview only, no S3/DB writes:
    python datagen/upload_evidence_s3.py --run golden-001 --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from typing import Callable, Optional

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:  # pragma: no cover
    pass

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SYNTHETIC_MARKER_EXPECTED = os.environ.get("SYNTHETIC_ENV_EXPECTED", "synthetic_hackathon")


# ---------------------------------------------------------------------------
# Pure, testable helpers
# ---------------------------------------------------------------------------
@dataclass
class FixtureObject:
    ref: str
    file: str
    sha256: str
    size: int
    type: str
    path: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_fixture_objects(run_dir: str) -> list[FixtureObject]:
    """Manifest entries whose file actually exists on disk."""
    manifest_path = os.path.join(run_dir, "evidence_manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        objects = json.load(fh).get("objects", [])
    out: list[FixtureObject] = []
    for o in objects:
        p = os.path.join(run_dir, o["file"])
        if os.path.isfile(p):
            out.append(FixtureObject(ref=o["ref"], file=o["file"], sha256=o["sha256"],
                                     size=int(o.get("size", 0)), type=o.get("type", "document"),
                                     path=p))
    return out


def derive_key(prefix: str, run: str, ref: str, filename: str) -> str:
    return f"{prefix.strip('/')}/fixtures/{run}/{ref}/{filename}"


def verify_roundtrip(get_bytes: Callable[[str, int], bytes], key: str,
                     expected_sha: str, max_bytes: int) -> bool:
    """Read the stored object back and confirm its SHA-256 matches. ``get_bytes``
    is any (key, max_bytes) -> bytes callable (S3 in prod, a dict in tests)."""
    data = get_bytes(key, max_bytes)
    return sha256_bytes(data) == expected_sha


# ---------------------------------------------------------------------------
# AWS + DB wiring
# ---------------------------------------------------------------------------
def _s3_client(profile: str, region: str):
    import boto3
    from botocore.config import Config
    session = boto3.Session(profile_name=profile or None, region_name=region)
    return session.client("s3", config=Config(signature_version="s3v4"))


def _db_connect():
    import psycopg2
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg2.connect(url, connect_timeout=int(os.environ.get("DB_CONNECT_TIMEOUT", "15")))


def _confirm_synthetic(conn) -> bool:
    """Read the synthetic marker without putting the connection into read-only
    mode (autocommit read), so the later write session stays writable."""
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute('SELECT "Value" FROM "synthetic_meta" WHERE "Key"=%s', ("app_environment",))
            row = cur.fetchone()
        return bool(row and row[0] == SYNTHETIC_MARKER_EXPECTED)
    except Exception:  # noqa: BLE001
        return False
    finally:
        conn.autocommit = False


def _reconcile_db(conn, *, sha: str, bucket: str, key: str, filename: str,
                  mime: Optional[str], size: int) -> Optional[int]:
    """Flip ONE still-pending EvidenceObject with this hash to available + real
    key; set its item available; append an 'uploaded' activity. Returns the
    EvidenceObjectID updated, or None if none pending (idempotent)."""
    storage_key = f"s3://{bucket}/{key}"
    with conn.cursor() as cur:
        cur.execute(
            'SELECT "EvidenceObjectID","EvidenceItemID" FROM "EvidenceObject" '
            'WHERE "Sha256"=%s AND "StorageStatus"=\'fixture_pending_cloud_upload\' '
            'ORDER BY "EvidenceObjectID" LIMIT 1', (sha,))
        row = cur.fetchone()
        if not row:
            return None
        obj_id, item_id = int(row[0]), int(row[1])
        cur.execute(
            'UPDATE "EvidenceObject" SET "StorageStatus"=\'available\', "StorageKey"=%s, '
            '"FileName"=%s, "SizeBytes"=%s WHERE "EvidenceObjectID"=%s',
            (storage_key, filename, size, obj_id))
        cur.execute(
            'UPDATE "EvidenceItem" SET "State"=\'available\', "UploadedAt"=now() '
            'WHERE "EvidenceItemID"=%s AND "State" <> \'archived\'', (item_id,))
        from psycopg2.extras import Json
        cur.execute(
            'INSERT INTO "EvidenceActivityEvent" ("EvidenceItemID","EventType","Actor","Detail") '
            'VALUES (%s,%s,%s,%s)',
            (item_id, "uploaded", "datagen.fixture_uploader",
             Json({"storage_key": storage_key, "sha256": sha, "source": "golden_fixture"})))
    return obj_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Upload golden evidence fixtures to S3 + reconcile metadata.")
    ap.add_argument("--run", default="golden-001", help="fixtures/<run> directory")
    ap.add_argument("--bucket", default=os.environ.get("S3_EVIDENCE_BUCKET", ""))
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-south-1"))
    ap.add_argument("--profile", default=os.environ.get("AWS_PROFILE", ""))
    ap.add_argument("--prefix", default=os.environ.get("S3_EVIDENCE_PREFIX", "evidence"))
    ap.add_argument("--limit", type=int, default=0, help="cap number of files (0 = all)")
    ap.add_argument("--max-verify-bytes", type=int, default=52_428_800)
    ap.add_argument("--update-db", action="store_true", help="reconcile EvidenceObject metadata")
    ap.add_argument("--dry-run", action="store_true", help="no S3/DB writes; list + verify local hashes only")
    args = ap.parse_args(argv)

    run_dir = os.path.join(_FIXTURES_DIR, args.run)
    if not os.path.isdir(run_dir):
        print(f"ERROR: fixture dir not found: {run_dir}", file=sys.stderr)
        return 2
    objects = load_fixture_objects(run_dir)
    if args.limit:
        objects = objects[: args.limit]
    print(f"[info] {len(objects)} fixture file(s) present in {args.run}")

    # 1. fixture self-integrity (always, even in dry-run)
    integrity_ok, integrity_bad = 0, 0
    for o in objects:
        if sha256_file(o.path) == o.sha256:
            integrity_ok += 1
        else:
            integrity_bad += 1
            print(f"[warn] local hash mismatch for {o.file}")
    print(f"[info] fixture self-integrity: {integrity_ok} ok, {integrity_bad} mismatched")

    if args.dry_run:
        for o in objects[:5]:
            print(f"  WOULD upload {o.file} -> "
                  f"s3://{args.bucket or '<bucket>'}/{derive_key(args.prefix, args.run, o.ref, o.file)}")
        print("DRY-RUN — no S3/DB writes.")
        return 0

    if not args.bucket:
        print("ERROR: --bucket (or S3_EVIDENCE_BUCKET) is required for a real upload.", file=sys.stderr)
        return 2

    # DB synthetic guard (before any DB write)
    conn = None
    if args.update_db:
        try:
            conn = _db_connect()
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: DB connect failed: {type(exc).__name__}", file=sys.stderr)
            return 2
        if not _confirm_synthetic(conn):
            print(f"ERROR: DB is not marked '{SYNTHETIC_MARKER_EXPECTED}'. Refusing to update metadata.",
                  file=sys.stderr)
            conn.close()
            return 2
        # allow writes on this connection even if a read-only default is inherited
        conn.autocommit = True
        with conn.cursor() as cur:
            try:
                cur.execute("SET SESSION default_transaction_read_only = off")
            except Exception:  # noqa: BLE001
                pass
        conn.autocommit = False

    try:
        s3 = _s3_client(args.profile, args.region)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR creating S3 client (is the SSO session valid?): {type(exc).__name__}", file=sys.stderr)
        if conn:
            conn.close()
        return 2

    def _get_bytes(key: str, max_bytes: int) -> bytes:
        r = s3.get_object(Bucket=args.bucket, Key=key, Range=f"bytes=0-{max_bytes - 1}")
        return r["Body"].read(max_bytes)

    uploaded, verified, db_updated, errors = 0, 0, 0, 0
    import mimetypes
    for o in objects:
        key = derive_key(args.prefix, args.run, o.ref, o.file)
        mime = mimetypes.guess_type(o.file)[0]
        try:
            with open(o.path, "rb") as fh:
                s3.put_object(Bucket=args.bucket, Key=key, Body=fh.read(),
                              ContentType=mime or "application/octet-stream")
            uploaded += 1
            if verify_roundtrip(_get_bytes, key, o.sha256, args.max_verify_bytes):
                verified += 1
            else:
                errors += 1
                print(f"[warn] round-trip hash mismatch for {o.file}")
                continue
            if conn is not None:
                obj_id = _reconcile_db(conn, sha=o.sha256, bucket=args.bucket, key=key,
                                       filename=o.file, mime=mime, size=o.size)
                if obj_id is not None:
                    db_updated += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"[warn] failed {o.file}: {type(exc).__name__}")
    if conn is not None:
        conn.commit()
        conn.close()

    print(json.dumps({
        "run": args.run, "bucket": args.bucket, "prefix": args.prefix,
        "fixture_files": len(objects), "self_integrity_ok": integrity_ok,
        "uploaded": uploaded, "hash_verified": verified,
        "db_rows_reconciled": db_updated, "errors": errors,
    }, indent=1))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
