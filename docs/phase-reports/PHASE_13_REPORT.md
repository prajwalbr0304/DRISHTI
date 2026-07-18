# Phase 13 Report — TabFM aggregate task and model validation

**Objective.** Replace the synthetic individual offender-risk score with a single
**approved aggregate / review-support task**, evaluated against baselines on
held-out data, and ensure no page presents synthetic individual risk as
operational truth.

**Outcome.** The approved task is an ordinal **case-review WORKLOAD band** for a
police **district** (`area_workload_band`): given strictly pre-cutoff aggregate
features, predict the band of case-review demand the district will register in the
next quarter — for supervisory review-queue / resource planning. It is aggregate,
area/period, human-reviewed decision support, never a person-level judgement. The
retired per-offender risk output is archived synthetic-demo-only.

> **Foundation-model note (Prompt 14).** The production foundation backend is
> **Google TabFM v1 on GPU**, validated at full scale in Prompt 14. This CPU
> phase uses **TabPFN v2** as an interim tabular-foundation candidate (it beats
> every baseline on held-out data) and a deterministic **in-context** stand-in as
> the offline fallback. The approved model version `drishti-tabfm-workload` is
> therefore left **staged** (approved schema + reproducible training snapshot),
> pending the Prompt-14 GPU-TabFM cutover.

---

## 1. Why district, not station (evidence-driven task selection)

A read-only signal audit of the synthetic data drove the subject choice:

| Level | recent-qtr → next-qtr corr | trailing-yr → next-qtr corr | 5-yr total CV | verdict |
|---|---:|---:|---:|---|
| **Station** (1,000 units) | −0.00 | 0.00 | 0.10 | pure Poisson noise around a near-constant rate → **not responsibly predictable** |
| **District** (32) | 0.98 | 0.99 | 0.83 | strong, persistent, heterogeneous → **tractable** |

Station next-quarter counts are Poisson noise (mean 5.0, std 2.23), so a
station-level band would fail the quality gate. District workload carries real
signal, and 32 districts × 16 quarterly cutoffs (~500 rows) is precisely the
small-tabular regime TabFM/TabPFN are designed for. This selection is itself the
required leakage/quality diligence.

---

## 2. Files and migrations changed

### SQL migrations (additive, idempotent — applied twice each)
- `services/ml/sql/020_tabfm_workload_task.sql` — seed 10 non-protected aggregate
  `FeatureDefinition`s + approved `FeatureSchemaVersion` (`tabfm-workload-band` v1);
  create `ModelBenchmark`; **archive/label** the individual offender-risk outputs
  (`SyntheticDemoOnly` columns on `CrimeRiskScore`/`ModelInference`; retire the
  per-offender classification `ModelVersion`s).
- `services/ml/sql/021_workload_area_level.sql` — retarget the approved task to the
  **district** level (`area_workload_band`, subject `area_district`), reusing the
  same `wl_*` features.

### Backend — new module `services/ml/app/workload/`
- `features.py` — leakage-safe (district, cutoff) dataset: strictly-pre-cutoff
  aggregate features + a forward-window banded label (train-only thresholds);
  time + geographic splits; `level="station"` path for benchmark scale only.
