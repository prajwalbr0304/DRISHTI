# Model Card — `drishti-tabfm-workload` (area case-review workload band)

| | |
|---|---|
| **Model** | `drishti-tabfm-workload` v1.0.0 |
| **Task** | `area_workload_band` — ordinal tabular classification (aggregate) |
| **Subject** | police **district** (`area_district`) |
| **Feature schema** | `tabfm-workload-band` v1 (approved) |
| **Lifecycle** | **staged** (approved schema + reproducible training snapshot; production GPU-TabFM cutover in Prompt 14) |
| **Environment** | `hackathon_demo` — synthetic data only |

## Intended use (approved)
- Rank / triage police **districts** by their likely **next-quarter case-review
  workload band** to support supervisory review-queue and resource planning.
- Aggregate, area/period decision support that a human supervisor reviews before
  any action.

## Prohibited use
- Any **person-level** scoring, targeting, arrest, detention, bail, guilt or other
  individual criminal-justice decision.
- Treating a band as evidence of an offence or as any individual's risk.
- Operationalising the retired synthetic offender-risk score (archived
  synthetic-demo-only in Phase 13).

## Prediction
- Ordinal band over `["Low", "Moderate", "Elevated", "High"]` for the forward
  window `(cutoff, cutoff + 3 months]`, with a calibrated top-1 confidence and an
  abstention flag.

## Label (leakage-safe)
- Verified **outcome**: the count of cases registered in the district during the
  forward 3-month window, banded into ordinal quartiles whose thresholds are fit on
  the **training split only**. The label is disjoint from, and independent of, the
  input feature formula.

## Features (10, aggregate, non-protected, strictly pre-cutoff)
`wl_recent_case_volume`, `wl_prev_quarter_volume`, `wl_trailing_year_volume`,
`wl_trend_slope`, `wl_seasonal_index`, `wl_prioryear_same_quarter`,
`wl_chargesheet_trailing_year`, `wl_backlog_ratio`, `wl_history_months`,
`wl_active_months_share`. No caste, religion, gender, juvenile status, age or any
protected/proxy attribute is present (enforced by the governed feature sensitivity
+ a leakage/proxy check).

## Data & splits
- 32 districts × 16 quarterly cutoffs (2021-12 … 2025-09) ≈ 512 rows.
- **Time split**: earliest cutoffs → train (320), middle → val (64), latest → test
  (128). **Geographic split**: a deterministic subset of districts held out for a
  spatial generalisation check.

## Models
- **Production foundation backend**: **Google TabFM v1 (GPU)** — validated at full
  scale in Prompt 14.
- **Phase-13 (CPU) candidates**: **TabPFN v2** (interim served backend — beats all
  baselines) and a deterministic **in-context** stand-in (guaranteed offline
  fallback).
- **Baselines**: prior-period (next quarter := this quarter's band), majority-class,
  and gradient-boosted trees (HistGradientBoosting; XGBoost opt-in).

## Held-out metrics (test split)
| Model | Accuracy | QWK | ECE | Beats baselines |
|---|---:|---:|---:|:--:|
| TabPFN v2 (interim served) | 0.805 | 0.914 | 0.104 | yes |
| in-context (fallback) | 0.641 | 0.805 | 0.098 | no |
| GBM baseline | 0.797 | 0.912 | 0.061 | — |
| prior-period baseline | 0.758 | 0.896 | — | — |
| majority baseline | 0.273 | 0.000 | — | — |

Geographic holdout (TabPFN): accuracy 0.781, QWK 0.915.

## Calibration, confidence and abstention
- Temperature scaling fit on the validation split; confidence is the top-1 band
  probability; the model abstains on low confidence or insufficient district
  history, and a confidence threshold-review sweep accompanies the evaluation.

## Governance
- Registered `ModelVersion` bound to the approved feature schema + a reproducible
  `TrainingDatasetSnapshot`; each prediction ties to an immutable, hashed
  `FeatureSnapshot` and a governed `PredictionResult` with a mandatory review path;
  staged/shadow/active/retired lifecycle.

## Limitations & ethics
- Synthetic-data-derived and uncertain — **not operational truth**; every result
  requires human review. Aggregate area/period support only, never person-level.
  Station-level workload is Poisson noise on this data and is intentionally not
  modelled.

---

## Prompt 24 - real Google TabFM on AWS GPU (live evidence)

The production foundation backend was executed for real on AWS in Prompt 24 (this
supersedes the "cutover in Prompt 14" note above).

| | |
|---|---|
| **Model / package** | Google **TabFM v1.0.0** PyTorch (`tabfm==1.0.0`, repo `google/tabfm-1.0.0-pytorch`) |
| **Weights licence** | **TabFM Non-Commercial License v1.0** (Google) - weights are for **non-commercial / research / evaluation** use only. The `tabfm` PyPI *code* is Apache-2.0. This hackathon uses it strictly on **synthetic data, non-commercial, non-production**; **no production/commercial licence is claimed**. |
| **Weight digest** | `928cb350becdc77cdb7a9e8c36deda88917bfd14a3091894a2dc516db58a2085` (classification/model.safetensors, ~6.25 GB), verified at load (fail-closed on mismatch). |
| **Runtime** | SageMaker asynchronous inference, `ml.g4dn.2xlarge`, **NVIDIA Tesla T4**, CUDA; in-context `TabFMClassifier` (fit sets labelled examples, never updates pretrained weights). AMP autocast fp16 on the T4 (bf16 on Ampere+). |
| **Live run** | `actual_backend=tabfm`, `actual_device=cuda`, `gpu_name=Tesla T4`, cold-start 84,166 ms (weight pull+load), inference 2,567 ms, peak GPU 6,633 MB. `artifacts/phase-24/model-runs/tabfm-run.log`. |
| **Held-out compare** | TabFM **0.9833** acc / 0.0167 ordinal MAE vs in-context CPU fallback 0.7333 vs majority 0.30 on the same 240-ctx/60-test split. `artifacts/phase-24/model-runs/baseline-compare.json`. |
| **Fail-closed** | Missing CUDA / tampered weight digest / unexpected licence -> `BackendUnavailable` (`CUDA_UNAVAILABLE`), never a fallback mislabelled as TabFM. The CPU fallback reports `actual_backend=incontext`, `actual_device=cpu`. |

Full phase evidence: `docs/phase-reports/PHASE_24_REPORT.md`.
