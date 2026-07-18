# Phase 14 — Pipeline & Workflow Specifications (18)

Companion to `PHASE_14_REPORT.md` §4. Every workflow below is specified with the
required fields: **owner, trigger, typed input/output, idempotency key, state
machine, retry/timeout, DLQ/failed-item path, audit & lineage, metrics/alerts,
credit limit, rollback/replay, and an end-to-end synthetic fixture**.

Fixture status legend: **runnable** (executes locally today) · **representative**
(committed synthetic input/expected-output contract; runs end-to-end once the
component is deployed+enabled) · **deferred** (phase-order rule — owning prompt
supplies it). Fixtures live in `infra/catalyst/workflows/fixtures/`.

Canonical idempotency key (prediction/feature family):
`<task>:<subject>:<cutoff>:<feature_schema_version>:<model_version>:<source_version_hash>`.

Global credit posture: all event/cron/RAG/notify handlers default **OFF**
(`DRISHTI_*_ENABLED`); AppSail capped at 1–2 instances; AWS GPU/Batch auto-stopped
by §17; budget alerts in `infra/catalyst/billing/budget.json`.

---

### 1. `catalyst-ci-cd`
- **Owner:** Catalyst Pipelines (`infra/catalyst/pipelines/catalyst-pipelines.yaml`).
- **Trigger:** repository change or approved manual release.
- **Input → Output:** In `{commit_sha, branch, actor}` → Out `{dev_deploy_id, prod_deploy_digest?, smoke_report, artifact_refs}`.
- **Idempotency key:** `cicd:<commit_sha>:<environment>` (a commit deploys once per env).
- **State machine:** `queued → validate → scan → build → deploy_dev → smoke → (approve → promote_prod | rollback) → done|failed`.
- **Retry/timeout:** per-stage runner timeout; transient deploy step retried x2; overall lock = 1 active release/env.
- **DLQ/failed-item:** hard failure → `rollback_dev` job (redeploy last-good) → pipeline marked failed; no partial prod promote.
- **Audit & lineage:** commit_sha, artifact digests, deployer, stage statuses, approval reviewer/time (Console pipeline history).
- **Metrics/alerts:** stage pass/fail, build duration, smoke pass %, deploy frequency; alert on failed prod promote.
- **Credit limit:** 1 concurrent pipeline/env; runners bounded by plan; no GPU in CI unless the immutable ECR test job is explicitly enabled.
- **Rollback/replay:** immutable-artifact promotion; `rollback_dev` redeploys last-good Slate/AppSail; re-run pipeline to replay.
- **E2E fixture:** `wf01-ci-cd.fixture.json` — **runnable** (smoke stage = `pipelines/smoke_test.py`, verified locally).

### 2. `bootstrap-catalyst-serving-data`
- **Owner:** Catalyst CLI `ds:import` + Stratus (`infra/catalyst/ds-import/`).
- **Trigger:** initial deployment or deliberate serving-layer rebuild.
- **Input → Output:** In `{source_table, serving_csv(ExternalID col), config}` → Out `{job_id, inserted, updated, rejected, content_sha256}`.
- **Idempotency key:** `ExternalID` (`operation:upsert`, `find_by:ExternalID`) — re-run never duplicates.
- **State machine:** `export → validate(synthetic/golden) → hash/count → upsert → s3→stratus copy → reconcile → cutover_report`.
- **Retry/timeout:** `ds:import` job async with `ds:status`; failed rows listed in the report CSV; safe to re-run (upsert).
- **DLQ/failed-item:** rejected rows enumerated in the ds:import report CSV (reason per row); re-export + re-run.
- **Audit & lineage:** mapping_version, ExternalID prefix, row counts, content SHA-256, job_id, source hash (cutover report).
- **Metrics/alerts:** rows in/accepted/rejected, hash match, per-table dev-cap breaches; alert on reconciliation mismatch.
- **Credit limit:** ≤5000 rows/table (dev); one-way bootstrap only, not continuous sync.
- **Rollback/replay:** re-run is idempotent (upsert); forward-recovery via re-import of a corrected export; no destructive delete.
- **E2E fixture:** `wf02-bootstrap.fixture.json` — **runnable** (`import_serving_subset.py` dry-run verified; stable content hash).

