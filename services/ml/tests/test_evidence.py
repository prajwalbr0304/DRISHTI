"""Phase 5 evidence tests.

Two isolation strategies (mirroring test_intake.py):
  * S3 is NEVER really called — an in-memory FakeS3Gateway is injected into the
    service, so upload/complete/download run with zero AWS dependency.
  * DB write-path tests drive the real SQL against the live schema through the
    ``rw_rollback`` fixture and ROLL BACK — nothing is persisted.

Covers the Phase-5 test checklist: successful upload + manual metadata; duplicate
hash warning; invalid size/type; corrupt/missing object; interrupted+retried
upload; metadata correction; version replacement + immutable activity history;
short-lived (expiring) download URL; fixture-uploader hash verification; and
proof that an upload creates NO extracted fields and triggers NO prediction.
"""
import hashlib
import importlib.util
import pathlib
import uuid

import pytest

from app.config import get_settings
from app.evidence import service as svc
from app.evidence import guards
from app.evidence.s3 import (ObjectHead, ObjectNotFound, PresignedUpload,
                             build_object_key, key_in_prefix)
from app.evidence.schemas import (ArchiveRequest, CompleteUploadRequest,
                                   EvidenceCreateRequest, EvidenceMetadataUpdate,
                                   LinkRequest, UploadUrlRequest)
from app.evidence.service import EvidenceConflict, EvidenceValidationError

requires_db = pytest.mark.skipif(not get_settings().database_url,
                                 reason="DATABASE_URL not configured")


# ---------------------------------------------------------------------------
# In-memory S3 gateway (no AWS)
# ---------------------------------------------------------------------------
class FakeS3Gateway:
    bucket = "test-evidence-bucket"

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.presign_put_calls: list[tuple[str, int]] = []
        self.presign_get_calls: list[tuple[str, int, str]] = []
        self.deleted: list[str] = []

    def presign_put(self, key, expires_in):
        self.presign_put_calls.append((key, expires_in))
        return PresignedUpload(url=f"https://s3.test/{key}?put", method="PUT",
                               headers={}, storage_key=key, expires_in=expires_in)

    def presign_get(self, key, *, filename=None, content_type=None,
                    expires_in=900, disposition="attachment"):
        self.presign_get_calls.append((key, expires_in, disposition))
        return f"https://s3.test/{key}?get&exp={expires_in}&disp={disposition}"

    def head(self, key):
        if key not in self.store:
            return ObjectHead(exists=False)
        return ObjectHead(exists=True, size=len(self.store[key]),
                          content_type="application/octet-stream", etag="etag")

    def get_bytes(self, key, max_bytes):
        if key not in self.store:
            raise ObjectNotFound(key)
        return self.store[key][:max_bytes]

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)

    # test helper: simulate the browser's pre-signed PUT
    def browser_put(self, key, data: bytes):
        self.store[key] = data


def _case_id(conn) -> int:
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "CaseMaster" ORDER BY "CaseMasterID" LIMIT 1')
        return int(cur.fetchone()[0])


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _create(conn, case_id=None, etype="document", **kw):
    req = EvidenceCreateRequest(case_id=case_id, evidence_type=etype,
                                title=kw.pop("title", "Test evidence"),
                                uploader_actor="demo.investigator", **kw)
    item_id, warn = svc._create_item(conn, req)
    return item_id


def _upload(conn, item_id, gw, data: bytes, *, file_name="a.pdf",
            mime="application/pdf", declared_sha=None, declared_size=None,
            do_put=True):
    up = svc._issue_upload_url(conn, item_id, UploadUrlRequest(
        file_name=file_name, mime_type=mime, size_bytes=len(data),
        sha256=_sha(data)), gw)
    if do_put:
        gw.browser_put(up.storage_key, data)
    return svc._complete_upload(conn, item_id, CompleteUploadRequest(
        storage_key=up.storage_key, file_name=file_name, mime_type=mime,
        size_bytes=(declared_size if declared_size is not None else len(data)),
        sha256=(declared_sha if declared_sha is not None else _sha(data)),
        version_no=up.version_no), gw)


