# PHASE 05 REPORT — Digital evidence upload, S3 storage, manual metadata, evidence UI

Status: **Complete**
Date: 2026-07-17
Target DB: AWS RDS PostgreSQL (`drishti-db.…ap-south-1.rds.amazonaws.com/drishti`), marked `synthetic_meta.app_environment = synthetic_hackathon`.
Evidence store: **Amazon S3** private bucket in `ap-south-1` (AWS account `860510875713`, SSO profile `drishti`).
Mode: synthetic hackathon demo only.

> No secret values (DB password, AWS keys/tokens, connection strings) are printed,
> logged, committed, or reproduced in this report or the code. Credentials come
> from the environment / SSO profile / task role. The browser never receives AWS
> credentials — it uses only short-lived, exact-object pre-signed URLs.

---

## 1. Outcome summary

Implemented the full hackathon digital-evidence platform: already-digital files
are stored in a **private, versioned, encrypted S3 bucket**; only **manually
entered** metadata + provenance live in PostgreSQL. File bytes never touch
PostgreSQL, are never parsed (no OCR/transcription/extraction), and an upload
**never** triggers a prediction. Browser ⇄ S3 transfers use short-expiry
pre-signed URLs minted by FastAPI after it authorises the request.

| Definition of Done | Result |
|---|---|
| Already-digital synthetic evidence can be uploaded to private S3 | Verified live: 1,365 golden fixtures uploaded + round-trip SHA-256 verified; a live create→presign PUT→head→hash→presign GET→expiry→delete round-trip passes |
| Every file has manually entered metadata, a hash, a version and activity history | `EvidenceItem` (manual metadata) + `EvidenceObject` (system SHA-256/size/MIME) + `EvidenceVersion` + append-only `EvidenceActivityEvent`; enforced + tested |
| Evidence UI supports upload, metadata editing, linking, versioning and download | New `EvidencePage` (dropzone + manual form + progress/cancel/retry, list, details/activity timeline, preview, short-lived download, correction, link/unlink, archive/restore) |
| No OCR/transcription/extraction dependency or automatic prediction is present | No extraction code/deps added; test asserts zero `ModelInference`/`CrimeRiskScore` rows created by an upload and no extracted metadata keys |

---

## 2. Files and migrations changed

### New SQL migration
- `services/ml/sql/013_evidence_activity_lifecycle.sql` — widens the
  `EvidenceActivityEvent.EventType` allow-list with the Phase-5 lifecycle verbs
  (`upload_url_issued`, `uploaded`, `failed`, `restored`, `reset`); adds indexes
  `idx_evidenceitem_case_created`, `idx_evidenceobject_item_current`,
  `idx_evidenceobject_status`, `idx_evidenceactivity_item_created`; re-runs
  `fn_disable_rls_all_app()` + `fn_assert_rls_disabled()` (RLS stays disabled +
  NO FORCE; no policies). Additive + idempotent (applied twice, no error).

### New backend module `services/ml/app/evidence/`
`__init__.py`, `s3.py` (injectable `S3Gateway` protocol + `Boto3S3Gateway`
SigV4 impl + `build_object_key`/`key_in_prefix`/`sanitize_filename`),
`guards.py` (role/localhost/synthetic/S3-config gates + `hackathon_status`),
`schemas.py` (typed request/response models), `service.py` (full lifecycle:
create, upload-url, complete+hash-verify, versions, activity, link/unlink,
metadata correction, archive/restore, download-url, legacy migration, synthetic
reset), `router.py` (16 endpoints, typed-error translation).

### Modified backend
- `services/ml/app/main.py` — register `evidence_router`.
- `services/ml/app/config.py` — AWS/S3 settings (`aws_region`, `aws_profile`,
  `s3_evidence_bucket`, `s3_evidence_prefix`, `s3_endpoint_url`,
  `s3_presign_expiry_s`, `evidence_max_bytes`, `evidence_allowed_extensions`,
  `evidence_allowed_mime`, `evidence_hash_verify_max_bytes`) + helpers
  `s3_configured()`, `evidence_allowed_ext_set()`, `evidence_allowed_mime_set()`.
