# DRISHTI execution decisions

This file is the compact, cross-session decision log for `prompt3new.md`. Add only
decisions that constrain later phases; keep investigation detail in phase artifacts.

## Active decisions

- Prompt 18 completed on 20 July 2026; its evidence is in
  `docs/phase-reports/PHASE_18_REPORT.md`. Execute Prompt 19 through Prompt 25 in order,
  then run Prompt 26 as a fresh independent audit.
- The existing Catalyst project is DHRISTI, project `48361000000030003`, organization
  `60075362708`, India DC. Do not create a duplicate project.
- Use AWS profile `drishti`; inventory and reuse resources before bounded mutation.
- Catalyst owns deployed operational serving data. AWS remains the protected historical,
  analytics, geospatial, and justified custom-ML plane.
- RLS/FORCE RLS stays disabled for this synthetic hackathon only; server-side role and
  scope authorization remains mandatory.
- Voice questions may be enabled. OCR, evidence extraction, face/object recognition,
  and evidence-media transcription remain out of hackathon scope.
- Completion requires real evidence; mocks, descriptors, and future-tense plans cannot
  satisfy a mandatory live gate.
- The release label is HACKATHON-DEMO READY, never production-ready.

## Decision entry format

Record date, phase, decision, authoritative source, affected contracts/paths, and any
superseded decision. Never put credentials or personal data here.

## Prompt 19 decisions (2026-07-21)

- Ask DRISHTI semantic planner is **Catalyst QuickML LLM Serving** (primary in the
  live-ready contract; QuickML LLM Serving is available in the IN DC and hosts open
  models such as Qwen 2.5). Provider-neutral settings; the `gpt-4o-mini` implied
  default is removed; the engine fails closed to a **labelled** deterministic planner
  (`planner_source`/`planner_degraded`) rather than a silent commercial API. Live
  invocation is verified in **Prompt 23**.
  Source: https://docs.catalyst.zoho.com/en/quickml/help/generative-ai/llm-serving/
- **Catalyst Zia does not expose speech-to-text / text-to-speech / translation** in
  the IN DC, so the submitted voice capability is the browser Web Speech API (labelled
  as browser voice, never Zia); bilingual EN/KN text always works. An env-gated Zia
  adapter contract (`DRISHTI_USE_CATALYST_ZIA_VOICE`) is ready if that changes.
  Source: https://docs.catalyst.zoho.com/en/zia-services/getting-started/components-of-zia-services/
- Voice query dictation is IN scope (`QUERY_VOICE_ENABLED=true`), strictly separate
  from evidence extraction (`EVIDENCE_EXTRACTION_ENABLED=false`, stays off).
- Ask answers carry a **server-validated typed visualization spec** (approved kinds
  only; never model-authored code) with an always-present accessible-table fallback.
- Low-confidence voice dictation must be confirmed/edited before it executes.

## Prompt 22 decisions (2026-07-21)

- The **strict local release gate** is `python scripts/release_gate.py` — one
  command, 16 mandatory gates, machine-readable `artifacts/phase-22/release-gate.json`,
  exit 0 only for a genuine candidate (any mandatory fail/skip/invalid-URL/missing-
  artifact/unclassified-route → non-zero). The Catalyst pipeline's validate/build/
  security stages mirror it 1:1, so CI and local are identical.
- The **mandatory backend release tier is the DB-free offline suite**
  (`DRISHTI_DISABLE_DB_TESTS=1`; 378 passed, 211 `@requires_db` skipped), matching
  the DB-free AppSail. The RDS DB pass and `@slow` model-quality thresholds are a
  separate tier. `test_risk::test_full_calibration_report_runs` (foundation acc
  0.2525 < 0.3 on the CPU in-context fallback over deliberately-noisy synthetic
  labels) is deferred to **Prompt 24** (real TabFM on GPU); it was NOT weakened.
