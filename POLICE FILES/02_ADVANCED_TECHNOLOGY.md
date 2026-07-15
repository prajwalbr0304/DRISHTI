# 02 — Advanced Technology
### The AI/ML brain: foundation models, spatio-temporal forecasting, and the production stack

> The client's stated top criterion is *"who is bringing advanced technology to the table."* This document is the answer. It explains what each model is, why it was chosen, its limits, and how it is served — with research citations so the choices are defensible in a technical review. TabFM is committed for prediction now; the spatial models complement it; the conversational/agent layer follows in a later phase.
>
> *Content synthesized from the sources cited inline; rephrased for licensing compliance.*

---

## 1. The core idea: two prediction brains, not one

Crime prediction is really two different questions, and one model cannot answer both well:

| Question | Nature | Right tool |
|---|---|---|
| *"Which **offenders / districts** are high-risk next period, given a row of features?"* | **Tabular** — heterogeneous columns (prior counts, severity trend, demographics, socio-economic overlay) | **TabFM** (zero-shot tabular foundation model) |
| *"**Where** and **when** will the next hotspot appear on the map?"* | **Spatio-temporal** — space × time, self-exciting, near-repeat | **Self-exciting point process + ST-GNN** (see [Doc 05](05_GEOSPATIAL_CRIME_ANALYTICS.md)) |
| *"What is the **crime-count trajectory** for this beat over the next 8 weeks?"* | **Pure time series** | **TimesFM** (zero-shot forecaster) |

DRISHTI runs all three and reconciles them in the UI. This section covers the tabular and time-series foundation models; the spatial models get their own document because they carry the map experience.

**Why foundation models at all?** Because they are *zero-shot*. The traditional path — train an XGBoost per district, tune hyperparameters, re-engineer features, re-train as data drifts — is exactly the operational bottleneck these models remove. You pass data in as context and get calibrated predictions out in a single forward pass, with no training loop to own. That is both a capability story and an operations story.

---

## 2. TabFM — Google's zero-shot tabular foundation model *(primary prediction engine)*

**What it is.** TabFM is a foundation model built specifically for tabular classification and regression, introduced by Google Research. It reframes tabular prediction as an **in-context learning (ICL)** problem — the same idea that lets large language models learn a task from examples in the prompt. You hand the model your labelled historical rows *and* the rows you want predicted as a single input; it reads the relationships between columns and rows at inference time and returns predictions in one forward pass — no per-dataset training, no hyperparameter search, no manual feature engineering. It is published on Hugging Face and GitHub, and is the tabular sibling to Google's TimesFM time-series model. (Source: [Google Research — *Introducing TabFM*](https://www.research.google/blog/introducing-tabfm-a-zero-shot-foundation-model-for-tabular-data/).)