- `services/ml/requirements.txt` — add `boto3>=1.34`.
- `.env.example` — documented AWS/S3 variables (names + safe examples only).

### New infrastructure + datagen
- `infra/aws/provision_evidence_bucket.py` — idempotent bucket provisioner
  (`--check`/`--dry-run`; private + versioned + SSE + TLS-only + CORS + lifecycle).
- `datagen/upload_evidence_s3.py` — fixture uploader (synthetic-marker guard,
  fixture self-integrity, upload, round-trip hash verify, `--update-db`
  reconcile of pending `EvidenceObject` rows; `--dry-run`/`--limit`).

### New / modified frontend `web/src/`
- `api/endpoints/evidence.ts` (new) wired into `api/index.ts` as `api.evidence`;
  `api/types.ts` appended with `Ev*` types (namespaced to avoid clashing with the
  legacy `CaseEvidence` types).
- `lib/evidenceUpload.ts` (new) — `sha256Hex`, `putToPresignedUrl` (XHR progress/
  cancel), `formatBytes`.
- `routes/cases/subpages/EvidencePage.tsx` — **replaced** the metadata-only page.
- `routes/cases/subpages/evidence/` — `evidenceShared.ts`, `AddEvidenceDialog.tsx`,
  `EvidenceDetailsDialog.tsx`.
- Tests: `lib/evidenceUpload.test.ts`, `routes/cases/subpages/evidence/evidenceShared.test.ts`,
  `routes/cases/subpages/EvidencePage.test.tsx`.

### New backend tests
- `services/ml/tests/test_evidence.py` (26 tests).

---

## 3. Database objects / endpoints / screens added

### Database (migration 013)
- Widened `EvidenceActivityEvent.EventType` CHECK; 4 new indexes; RLS-disabled
  assertion. (The evidence tables themselves — `EvidenceItem`, `EvidenceObject`,
  `EvidenceVersion`, `EvidenceCaseLink`, `EvidenceActivityEvent`,
  `EvidenceEntityLink` — already existed from Phase 1 migrations 006/007.)

### API endpoints (prefix `/evidence`)
Read (role: any except policymaker): `GET /status`, `GET /lookups`,
`GET /items`, `GET /items/{id}`, `GET /items/{id}/activity`.
Write (investigator/supervisor/super_admin + localhost + synthetic-DB guard):
`POST /items`, `PUT /items/{id}`, `POST /items/{id}/links`,
`DELETE /items/{id}/links`, `POST /items/{id}/archive`, `POST /items/{id}/restore`,
`POST /migrate-legacy`.
Write + S3 required: `POST /items/{id}/upload-url`, `POST /items/{id}/complete`,
`POST /items/{id}/download-url`.
Admin only: `POST /reset` (synthetic-demo reset; requires `confirm=true`).

### Screens (case Evidence sub-page)
Evidence list (type, title, source, captured date, tags, version, short hash,
state) with state-filter tabs + search; "Add evidence" dialog (drag/drop + manual
metadata form, upload progress/cancel/retry); details dialog (current file +
SHA-256, safe-format preview, short-lived download, versions, linked cases/
entities with unlink, append-only activity timeline, metadata correction,
archive/restore). Persistent "File contents are not automatically extracted."
notice.

---

## 4. AWS / S3 bucket settings (no secrets)

- Bucket: `drishti-synthetic-evidence-860510875713-ap-south-1` (region `ap-south-1`).
- Block Public Access: **all four flags true** (`BlockPublicAcls`, `IgnorePublicAcls`,
  `BlockPublicPolicy`, `RestrictPublicBuckets`).
- Versioning: **Enabled**.
- Default encryption: **SSE-S3 (AES256)** with bucket keys enabled.
- Bucket policy: **deny non-TLS** (`aws:SecureTransport = false`).
- CORS: methods `PUT/GET/HEAD`, origins limited to the localhost demo origins
  (`http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:4173`,
  `http://127.0.0.1:4173`), expose `ETag`.
- Lifecycle (`drishti-synthetic-evidence-cleanup`, prefix `evidence/`): abort
  incomplete multipart uploads after 3 days; expire noncurrent versions after
  30 days; expire objects after 30 days (synthetic-data retention).
