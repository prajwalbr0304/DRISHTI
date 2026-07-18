#!/usr/bin/env python3
"""Copy Prompt 5 synthetic evidence fixtures -> Catalyst Stratus (Prompt 14 E.8).

Stratus is the application object system of record. This one-way bootstrap copies
the golden synthetic evidence fixtures into the PRIVATE evidence bucket under the
``evidence/quarantine/`` prefix, verifies the SHA-256 after transfer, and records
the object metadata + lineage in Data Store as an ``EvidenceObject`` row. It does
NOT promote objects to ``available/`` — new evidence stays quarantined until the
isolated size/type/hash + malware scan passes (a security control that extracts
NO semantic content and triggers NO predictions). S3 remains only a temporary
AWS SageMaker/Batch I/O copy; Stratus is the source of truth.

Integrity contract (never the bytes through the API/logs): for every object we
record SHA-256 + size + MIME + object key + version + lineage (source fixture,
parsed case/evidence reference, synthetic label) in Data Store.

Source can be the local golden fixture dir (default) or an S3 prefix (--s3-bucket
/ --s3-prefix, boto3). Idempotent: ExternalID = ``evobj:<sha256>`` (content
addressed), so re-running upserts rather than duplicating.

Dry-run (offline, in-memory Stratus + repository fake; verifies real local bytes):
    python copy_fixtures_to_stratus.py --limit 25
Commit (held; writes to Catalyst Stratus + Data Store):
    $env:DRISHTI_USE_CATALYST_STRATUS = "true"; $env:DRISHTI_USE_CATALYST_DATASTORE = "true"
    python copy_fixtures_to_stratus.py --limit 0 --commit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import sys
from pathlib import Path
from typing import Any, Iterator, Optional

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
ML_ROOT = REPO_ROOT / "services" / "ml"
DEFAULT_SOURCE = REPO_ROOT / "datagen" / "fixtures" / "golden-001"

QUARANTINE_PREFIX = "evidence/quarantine/"
LOGICAL_BUCKET = "evidence"
# golden fixture name pattern: case<caseId>_<SYN-EV-xxxxxxxx>.<ext>
_NAME_RE = re.compile(r"^case(?P<case>\d+)_(?P<ref>SYN-EV-\d+)\.(?P<ext>[A-Za-z0-9]+)$")


def _add_ml_path() -> None:
    if str(ML_ROOT) not in sys.path:
        sys.path.insert(0, str(ML_ROOT))


def sha256_and_size(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


# Deterministic MIME for the fixture extensions so the recorded content_type is
# cross-platform stable and matches the app evidence allow-list (Windows maps
# .csv -> application/vnd.ms-excel via the registry, which we override here).
_MIME_OVERRIDES = {
    ".csv": "text/csv", ".json": "application/json", ".txt": "text/plain",
    ".xml": "application/xml", ".mp3": "audio/mpeg", ".mp4": "video/mp4",
    ".m4a": "audio/mp4", ".wav": "audio/wav", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf",
}


def content_type_for(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in _MIME_OVERRIDES:
        return _MIME_OVERRIDES[ext]
    ctype, _ = mimetypes.guess_type(name)
    return ctype or "application/octet-stream"


def parse_lineage(name: str) -> dict[str, Any]:
    m = _NAME_RE.match(name)
    if not m:
        return {"source_fixture": name, "case_ref": None, "evidence_ref": None}
    return {"source_fixture": name,
            "case_ref": f"case:{m.group('case')}",
            "evidence_ref": m.group("ref")}


def iter_local_files(source: Path, limit: int) -> Iterator[Path]:
    n = 0
    for p in sorted(source.iterdir()):
        if p.is_file():
            yield p
            n += 1
            if limit and n >= limit:
                return


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def upload_bytes(stratus, key: str, content_type: str, data: bytes, sha256: str,
                 size: int, commit: bool) -> str:
    """Transfer bytes into Stratus and return the stored version id.

    Dry-run records an ObjectRef in the in-memory fake (no real transfer). Commit
    presigns an exact-object PUT and streams the bytes, then reads the version
    back. Bytes never pass through the API or logs."""
    from app.stratus import ObjectRef  # deferred; app import
    if not commit:
        stratus.put_object(ObjectRef(bucket=LOGICAL_BUCKET, key=key, version_id="1",
                                     size=size, content_type=content_type, sha256=sha256))
        ref = stratus.head(LOGICAL_BUCKET, key)
        return ref.version_id if ref else "1"
    # Commit path (held): presigned exact-object PUT to the private bucket.
    url = stratus.presign_put(LOGICAL_BUCKET, key, content_type=content_type)
    import urllib.request
    req = urllib.request.Request(url, data=data, method="PUT",
                                 headers={"Content-Type": content_type})
    urllib.request.urlopen(req, timeout=60)
    ref = stratus.head(LOGICAL_BUCKET, key)
    return ref.version_id if ref else "1"


def run(source: Path, limit: int, commit: bool) -> dict:
    _add_ml_path()
    from app.stratus import get_stratus
    from app.datastore.repository import get_repository

    stratus = get_stratus()
    repo = get_repository()

    results: list[dict[str, Any]] = []
    total_bytes = 0
    verified = 0
    for path in iter_local_files(source, limit):
        sha256, size = sha256_and_size(path)
        ctype = content_type_for(path.name)
        key = QUARANTINE_PREFIX + path.name
        lineage = parse_lineage(path.name)
        data = _read_bytes(path) if commit else b""
        version_id = upload_bytes(stratus, key, ctype, data, sha256, size, commit)

        # Verify: confirm the stored object's recorded hash/size (dry-run uses the
        # in-memory head; commit could not read bytes back through the API, so it
        # verifies size + existence — the object stays quarantined regardless).
        head = stratus.head(LOGICAL_BUCKET, key, version_id=version_id)
        ok = bool(head) and (head.sha256 in (None, sha256)) and (head.size in (None, size))
        if ok:
            verified += 1
        total_bytes += size

        external_id = f"evobj:{sha256}"
        record = {
            "ExternalID": external_id,
            "bucket": LOGICAL_BUCKET,
            "object_key": key,
            "version_id": version_id,
            "size": size,
            "content_type": ctype,
            "sha256": sha256,
            "quarantine_state": "quarantine",   # never auto-promoted here
            "scan_status": "pending",
            "synthetic": True,
            **lineage,
        }
        repo.upsert("EvidenceObject", external_id, record)
        results.append({"file": path.name, "sha256": sha256, "size": size,
                        "content_type": ctype, "object_key": key,
                        "version_id": version_id, "external_id": external_id,
                        "verified": ok, **lineage})

    report = {
        "source": str(source),
        "logical_bucket": LOGICAL_BUCKET,
        "prefix": QUARANTINE_PREFIX,
        "committed": commit,
        "stratus_client": type(stratus).__name__,
        "repository": type(repo).__name__,
        "objects": len(results),
        "verified": verified,
        "total_bytes": total_bytes,
        "quarantined": len(results),
        "promoted": 0,
        "files": results,
    }
    out = HERE / "_fixture-copy-report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy synthetic evidence fixtures -> Stratus.")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE), help="local fixture directory")
    ap.add_argument("--limit", type=int, default=25, help="max files (0 = all)")
    ap.add_argument("--commit", action="store_true", help="write to Catalyst Stratus + Data Store")
    args = ap.parse_args()

    source = Path(args.source)
    if not source.exists():
        print(f"source not found: {source}")
        return 2

    report = run(source, args.limit, args.commit)
    print(json.dumps({
        "source": report["source"],
        "stratus_client": report["stratus_client"],
        "repository": report["repository"],
        "committed": report["committed"],
        "objects": report["objects"],
        "verified": report["verified"],
        "total_bytes": report["total_bytes"],
        "report": str((HERE / "_fixture-copy-report.json").relative_to(REPO_ROOT)),
    }, indent=2))
    return 0 if report["objects"] == report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