# ===========================================================================
# Pure unit tests (no DB, no AWS)
# ===========================================================================
def test_key_derivation_and_prefix_guard():
    key = build_object_key("evidence", 42, "SYN-EV-1", 1, "photo.jpg")
    assert key == "evidence/case-42/SYN-EV-1/v1/photo.jpg"
    assert key_in_prefix(key, "evidence")
    assert not key_in_prefix("other/x.jpg", "evidence")
    assert not key_in_prefix("evidence/../etc/passwd", "evidence")


def test_validate_upload_allow_list():
    with pytest.raises(EvidenceValidationError):
        svc._validate_upload("a.exe", "application/x-msdownload", 10)  # bad ext
    with pytest.raises(EvidenceValidationError):
        svc._validate_upload("a.pdf", "application/x-msdownload", 10)  # bad mime
    with pytest.raises(EvidenceValidationError):
        svc._validate_upload("a.pdf", "application/pdf", 0)            # empty
    with pytest.raises(EvidenceValidationError):
        svc._validate_upload("a.pdf", "application/pdf",
                             get_settings().evidence_max_bytes + 1)    # too large
    # valid: no raise
    svc._validate_upload("a.pdf", "application/pdf", 1234)


def test_hackathon_status_shape():
    st = guards.hackathon_status()
    assert st["environment_label"] == "Synthetic Hackathon Demo"
    assert "File contents are not automatically extracted." == st["extraction_disabled_note"]
    assert isinstance(st["allowed_extensions"], list) and "pdf" in st["allowed_extensions"]


# ===========================================================================
# DB write-path tests (rolled back) with the fake S3 gateway
# ===========================================================================
@requires_db
def test_create_draft_and_activity(rw_rollback):
    conn = rw_rollback
    cid = _case_id(conn)
    item_id = _create(conn, case_id=cid, title="Draft item")
    row = svc._item_row(conn, item_id)
    assert row[13] == "draft"                       # State
    item = svc._serialize_item(conn, item_id)
    assert item.case_master_id == cid
    assert [a.event_type for a in item.activity] == ["created"]
    assert any(cl.case_master_id == cid for cl in item.case_links)


@requires_db
def test_metadata_only_item_is_available(rw_rollback):
    conn = rw_rollback
    item_id = _create(conn, etype="external_reference", title="URL ref",
                      external_reference_url="https://synthetic.example/ref")
    assert svc._item_row(conn, item_id)[13] == "available"
    item = svc._serialize_item(conn, item_id)
    assert item.current_object is None


