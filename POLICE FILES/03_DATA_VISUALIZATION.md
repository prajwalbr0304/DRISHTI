# 03 — Data Visualization Strategy
### One right way to draw each kind of data point

> The client asked for *"advanced data visualization techniques for different types of data or feature"* and for the *type of widget* to make the data instantly clear. This document is the visual grammar of DRISHTI: for every shape of data the platform holds, the chosen encoding, the reasoning, the advanced techniques worth the effort, and the exact open-source library to build it with. It operationalizes Law 2 from [Doc 01](01_UX_UI_ARCHITECTURE.md) — *the data type chooses the visual.*

---

## 1. Principles for police data specifically

Generic dashboard advice is not enough here. Four rules are shaped by *who* is looking and *why*:

1. **An officer reads for action, not admiration.** Every chart must answer "so what do I do?" within one glance. Decorative variety is a bug. A small, fixed vocabulary of charts, reused everywhere, means the officer learns the language once.
2. **Encode uncertainty honestly.** A forecast is not a fact. Predicted values always show their confidence (fan bands, hatching, opacity). Hiding uncertainty on a policing tool is a safety problem, not a style choice.
3. **Provenance travels with the pixel.** Any derived visual carries the "⌄ source" affordance from the widget frame ([01 §2.4](01_UX_UI_ARCHITECTURE.md)). A number you cannot trace is a number an officer should not act on.
4. **Sensitive by default.** Aggregate views never leak individuals. Below a small count threshold (k-anonymity), a cell is suppressed, not shown — critical for the policymaker role and any exportable chart.

---

## 2. The visual grammar — data shape → encoding (the master catalogue)

Each entry: what the data *is*, the primary encoding, the advanced upgrade, what to avoid, and the DRISHTI screen it powers.

### 2.1 A single measure (with movement) → **KPI stat card**
- **Primary:** big tabular number + label + delta vs. prior period + a 12-point **sparkline**.
- **Advanced:** **bullet chart** when there's a target/threshold (e.g., chargesheet rate vs. target); micro-color the delta by direction with an arrow *and* sign (never colour alone).
- **Avoid:** a pie chart for one value; gauges for non-bounded metrics.
- **Powers:** Command Center KPI band; Trends deltas.

### 2.2 Parts of a whole, few categories → **horizontal bar / treemap**
- **Primary:** sorted **horizontal bars** (labels are readable, comparison is length — the easiest visual judgement).
- **Advanced:** **treemap** when there's hierarchy (Crime Head → Sub-Head) and you want share *and* structure at once; **icicle** if the hierarchy is deeper.
- **Avoid:** pie/donut beyond ~4 slices; 3-D anything.
- **Powers:** crime mix by head; caseload by status.

### 2.3 A value over time → **line / area with anomaly band**
- **Primary:** **line** for one series, **stacked area** for composition-over-time. Tabular numerals in tooltips.
- **Advanced:** overlay a **rolling-average band**; shade **statistically anomalous points** (the Phase 7 emerging-trend logic) so a spike is *pre-attentively* obvious; add **STL decomposition** (trend / seasonal / residual) as a toggle for analysts investigating a seasonal spike.
- **Avoid:** dual y-axes (they imply correlations that may not exist); one bar per day for months of data.
- **Powers:** Analytics → Trends; seasonal analysis.