### 3. `structured-intake-and-import`
- **Owner:** AppSail/Functions + Data Store + Stratus (`app/intake`, `app/imports`, `gateway_api`).
- **Trigger:** FIR/case draft save/submission, supervisor approval, or approved CSV/JSON import.
- **Input → Output:** In `{draft|import_batch, actor, role}` → Out `{staging_id | CaseVersion(canonical) after approval, audit_id}`.
- **Idempotency key:** `intake:<draft_id>:<content_hash>` (draft) / `import:<batch_id>` (import).
- **State machine:** `draft/staging → validate(schema/size/type/dup) → quality_review → approval → canonicalize → authoritative_write → audit/Signal`. Draft/submit **never** create a canonical CaseVersion or PredictionRequest.
- **Retry/timeout:** validation synchronous (≤30s aio); large imports via job (15min); resumable by batch.
- **DLQ/failed-item:** partial-error review queue; rejected rows retained in `import/staging/` with reasons.
- **Audit & lineage:** actor, role, approval chain, source hash, staging→canonical linkage, CaseVersion id.
- **Metrics/alerts:** drafts, submissions, approvals, rejection rate, time-to-approve; alert on approval-gate bypass attempts.
- **Credit limit:** function invocations bounded; import CSV ≤5000 rows dev.
- **Rollback/replay:** canonicalization is versioned (new CaseVersion); revert = supersede with a corrected approved version (append-only).
- **E2E fixture:** `wf03-intake.fixture.json` — **representative** (draft→approve→CaseVersion; asserts draft creates no canonical row).

### 4. `digital-evidence-ingestion`
- **Owner:** Stratus + Data Store + Signals/Event Fn + isolated AppSail scanner (`functions/evidence_event`, `app/evidence`, `app/stratus.py`).
- **Trigger:** already-digital file upload (`stratus_object_uploaded`, evidence prefix).
- **Input → Output:** In `{object_key, version_id, size, content_type, sha256}` → Out `{EvidenceObject(state=available|rejected), audit_id}`.
- **Idempotency key:** `evidence:<object_key>:<version_id>`.
- **State machine:** `uploaded(quarantine) → validate(mime/size/hash/version) → malware_scan → available|rejected → manual_metadata → case_link → audit`.
- **Retry/timeout:** Signals auto-retry (exp backoff, ≤20); scan job 15min; re-scan idempotent.
- **DLQ/failed-item:** scan failure → `rejected` + Dropped-after-TTL; quarantine object purged in 24h.
- **Audit & lineage:** uploader, object_key+version, sha256, scan verdict, case link, state transitions.
- **Metrics/alerts:** uploads, quarantine depth, scan pass/fail, time-in-quarantine; alert on scanner backlog.
- **Credit limit:** scanner disabled until `DRISHTI_EVIDENCE_SCAN_ENABLED`; bounded scan concurrency.
- **Rollback/replay:** re-run scan by object+version (idempotent); no byte mutation; **no OCR/transcription/extraction**.
- **E2E fixture:** `wf04-evidence.fixture.json` — **representative** (upload→quarantine→scan→available; asserts no extraction).

### 5. `identity-resolution-and-graph-refresh`
- **Owner:** AppSail/Job Scheduling + protected AWS analytics adapter (`app/identity`, `app/graph`).
- **Trigger:** validated person/party/import change or approved batch run.
- **Input → Output:** In `{party_change|batch_ref}` → Out `{canonical_identity_decision, graph_version, cache_invalidation}`.
- **Idempotency key:** `idres:<batch_ref|party_id>:<source_version_hash>`.
- **State machine:** `candidate_gen → review_queue → canonical_decision → graph_rebuild/version → safe_cache_invalidation → activity_result`.
- **Retry/timeout:** batch job 15min/chunk; adapter call retried x2 with timeout; resumable by candidate block.
- **DLQ/failed-item:** unresolved candidates stay in review queue; failed adapter batch → DLQ + operator review.
- **Audit & lineage:** candidate set, reviewer decision, graph_version, prior→new identity mapping.
- **Metrics/alerts:** candidates, auto vs manual merges, graph rebuild time; alert on merge-rate spike.
- **Credit limit:** adapter batch only on approval; GPU not required; AppSail bounded.
- **Rollback/replay:** graph is versioned; roll back to prior graph_version; replay from candidate set.
- **E2E fixture:** `wf05-identity.fixture.json` — **representative** (2 party records → 1 review-queued candidate → versioned graph).

