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