- **Money-trail authz contract:** `action_for_role` returns `'read'`/`'write'`
  for grants, an explicit **`'none'`** for a known-but-denied role (policymaker,
  disaster_coordinator — matches the `police_fir_extensions.sql` seed), and
  `None` only for an unknown role. Both `'none'` and `None` deny.
- **Dependency posture:** shipped npm deps are clean (`npm audit --omit=dev` = 0);
  `python-dotenv` bumped 1.0.1→1.2.2 (CVE-2026-28684). The 9 `starlette` 0.41.3
  advisories are **accepted exceptions** (`docs/deployment/security-exceptions.json`,
  owner + expiry 2026-09-30) — not applicable in the linux/JSON-API/behind-Gateway
  context; the full fix (fastapi≥0.139 / starlette≥1.3.1, a cross-major upgrade)
  is deferred to **Prompt 25** to protect the working backend. New/expired
  high/critical findings block the `dep_audit` gate.
- **Release build guard:** a production build FAILS on an unset/invalid
  `VITE_API_BASE_URL` (must be an https Catalyst API-Gateway origin routing
  `/api`; never http/localhost/AWS/raw-AppSail). Enabled via
  `npm run build:release` / `check:bundle:release --release`.
- **Pipeline:** `catalyst-pipelines.yaml` has no `|| true` on mandatory steps;
  catalyst commands run from `infra/catalyst`; smoke goes through the API Gateway
  (`/api/*`) + Auth boundary; a mandatory `preflight_deploy.py` (project ==
  DHRISTI 48361000000030003, synthetic marker, DB-free posture, no-duplicate)
  runs before deploy; the GPU worker is only static-checked here (built/deployed
  separately in Prompt 24). Live deploy/smoke/rollback proof is **Prompt 23**.

## Prompt 24 decisions (2026-07-23)

- **AWS GPU mechanism** is a **SageMaker asynchronous-inference endpoint on
  `ml.g4dn.2xlarge` (NVIDIA T4)** in ap-south-1. This account's GPU quota is `0`
  for every type EXCEPT `ml.g4dn.2xlarge for endpoint usage = 1` (code
  `L-EA346344`); Prompt 25 redeploys must use that single-T4 mechanism (no
  quota increase, no other GPU type). Credits do not bypass the quota.
- **TabFM weights licence is "TabFM Non-Commercial License v1.0"** (Google;
  HF tag `other`) - research/evaluation/non-commercial only. The `tabfm` PyPI
  *code* is Apache-2.0. Prompts 25/26 must **never** claim a production/commercial
  TabFM licence. TimesFM 2.5-200m is Apache-2.0. Weight digests: TabFM classification
  `928cb350…`, TimesFM `2f776efe…` (verified at load, fail-closed).
- **GPU image is built in AWS CodeBuild** (`drishti-gpu-worker-build`), not locally
  (host disk too small; `tabfm`/`timesfm` need Python>=3.11). Immutable ECR digest
  in use: `…/drishti-gpu-worker@sha256:a2944b79…` (tag 0.2.3). Weights are pulled
  from HF at T4 cold-start (not baked; classification alone is ~6.25 GB).
- **The temporary GPU endpoint is torn down** after proof (cost control); the
  protected adapter (API GW `1ym4tv6g13`, Lambda `drishti-aws-adapter`, secret in
  Secrets Manager `drishti/aws-adapter-secret`, DLQ), ECR images, KMS-encrypted S3
  model plane, Budget + alarm all remain. Prompt 25 live AWS re-proof =
  `sagemaker_ops.py deploy` then `invoke`, then teardown again.
- **Deployed-AppSail -> adapter wiring** is a Console step: set
  `DRISHTI_AWS_ADAPTER_URL` + `DRISHTI_AWS_ADAPTER_SECRET` on AppSail. Prompt 24
  proved the exact server-side client code path against real AWS via a driver; the
  live Catalyst Data Store + Signal side was proven in Prompt 23.