### 6. `feature-snapshot-and-staleness`
- **Owner:** Data Store event → Event Function/AppSail (`functions/datastore_event`, `app/workload`).
- **Trigger:** committed **approved** canonical-version or reviewed-metadata change.
- **Input → Output:** In `{subject_kind(aggregate), subject_id, observation_cutoff, feature_schema_version, source_version_hash}` → Out `{FeatureSnapshot(immutable), stale_marks, coalesced_prediction_request?}`.
- **Idempotency key:** `snap:<subject_kind>:<subject_id>:<cutoff>:<feature_schema_version>:<source_version_hash>`.
- **State machine:** `eligibility/leakage_check → immutable_snapshot → mark_affected_prior_stale → coalesced_idempotent_request → audit`. Draft/submitted/rejected/quarantined sources ineligible; person subjects rejected.
- **Retry/timeout:** event fn 15min; snapshot write idempotent; coalescing dedupes bursts.
- **DLQ/failed-item:** ineligible events ignored (logged); failed snapshot → Signals retry → Dropped after TTL.
- **Audit & lineage:** source CaseVersion id, cutoff, feature_schema_version, snapshot id, superseded prediction ids.
- **Metrics/alerts:** snapshots/day, stale marks, coalescing ratio; alert on leakage-check failure.
- **Credit limit:** disabled until `DRISHTI_FEATURE_SNAPSHOT_ENABLED`; aggregate subjects only.
- **Rollback/replay:** snapshots immutable + versioned; replay by re-emitting the canonical-version event.
- **E2E fixture:** `wf06-feature-snapshot.fixture.json` — **representative** (approved CaseVersion → area snapshot; asserts person subject rejected).

### 7. `custom-prediction-dispatch-and-result`
- **Owner:** Job Scheduling + AppSail/Fn + protected AWS adapter (`functions/prediction_event`, `app/predict/{adapter,envelope,routing}.py`).
- **Trigger:** approved `PredictionRequest`.
- **Input → Output:** In `PredictionRequestEnvelope{request_id, task, snapshot_ref, model_version}` → Out `PredictionResultEnvelope{result_id, outputs, confidence, safety_flags}`.
- **Idempotency key:** `pred:<request_id>` (+ canonical family key); duplicate-result protection on `result_id`.
- **State machine:** `approved → build_min_snapshot → dispatch(SQS/Batch/SageMaker) → validate(output/schema/safety) → PredictionResult → Signal → UI_review`.
- **Retry/timeout:** dispatch timeout + retry x2; DLQ on repeated failure; fail-closed for `tabfm` (errors, never a silent fallback).
- **DLQ/failed-item:** SQS DLQ; failed request → `failed` state + operator review; duplicate results dropped.
- **Audit & lineage:** request_id, snapshot id, model_version, backend, latency, safety validation result.
- **Metrics/alerts:** dispatch count, p50/p95 latency, failure/DLQ rate, safety-reject rate; alert on DLQ growth.
- **Credit limit:** disabled until `DRISHTI_PREDICTION_DISPATCH_ENABLED`; AWS GPU capped + auto-stop; min-required snapshot only.
- **Rollback/replay:** re-dispatch by request_id (idempotent); results versioned; supersede on model_version change.
- **E2E fixture:** `wf07-prediction.fixture.json` — **representative** (approved request → envelope → result; asserts tabfm fail-closed).

### 8. `model-training-evaluation-and-release`
- **Owner:** QuickML (no-code baseline) + AWS Batch/SageMaker (TabFM/TimesFM/ST-GNN) (`quickml/nocode-experiment.json`, `app/workload`).
- **Trigger:** approved offline experiment, dataset/context release, or retraining request — **never** a raw upload or single FIR.
- **Input → Output:** In `{versioned_dataset, split, candidate_models}` → Out `{metrics, baseline_comparison, cost/latency, ModelVersion(on approval)}`.
- **Idempotency key:** `train:<experiment>:<dataset_version>:<split_hash>`.
- **State machine:** `dataset/split → leakage/fairness/safety → train(conventional/ST-GNN)+zero-shot(TabFM/TimesFM, no weight update) → holdout_baseline_cmp → cost/latency → human_approval → ModelVersion/context register → canary/rollback_meta`.
- **Retry/timeout:** Batch job retries; long jobs chunked; TabFM/TimesFM evaluated in-context (no fine-tune).
- **DLQ/failed-item:** failed training run archived with logs; not promoted; operator review.
- **Audit & lineage:** dataset_version, split, metrics, fairness report, approver, ModelVersion lineage.
- **Metrics/alerts:** metric vs baseline, fairness slices, cost/latency; alert on fairness regression or leakage.
- **Credit limit:** offline only; GPU capped + auto-stop; QuickML no-code baseline preferred where sufficient.
- **Rollback/replay:** ModelVersion registry + canary; roll back to prior ModelVersion; replay from dataset_version.
- **E2E fixture:** `wf08-training.fixture.json` — **representative** (tiny dataset → leakage check + baseline compare; no auto-promote).