- Key layout: `evidence/case-<id>/<ref>/v<n>/<filename>` (app uploads);
  `evidence/fixtures/golden-001/<ref>/<filename>` (datagen fixtures).
- Pre-signed URLs: SigV4, 900 s expiry, single exact object.

---

## 5. Commands run and results

| Command | Result |
|---|---|
| Apply `013_evidence_activity_lifecycle.sql` twice | PASS — constraint widened, indexes created, RLS-disabled asserted (idempotent) |
| `python -c "from app.main import app"` | PASS — 16 `/evidence` routes registered |
| `python -m pytest tests/test_evidence.py -q` | **26 passed** (~26 s) |
| `python -m pytest tests/test_readonly.py tests/test_intake.py -q` | 32 passed (no regressions) |
| `python -m pytest --collect-only -q` | 231 tests collected, no import errors |
| `npm run typecheck` (web) | PASS (tsc, 0 errors) |
| `npm run test` (web, vitest) | **30 passed** (9 files) |
| `npm run build` (web) | PASS (dist emitted) |
| `provision_evidence_bucket.py … --check` | PASS — private/versioned/SSE-AES256/TLS-only/CORS/lifecycle all confirmed |
| `upload_evidence_s3.py --run golden-001 --update-db` | **1,365 uploaded, 1,365 hash-verified, 327 rows reconciled, 0 errors** |
| Live presigned round-trip (PUT/head/GET/expiry/delete) | PASS — PUT 200, hash match, GET 200 body match, expired URL → HTTP 403, delete OK |

> Note: `npm` exits non-zero whenever a tool writes to stderr (React Router
> future-flag / chunk-size warnings) even on success; the authoritative signal is
> the printed `passed` / `built` lines.

### Backend test coverage (`test_evidence.py`, 26)
Pure unit (no DB/AWS): key derivation + prefix guard, allow-list validation
(bad extension/MIME/empty/too-large), hackathon-status shape. DB write-path
(driven against the live schema, rolled back via `rw_rollback`, with an in-memory
fake S3 gateway): draft create + `created` activity; metadata-only item is
`available`; successful upload + metadata (state `draft→uploading→available`,
activity `created/upload_url_issued/uploaded`, verified SHA-256); duplicate-hash
warning; invalid size/type rejected; missing object → `failed`; hash mismatch →
`failed`; size mismatch → `failed`; interrupted then retried upload succeeds;
metadata correction is appended (history intact); version replacement + immutable
v1 history; short-lived (expiring) download URL; archive then restore; link/unlink
a second case; **upload creates no `ModelInference`/`CrimeRiskScore` rows and no
extracted metadata keys**; legacy `CaseEvidence`→`EvidenceItem` migration is
idempotent. Fixture-uploader hash verification + manifest read. API surface:
`/status`, `/lookups`, policymaker 403, `upload-url` 503 when S3 unset, list read.

### Frontend test coverage (vitest, 30 total; 8 new)
`evidenceUpload.test.ts` (formatBytes + SHA-256 known vector), `evidenceShared.test.ts`
(state badge/type/hash helpers), `EvidencePage.test.tsx` (renders the no-extraction
note + rows; empty state). Existing 22 intake/review tests still pass.

---

## 6. Row counts / coverage

- `EvidenceObject` by storage status after the fixture upload:
  `available` = **327**, `fixture_pending_cloud_upload` = **7,688**,
  `quarantined` = **8** (total 8,023).
- Objects now pointing at the real bucket: **327**; `uploaded` activity events
  from the fixture uploader: **327**.
- Fixture files processed: **1,365** (all self-integrity OK, all uploaded, all
  round-trip SHA-256 verified). Reconcile matches DB rows by SHA-256, one per
  file; the remaining pending rows belong to a different generator run whose
  bytes are not in the committed `golden-001` set (matched-hash rows only are
  flipped — deliberately conservative, never corrupting DB↔S3 linkage).
- `EvidenceItem` = 8,015; legacy `CaseEvidence` = 0 (migration path exists + tested).

---

## 7. Security and data-quality checks