### 2.4 Events along a life-cycle → **horizontal event timeline**
- **Primary:** a horizontal track with typed event markers (registered, incident window, arrest, chargesheet, court date).
- **Advanced:** **swimlanes** when multiple actors/threads run in parallel (e.g., several accused's arrest timelines within one case); brush-to-zoom on dense timelines.
- **Avoid:** representing a sequence as a plain date table.
- **Powers:** Case → Timeline; Entity → Criminal History.

### 2.5 Point locations → **map: cluster / hexbin / heat**
- **Primary:** **clustered points** at wide zoom (counts, not overlapping dots), resolving to individual incidents on zoom-in.
- **Advanced:** **hexbin aggregation** for even density reading; **KDE heat surface** for hotspots; **time-animated** points driven by the global scrubber; **3-D extrusion** (hex height = count) in kepler.gl for a briefing-room "wow" that still encodes data honestly.
- **Avoid:** thousands of raw pins (unreadable, and a privacy risk); heat maps without a legend.
- **Powers:** Map → Live / Hotspots. Full method in [Doc 05](05_GEOSPATIAL_CRIME_ANALYTICS.md).

### 2.6 Values by region → **choropleth**
- **Primary:** district/beat polygons shaded by a **rate** (per capita), never raw counts (which just re-draw the population map).
- **Advanced:** **bivariate choropleth** to show two variables at once (e.g., crime rate × unemployment) for the socio-economic story; **choropleth + confidence hatching** for forecasts.
- **Avoid:** shading by raw counts; rainbow colour ramps (perceptually misleading) — use a single-hue sequential or a diverging ramp centered on a meaningful midpoint.
- **Powers:** Map forecast; Socio-Economic; the policymaker's world (district-only).

### 2.7 Relationships between entities → **node-link graph**
- **Primary:** force-directed layout; **node size = importance** (degree/PageRank), **node colour = entity type**, **edge thickness = relationship strength/frequency**, **edge style = relationship type**.
- **Advanced:** **community colouring** (Louvain clusters); **halo/glow** on high-centrality "kingpin" nodes; **hop-by-hop reveal** (expand neighbours on click) to avoid hairballs; **hierarchical or geo-anchored layouts** as alternates; **edge bundling** on dense graphs.
- **Avoid:** dumping the whole graph at once (a "hairball" teaches nothing); adjacency tables in place of a graph.
- **Powers:** Network Analysis; Case → Network; Entity → Network. Encoding detail in [Doc 04](04_NETWORK_GRAPH_ANALYSIS.md).

### 2.8 Flows / money movement → **Sankey + directed weighted graph**
- **Primary:** **Sankey** for volume-of-flow between accounts/stages (width = amount); a **directed graph** for the account-to-account topology.
- **Advanced:** **animated particle flow** along edges to show direction and tempo of a money trail; **loop highlighting** for circular transactions; **threshold markers** for structuring/smurfing (many transfers just under a reporting limit).
- **Avoid:** a table of transactions where a flow diagram is meant — the pattern is the point.
- **Powers:** Network → Money Trail (Phase 11).

### 2.9 A score and *why* → **gauge + signed factor bars**
- **Primary:** a bounded **radial or linear gauge** for the score (Low→Severe), beside **signed horizontal bars** for the top contributing factors (SHAP-style: "+3 prior offences", "+escalating severity", "−long dormancy").
- **Advanced:** a **waterfall** from base rate to final score for full attribution; **peer distribution** ("this offender vs. district distribution") for context.
- **Avoid:** a lone risk number with no drivers — untrustworthy and unusable.
- **Powers:** Entity → Risk (TabFM, Phase 9); alert risk.

### 2.10 Relationship between two variables → **scatter + correlation matrix**
- **Primary:** **scatter** with a fitted line and a clearly labelled "correlational, not causal" caption; **correlation-matrix heatmap** for many variables at once.
- **Advanced:** **hexbin scatter** when districts×periods produce many points; **small multiples** (one scatter per crime category) to compare relationships side by side.
- **Avoid:** implying causation; two lines on twin axes as a "correlation."
- **Powers:** Analytics → Socio-Economic (Phase 8).

### 2.11 Ranked similarity → **ranked list with similarity bars**
- **Primary:** ordered cards, each with a **similarity bar** (0–100%) and the key matching features called out.
- **Advanced:** a **2-D embedding projection** (UMAP/t-SNE of `CrimeEmbedding`) so an analyst can *see* the neighbourhood a case sits in — a genuinely novel view for investigators.
- **Powers:** Case → Similar Cases (Phase 10).

### 2.12 Grounded prose → **citation-annotated text card**
- **Primary:** the AI summary with **inline numbered citations** (Perplexity-style) that resolve to source records on hover/click.
- **Advanced:** claim-level confidence shading; a toggle to reveal the exact SQL/records behind the whole summary.
- **Powers:** Case → AI Summary; Ask DRISHTI answers.

### 2.13 Process state → **status pipeline (stepper)**
- **Primary:** a horizontal stepper (Registered → Under Investigation → Chargesheeted → Trial → Disposed) with the current stage lit and durations between stages.
- **Advanced:** **funnel** across a caseload (how many cases sit at each stage) for supervisors; colour a stalled stage by dwell-time.
- **Powers:** Case → Overview; Supervisor Command Center.

### 2.14 Comparison of items → **grouped bar / bullet / small multiples**
- **Primary:** grouped bars for a few items; **small multiples** (a grid of identical mini-charts) for many — the cleanest way to compare 30 districts without 30 colours.
- **Powers:** split-view compare; station-vs-station.

### 2.15 Uncertainty itself → **fan chart / hatching / opacity**
- A cross-cutting encoding, not a standalone widget: forecasts render as a **fan** (median + confidence bands); map forecasts use **hatching density**; low-confidence anything is **de-saturated**. Confidence is never hidden and never encoded by hue alone.

---

## 3. Geospatial visualization — the stack

| Need | Library | Why |
|---|---|---|
| GPU point/hex/heat/arc layers, millions of features at 60 fps | **deck.gl** (WebGL2/WebGPU) | the performance ceiling; composable layers ([visgl/deck.gl](https://github.com/visgl/deck.gl)) |
| Analyst-facing map building, time slider, 3-D hex, no-code exploration | **kepler.gl** (built on deck.gl, MIT, Uber) | drop-in for the Hotspots/Live views; officers can explore without code ([kepler.gl](https://kepler.gl)) |
| Base map / vector tiles | MapLibre GL (open) | open base tiles, avoids proprietary lock-in |
| Choropleth / spatial ops server-side | **PostGIS** | boundaries, rate joins, spatial indexes already in schema |

Design choices: **rate not count** on choropleths; **k-anonymity suppression** on any public/policymaker map; **time animation** wired to the global scrubber; a **persistent legend** on every map (a heat map without a legend is decoration).

---

## 4. Network visualization — the stack

| Need | Library | Why |
|---|---|---|
| Large graphs, WebGL, smooth pan/zoom | **sigma.js** | renders big graphs fast via WebGL ([sigmajs.org](https://www.sigmajs.org/)) |
| Rich interaction + built-in graph algorithms (centrality, layouts) | **Cytoscape.js** (MIT) | analysis + viz in one; production-proven ([cytoscape.js](https://js.cytoscape.org/)) |
| React-native flow/board diagrams (Investigation Board, small case graphs) | **React Flow** (MIT) | clean node/edge React model for the board & embedded case graph |
| Graph metrics (Louvain, PageRank, betweenness) | **graphology** (JS) / server-side (see [Doc 04](04_NETWORK_GRAPH_ANALYSIS.md)) | compute once, render the result |

Encoding contract (consistent everywhere a graph appears):

| Channel | Encodes |
|---|---|
| node size | importance (degree / PageRank / betweenness) |
| node colour | entity type (fixed palette) OR community (mode-dependent) |
| node halo | high centrality ("person of interest") |
| edge width | relationship strength / co-occurrence frequency |
| edge colour/style | relationship type (co-accused, shared address, financial, gang) |
| animation | direction/tempo (money flow) or time-window activity |

---

## 5. Dashboard & chart stack

| Need | Library | License |
|---|---|---|
| Dashboard components (cards, KPIs, layouts) that look right out of the box | **Tremor** | Apache-2.0 |
| Core UI primitives (cards, tabs, tables, dialogs) | **shadcn/ui** + Tailwind | MIT |
| Charts — declarative & flexible | **Recharts** (simple) / **visx** (bespoke, D3-powered) | MIT |
| High-density / large-data charts (correlation matrices, big time series) | **Apache ECharts** | Apache-2.0 |
| Dimensionality-reduction projections (embedding maps) | UMAP-JS / server-computed + scatter | BSD/MIT |
| Timelines | **vis-timeline** | MIT/Apache-2.0 |

One rule enforced across all of them: **the same chart type uses the same library and the same tokens everywhere.** A line chart looks identical whether it's in Command Center or Analytics.

---

## 6. Colour & encoding system (the anti-rainbow rules)

- **Sequential** (single hue, light→dark) for magnitude — crime rate, density.
- **Diverging** (two hues from a neutral middle) only when there's a true midpoint — change vs. last year, above/below average.
- **Categorical** — the *one* fixed 12-hue palette from [01 §2.1](01_UX_UI_ARCHITECTURE.md), assigned to crime categories *once* and reused identically in every chart, map legend, and graph. A category is always the same colour, product-wide. This single decision does more for "instant understanding" than any individual chart choice.
- **No rainbow/jet ramps** — they distort magnitude perception.
- **Semantic colours (severity) are reserved** — never used for a decorative category.

---

## 7. Accessibility & honesty in charts

- **Never colour alone:** pair with shape, icon, direct label, or pattern. Severity and status always carry a glyph.
- **Colour-blind-safe** sequential/diverging ramps (Viridis-class / ColorBrewer-safe); test with a simulator.
- **Direct labelling** over legends where space allows (less eye-travel).
- **Tooltips are keyboard-reachable**; charts expose an accessible data-table fallback.
- **Uncertainty shown, small-N suppressed, causation never implied** — the three honesty rules, enforced in the chart components themselves so they can't be skipped.
- Full WCAG conformance for data viz requires manual testing with assistive technology; this is the design target.

---

## 8. Performance budget

- **WebGL** for maps (deck.gl) and large graphs (sigma.js) — CPU/SVG can't hold 60 fps at police-data scale.
- **Server-side aggregation:** the client receives hexbins/summaries, not 100k raw rows; PostGIS and matviews (`mv_crime_stats`, `mv_active_hotspots`) do the heavy lifting.
- **Virtualized tables** for the Case/Entity explorers.
- **Progressive rendering:** skeleton → aggregate → detail-on-demand, so a screen is useful in <1 s even while detail streams in.

---

*Previous: [← 02 Advanced Technology](02_ADVANCED_TECHNOLOGY.md)  ·  Next: [04 Network / Graph Analysis →](04_NETWORK_GRAPH_ANALYSIS.md)*