### 9. `aggregate-and-spatiotemporal-forecast`
- **Owner:** Job Scheduling + AWS Batch/SageMaker (`functions/cron_forecast`, `app/forecast`).
- **Trigger:** scheduled forecast/backfill or approved manual run.
- **Input → Output:** In `{time/area_window}` → Out `{ForecastResult(per typed layer), map/dashboard Signal}`.
- **Idempotency key:** `forecast:<window>:<layer>:<model_version>`.
- **State machine:** `snapshot → task_router(baseline|TimesFM|ST-GNN|hotspot|near-repeat) → validate/calibrate each → fuse_compatible_layers → forecast_result → Signal → stop_compute`.
- **Retry/timeout:** per-layer job retry; timeout per job; incompatible layers never fused.
- **DLQ/failed-item:** failed layer excluded from fusion + flagged; DLQ for repeated failure.
- **Audit & lineage:** window, per-layer model_version, calibration, fusion inputs.
- **Metrics/alerts:** per-layer success, calibration error, fusion coverage; alert on stale/failed layer.
- **Credit limit:** cron disabled (`DRISHTI_FORECAST_CRON_ENABLED`); temporary compute auto-stopped.
- **Rollback/replay:** results versioned by window+model_version; replay a window; no operational auto-publish.
- **E2E fixture:** `wf09-forecast.fixture.json` — **representative** (window → typed layers → compatibility-checked fusion).

### 10. `approved-knowledge-rag`
- **Owner:** Catalyst QuickML (`app/quickml.py`, `quickml/rag-knowledge-base.json`).
- **Trigger:** approved SOP/policy knowledge-base release.
- **Input → Output:** In `{approved_text, source, version}` → Out `{kb_version, rag_endpoint, eval_report}`; query → `{answer, citations, refused}`.
- **Idempotency key:** `kb:<source>:<version>`.
- **State machine:** `validate(approved/source/version) → kb_update → citation/refusal_eval → enable_endpoint`.
- **Retry/timeout:** KB build async; query ≤30s; refusal on unsupported.
- **DLQ/failed-item:** failed eval blocks enablement; endpoint stays disabled.
- **Audit & lineage:** source id+version, kb_version, eval results.
- **Metrics/alerts:** answer/refusal ratio, citation coverage; alert on uncited answer.
- **Credit limit:** disabled until `DRISHTI_QUICKML_RAG_ENABLED`; approved text only (no evidence bytes / unreviewed narratives).
- **Rollback/replay:** kb_version pinned; roll back to prior kb_version; re-run eval.
- **E2E fixture:** `wf10-rag.fixture.json` — **runnable** (offline RAG: known Q → cited answer; PII Q → refusal, verified).

### 11. `report-generation-and-delivery`
- **Owner:** Job Scheduling/AppSail + SmartBrowz + Stratus + Signals (`functions/report_event`, `app/smartbrowz.py`, `app/stratus.py`).
- **Trigger:** authorized report/export request.
- **Input → Output:** In `{report_type, source_snapshot_ref, actor}` → Out `{Stratus report object(watermark/hash/version), report.ready Signal}`.
- **Idempotency key:** `report:<report_id>:<version>`.
- **State machine:** `immutable_source_snapshot → SmartBrowz_render → watermark/hash/version → private_stratus_object → audit → report.ready`.
- **Retry/timeout:** render job 15min; retry x2; re-render idempotent by report_id+version.
- **DLQ/failed-item:** render failure → `failed` + retry → Dropped after TTL; operator review.
- **Audit & lineage:** source snapshot id, renderer version, sha256, object version, requester.
- **Metrics/alerts:** reports/day, render time, failure rate; alert on render backlog.
- **Credit limit:** disabled until `DRISHTI_REPORT_DELIVERY_ENABLED`; bounded render concurrency.
- **Rollback/replay:** report objects versioned in Stratus; re-generate a new version; prior retained for audit.
- **E2E fixture:** `wf11-report.fixture.json` — **runnable** (SmartBrowz fake renders watermarked PDF; sha256+version asserted).