- **Browser never gets AWS credentials**: uploads/downloads use short-expiry
  (900 s), exact-object pre-signed URLs; the live expiry test confirmed an
  expired URL is rejected (HTTP 403).
- **Bucket is private**: all public access blocked; TLS-only bucket policy;
  SSE-AES256; versioning on. Verified via `--check`.
- **File bytes never in PostgreSQL**: only storage key + system SHA-256/size/MIME.
- **Server-side hash verification** on completion (re-downloads the object,
  recomputes SHA-256, rejects mismatch/size-mismatch/missing → item `failed`).
- **Allow-list** on size (≤ 50 MB) + extension + MIME, enforced at upload-url
  issuance and re-checked on completion.
- **RLS** stays disabled + NO FORCE on every application table (migration 013
  re-asserts `fn_assert_rls_disabled()`).
- **Write guards**: localhost-only + synthetic-DB marker required for every
  write; the fixture uploader refuses to touch a non-synthetic DB.
- **Audit**: create/update/delete, `evidence.upload`, `evidence.download`,
  entity link/unlink, and legacy import write sanitised `audit_logs` rows (no
  secrets/filenames-as-PII/narratives); append-only `EvidenceActivityEvent`
  custody trail is never overwritten.
- **No prediction / no extraction**: proven by test (no `ModelInference` /
  `CrimeRiskScore` created; no extracted metadata keys). No OCR/transcription/
  extraction dependency was added.
- **Git hygiene**: `datagen/fixtures/` and `.env` are gitignored — fixture files
  and the bucket name/credentials are not committed.

---

## 8. Known limitations

1. **Fixture ↔ DB run mismatch**: the committed `golden-001` fixtures and the
   loaded `EvidenceObject` rows come from different generator runs (0 filename
   matches; 327 SHA-256 matches). The uploader therefore reconciles only
   hash-matched pending rows (327) and never rewrites unrelated rows. All 1,365
   fixtures are still uploaded to S3 and round-trip verified. A future full
   regenerate+reload would align 1:1.
2. **Server-side hash verification** downloads the object (bounded by
   `evidence_hash_verify_max_bytes`, = the 50 MB cap). Fine for the hackathon
   allow-list; a very large-object tier would move to checksum headers.
3. **Malware scanning / quarantine-on-upload** is out of hackathon scope
   (deferred with OCR/extraction to post-hackathon Phase 3-equivalent work).
4. **CORS** is pinned to localhost demo origins; a deployed frontend origin must
   be added (re-run the provisioner with `--frontend-origin`).
5. **Auth** remains UX-simulation (X-Role); real identity/authorization is
   deferred. Write guards are defence-in-depth, not authentication.

---

## 9. Next-phase prerequisites (Prompt 7 — structured statements/property/court)

- Migrations 006/007 provide `Statement`, `StatementVersion`, `Seizure`,
  `PropertyItem`, `CourtEvent`, `BailEvent`, `CaseDisposition`,
  `OutcomeObservation` — ready for Prompt 7 forms/APIs.
- Evidence items can be linked from statements/seizures via the existing
  `EvidenceItem` + `EvidenceEntityLink` (e.g. `Seizure.MemoEvidenceItemID`,
  `Statement.EvidenceItemID`).
- The `api.evidence.*` client + `EvidencePage` patterns (draft → presigned
  upload → complete → activity) are reusable for any file-backed reference in
  Prompt 7/8 (an uploaded file is a *reference* only; its content must not
  auto-populate forms).
- Prompt 6 (OCR/transcription/extraction) remains **Deferred**; continue directly
  to Prompt 7.

---

## 10. Definition of Done — verification

- [x] Already-digital synthetic evidence uploads to private S3 (live-verified round-trip; 1,365 fixtures uploaded + hash-verified).
- [x] Every file has manual metadata, a system SHA-256, a version, and append-only activity history.
- [x] Evidence UI supports upload (progress/cancel/retry), metadata editing, linking/unlinking, versioning, preview and short-lived download.
- [x] No OCR/transcription/extraction dependency; an upload creates no extracted fields and triggers no prediction (test-proven).
- [x] RLS disabled + NO FORCE re-asserted; browser has no direct DB/S3 credential path; writes are localhost + synthetic-guarded and audited.
