# 05 — Geospatial & Crime-Pattern Analytics
### Hotspot detection and spatio-temporal forecasting that complements TabFM

> The client asked specifically how to do *geospatial / crime-pattern analysis (hotspot prediction, not just TabFM tabular forecasting)* and how a **spatio-temporal model could complement TabFM**. This document is the answer: why tabular forecasting alone isn't enough for "where," the layered model pipeline, the data flow into the existing schema, and the map experience it drives. It powers the [Map & Hotspots destination](01_UX_UI_ARCHITECTURE.md#45--map--hotspots--geospatial-operations--phases-7--12).

---

## 1. Why TabFM alone can't answer "where"

TabFM is superb at a **row-shaped** question: *given this district's features this month, what's next month's risk class?* But crime is not only rows — it has a **physics of place and time** that a tabular model doesn't natively represent:

- **Spatial spillover.** A surge in one beat raises risk in *adjacent* beats. Neighbour relationships are geometry, not columns.
- **Near-repeat / self-excitation.** A burglary sharply raises the odds of *another burglary nearby within days* — then decays. Crime "echoes."
- **Fine spatial resolution.** "Which district next month" is useful for the DGP; a Sub-Inspector needs "which 250 m grid cell tonight."
- **Continuous space.** Incidents are points on a surface, not pre-bucketed rows.

So DRISHTI runs a **layered spatial stack** and reconciles it with TabFM: TabFM answers *district/offender risk class* (the tabular question), the spatial models answer *where the surface will bloom and when* (the geometry question). Both write into the same schema and appear together on the map, each with its confidence.

---

## 2. The layered model pipeline

Four layers, from a familiar baseline to a learned forecaster. Ship them in order; each is independently useful.

### Layer 0 — Descriptive hotspots (baseline, Phase 7)
Where crime *has been* dense. Fast, interpretable, the analyst's trusted heatmap.
- **Kernel Density Estimation (KDE)** → a smooth density surface written to `CrimeHotspot` (`geom`, `Centroid`, `Intensity`, `CaseCount`, `PeriodStart/End`).
- **DBSCAN / ST-DBSCAN** on incident points (`CaseMaster.geom` + `IncidentFromDate`) → discrete clusters with no preset cluster count; ST-DBSCAN adds the *time* dimension so a "cluster" is dense in space *and* period.
- **Library:** scikit-learn (DBSCAN), PySAL / PostGIS for KDE and spatial stats.