- `models_iface.py` — n-band-parameterised backends: prior-period, majority and
  gradient-boosted-tree baselines; in-context (deterministic), TabPFN and TabFM
  (reusing the risk module's cached loader) foundation candidates; env override +
  RAM gate + graceful deterministic fallback; `limit_threads()` OpenMP guard.
- `evaluation.py` — accuracy / macro-F1 / QWK / Brier / ECE; temperature
  calibration; confidence, abstention + threshold review; baseline comparison +
  skill; metrics by time / geography / data-completeness; geographic holdout;
  leakage / protected / proxy checks.
- `governance_bridge.py` — approved `ModelVersion` bound to the approved schema +
  a reproducible `TrainingDatasetSnapshot`; immutable hashed `FeatureSnapshot`
  (`area_district`) + idempotent `PredictionRequest`/`PredictionResult` with
  supersession + staleness; staged/shadow/active/retired lifecycle; benchmark
  persistence; stores the full held-out report for static UI serving.
- `benchmark.py` — 500 / 5,000 / full-row runtime, CPU/GPU memory, latency,
  throughput, cost estimate and metric comparison → `ModelBenchmark`.
- `service.py`, `schemas.py`, `router.py`, `__init__.py` — model card, reads,
  typed request/response models, FastAPI router (role-gated + synthetic-DB-guarded
  writes).

### Backend — wiring
- `app/main.py` — register the workload router.
- `app/batch.py` — CLI: `workload-eval`, `workload-run`, `workload-benchmark`.

### Frontend (`web/src`)
- `api/endpoints/workload.ts` (+ `api/index.ts`) — typed workload API client.
- `routes/analytics/modes/WorkloadMode.tsx` (+ `routes/analytics/Analytics.tsx`) —
  new **Case-Review Workload** analytics mode.
- `routes/entities/EntityProfile.tsx`, `components/peek/PeekContent.tsx` —
  individual offender-risk displays **relabelled as retired / synthetic-demo-only /
  not operational**, linking to the aggregate model.

### Tests / docs
- `services/ml/tests/test_workload.py` (15 tests).
- `services/ml/tests/test_risk.py` — the two `requires_db` **individual** offender-risk
  read tests now `skip` gracefully when `CrimeRiskScore` is empty (its intended
  retired state), instead of asserting a retired feature works.
- `docs/model-cards/tabfm-workload-band.md`, this report.

---

## 3. Database objects, endpoints and screens

**Database objects**
- `FeatureSchemaVersion` #20 `tabfm-workload-band` v1 — task `area_workload_band`,
  **approved**, 10 features (all `Sensitivity = normal`).
- 10 `FeatureDefinition`s: `wl_recent_case_volume`, `wl_prev_quarter_volume`,
  `wl_trailing_year_volume`, `wl_trend_slope`, `wl_seasonal_index`,
  `wl_prioryear_same_quarter`, `wl_chargesheet_trailing_year`, `wl_backlog_ratio`,
  `wl_history_months`, `wl_active_months_share`.
- `ModelBenchmark` table (RLS disabled, `relrowsecurity=false` verified) — 15 rows.
- `ModelVersion` #38 `drishti-tabfm-workload` v1.0.0 (classification): approval
  `approved`, status **`staged`**, env `hackathon_demo`, bound to schema #20 +
  `TrainingDatasetSnapshot` #2; `EvaluationReport` stores summary + full held-out
  report + `production_backend = google-tabfm-v1 (GPU, Prompt 14)`.
- `TrainingDatasetSnapshot` #2 — time split (train/val/test cutoffs), geo split
  (held-out districts), row count 512, label windows, content hash.
- 32 `FeatureSnapshot` (`area_district`, immutable, hashed) + 32 `PredictionRequest`
  (idempotent) + 32 `PredictionResult` (band, calibrated confidence, abstention,
  limitations, expiry) for the 2025-12 cutoff.
- Retirement: `CrimeRiskScore."SyntheticDemoOnly"` (default TRUE) and
  `ModelInference."SyntheticDemoOnly"`; `ModelVersion` #12 (`drishti-tabfm-incontext`)
  and #13 (`drishti-xgboost`) → approval `retired`, env `synthetic_demo_only`.

**Endpoints** — `GET /workload/task`, `/workload/models`, `/workload/predictions`,
`/workload/evaluation`, `/workload/benchmarks`; `POST /workload/run`,
`/workload/benchmark`, `/workload/models/{id}/lifecycle`.

**Screens** — Analytics → **Case-Review Workload** (task + model card; held-out
KPIs; foundation-vs-baselines table; calibration / abstention / leakage-safe /
geo-holdout badges; per-district band predictions; benchmark table; limitations).
Entity Profile **Risk** tab and Peek **Risk** section now show a retirement notice
instead of any individual score.

---

## 4. Commands run and results

| Command | Result |
|---|---|
| `apply-sql 020`, `021` (×2 each) | idempotent; schema/table/columns/retirement verified |
| `workload-eval --foundation incontext` | in-context (fallback) acc 0.641, **QWK 0.805**, ECE 0.098 |
| `workload-eval --foundation tabpfn` | TabPFN acc 0.805, **QWK 0.914**, ECE 0.104, **beats_all_baselines=true** |
| `workload-run --foundation tabpfn --lifecycle staged` | 32 governed snapshots+requests+results; model #38 staged; held-out report stored |
| `workload-benchmark` | 15 `ModelBenchmark` rows (500/5,000/full, real runtime/memory/throughput/cost) |
| `pytest tests/test_workload.py` | **15 passed** (28.8s) |
| `pytest test_governance test_hackathon test_contract` | **37 passed** (no regressions) |
| `pytest test_explain` | 8 passed, 1 skipped (registry changes clean) |
| `pytest test_risk -m "not slow"` | 6 passed, **2 skipped** (retired individual-risk reads; empty `CrimeRiskScore` — pre-existing, aligned to the retirement) |
| app import / `TestClient` smoke | 185 routes (8 `/workload`); all workload endpoints `200` |
| `web: npm run typecheck` | clean (exit 0) |

### Held-out evaluation (test = 4 latest quarterly cutoffs, 128 district-quarters)

| Model | Accuracy | Macro-F1 | QWK | ECE | Beats baselines |
|---|---:|---:|---:|---:|:--:|
| **TabPFN v2** (interim served) | 0.805 | 0.799 | **0.914** | 0.104 | **yes** |
| in-context (deterministic fallback) | 0.641 | 0.619 | 0.805 | 0.098 | no |
| baseline · GBM (HistGradientBoosting) | 0.797 | — | 0.912 | 0.061 | — |
| baseline · prior-period | 0.758 | — | 0.896 | — | — |
| baseline · majority-class | 0.273 | — | 0.000 | — | — |

Geographic holdout (TabPFN, held-out districts, n=32): accuracy 0.781, **QWK 0.915**
— no spatial over-fit. Splits: train 320 / val 64 / test 128 over 16 quarterly
cutoffs (2021-12 … 2025-09); band thresholds (train-only) `[85.75, 114.0, 167.0]`.

### Benchmarks (computational scaling, station-level 16k matrix, CPU host)

| Model | 500 | 5,000 | full (10k) | throughput | peak RSS |
|---|---:|---:|---:|---:|---:|
| prior-period | 0.02s | 0.01s | 0.02s | 170k–325k rows/s | ~245–349 MB |
| majority | ~0s | ~0s | ~0s | — | ~349 MB |
| GBM (HistGBM) | 2.33s | 3.28s | 4.26s | ~5k rows/s | ~347–349 MB |
| in-context | 0.22s | 1.14s | 2.01s | 2k–21k rows/s | ~348–350 MB |
| **Google TabFM** | *deferred* | *deferred* | *deferred* | — | — |
| TabPFN v2 | (heavy) | (heavy) | *deferred* | — | — |

GPU memory: N/A (CPU-only host). Cost estimate (documented assumption): CPU
`ml.m5.xlarge` ~$0.23/hr, GPU `ml.g5.xlarge` ~$1.40/hr; per-1,000-prediction cost
derived from measured throughput. **Google TabFM at scale is deferred to AWS Batch
GPU (Prompt 14)** and recorded as such rather than faked.

---

## 5. Security and data-quality checks
- **RLS** disabled + NO FORCE re-asserted in both migrations
  (`fn_disable_rls_all_app` / `fn_assert_rls_disabled`); `ModelBenchmark`
  `relrowsecurity=false` verified. No RLS policies created.
- **No protected/proxy features**: all 10 features `Sensitivity=normal`; the
  governed builder runs `assert_no_protected_features`; a keyword proxy guard +
  the leakage report confirm `has_protected_or_proxy=false`.
- **Leakage-safe**: forward label window is disjoint from and after every cutoff;
  band thresholds fit on train only; built dataset reports `leakage_safe=true`
  (max feature↔label correlation 0.99 is genuine same-quarter-last-year signal,
  not a leak — `suspected_leak=false`).
- **Individual scoring retired**: `CrimeRiskScore`/`ModelInference` marked
  synthetic-demo-only; per-offender model versions retired; UI relabelled.
- **No secrets** in code/logs/report; browser → FastAPI → PostgreSQL/S3 only;
  workload writes are role-gated + synthetic-DB-guarded; predictions are aggregate
  decision-support with a mandatory `PredictionReview` path.

---

## 6. Known limitations
- Synthetic development data — bands are not operational truth; the served model is
  **staged**, not active.
- On the strongly auto-correlated district series the prior-period and GBM
  baselines are already strong; TabPFN beats them (QWK 0.914 vs 0.912 / 0.896) but
  modestly. The in-context fallback (QWK 0.805) does **not** beat GBM — reported
  honestly.
- Station-level workload is unpredictable on this data and is intentionally not
  modelled.
- Benchmark quality columns at station scale reflect noise (the benchmark measures
  compute scaling); task quality is the district evaluation.
- Full-scale + GPU **TabFM** benchmark and serving are deferred to Prompt 14; the
  interim CPU backend is TabPFN with an in-context fallback.

---

## 7. Exact next-phase (Prompt 14) prerequisites
1. Run **Google TabFM v1 on AWS Batch / SageMaker GPU** for `area_workload_band`
   using `app/workload/models_iface.py::TabFMCandidate`; persist `ModelBenchmark`
   rows at 500 / 5,000 / full on GPU (real GPU memory + latency + cost).
2. If GPU-TabFM beats the baselines on the held-out split, **promote**
   `drishti-tabfm-workload` staged → active via `/workload/models/{id}/lifecycle`;
   record ECR image + artifact/image digests on the `ModelVersion`.
3. Wire the governed `workload-run` into the Catalyst/AWS deployment on a quarterly
   schedule; keep the CPU in-context stand-in as the guaranteed offline fallback.

## Definition of Done
- [x] TabFM is used only for an approved aggregate/review-support task
  (`area_workload_band`); the retired individual offender-risk target is archived
  synthetic-demo-only.
- [x] Baselines (prior-period, majority, GBM) and held-out evaluation (time + geo
  splits, calibration, abstention, leakage checks) are documented.
- [x] Synthetic individual scoring is not operationally displayed (Risk tab + Peek
  relabelled; scores archived; per-offender models retired).