### 12. `notification-delivery`
- **Owner:** Signals/Event Fn + Catalyst Mail/Push (`functions/notify_dispatch`).
- **Trigger:** approved task/report/prediction/alert lifecycle event (`notify.requested`).
- **Input → Output:** In `{template, subject_ref, recipients_role}` → Out `{delivery_status row}`. **Never** evidence content or full narratives.
- **Idempotency key:** inbound `idempotency_key` (e.g., `notify:<subject>`).
- **State machine:** `template → recipient/role_validation → send(mail/push) → delivery_status/audit`.
- **Retry/timeout:** Signals retry (≤20); send timeout 30s; idempotency guards duplicate sends.
- **DLQ/failed-item:** send failure → retry → Dropped after TTL; delivery_status=failed recorded.
- **Audit & lineage:** template, recipient role, subject_ref, delivery status, timestamps (no PII/content).
- **Metrics/alerts:** sent/failed, delivery latency; alert on failure spike.
- **Credit limit:** disabled until `DRISHTI_NOTIFY_ENABLED`; data-minimized templates only.
- **Rollback/replay:** re-send by idempotency_key (deduped); no rollback needed (notice-only).
- **E2E fixture:** `wf12-notify.fixture.json` — **representative** (Node template render contract: body carries only reference + role + synthetic marker, no evidence/PII).

### 13. `investigation-board-activity-and-export`  — **RESERVED (Prompt 16)**
- **Owner:** AppSail + Data Store/NoSQL/Cache + Signals + SmartBrowz/Stratus.
- **Trigger:** authenticated board mutation, replay or export.
- **Input → Output:** In `{board_mutation}` → Out `{append-only BoardActivity, reconstructable layout, locked snapshot, attributed export}`.
- **Idempotency key:** `board:<board_id>:<mutation_id>`.
- **State machine:** `optimistic/idempotent_mutation → append_BoardActivity → event/replay → reconstruct_layout → locked_snapshot → attributed_export`.
- **Retry/timeout / DLQ / audit / metrics / credit / rollback:** contracts defined; **not enabled here.** NoSQL `BoardLayout` segment reserved+disabled (`nosql/segments.json`); no Signals rule active.
- **E2E fixture:** **deferred** — supplied by Prompt 16 (not claimed functional in Prompt 14).

### 14. `hazard-feed-ingestion-and-freshness`  — **RESERVED (Prompt 17)**
- **Owner:** Job Scheduling + Functions/AppSail + Stratus/Data Store.
- **Trigger:** synthetic replay cron or approved digital connector.
- **Input → Output:** In `{raw_versioned_payload}` → Out `{HydroMetReading/HazardEvent candidate, freshness heartbeat}`.
- **Idempotency key:** `hazardfeed:<source>:<payload_version>`.
- **State machine:** `raw_stratus_payload → normalize(unit/geometry/dup) → candidate → freshness_heartbeat → stale/failed Signal + DLQ`.
- **Retry/timeout / DLQ / audit / metrics / credit / rollback:** contracts defined; **not enabled** (cron RESERVED disabled; `FeedEnvelope` NoSQL reserved).
- **E2E fixture:** **deferred** — supplied by Prompt 17.

### 15. `hazard-forecast-review-and-alert`  — **RESERVED (Prompt 17)**
- **Owner:** Functions + Job Scheduling + protected AWS model adapter.
- **Trigger:** validated readings/time window.
- **Input → Output:** In `{readings_snapshot}` → Out `{HazardPrediction/RiskZone, human-reviewed AlertHistory?}`. **Never** auto-warn or auto all-clear.
- **Idempotency key:** `hazardfx:<window>:<model_version>`.
- **State machine:** `immutable_snapshot → model → output_validation → HazardPrediction/RiskZone → human_review → optional_AlertHistory → Mail/Push`.
- **Retry/timeout / DLQ / audit / metrics / credit / rollback:** contracts defined; **not enabled** (cron RESERVED disabled).
- **E2E fixture:** **deferred** — supplied by Prompt 17.