@requires_db
def test_successful_upload_and_metadata(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    item_id = _create(conn, case_id=_case_id(conn))
    assert svc._item_row(conn, item_id)[13] == "draft"
    data = b"SYNTHETIC-DRISHTI evidence pdf bytes"
    up_state_seen = []
    # issue url -> state uploading
    up = svc._issue_upload_url(conn, item_id, UploadUrlRequest(
        file_name="scene.pdf", mime_type="application/pdf", size_bytes=len(data),
        sha256=_sha(data)), gw)
    up_state_seen.append(svc._item_row(conn, item_id)[13])
    gw.browser_put(up.storage_key, data)
    done = svc._complete_upload(conn, item_id, CompleteUploadRequest(
        storage_key=up.storage_key, file_name="scene.pdf", mime_type="application/pdf",
        size_bytes=len(data), sha256=_sha(data), version_no=up.version_no), gw)
    assert up_state_seen == ["uploading"]
    assert done.sha256 == _sha(data)
    assert done.version_no == 1
    item = svc._serialize_item(conn, item_id)
    assert item.state == "available"
    assert item.current_object.sha256 == _sha(data)
    assert item.current_object.storage_status == "available"
    assert item.uploaded_at is not None
    assert [a.event_type for a in item.activity] == ["created", "upload_url_issued", "uploaded"]


@requires_db
def test_duplicate_hash_warning(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    cid = _case_id(conn)
    data = b"identical synthetic bytes " + uuid.uuid4().bytes
    a = _create(conn, case_id=cid, title="A")
    _upload(conn, a, gw, data)
    b = _create(conn, case_id=cid, title="B")
    done = _upload(conn, b, gw, data, file_name="b.pdf")
    assert done.duplicate_warning is not None
    assert a in done.duplicate_of_item_ids


@requires_db
def test_invalid_size_and_type_rejected(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    item_id = _create(conn, case_id=_case_id(conn))
    with pytest.raises(EvidenceValidationError):
        svc._issue_upload_url(conn, item_id, UploadUrlRequest(
            file_name="x.exe", mime_type="application/x-msdownload", size_bytes=5), gw)
    with pytest.raises(EvidenceValidationError):
        svc._issue_upload_url(conn, item_id, UploadUrlRequest(
            file_name="x.pdf", mime_type="application/pdf",
            size_bytes=get_settings().evidence_max_bytes + 1), gw)


@requires_db
def test_missing_object_marks_failed(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    item_id = _create(conn, case_id=_case_id(conn))
    with pytest.raises(EvidenceValidationError):
        _upload(conn, item_id, gw, b"never uploaded", do_put=False)  # object absent
    assert svc._item_row(conn, item_id)[13] == "failed"
    item = svc._serialize_item(conn, item_id)
    assert any(a.event_type == "failed" for a in item.activity)


@requires_db
def test_corrupt_hash_mismatch_marks_failed(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    item_id = _create(conn, case_id=_case_id(conn))
    data = b"real synthetic bytes"
    with pytest.raises(EvidenceValidationError):
        _upload(conn, item_id, gw, data, declared_sha="deadbeef" * 8)  # wrong hash
    assert svc._item_row(conn, item_id)[13] == "failed"


@requires_db
def test_size_mismatch_marks_failed(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    item_id = _create(conn, case_id=_case_id(conn))
    with pytest.raises(EvidenceValidationError):
        _upload(conn, item_id, gw, b"ten bytes!", declared_size=999)  # stored != declared
    assert svc._item_row(conn, item_id)[13] == "failed"


@requires_db
def test_interrupted_then_retried_upload(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    item_id = _create(conn, case_id=_case_id(conn))
    data = b"retry synthetic bytes"
    # first attempt: object missing -> failed
    with pytest.raises(EvidenceValidationError):
        _upload(conn, item_id, gw, data, do_put=False)
    assert svc._item_row(conn, item_id)[13] == "failed"
    # retry: now the browser PUT succeeds -> available
    done = _upload(conn, item_id, gw, data, do_put=True)
    assert done.version_no == 1
    assert svc._item_row(conn, item_id)[13] == "available"


@requires_db
def test_metadata_correction_is_appended_not_overwritten(rw_rollback):
    conn = rw_rollback
    item_id = _create(conn, case_id=_case_id(conn), title="Old title")
    before = len(svc._serialize_item(conn, item_id).activity)
    svc._update_metadata(conn, item_id, EvidenceMetadataUpdate(
        title="Corrected title", tags=["synthetic", "corrected"],
        change_reason="fix typo", actor="demo.supervisor"))
    item = svc._serialize_item(conn, item_id)
    assert item.title == "Corrected title"
    assert "corrected" in item.tags
    # history grew (append-only); the original 'created' event is still first
    assert len(item.activity) == before + 1
    assert item.activity[0].event_type == "created"
    assert item.activity[-1].event_type == "metadata_updated"


@requires_db
def test_version_replacement_and_immutable_history(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    item_id = _create(conn, case_id=_case_id(conn))
    _upload(conn, item_id, gw, b"version one bytes", file_name="v1.pdf")
    v1 = svc._serialize_item(conn, item_id)
    v1_version_row = next(v for v in v1.versions if v.version_no == 1)
    # replace with a new version
    done2 = _upload(conn, item_id, gw, b"version two bytes now", file_name="v2.pdf")
    assert done2.version_no == 2
    item = svc._serialize_item(conn, item_id)
    assert item.current_object.version_no == 2
    assert len(item.objects) == 2
    assert len(item.versions) == 2
    # v1 version row is unchanged (immutable)
    v1_after = next(v for v in item.versions if v.version_no == 1)
    assert v1_after.evidence_version_id == v1_version_row.evidence_version_id
    assert v1_after.created_at == v1_version_row.created_at
    # exactly one v1 object remains, no longer current
    v1_obj = next(o for o in item.objects if o.version_no == 1)
    assert v1_obj.is_current is False
    # activity kept both upload events
    kinds = [a.event_type for a in item.activity]
    assert kinds.count("uploaded") == 1 and kinds.count("version_added") == 1


@requires_db
def test_download_url_is_short_lived(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    item_id = _create(conn, case_id=_case_id(conn))
    _upload(conn, item_id, gw, b"downloadable synthetic bytes")
    resp = svc._download_url(conn, item_id, None, "demo.analyst", gw)
    expiry = get_settings().s3_presign_expiry_s
    assert resp.expires_in == expiry
    assert expiry <= 3600                              # short-lived
    # the gateway was asked for exactly that (expiring) lifetime
    assert gw.presign_get_calls and gw.presign_get_calls[-1][1] == expiry
    item = svc._serialize_item(conn, item_id)
    assert any(a.event_type == "download" for a in item.activity)


@requires_db
def test_archive_then_restore(rw_rollback):
    conn = rw_rollback
    gw = FakeS3Gateway()
    item_id = _create(conn, case_id=_case_id(conn))
    _upload(conn, item_id, gw, b"archivable bytes")
    svc._archive(conn, item_id, ArchiveRequest(reason="demo", actor="demo.super_admin"))
    assert svc._item_row(conn, item_id)[13] == "archived"
    # archived items cannot be edited
    with pytest.raises(EvidenceConflict):
        svc._update_metadata(conn, item_id, EvidenceMetadataUpdate(title="nope"))
    svc._restore(conn, item_id, "demo.super_admin")
    assert svc._item_row(conn, item_id)[13] == "available"   # has an object -> available


@requires_db
def test_link_and_unlink_second_case(rw_rollback):
    conn = rw_rollback
    with conn.cursor() as cur:
        cur.execute('SELECT "CaseMasterID" FROM "CaseMaster" ORDER BY "CaseMasterID" LIMIT 2')
        c1, c2 = [int(r[0]) for r in cur.fetchall()]
    item_id = _create(conn, case_id=c1)
    svc._link(conn, item_id, LinkRequest(case_id=c2, link_type="related"))
    item = svc._serialize_item(conn, item_id)
    assert {cl.case_master_id for cl in item.case_links} == {c1, c2}
    svc._unlink(conn, item_id, c2, None, "demo.investigator")
    item = svc._serialize_item(conn, item_id)
    assert {cl.case_master_id for cl in item.case_links} == {c1}


@requires_db
def test_upload_creates_no_extracted_fields_and_no_prediction(rw_rollback):
    """An upload must not create extracted/canonical fields or a model inference."""
    conn = rw_rollback
    gw = FakeS3Gateway()

    def _count(table):
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            return int(cur.fetchone()[0])

    inf_before = _count("ModelInference")
    risk_before = _count("CrimeRiskScore")
    item_id = _create(conn, case_id=_case_id(conn))
    _upload(conn, item_id, gw, b"no extraction should happen from these bytes")
    assert _count("ModelInference") == inf_before        # no prediction
    assert _count("CrimeRiskScore") == risk_before
    item = svc._serialize_item(conn, item_id)
    # metadata is purely manual — no OCR/extraction/transcript keys
    banned = {"extracted", "ocr", "ocr_text", "transcript", "extracted_fields", "entities"}
    assert not (set(item.manual_metadata.keys()) & banned)


@requires_db
def test_legacy_migration_idempotent(rw_rollback):
    conn = rw_rollback
    cid = _case_id(conn)
    # seed one legacy CaseEvidence row (rolled back with the test)
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "CaseEvidence" ("CaseMasterID","EvidenceType","Title","Description","Reference","CreatedByRole") '
            'VALUES (%s,%s,%s,%s,%s,%s) RETURNING "EvidenceID"',
            (cid, "seizure", "Legacy seizure memo", "desc", "SEIZ-TEST-1", "investigator"))
        leg_id = int(cur.fetchone()[0])
    res = svc._migrate_legacy(conn, cid, "demo.super_admin")
    assert res.migrated >= 1
    # the migrated item carries the legacy marker + mapped type
    with conn.cursor() as cur:
        cur.execute("SELECT \"EvidenceType\",\"ManualMetadata\"->>'legacy_ref' FROM \"EvidenceItem\" "
                    "WHERE \"ManualMetadata\"->>'legacy_ref' = %s", (f"CaseEvidence:{leg_id}",))
        row = cur.fetchone()
    assert row is not None and row[0] == "property_item"      # seizure -> property_item
    # re-run: already migrated -> skipped, not duplicated
    res2 = svc._migrate_legacy(conn, cid, "demo.super_admin")
    assert res2.skipped_existing >= 1


# ===========================================================================
# Fixture uploader (datagen) — hash verification, no AWS
# ===========================================================================
def _load_uploader():
    import sys
    path = pathlib.Path(__file__).resolve().parents[3] / "datagen" / "upload_evidence_s3.py"
    spec = importlib.util.spec_from_file_location("upload_evidence_s3", path)
    mod = importlib.util.module_from_spec(spec)
    # register before exec so the module's @dataclass (with `from __future__ import
    # annotations`) can resolve its own module namespace during class processing.
    sys.modules["upload_evidence_s3"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_fixture_uploader_hash_verification(tmp_path):
    up = _load_uploader()
    data = b"SYNTHETIC fixture bytes for hash round-trip"
    sha = up.sha256_bytes(data)
    # a dict-backed "storage" verifies the round-trip helper end to end
    store = {"evidence/fixtures/golden-001/SYN-EV-1/f.pdf": data}

    def get_bytes(key, max_bytes):
        return store[key][:max_bytes]

    key = up.derive_key("evidence", "golden-001", "SYN-EV-1", "f.pdf")
    assert key == "evidence/fixtures/golden-001/SYN-EV-1/f.pdf"
    assert up.verify_roundtrip(get_bytes, key, sha, 1_000_000) is True
    # a corrupted object fails verification
    store[key] = data + b"tampered"
    assert up.verify_roundtrip(get_bytes, key, sha, 1_000_000) is False


def test_fixture_uploader_reads_manifest():
    up = _load_uploader()
    run_dir = pathlib.Path(__file__).resolve().parents[3] / "datagen" / "fixtures" / "golden-001"
    if not run_dir.exists():
        pytest.skip("golden-001 fixtures not present")
    objs = up.load_fixture_objects(str(run_dir))
    assert len(objs) > 0
    # every listed object exists on disk and its recorded hash matches the file
    sample = objs[0]
    assert up.sha256_file(sample.path) == sample.sha256


# ===========================================================================
# API surface (read + guard rejections only — no committed writes)
# ===========================================================================
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_status_endpoint():
    r = client.get("/evidence/status", headers={"X-Role": "investigator"})
    assert r.status_code == 200
    body = r.json()
    assert body["environment_label"] == "Synthetic Hackathon Demo"
    assert "pdf" in body["allowed_extensions"]


def test_lookups_endpoint():
    r = client.get("/evidence/lookups", headers={"X-Role": "investigator"})
    assert r.status_code == 200
    assert any(t["value"] == "document" for t in r.json()["evidence_types"])


def test_policymaker_denied_evidence():
    assert client.get("/evidence/items", headers={"X-Role": "policymaker"}).status_code == 403
    r = client.post("/evidence/items", headers={"X-Role": "policymaker"},
                    json={"title": "x", "evidence_type": "document"})
    assert r.status_code == 403


def test_upload_url_requires_s3_config():
    # S3_EVIDENCE_BUCKET is unset in the test env -> upload is 503 (metadata-only mode).
    if get_settings().s3_configured():
        pytest.skip("S3 configured in this environment")
    r = client.post("/evidence/items/1/upload-url", headers={"X-Role": "investigator"},
                    json={"file_name": "a.pdf", "mime_type": "application/pdf", "size_bytes": 10})
    assert r.status_code == 503


@requires_db
def test_items_list_read():
    r = client.get("/evidence/items", headers={"X-Role": "investigator"},
                   params={"page_size": 5})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "by_state" in body