**How it works, briefly.** TabFM combines ideas from TabPFN and TabICL into a hybrid architecture with three mechanisms (per Google's description, rephrased): *alternating attention across both columns and rows* so the model captures feature interactions natively; *row compression* into dense vectors; and *in-context learning* over the provided examples. The practical upshot: the "feature engineering" a data scientist would normally do by hand is absorbed into the model's attention.

**How DRISHTI uses it — two integration points from the project plan:**

- **Offender risk scoring (Phase 9).** Build a context window of labelled historical offender rows — features like prior-incident count, severity trend, recency, MO cluster, district — then query the target offenders for a risk level in one pass. Write results to `CrimeRiskScore` (using its `AccusedMasterID` column) with `ModelVersionID`, `RiskScore`, `RiskLevel`, and a `Factors` JSONB for explainability.
- **District/beat forecasting (Phase 12).** Use recent per-district time-series features (crime counts by category, trend, plus the Phase 8 socio-economic overlay) as context rows; query next-period risk per district. Write to `CrimePrediction` (`PredictionStart/End`, `PredictedCount`, `Probability`, `Confidence`, `Features`).

**Constraints to design around** (shared by this family of models):
- Prediction quality is best with a **bounded number of classes** — keep risk classification to a small ordinal set (e.g., Low / Guarded / Elevated / High / Severe), not dozens of buckets.
- **Context memory scales with rows** — sample a representative few hundred–few thousand rows per scoring batch rather than passing every offender at once. Stratify the sample so rare-but-important classes (e.g., habitual violent offenders) are represented.
- Treat outputs as **decision support, not verdicts** — every score is written with its inputs and model version so it is auditable and contestable (Phase 13).

---

## 3. TabPFN v2 — the alternative / fallback tabular model

It is worth knowing the landscape, because a technical reviewer will ask "why TabFM and not TabPFN?"

**What it is.** TabPFN (Tabular Prior-data Fitted Network) is a transformer-based tabular foundation model from Prior Labs, published in *Nature* in 2025. It is pre-trained purely on synthetic data drawn from a prior over tabular problems, and reports strong results on small datasets in very little time. (Source: [Hollmann et al., *Accurate predictions on small data with a tabular foundation model*, Nature, 2025](https://www.nature.com/articles/s41586-024-08328-6).)

**Known strengths & limits** (useful for honest evaluation):
- Excellent on **small, class-balanced** problems with modest dimensionality; weaker on very high-dimensional, many-category, or very large-scale tasks — a limitation studied directly in the literature, along with test-time divide-and-conquer strategies to mitigate it. (Source: [*Understanding TabPFN v2's strengths and extending its capabilities*, arXiv:2502.17361](https://arxiv.org/abs/2502.17361).)
- In "open-environment" evaluations with distribution shift, well-tuned **tree ensembles remain competitive** for general large-scale tabular tasks — so DRISHTI keeps a gradient-boosted baseline for sanity-checking, not as the headline. (Source: [*Realistic Evaluation of TabPFN v2 in Open Environments*, arXiv:2505.16226](https://arxiv.org/html/2505.16226v1).)
- A time-series variant, **TabPFN-TS**, reaches top ranks on public forecasting benchmarks with lightweight feature engineering despite a compact size. (Source: [*The Tabular Foundation Model TabPFN Outperforms Specialized Time Series Forecasting Models*, arXiv:2501.02945](https://arxiv.org/abs/2501.02945).)

**DRISHTI's position:** **TabFM is primary** (it is the client's pick and is purpose-built for zero-shot ICL at the scale we need). **TabPFN v2 is a drop-in alternative** behind the same `ModelVersion` abstraction — because both are foundation models consumed as "context in → prediction out," swapping them is a serving-config change, not a rewrite. A **gradient-boosted baseline (XGBoost/LightGBM)** is retained purely as a calibration reference.

---

## 4. TimesFM — pure temporal forecasting

For questions that are cleanly time-series ("crime-count trajectory for this beat over 8 weeks"), a dedicated forecaster is cleaner than reshaping the problem into tabular form.

**What it is.** TimesFM is Google Research's decoder-only transformer foundation model for time-series forecasting, pre-trained so it forecasts **zero-shot** — accurate predictions on unseen series without retraining. It is available as open weights (e.g., `google/timesfm-2.5-200m-pytorch` on Hugging Face) and is also offered inside BigQuery/AlloyDB for teams already in that ecosystem. Recent work adds in-context fine-tuning to make it a few-shot learner. (Sources: [TimesFM on Hugging Face](https://huggingface.co/docs/transformers/main/model_doc/timesfm); [Google Cloud — *TimesFM in BigQuery/AlloyDB*](https://cloud.google.com/blog/products/data-analytics/timesfm-models-in-bigquery-and-alloydb/); [Google Research — *Time series foundation models can be few-shot learners*](https://research.google/blog/time-series-foundation-models-can-be-few-shot-learners).)

**DRISHTI's use:** power the **Trends → Forecast** fan charts (Analytics §4.6) and provide the temporal component that the spatio-temporal hotspot model consumes. Because TabFM and TimesFM are siblings from the same lab and both zero-shot, presenting them together ("tabular + temporal foundation models") is a clean, coherent technology narrative for the pitch.

---

## 5. Semantic search & embeddings — "find cases like this one"

**The capability:** an investigator describes or opens a case and asks for the most similar historical cases by *modus operandi and context*, not keywords. This is Phase 10, and it is already scaffolded in the schema.

**How it works in DRISHTI:**
- `CrimeEmbedding` stores a `vector(768)` per case (and per entity), indexed with **HNSW** for approximate-nearest-neighbour search under cosine distance, using **pgvector** inside the same Supabase Postgres.
- At query time: embed the query case's features → `ORDER BY embedding <=> :query_vec LIMIT 5` → return the top-5 similar cases with their outcomes.
- The embedding dimension (768) is a config; match it to whichever encoder is deployed (e.g., a multilingual sentence-transformer so Kannada and English case text land in the same space). Keep `EmbeddingDim` and the column in sync.

This is strictly better than pre-computing a `similar_case_links` table: similarity is computed at query time against the live corpus, so new cases are searchable immediately.

---

## 6. The language layer — NL→SQL and grounded summaries

**Natural-language querying (Phases 2–3).** An LLM translates an investigator's question (English or Kannada) into **read-only SQL** against the real schema. Non-negotiable design constraints:
- **Read-only, enforced at execution:** whitelist `SELECT` only; reject any DDL/DML; run under a **restricted DB role**. The model's SQL is a *proposal*, executed by a guarded layer.
- **Schema-grounded:** the model is given the actual schema; it cannot reference a column that doesn't exist. Ambiguity triggers a clarifying question, not a guess.
- **Cited:** every answer returns the SQL and the specific record IDs used — the Phase 13 evidence-trail contract.
- **Multilingual:** for domain terms that generic translation mangles (FIR, accused, MO), a curated Kannada police/legal glossary is injected so translation stays correct.

**Grounded summarization (Phase 10).** Case summaries and timelines are generated *strictly* from linked records, with every claim cited to a source record ID. This is the "Ontology-Augmented Generation" pattern — the model is grounded in real objects, so it summarizes rather than invents (concept from [Palantir — Logic Tools for RAG/OAG](https://blog.palantir.com/building-with-palantir-aip-logic-tools-for-rag-oag-fdaf8938d02e), rephrased for compliance).

**Model choice is pluggable.** The LLM sits behind an interface; a hosted API or an India-hosted open model (e.g., a Llama-/Mistral-class or an Indic-tuned model) can serve it, chosen on data-residency and cost grounds. What matters architecturally is the *contract* (grounded, read-only, cited), not the specific vendor.

---

## 7. Complementary spatial models (full detail in Doc 05)

Summarized here so the model roster is complete; the pipeline, math, and map UX are in [05 — Geospatial & Crime-Pattern Analytics](05_GEOSPATIAL_CRIME_ANALYTICS.md).

| Model | Role | One-line rationale |
|---|---|---|
| **Kernel Density Estimation (KDE)** | baseline hotspot surface | fast, interpretable, the analyst's familiar heatmap |
| **DBSCAN / ST-DBSCAN** | incident clustering | finds dense clusters in space (and time) without a preset count |
| **Self-exciting point process (Hawkes / ETAS)** | near-repeat forecasting | models crime "aftershocks" — a burglary raises nearby short-term risk; the basis of the well-known predictive-policing approach |
| **Spatio-temporal GNN (ST-GCN + Transformer)** | learned hotspot forecasting | districts/beats as a graph; captures spatial spillover + long temporal dependence |
| **Risk Terrain Modeling (RTM)** | environmental risk | ties risk to place features (bars, highways, ATMs) for explainable resourcing |

---

## 8. Research bibliography (defensible choices)

Curated, recent, and load-bearing. All are linked for the technical annex of the pitch.

**Tabular foundation models**
- Hollmann et al., *Accurate predictions on small data with a tabular foundation model*, **Nature** 637 (2025). [nature.com](https://www.nature.com/articles/s41586-024-08328-6)
- *Understanding TabPFN v2's Strengths and Extending Its Capabilities*, arXiv:2502.17361. [arxiv.org](https://arxiv.org/abs/2502.17361)
- *Realistic Evaluation of TabPFN v2 in Open Environments*, arXiv:2505.16226. [arxiv.org](https://arxiv.org/html/2505.16226v1)
- *The Tabular Foundation Model TabPFN Outperforms Specialized Time Series Forecasting Models* (TabPFN-TS), arXiv:2501.02945. [arxiv.org](https://arxiv.org/abs/2501.02945)

**Time-series foundation models**
- Google Research, *Introducing TabFM: A zero-shot foundation model for tabular data*. [research.google](https://www.research.google/blog/introducing-tabfm-a-zero-shot-foundation-model-for-tabular-data/)
- Google Research, *Time series foundation models can be few-shot learners* (ICML 2025). [research.google](https://research.google/blog/time-series-foundation-models-can-be-few-shot-learners)

**Spatio-temporal crime prediction**
- *Research on a Crime Spatiotemporal Prediction Method Integrating Informer and ST-GCN*, MDPI Big Data & Cognitive Computing, 2025. [mdpi.com](https://www.mdpi.com/2504-2289/9/7/179)
- *Uncertainty-Aware Crime Prediction With Spatial Temporal Multivariate Graph Neural Networks*, arXiv:2408.04193. [arxiv.org](https://arxiv.org/abs/2408.04193v1)
- *Crime Hotspot Prediction Using Deep Graph Convolutional Networks*, arXiv:2506.13116. [arxiv.org](https://arxiv.org/abs/2506.13116)
- *Spatial-Temporal Sequential Hypergraph Network for Crime Prediction*, arXiv:2201.02435. [arxiv.org](https://ar5iv.labs.arxiv.org/html/2201.02435)
- *Crime Prediction by Data-Driven Green's Function method* (self-exciting point process), arXiv:1704.00240. [emergentmind](https://api.emergentmind.com/papers/1704.00240)
- Caplan & Kennedy, *Risk Terrain Modeling* — risk clusters & police resource allocation, J. Quantitative Criminology. [springer.com](https://link.springer.com/doi/10.1007/s10940-010-9126-2)

> **Ethics note carried through the whole stack:** predictive policing has documented feedback-loop and bias risks. DRISHTI treats every prediction as *decision support with visible confidence and provenance*, forecasts at area/period granularity for **resource allocation** rather than targeting individuals from a model score alone, keeps a human in the loop, and logs model version + inputs for audit. This is a design stance, stated in the pitch, not an afterthought.

---

## 9. Production OSS & serving — what actually ships

Everything below is open-source and production-usable, or an open-weights model.

| Layer | Choice | License / basis |
|---|---|---|
| Tabular prediction | **TabFM** (primary), **TabPFN v2** (alt) | open weights (HF/GitHub) |
| Baseline / calibration | **XGBoost / LightGBM** | Apache-2.0 / MIT |
| Time-series | **TimesFM 2.5** | open weights (HF) |
| Spatial clustering | **scikit-learn** (DBSCAN), **PySAL** | BSD |
| Self-exciting process | **tick** / custom Hawkes | BSD |
| ST-GNN | **PyTorch Geometric (Temporal)** | MIT |
| Embeddings / ANN | **sentence-transformers** + **pgvector (HNSW)** | Apache-2.0 / PostgreSQL |
| Full-text search | **Postgres FTS** (`tsvector`) + **pg_trgm** | PostgreSQL |
| Model serving | **FastAPI** + **ONNX Runtime / TorchServe**, containerized | MIT / Apache-2.0 |
| Orchestration/retraining refresh | scheduled jobs (cron/Airflow-style) refresh matviews & re-score | Apache-2.0 |

**Serving pattern.** ML lives behind a thin **FastAPI** service (its own container, deployable as a separate Catalyst AppSail service). It:
1. pulls a stratified context sample from Postgres,
2. runs the foundation model (GPU optional for TabFM/TimesFM; the models are compact enough that CPU inference is viable for batch scoring),
3. writes typed results back (`CrimeRiskScore`, `CrimePrediction`, `CrimeHotspot`, `AlertHistory`) with a `ModelVersion` row,
4. refreshes the dependent materialized views (`mv_district_risk_profile`, `mv_active_hotspots`).

Scoring is **batch + on-demand**: nightly batch keeps district/offender scores fresh; an on-demand path re-scores a single entity when an officer opens its profile.

---

## 10. Explainability as an architecture, not a feature (Phase 13)

Because the differentiator is trust, explainability is structural:

- **Every AI write is a typed row with `ModelVersionID` + input snapshot** (`ModelInference`), so any score is reproducible: same inputs + same model version → same output.
- **The shared response contract** across every AI endpoint: `{ answer, confidence, source_record_ids[], reasoning_summary, model_version }`. The UI's provenance chip ([01 §8.5](01_UX_UI_ARCHITECTURE.md)) renders exactly this.
- **Factor attributions** for risk scores (stored in `Factors` JSONB) drive the gauge-plus-factor-bars widget, so an officer sees *why* — "3 prior offences, escalating severity, active MO cluster" — not just a number.
- **Calibration is monitored:** the Model Explainability sub-page shows reliability/calibration plots and drift, so a degrading model is visible before it misleads anyone.

---

*Previous: [← 01 UX / UI Architecture](01_UX_UI_ARCHITECTURE.md)  ·  Next: [03 Data Visualization →](03_DATA_VISUALIZATION.md)*
