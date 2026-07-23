# Model Card - `drishti-timesfm-count` (area incident-count forecast)

| | |
|---|---|
| **Model** | Google **TimesFM 2.5 (200M, PyTorch)** — `google/timesfm-2.5-200m-pytorch` |
| **Package** | `timesfm==2.0.2` (PyPI) |
| **Licence** | **Apache-2.0** (package + weights). Hackathon-permitted; not a production claim. |
| **Task** | `timesfm_count_forecast` — univariate zero-shot time-series forecast (aggregate) |
| **Subject** | police **district / area** aggregate monthly incident counts |
| **Runtime** | AWS SageMaker asynchronous inference, GPU worker image, **NVIDIA T4** (ml.g4dn.2xlarge), CUDA |
| **Environment** | `hackathon_demo` — synthetic data only |

## Intended use (approved)
- Produce an aggregate **incident-count trajectory** with calibrated fan-chart
  intervals for a district/area over a short forward horizon, to support
  supervisory planning and the emergency-response forecast view.
- Aggregate, area/period decision support that a human reviews before any action.

## Prohibited use
- Any person-level scoring, targeting, or individual criminal-justice decision.
- Treating a forecast as operational truth; every result requires human review.

## Contract (Catalyst -> AWS envelope, `timesfm_count_forecast`)
- **Input**: a versioned, gap-handled **aggregate** count series in `query_rows`
  (column 0), with `observation_cutoff`, `output_schema.horizon` and
  `output_schema.freq`. No FIR JSON, narrative, evidence bytes or person
  attributes ever cross the boundary.
- **Model**: `TimesFM_2p5_200M_torch.from_pretrained(...)` + `compile(ForecastConfig(
  max_context=1024, max_horizon=64, normalize_inputs=True,
  use_continuous_quantile_head=True, fix_quantile_crossing=True,
  infer_is_positive=True))` + `forecast(horizon, inputs=[series])`.
- **Output** per step: `point`, `p10`, `p50`, `p90`, and the full decile
  `quantiles` `[mean, q0.1..q0.9]` (continuous quantile head, crossing fixed),
  plus `actual_backend=timesfm`, `actual_device`, `model_artifact_digest`,
  `observation_cutoff`, cold-start vs inference latency, peak GPU memory, and
  warnings. A confidence proxy is derived from the first-step interval width.
- **Fail-closed**: missing CUDA / weights / a series shorter than 3 points raises
  `BackendUnavailable`; there is no silent CPU substitution labelled as TimesFM.
  The always-available statistical `SeasonalForecaster`
  (`services/ml/app/forecast/timesfm.py`) is a **distinctly named** fallback.

## Weight integrity
- `model.safetensors` SHA-256 (verified at load): `2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8`
  (captured from the pinned `google/timesfm-2.5-200m-pytorch` snapshot).

## Live AWS execution evidence (T4)
Real SageMaker async invocation, `drishti-gpu-async2` on `ml.g4dn.2xlarge`
(NVIDIA Tesla T4), ap-south-1 (`artifacts/phase-24/model-runs/timesfm-run.log`):

- `actual_backend=timesfm`, `actual_device=cuda`, `gpu_name=Tesla T4`.
- `model_artifact_digest=2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8`.
- 14-step forecast with per-step `point`, `p10`, `p50`, `p90` + full decile
  `quantiles` (continuous quantile head, crossing fixed); `observation_cutoff`
  echoed for freshness; first-step interval-width confidence ~0.955.
- Latency: cold-start 2,598 ms, inference 109 ms, peak GPU ~1,871 MB.
- Fail-closed verified separately; the always-available `SeasonalForecaster`
  is the distinctly-named CPU fallback.

Full phase evidence: `docs/phase-reports/PHASE_24_REPORT.md`.

## Limitations & ethics
- Synthetic-data-derived and uncertain - **not operational truth**. Univariate
  aggregate counts only; covariate forecasting (`forecast_with_covariates`) is
  available in the package but not enabled in the demo. A new FIR changes a later
  approved aggregate snapshot; it never fine-tunes or updates the pretrained model.