### Layer 1 — Near-repeat forecasting (self-exciting, the crime "physics")
The step beyond description: model that one crime *raises the near-term probability* of another nearby.
- **Self-exciting point process (Hawkes / ETAS-style).** Mathematically the same family used for earthquake aftershocks — each event adds a decaying "excitation" in space and time. This is the well-documented basis of near-repeat predictive policing. (Sources: [*Crime Prediction by Data-Driven Green's Function method*, arXiv:1704.00240](https://api.emergentmind.com/papers/1704.00240); self-exciting/near-repeat literature.)
- **Output:** a short-horizon (hours–days) risk intensity per grid cell → `CrimePrediction`.
- **Library:** `tick` (Hawkes) or a custom kernel; PostGIS grid for the spatial bins.

### Layer 2 — Environmental risk (explainable "why here")
Not everything is history-driven; some places are risky because of *what's there*.
- **Risk Terrain Modeling (RTM).** Attributes risk to spatial features — proximity to highways, bars, ATMs, bus/railway stations, borders. Produces an **explainable** risk surface that supports resource allocation and survives scrutiny ("this corridor is high-risk because of X and Y"), not a black box. (Source: [Caplan & Kennedy, *Risk Terrain Modeling*, J. Quantitative Criminology](https://link.springer.com/doi/10.1007/s10940-010-9126-2).)
- **Fit for KSP context:** border districts (NDPS/smuggling), highway corridors (drug transport), market/transit hubs (theft) — exactly the patterns the synthetic data already encodes.

### Layer 3 — Learned spatio-temporal forecasting (the advanced layer)
The state-of-the-art layer, and the one that most complements TabFM.
- **Spatio-temporal Graph Neural Network:** model districts/stations/beats as a **graph** (nodes = areas, edges = adjacency/road-network), and learn crime evolution across both space and time. Recent work combines an **ST-GCN** (spatial spillover) with a **Transformer/Informer** (long temporal dependence) and reports strong community-level results on large real datasets. (Sources: [*Integrating Informer and ST-GCN*, MDPI 2025](https://www.mdpi.com/2504-2289/9/7/179); [*Uncertainty-Aware Crime Prediction with ST Multivariate GNNs*, arXiv:2408.04193](https://arxiv.org/abs/2408.04193v1); [*Crime Hotspot Prediction Using Deep Graph Convolutional Networks*, arXiv:2506.13116](https://arxiv.org/abs/2506.13116).)
- **Uncertainty-aware variants** emit probability distributions, not point estimates — essential for the honest **confidence bands** on the forecast map.
- **Library:** PyTorch Geometric (Temporal).
- **Pure-temporal companion:** **TimesFM** ([Doc 02](02_ADVANCED_TECHNOLOGY.md)) supplies the per-area count trajectory that feeds both the ST-GNN and the Analytics fan charts.

---

## 3. How the layers complement TabFM (the reconciliation)

The layers are not redundant; they answer different resolutions of the same concern and are **fused** for the officer.

| Layer | Question | Resolution | Horizon | Writes to |
|---|---|---|---|---|
| **TabFM** | risk *class* per district / offender | district / person | next period | `CrimeRiskScore`, `CrimePrediction` |
| **Hawkes (L1)** | near-repeat risk after an event | grid cell (250 m) | hours–days | `CrimePrediction` |
| **RTM (L2)** | baseline environmental risk | grid cell | slow-changing | `CrimeHotspot`/risk surface |
| **ST-GNN (L3)** | learned risk surface + spillover | beat / grid | days–weeks | `CrimePrediction` |

**Fusion rule (transparent, not a mystery ensemble):**
- TabFM sets the **district-level expectation** (the "how much" and "what class").
- The spatial layers **distribute that expectation over geometry** (the "where within the district") and add **near-term spikes** (Hawkes) that a monthly tabular view would miss.
- The map shows the **fused surface** with a **layer switcher** so an analyst can inspect each model alone. Every predicted cell carries the contributing models and a confidence — clicking it opens the Evidence Trail (which models, which inputs, `ModelVersion`).

This is defensible in review: it's a **stacked, inspectable pipeline**, each layer with a citation and a job, not one opaque model claiming to do everything.

---

## 4. Data flow (all inside the existing schema)

```
CaseMaster.geom / IncidentFromDate ──┐
SocialIndicator / EconomicIndicator ─┼─► FastAPI ML service (Doc 02 §9)
WeatherIndicator ────────────────────┤     ├─ L0 KDE/DBSCAN  ─► CrimeHotspot
Unit/District boundaries (PostGIS) ──┘     ├─ L1 Hawkes      ─► CrimePrediction
                                            ├─ L2 RTM         ─► risk surface
                                            ├─ L3 ST-GNN      ─► CrimePrediction
                                            └─ threshold breach ─► AlertHistory
                                                     │
                          mv_active_hotspots ◄───────┘ (refreshed) ─► Map UI (deck.gl/kepler.gl)
```

- **Inputs** already exist: incident geometry/time on `CaseMaster`; the socio-economic/weather overlays as their own tables (a genuine advantage — weather feeds short-term correlation and the ST-GNN covariates).
- **Outputs** are typed rows with `ModelVersion` (auditable), not files.
- **Emerging-trend alerts (Phase 7/12):** when a cell/category's current count exceeds its historical rolling average by a configurable threshold, write to `AlertHistory` (Severity, Title, Payload) → the map's **red-zone pulse** and the 🔔 feed.
- **Refresh cadence:** nightly batch for L0/L2/L3 surfaces + matview refresh; near-real-time for L1 near-repeat when a new FIR lands in a watched area.

---

## 5. The map experience (ties to Docs 01 & 03)

The Map & Hotspots destination is where this stack becomes tangible. Sub-pages map 1:1 to the layers:

| Sub-page | Shows | Model behind it |
|---|---|---|
| **Live Map** | current incidents, clustered, drill district→station→point | descriptive |
| **Hotspots** | KDE/DBSCAN density surface, time-of-day filter | L0 |
| **Forecast** | next-period predicted risk: choropleth (TabFM) + fine surface (ST-GNN/Hawkes) with **confidence hatching** and a **horizon selector** | TabFM + L1/L3 |
| **Patrol Planning** | beats overlaid on forecast; **coverage-gap** highlighting; suggested reallocation | fused surface + RTM |
| **Red-Zone Alerts** | active `AlertHistory` as **pulsing markers**; ack/assign | threshold breach |

Signature interactions (from [01](01_UX_UI_ARCHITECTURE.md)):
- **Global time-scrubber** drives everything — drag it and hotspots bloom and fade through time; set it in the future and the Forecast layer takes over with visible confidence.
- **Drill-down** district → station → point; the policymaker is **capped at district choropleth** (no point-level pins — privacy).
- **Rate, not count**, on choropleths; **legend always present**; **3-D hex extrusion** in kepler.gl for the briefing-room view.
- **"Forecast this district"** and **"explain this hotspot"** route context into Ask DRISHTI for a grounded, cited narrative.

Rendering stack: **deck.gl / kepler.gl** (WebGL, millions of points at 60 fps) over **MapLibre** base tiles, all fed by **PostGIS** server-side aggregation. Details in [03 §3](03_DATA_VISUALIZATION.md).

---

## 6. Karnataka-specific patterns the models should capture

The synthetic data already encodes these, so the pipeline can be validated against known ground truth:

- **Bengaluru** — cyber fraud, vehicle theft, robbery concentration (urban, high-density).
- **Coastal Karnataka** (Dakshina Kannada, Udupi, Uttara Kannada) — smuggling corridors.
- **Border districts** (Belagavi, Kalaburagi, Bidar…) — NDPS / illegal transport along highways.
- **Temporal:** festival-season theft spikes, weekend/Friday-night assault and drunk-driving, monsoon suppression of outdoor crime, summer burglary.
- **Near-repeat:** burglary and vehicle-theft clusters that bloom for days after a first event — the Hawkes layer's home turf.

A good validation slide: overlay the model's predicted hotspots on held-out incidents and show the **PAI (Prediction Accuracy Index) / hit-rate** — the standard hotspot-forecast metric — per district and crime type.

---

## 7. Responsible-forecasting guardrails (carried from Doc 02)

Predictive geospatial policing has real, documented risks (feedback loops, over-policing of already-surveilled areas). DRISHTI's stance, stated in the pitch and built into the product:

- Forecast at **area/period** granularity for **resource allocation**, not individual targeting from a score.
- **Show confidence** on every predicted cell; never present a forecast as certainty.
- **Human-in-the-loop:** a forecast informs a patrol decision; it does not make one.
- **Audit everything:** every surface is a typed row with `ModelVersion` + inputs, reproducible and contestable.
- **Watch for feedback:** monitor whether predictions merely mirror past enforcement; the socio-economic and RTM layers help distinguish *risk* from *reporting/enforcement bias*.

---

*Previous: [← 04 Network / Graph Analysis](04_NETWORK_GRAPH_ANALYSIS.md)  ·  Back to: [00 Master Plan](00_MASTER_PLAN.md)  ·  Open the [clickable mockups →](mockups/index.html)*
