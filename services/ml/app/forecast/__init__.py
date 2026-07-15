"""Crime forecasting + early warning (Phase 12 / doc 05 Layers 1-3 + doc 02 §4).

A stacked, INSPECTABLE spatial forecast pipeline reconciled with TabFM:

  * tabfm      — next-period risk CLASS per district from recent time-series
                 features + the socio-economic overlay (the "how much / what
                 class"); the district-level expectation.
  * timesfm    — per-area crime-count TRAJECTORY with fan-chart confidence bands
                 (real TimesFM if importable, else a seasonal statistical
                 forecaster behind the same interface).
  * near_repeat— self-exciting (Hawkes/ETAS) short-horizon grid-cell intensity
                 after recent events; triggerable near-real-time on a new FIR.
  * st_gnn     — uncertainty-aware spatio-temporal spillover over the district
                 graph (emits mean+std -> confidence bands; PyG-Temporal drops in).
  * fusion     — TabFM sets the district expectation; the spatial layers
                 distribute it over geometry and add near-term spikes. Every fused
                 cell records its contributing models + confidence (Evidence Trail),
                 and each layer can be inspected alone (layer switcher).

All layers write typed CrimePrediction rows with a ModelVersion + ModelInference
audit and a confidence; early-warning breaches raise AlertHistory. Forecasts are
area/period decision support with visible confidence (doc 05 §7).
"""