### 16. `resource-allocation-and-routing`  — **RESERVED (Prompt 17)**
- **Owner:** AppSail/Job Scheduling + protected AWS OR-Tools/PostGIS/pgRouting.
- **Trigger:** approved hazard/resource planning request.
- **Input → Output:** In `{constraints, resources}` → Out `{proposed allocation/route (human-approved)}`. **Never** auto-dispatch or claim a guaranteed-safe route.
- **Idempotency key:** `alloc:<plan_id>:<constraints_hash>`.
- **State machine:** `constraint_validation → greedy/baseline_cmp → proposal → hazard_intersection_validation → Data Store proposal → human_approval`.
- **Retry/timeout / DLQ / audit / metrics / credit / rollback:** contracts defined; **not enabled** (RESERVED disabled).
- **E2E fixture:** **deferred** — supplied by Prompt 17.

### 17. `reconciliation-backup-recovery-and-cleanup`
- **Owner:** Job Scheduling/Functions + Catalyst/AWS ops APIs (`functions/cron_reconcile`).
- **Trigger:** schedule, release gate, or recovery exercise.
- **Input → Output:** In `{run_date}` → Out `{reconciliation_report, backup_ref, cleanup_stats, budget/health_evidence}`.
- **Idempotency key:** `reconcile:<run_date>`.
- **State machine:** `count/hash/version_reconcile → backup/export → restore_drill → failed_job_replay → stale_temp_cleanup → GPU/Batch_shutdown → budget/health_evidence`.
- **Retry/timeout:** cron 15min/chunk; each sub-step idempotent by run_date; resumable.
- **DLQ/failed-item:** failed sub-step logged + retried next run; failed-job replay handles stragglers.
- **Audit & lineage:** counts/hashes per store, backup id, restore-drill result, shutdown confirmations.
- **Metrics/alerts:** reconciliation diffs, backup success, temp cleanup count, budget %; alert on diff or budget breach.
- **Credit limit:** cron disabled (`DRISHTI_RECONCILE_ENABLED`); its job is to **reduce** cost (stops temp compute).
- **Rollback/replay:** read-mostly + guarded; backups enable forward-recovery; re-run by run_date.
- **E2E fixture:** `wf17-reconcile.fixture.json` — **representative** (count/hash diff → report + shutdown confirmation).

### 18. `embeddings-and-similarity-index-refresh`
- **Owner:** Job Scheduling + AWS Batch/AppSail worker + vector/index store (`app/cases/similar.py`, `app/graph`).
- **Trigger:** approved source/version/model change or deliberate rebuild.
- **Input → Output:** In `{authorized_reviewed_text/struct, model_version}` → Out `{shadow_index, active_index(atomic switch), index/version metadata}`.
- **Idempotency key:** `embed:<corpus_version>:<model_version>`.
- **State machine:** `select_authorized_reviewed → embed(one space/ModelVersion) → validate(dims/digest) → build_shadow → labelled_retrieval_eval → atomic_active_switch → Data Store metadata → Cache_invalidation → rollback_meta`.
- **Retry/timeout:** Batch job retries; shadow build isolated from active; eval gate before switch.
- **DLQ/failed-item:** failed build stays shadow (never switched); operator review.
- **Audit & lineage:** corpus_version, model_version, dims/digest, eval scores, active-index pointer history.
- **Metrics/alerts:** retrieval quality vs prior, dim/digest mismatch; alert on eval regression.
- **Credit limit:** on approval only; GPU capped + auto-stop; raw file bytes/unreviewed text **never** enter.
- **Rollback/replay:** atomic active-index switch is reversible (repoint to prior); replay from corpus_version.
- **E2E fixture:** `wf18-embeddings.fixture.json` — **representative** (shadow build + dim/digest validate → atomic switch + rollback pointer).

---

**Phase-order compliance:** workflows 13–16 above define their contracts (owner,
trigger, typed I/O, idempotency key, state machine) but are **RESERVED and
disabled** — no schedule/Signal is active, NoSQL segments `BoardLayout`/
`FeedEnvelope` are reserved-disabled, and their fixtures are **deferred** to the
owning prompts (16/17). Prompt 14 does not claim them functional.
