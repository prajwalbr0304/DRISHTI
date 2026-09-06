# DRISHTI — KSP Datathon 2026 Prototype Submission Deck
## Complete content + build brief for the PPT-authoring AI agent

**Target file:** `KSP Datathon 2026 _ Prototype Submission Template (2).pptx`
(workspace root: `c:\Users\Varshith\OneDrive\Desktop\DRISHTI\`)

**Brief compiled:** 6 September 2026, from a direct read of the repository at commit `198ab55` (branch `main`, 99 commits) and a live probe of the deployed Catalyst endpoints.

**Who this is for:** an AI agent that will populate the official KSP template with `python-pptx` (already installed, v1.0.2) or equivalent. Every number, path, name and URL below was verified against code, config or a live HTTP response. Anything unverified is marked `[MUST-FILL]` or `[UNVERIFIED]`.

---

## 0. How to use this document

1. Read **§1 (template mechanics)** and **§2 (design system)** before writing any shape. The template has a fixed brand frame; content that ignores it will overlap the KSP header band or the gradient footer.
2. Build slides in the order of **§4**. Each slide entry gives: required title, layout plan, exact copy, tables with final values, asset paths, and speaker notes.
3. Before claiming anything not in this document, check **§6 (honesty guardrails)**. The repo's own `README.md` is partly stale relative to the code; §6 lists every divergence and which value to use.
4. **§5** is the verified fact sheet — the single source of truth for numbers.
5. **§7** gives ready-to-adapt `python-pptx` patterns for the two hard problems: adding slides that keep the brand background, and building readable tables.

---

## 1. Template mechanics (measured, not assumed)

### 1.1 Deck geometry

| Property | Value |
|---|---|
| Slide size | 9,144,000 × 5,143,500 EMU = **10.0 in × 5.625 in** (16:9) |
| Existing slides | **16** |
| Layout used by every slide | `TITLE` (index 0). Other available layouts: `SECTION_HEADER`, `TITLE_AND_BODY`, `TITLE_AND_TWO_COLUMNS`, `TITLE_ONLY`, `ONE_COLUMN_TEXT`, `MAIN_POINT`, `SECTION_TITLE_AND_DESCRIPTION`, `CAPTION_ONLY`, `BIG_NUMBER`, `BLANK` |
| Master background | solid `lt1` (white) |
| Origin of deck | exported from Google Slides (shapes are named `Google Shape;NN;pNN`) |

### 1.2 The three background treatments

There are exactly **two** background images plus one slide-level fill:

| Slides | Background | Description |
|---|---|---|
| **1** | slide-level `blipFill` (`ppt/media/image2.png`, 2048×1152) | Full-bleed **"Datathon 2026" cover art** — black centre block with KSP emblem, Zoho + H2S logos, rainbow-gradient surround on the **top ~60 %** of the slide; the **bottom ~40 % is plain white** with a thin gradient bar at the very bottom. This is why the Team Details text box sits at y = 3.48 in — it is on the white area. |
| **2–15** | in-slide `PICTURE` shape at (0, 0, 10.0 × 5.63) | **Content frame**: dark near-black header band across the top **0 → 0.60 in** carrying `Karnataka State Police / Government of Karnataka` (left), `Technology partner ZOHO` and `Powered by H2S` (right); **white body 0.60 → 5.50 in**; **teal→blue→indigo gradient bar 5.50 → 5.625 in**. |
| **16** | in-slide `PICTURE` (2048×1152, 1.9 MB) | Branded **"THANK YOU"** closing art. **Do not modify slide 16.** |

**Consequences for the agent**
- All body text on slides 2–15 sits on **white**. Use dark text. Do **not** use white or light text on the body area.
- **Never place any shape above y = 0.62 in** on slides 2–15 — it will collide with the KSP/Zoho header band.
- **Never place any shape below y = 5.42 in** — it will collide with the gradient footer bar.
- The background picture is the **first shape in z-order**. Any shape you add is drawn on top of it, which is what you want. Do not delete it.

### 1.3 Existing shapes, exact positions (inches: left, top, width, height)

| Slide | Existing text box | Position | Current text (verbatim) | Font size / weight |
|---|---|---|---|---|
| 1 | `Google Shape;54;p13` | 0.50, 3.48, 8.99, 1.96 | `Team Details` ⏎ (blank) ⏎ `Team name: ` ⏎ `Team leader name: ` ⏎ `Team size:` ⏎ `Problem Statement: ` ⏎ (blank) | 15 pt bold |
| 2 | `Google Shape;60;p14` | 0.35, 0.76, 9.78, 0.61 | `Brief about the solution` | 16 pt bold |
| 3 | `Google Shape;66;p15` | 0.26, 0.78, 9.61, **1.55** | 4 lines: `Opportunities` / `How different is it from any of the other existing ideas?` / `How will it be able to solve the problem?` / `USP of the proposed solution` | 16 pt bold, colour `#000000` |
| 4 | `Google Shape;72;p16` | 0.21, 0.94, 9.51, 0.60 | `List of features offered by the solution` | 18 pt bold |
| 5 | `Google Shape;78;p17` | 0.21, 0.91, 9.59, 0.56 | `Process flow diagram or Use-case diagram` | 18 pt bold |
| 6 | `Google Shape;84;p18` | 0.23, 0.96, 9.54, 0.65 | `Wireframes/Mock diagrams of the proposed solution (optional)` | 18 pt bold |
| 7 | `Google Shape;90;p19` | 0.19, 0.95, 9.65, 0.65 | `Architecture diagram of the proposed solution` | 18 pt bold |
| 8 | `Google Shape;96;p20` | 0.17, 0.94, 9.61, 0.49 | `Technologies to be used in the solution` | 18 pt bold |
| 9 | `Google Shape;102;p21` | 0.17, 0.94, 9.61, 0.49 | `List down Catalyst Services being used in the solution` | 18 pt bold |
| 10 | `Google Shape;108;p22` | 0.17, 0.90, 9.67, 0.69 | `Estimated implementation cost (optional)` | 18 pt bold |
| 11 | `Google Shape;114;p23` | 0.24, 0.94, 9.54, 0.65 | `Snapshots of the prototype` | 18 pt bold |
| 12 | `Google Shape;120;p24` | 0.17, 0.88, 9.62, 0.53 | `Prototype Performance report/Benchmarking` | 18 pt bold |
| 13 | `Google Shape;126;p25` | 0.16, 0.92, 9.66, 0.69 | `Provide links to your:` ⏎ (blank) ⏎ `GitHub Public Repository` ⏎ `Demo Video Link (3 Minutes)` ⏎ `Deployed Link` | 18 pt bold |
| 14 | `Google Shape;132;p26` | 0.12, 0.86, 9.73, 0.76 | `Additional Details/Future Development (if any)` | 18 pt bold |
| 15 | `Google Shape;138;p27` | 0.16, 2.46, 9.66, 1.60 | `Blank slide` | 18 pt bold |
| 16 | — | — | (picture only) | — |

### 1.4 Per-slide safe content zone

Derived from each title box's bottom edge. Use `left = 0.45`, `width = 9.10` unless a slide entry says otherwise. Bottom limit is **5.40 in** everywhere.

| Slide | Title bottom | Content zone top | Usable height |
|---|---|---|---|
| 2 | 1.37 | **1.50** | 3.90 |
| 3 | 2.33 | see §4.3 — **retitle this slide**, do not accept 2.45 | — |
| 4 | 1.54 | **1.66** | 3.74 |
| 5 | 1.47 | **1.60** | 3.80 |
| 6 | 1.61 | **1.74** | 3.66 |
| 7 | 1.60 | **1.72** | 3.68 |
| 8 | 1.43 | **1.56** | 3.84 |
| 9 | 1.43 | **1.56** | 3.84 |
| 10 | 1.59 | **1.72** | 3.68 |
| 11 | 1.59 | **1.72** | 3.68 |
| 12 | 1.41 | **1.54** | 3.86 |
| 13 | 1.61 | **1.74** | 3.66 |
| 14 | 1.62 | **1.75** | 3.65 |

### 1.5 Rules for changing the template

Allowed, and expected:
- Add text boxes, tables, pictures and simple autoshapes to slides 1–15.
- **Rewrite** the title text on slides 3 and 13 where the placeholder is a list of required topics rather than a usable title (see §4.3, §4.13). Keep the required topic words present somewhere on the slide so a reviewer can tick them off.
- **Insert extra slides** where one slide cannot hold the content (§4.3 needs 4, §4.11 needs 3, §4.4 benefits from 2). Use the pattern in §7.2 so inserted slides carry the same brand background.
- Replace `Blank slide` on slide 15 with a closing/appendix slide, or use 15 as the first appendix page.

Not allowed:
- Changing slide size, deleting the background pictures, or touching slide 16.
- Moving the KSP header band or the footer gradient.
- Reordering slides 2–14 relative to the official topic sequence. Extra slides go **immediately after** the slide they extend.

---

## 2. Design system

The template supplies the brand chrome; you supply a quiet, dense, government-grade content style. Do not introduce a second visual language.

### 2.1 Palette

| Token | Hex | Use |
|---|---|---|
| Ink | `#111827` | All body text, table body text |
| Ink-dim | `#4B5563` | Captions, source lines, footnotes, "synthetic data" labels |
| Rule | `#D1D5DB` | Table gridlines, dividers, card borders |
| Surface | `#F3F4F6` | Table header fill, card fill |
| Primary | `#0B6CFB` | Section accents, table header text, key figures, link text |
| Accent-teal | `#0E9F8C` | "verified / live / measured" markers |
| Accent-amber | `#B45309` | "pending / held / limitation" markers |
| Accent-indigo | `#4338CA` | Emergency Response workspace accents |

Rationale: `#0B6CFB` is DRISHTI's own product primary (it appears as the badge colour in the repo README) and it sits comfortably beside the template's blue-indigo footer gradient. Teal and amber echo the footer gradient's ends.

### 2.2 Type

| Role | Font | Size | Weight | Colour |
|---|---|---|---|---|
| Slide title (existing boxes) | leave as-is (theme font) | keep 16/18 pt | bold | keep |
| Section label / kicker | Segoe UI (fallback Calibri) | 9 pt | bold, letter-spaced caps | Primary |
| Body bullet, level 1 | Segoe UI | **11 pt** | regular | Ink |
| Body bullet, level 2 | Segoe UI | 9.5 pt | regular | Ink-dim |
| Table header | Segoe UI | 9.5 pt | bold | Primary on Surface |
| Table body | Segoe UI | **8.5 pt** | regular | Ink |
| Big figure (KPI) | Segoe UI | 22–26 pt | bold | Primary |
| KPI caption | Segoe UI | 8 pt | regular | Ink-dim |
| Source / provenance line | Segoe UI | 7.5 pt | italic | Ink-dim |

**Minimum sizes:** never below 8 pt for table body, never below 7.5 pt for a source line. If content does not fit at those sizes, the content is too long — cut it or add a slide. Do not shrink to 6 pt.

### 2.3 Layout grid

- Outer margin: 0.45 in left/right.
- Two-column: 4.40 in each, 0.30 in gutter (`x = 0.45` and `x = 5.15`).
- Three-column: 2.87 in each, 0.25 in gutter (`x = 0.45`, `3.57`, `6.69`).
- Four-up KPI strip: 2.20 in each, 0.15 in gutter (`x = 0.45`, `2.80`, `5.15`, `7.50`).
- Card: `Surface` fill, 0.5 pt `Rule` outline, 0.08 in internal padding, 0.06 in corner radius (use `ROUNDED_RECTANGLE` with adjustment 0.06).

### 2.4 Mandatory recurring elements

1. **Synthetic-data label.** Every slide that shows data, a screenshot, a metric or a model output carries this line in 7.5 pt italic Ink-dim, bottom-left at `y = 5.24`:
   `All figures and records are synthetic demonstration data. Decision support only — a human officer decides.`
2. **Provenance line on data slides.** 7.5 pt italic, bottom-right: e.g. `Measured: AWS RDS PostgreSQL 17.10, exact COUNT(*), 26 Jul 2026.`
3. **No page numbers needed** — the layout's slide-number placeholder is unused and the footer gradient is thin. Skip them rather than risk collision.

### 2.5 Accessibility

- Contrast: Ink on white ≈ 16:1; Primary on white ≈ 5.0:1; Primary on Surface ≈ 4.6:1 — all pass WCAG AA for the sizes used. Do not put Ink-dim below 8 pt on Surface.
- Never encode meaning in colour alone. Pair every colour marker with a word or glyph: `Live ✓`, `Pending ⏳`, `Limitation !`.
- Add alt text to every picture via `shape._element._nvXxPr.cNvPr.set('descr', "...")`. Alt text is supplied per asset in §3.
- Full WCAG conformance cannot be asserted from authoring alone; it needs assistive-technology testing. Do not claim WCAG compliance on any slide.

---

## 3. Asset manifest

All paths are relative to the workspace root. **Every file listed here exists and was verified on 6 Sep 2026.**

### 3.1 Architecture (slide 7 — the single most important asset)

| Path | Size | Notes |
|---|---|---|
| `docs/assets/architecture/drishti-solution-architecture-ppt.png` | 581 KB | **Use this.** Purpose-built for a PPT. Raster, safe in PowerPoint. |
| `docs/assets/architecture/drishti-solution-architecture-ppt.svg` | 13 KB | Vector source. `python-pptx` cannot insert SVG — do not attempt. |

Alt text: `DRISHTI solution architecture: browser to Zoho Catalyst Slate, Catalyst Authentication, API Gateway, gateway_api function minting a signed context, AppSail FastAPI, Catalyst Data Store, Stratus, Cache, Signals, Cron, and a protected server-to-server AWS analytics plane.`

### 3.2 Benchmark dashboards (slide 12)

All four are **SVG only** — `python-pptx` cannot embed SVG. **You must rasterise them to PNG first** (see §7.4), or rebuild the charts natively.

| Path | Size | Content |
|---|---|---|
| `docs/assets/benchmarks/database-inventory.svg` | 7 KB | Database inventory dashboard: 140 tables, 3,011,145 rows, 1.02 GB |
| `docs/assets/benchmarks/model-stack-overview.svg` | 11 KB | The five governed forecast layers and where each runs |
| `docs/assets/benchmarks/workload-model-comparison.svg` | 7 KB | TabFM workload task vs conventional ML baselines |
| `docs/assets/benchmarks/timesfm-backtest-comparison.svg` | 8 KB | TimesFM trajectory layer vs seasonal-naive and moving-average |

**Recommendation:** rather than rasterising, **rebuild `workload-model-comparison` and `timesfm-backtest-comparison` as native PowerPoint charts** from the tables in §5.6 and §5.7. Native charts stay crisp at any zoom and are far more legible at 10 × 5.625 in than a downscaled SVG. Use `model-stack-overview` as a rasterised image or redraw it as a 6-row table.

### 3.3 Prototype screenshots (slide 11)

Twelve PNGs in `docs/assets/screenshots/`, all dated **26 July 2026**:

| # | File | KB | Shows | Recommended slide |
|---|---|---|---|---|
| 1 | `01-landing-hero.png` | 88 | Catalyst landing / India-to-Karnataka hero | 11A |
| 2 | `02-login-role-selection.png` | 1571 | Role-scoped sign-in, officer seats and scopes | 11A |
| 3 | `03-command-center.png` | 98 | Role-adaptive Command Center | 11A |
| 4 | `04-case-explorer.png` | 368 | Case Explorer: filters, free-text, MO similarity | 11A |
| 5 | `05-map-hotspots.png` | 536 | Map & Hotspots with boundary layers | 11B |
| 6 | `05b-map-case-popup.png` | 521 | Incident popup → case-file action | 11B |
| 7 | `06-case-file.png` | 341 | Complete case file | 11B |
| 8 | `07-investigation-board.png` | 371 | Investigation Board, governed network expansion | 11B |
| 9 | `08-network-analysis.png` | 52 | Network Analysis workspace | 11C |
| 10 | `09-analytics-forecasting.png` | 79 | Analytics & Forecasting with provenance | 11C |
| 11 | `10-ask-drishti.png` | 74 | Ask DRISHTI, cited answers | 11C |
| 12 | `11-emergency-response.png` | 68 | Emergency Response workspace | 11C |

**⚠ Important gap.** These screenshots predate three shipped feature areas: **Live Watch Wall (CCTV video analytics)**, **Face Recognition search**, and the **Admin Console / role-scoped Command Center** rework (commits dated 5–6 Sep 2026). There is **no screenshot of any of them in the repo**. Options, in order of preference:
1. Capture fresh screenshots of `/watch`, `/people/face` and `/admin` from the live deployment or a local run, and add them to slide 11C. This is the single highest-value manual action before submission.
2. If no new capture is possible, describe those three features in text on slide 4 and add a one-line note on slide 11: `Live Watch Wall, Face Recognition and the Admin Console shipped after this screenshot set was captured; see the demo video.`

Do **not** silently present the July screenshots as covering the whole feature list.

Also available: `web/public/landing/films/*.mp4` and `*-poster.webp` (landing films). Video embedding in a submission deck is risky (file size, codec, autoplay) — prefer the poster `.webp` frames if you want landing imagery, and note that `python-pptx` handles `.webp` poorly; convert to PNG first.

### 3.4 Diagram sources for slides 5 and 6

`README.md` contains ready-made **Mermaid** diagrams you can render to PNG and drop in, or re-draw natively:

| Diagram | README section | Use on |
|---|---|---|
| End-to-end operational process (`flowchart LR`) | "Process flow and use-case diagrams" | Slide 5 (primary) |
| Use-case diagram (actors → capabilities) | same | Slide 5 (secondary, or 5B) |
| Investigation-board expansion `sequenceDiagram` | same | Slide 5B or appendix |
| System architecture `flowchart TB` | "Detailed solution architecture" | Slide 7 fallback if the PNG is unusable |
| Data architecture `flowchart LR` | same | Slide 7B (optional) |
| Governance lifecycle `flowchart LR` | "Data, AI and model-governance approach" | Slide 14 or appendix |
| CI/CD pipeline `flowchart LR` | "Testing and release validation" | Slide 14 appendix |
| ASCII wireframes: role selection, app shell, Map & Hotspots, Investigation Board | "Wireframes and mock diagrams" | Slide 6 — **redraw these as clean PowerPoint rectangles**, do not paste ASCII art |

**Recommendation for slide 5:** redraw the process flow natively as a left-to-right chevron/box chain. A rasterised Mermaid diagram at 10 in wide is usually legible, but native shapes let you control type size and stay on-brand.

**Recommendation for slide 6:** redraw the app-shell wireframe as grey rectangles with 8 pt labels. ASCII box-drawing characters render inconsistently across fonts and will look broken.

---

## 4. Slide-by-slide content

Notation: `[MUST-FILL]` = the agent cannot know this, a human must supply it. `[UNVERIFIED]` = stated in repo docs but not confirmed by the agent.

---

### 4.1 Slide 1 — Team Details

**Do not add a background.** Slide 1 already carries the cover art; its bottom 40 % is white and the existing text box is correctly placed on it.

**Edit the existing box** (`0.50, 3.48, 8.99, 1.96`) in place. Keep 15 pt bold for the labels; set the filled-in values in 15 pt **regular** so labels and answers are visually distinct. Text colour Ink (`#111827`).

```
Team Details

Team name:            [MUST-FILL]
Team leader name:     [MUST-FILL]
Team size:            [MUST-FILL]
Problem Statement:    Turning fragmented public-safety data into one governed,
                      explainable and human-controlled operational picture for
                      Karnataka Police — without building an opaque automated
                      policing system.
```

Notes for the human filling this in:
- The repository owner on GitHub is `prajwalbr0304`; the AWS SSO profile in the docs is `prajwal-sso`. That is **not** sufficient to assert a team name, leader or size — leave the placeholders.
- If the datathon assigned a numbered problem statement, use the official wording and put the line above underneath it as a one-line restatement.
- The 1.96 in box height at 15 pt fits about 7 lines. If the official problem statement is long, drop the font to 13 pt rather than overflowing.

**Optional addition (recommended):** a single 11 pt line under the block, in Primary:
`DRISHTI — Decision Intelligence for Public Safety · Deployed on Zoho Catalyst`

**Speaker notes:** One sentence on who the team is, then: "DRISHTI is an evidence-backed decision-intelligence platform for public safety. Two connected workspaces — Crime Intelligence and Emergency Response — over one governed data ontology, deployed on Zoho Catalyst."

---

### 4.2 Slide 2 — Brief about the solution

**Title:** keep `Brief about the solution`.

**Layout:** a 4-up KPI strip at the top, then two columns.

**KPI strip** (`y = 1.50`, height 0.72; four cards at `x = 0.45 / 2.80 / 5.15 / 7.50`, width 2.20):

| Figure | Caption |
|---|---|
| **3.01 M** | synthetic rows across 140 tables |
| **37** | governed API router groups |
| **40** | role-scoped application routes |
| **5** | independently inspectable forecast layers |

**Left column** (`x = 0.45, y = 2.32, w = 4.40`) — kicker `WHAT IT IS`:

- DRISHTI is a **governed decision-intelligence platform for public safety**. It connects crime records, people, property, digital and financial evidence, geography, live operational events and predictive signals into one explainable interface.
- It does not replace an officer's judgement. It prepares the evidence, exposes the relationships, quantifies the uncertainty, records the provenance, and keeps a named human accountable for the decision.
- Two connected workspaces over one ontology:
  - **Crime Intelligence** — cases, entities, networks, hotspots, forecasting, investigation boards, evidence trails, natural-language analysis.
  - **Emergency Response** — multi-hazard situation awareness, forecast risk, resources, response plans.

**Right column** (`x = 5.15, y = 2.32, w = 4.40`) — kicker `THE FIVE CAPABILITIES`:

| Capability | What it does |
|---|---|
| **Observe** | Unify cases, live events, alerts, resources and maps into one role-scoped picture |
| **Understand** | Resolve entities, expose networks, find similar cases, read spatial-temporal patterns |
| **Investigate** | Assemble a case's governed network on a shared canvas with notes, frames, paths, provenance |
| **Decide** | Present explainable forecasts with confidence, alternatives and mandatory human review |
| **Audit** | Preserve source references, model versions, snapshots, user actions, append-only evidence |

**Closing line** (full width, `y = 5.02`, 10 pt bold, Primary):
`One operational picture. Every insight traceable to governed evidence. Every decision attributable to a person.`

Plus the mandatory synthetic-data label at `y = 5.24`.

**Speaker notes:** "Police teams rarely lack data — they lack one picture of it. A single incident touches an FIR, multiple parties, phones, vehicles, accounts, sections, arrests, court events, evidence, several stations and historical similar cases. Those facts live in different screens. DRISHTI maps them into typed objects with typed relationships, then projects that ontology into the screens an officer actually works in. The ontology is the product; the screens are views of it."

---

### 4.3 Slide 3 — Opportunities / Differentiation / How it solves / USP

**This slide must become four slides.** The template's title box holds four separate required topics stacked in 1.55 in of vertical space, leaving under 3 in for content — not enough for four substantial answers.

**Plan:** keep slide 3 as **3A** and insert **3B, 3C, 3D** immediately after it (§7.2 pattern). On each, replace the four-line title with the single relevant line, retaining the exact official wording so a reviewer can tick the requirement.

> If the evaluation rubric forbids adding slides: keep one slide with a 2 × 2 quadrant, one topic per quadrant, and cut each to the three bullets marked ★ below. Content zone `y = 2.45`, quadrants 4.40 × 1.40 at `(0.45, 2.45)`, `(5.15, 2.45)`, `(0.45, 3.95)`, `(5.15, 3.95)`.

#### Slide 3A — `Opportunities`

Two columns.

**Immediate operational opportunities**
- ★ **Reduce search time** — one search surface across cases, people, devices, accounts, vehicles and evidence, instead of one query per system.
- ★ **Improve case linkage** — surface shared identifiers, co-occurrence, financial transfers, repeat locations and similar modus operandi across 100,003 cases.
- **Strengthen supervisory awareness** — case freshness, workload, alerts and jurisdiction-wide patterns in one role-scoped command view.
- **Support patrol planning** — translate spatial concentration and time windows into reviewable patrol recommendations.
- ★ **Accelerate hand-off** — send a complete case *network* to an investigation board, not just a case number.
- **Improve audit quality** — preserve where a fact came from and when an analytic result was generated.
- **Unify emergency operations** — apply the same governed, human-controlled model to hazards, resources and response plans.

**Strategic opportunities**
- State-wide public-safety ontology and interoperability standards.
- Kannada and multilingual natural-language access (Kannada is already in the embedding space and the UI translation map).
- Cross-district collaboration under explicit purpose- and role-based controls.
- Privacy-preserving federated analytics across agencies.
- Institution-level model monitoring, backtesting and formal approval.
- Evidence-integrity integrations using immutable object versions and signed manifests.
- Offline-first field applications for low-connectivity policing.

#### Slide 3B — `How different is it from any of the other existing ideas?`

Use a table. This is the strongest slide in the deck — it is the differentiation argument in one view.

| Typical existing approach | Its limitation | DRISHTI's approach |
|---|---|---|
| Static BI dashboard | Aggregates metrics; cannot explain one case relationship or support investigation work | ★ Every metric drills into cases, entities, sources, geography and governed evidence |
| Standalone crime map | Shows where, not the case network, status, jurisdiction or accountable action | ★ Map markers open case context; hotspots connect to forecast, patrol planning and red-zone review |
| Black-box risk score | Encourages automation bias; hard to contest | ★ Model, version, inputs, confidence, time window and provenance are all exposed; human review required |
| Generic graph tool | Manual data prep; loses the source-of-truth link | "Send to Board" expands a *governed* case network and pins live references with snapshots |
| Case-management system | Records procedure; rarely gives cross-case spatial, network or forecast intelligence | Lifecycle records **plus** graphs, maps, similarity search, analytics and evidence trails |
| General-purpose chatbot | Hallucinates, over-discloses, untraceable | Scoped semantic planner, deterministic query contracts, read-only SQL guard, citations, fail-closed |
| Automated predictive policing | Feedback loops; authority transferred to a model | Decision support only. **No person-level re-scoring, no auto-dispatch** |
| Separate crime and disaster apps | Duplicates identity, governance, mapping, command | Two workspaces over one governed platform and one human-control model |

**Architectural differentiators** (second block, 4 bullets, 9.5 pt):
- **Catalyst-first deployment** — Catalyst is the authentication and operational edge, not an afterthought.
- **Live reference + pinned snapshot** — board objects stay linked to governed sources while preserving exactly what the investigator saw.
- **Dual-plane data design** — Catalyst serves the operational plane; the analytical plane is isolated behind a signed server-to-server boundary. No browser ever holds a database credential.
- **Deliberate ML placement** — each model is placed by latency, governance and compute need, and *fails closed* rather than silently substituting a weaker model.

#### Slide 3C — `How will it be able to solve the problem?`

Seven numbered mechanisms, two columns.

1. **Unifies records without flattening meaning.** Source records map to typed objects — case, person, party role, station, evidence, transaction, property, statement, lifecycle event. Relationships keep their meaning, direction and source.
2. **Adapts to operational responsibility.** Six application roles × nine scope types. The server derives the role and scope from the authenticated session; the client can never assert them.
3. **Makes relationships explorable.** Case → people → phones → accounts → property → evidence → events; search-around, shortest path, communities, money trails, then push selected objects to a board.
4. **Connects maps to case work.** State / district / taluk / SHO boundaries, incident filters, clickable case markers, hotspots, forecasts, patrol planning, red-zone alerts. A marker is a traceable record, not decoration.
5. **Turns models into governed evidence.** Every forecast stores model identity, version, feature-snapshot id, horizon, timestamp, confidence and provenance. Backtesting and human review are first-class endpoints.
6. **Keeps reasoning collaborative.** The Investigation Board carries typed nodes, verified links, sticky notes, frames, path finding, timeline and evidence-trail views, history, statistics, sharing, locking and export — with source inspection that never detaches the record.
7. **Preserves accountability.** Material transitions append audit events transactionally with the action. Client-supplied identity headers are stripped at the gateway and replaced with a signed, short-lived server context.

#### Slide 3D — `USP of the proposed solution`

Hero statement (full width, 16 pt bold, Primary, centred at `y = 2.10`):

> **DRISHTI is a human-controlled public-safety operating system that connects every insight to governed evidence, every model to reproducible provenance, and every decision to an accountable user.**

Four cards beneath (`y = 3.20`, 2.20 × 1.40 each):

| Card | Body |
|---|---|
| **One operational picture** | Cases, entities, maps, networks, forecasts, resources and response plans are connected, not adjacent |
| **Evidence-backed intelligence** | Users can inspect the actual records and links behind any conclusion |
| **Human-in-the-loop control** | The system never converts a model output into a coercive action |
| **Auditability by design** | Identity, source snapshots, mutations, model versions and approvals can be reconstructed |

---

### 4.4 Slide 4 — List of features offered by the solution

**Title:** keep `List of features offered by the solution`.

This is the densest slide. **Recommended: split into 4A (Crime Intelligence) and 4B (Emergency Response, CCTV, governance and platform).** If one slide is mandatory, use the 15-row table below at 8 pt with tight row height and drop the "Operational value" column.

#### Slide 4A — Crime Intelligence modules

| Module | Key functionality | Operational value |
|---|---|---|
| **Public landing** | Cinematic India→Karnataka operational map, platform narrative, entry point | Establishes purpose and geographic focus immediately |
| **Role-scoped sign-in** | Searchable seat picker over ~11,800 provisioned seats; six application roles × nine scope types | Demonstrates role- and scope-aware views without real credentials |
| **Command Center** | Role-adaptive dashboard — the widget **set** is swapped per role, not relabelled; drag/resize grid; scope trail; data-freshness banner | Each seat gets the briefing its accountability actually needs |
| **Case Explorer** | Multi-filter FIR search, free-text search, table/map modes, modus-operandi similarity search | Cuts the time to find the relevant cases |
| **Case File** | **18 sub-pages**: overview, timeline, complainant, victims, accused, acts & sections, arrests, chargesheet, evidence, statements, property & seizures, digital & financial, court & lifecycle, network, similar cases, AI summary, leads, investigation assistant | Reconstructs the complete governed record in one place |
| **Intake** | 7-step guided FIR wizard; scanned-FIR OCR lane that **pre-fills** a draft and never registers a case; import inbox with dry-run / commit / rollback; supervisory review states | Improves data quality *before* operational use |
| **People & Entities** | Entity search across persons, gangs, vehicles, phones, accounts; canonical profiles; controlled entity-resolution review (nothing is ever auto-merged) | Reduces duplicate identities and identity fragmentation |
| **Face Recognition** | 1:N probe search over the canonical person gallery using pgvector HNSW cosine over 512-dim ArcFace descriptors; every probe audited; a confirmed match raises a **reviewable candidate, never a merge** | Biometric identification kept inside a review workflow |
| **Network Analysis** | Five modes: Explore, Communities, Hidden associations, Money trail, Path finder. Louvain communities validated against ground truth; exact PageRank; sampled betweenness | Reveals non-obvious cross-record relationships |
| **Investigation Board** | Governed network expansion, typed objects, verified links, flow **and** graph render modes, sticky/frame/text annotations, path finding, search-around, timeline, evidence trail, history, diffs, branch, presence, share, lock, export. **36 API endpoints.** | Collaborative, explainable investigation reasoning |
| **Map & Hotspots** | Five modes (Live Map, Hotspots, Forecast, Patrol Planning, Red-Zone Alerts); four boundary layers; **19 deck.gl layer builders**; time-of-day buckets; 7/14/30-day horizons; Mapillary street view; fullscreen; print/export | Converts spatial pattern into a reviewable operation |
| **Live Watch Wall** | CCTV video analytics that **proposes** an incident alert (fight, road rage, traffic block…) → human confirms or dismisses → only a confirmed alert may raise a nearest-responder dispatch, which needs its own fresh confirmation | Human confirmation at every step; nothing auto-dispatches |
| **Analytics & Forecasting** | Six modes: Trends, Crime Patterns, Socio-economic, Forecasts, Workload, Explainability. Backtesting, model registry, forecast provenance, human review | Makes analytic performance visible and contestable |
| **Ask DRISHTI** | Scoped natural-language questions → constrained query plan → read-only guarded SQL → grounded reply with citations, confidence and the executed SQL. Chat / History / Saved Queries. Session PDF export. Voice: browser dictation, TTS, and real-time duplex Amazon Nova 2 Sonic | Complex analysis without bypassing a single control |
| **Admin Console** | **15 tabs**: status, identity & roles, access & hierarchy, roles & permissions, seat profiles, UI visibility, reconciliation, retention & legal hold, model review, queues, usage & flags, audit, reports, notifications, assistant | Institutional oversight and safe operation |

#### Slide 4B — Emergency Response, governance and platform

| Module | Key functionality |
|---|---|
| **Situation Overview** | Active hazards, alerts, readiness KPIs, allocated-vs-required resources, open tasks, low-confidence warnings, data-freshness banner |
| **Live Situation** | Hazard extents, risk zones, sensor readings, resources and evacuation routes on one map |
| **Forecast & Risk** | Per-hazard risk surface with confidence, contributing factors and model evidence |
| **Resources** | Inventory, readiness, allocation planner, dispatch lifecycle |
| **Response Plans** | Per-hazard SOP checklists, task assignment, after-action review |
| **Governance Registry** | Feature definitions and schema versions, model versions, immutable feature snapshots, outcome labels, prediction requests, prediction review, model rollback |
| **Review queues** | Data-quality issues, entity-resolution candidates, jurisdiction containment failures — all staged for a human, none auto-applied |
| **Evidence lifecycle** | Private object storage with pre-signed exact-object URLs, quarantine → scan → available/rejected, activity trail, archive/restore, legal hold contract |
| **Reports** | Templates, snapshot creation, hash verification, download |
| **Notifications & work** | Preferences, notification list, work tasks, escalation run — all data-minimised (a delivery notice never carries report bytes) |

**Footer line for 4A/4B:** `Every module is served by live APIs. There is no mock data layer in the frontend — each screen calls a real service.`

**Speaker notes:** "Breadth is only defensible if it is governed breadth. Two things to notice: first, `requiresCaseLevel` — aggregate-only seats such as a DGP or an ADGP wing physically do not get Cases, Intake, People, Face Recognition, Network or Board in the sidebar, because they have no case-level remit and the server refuses those reads. Second, every proposal step is separated from every action step — CCTV proposes, a human confirms, and only then can a dispatch be proposed, which needs its own confirmation."

---

### 4.5 Slide 5 — Process flow / Use-case diagram

**Title:** keep `Process flow diagram or Use-case diagram`.

**Plan:** slide 5A = end-to-end operational process; slide 5B = use-case diagram by actor. If only one slide, use 5A and put the actor mapping as a compact strip beneath it.

#### Slide 5A — End-to-end operational process

Redraw natively as a left-to-right flow. Nodes (Surface fill, Rule outline, 9 pt Ink; decision nodes as diamonds in Primary outline):

```
Complaint / FIR / import / live event
        ↓
Validate schema, quality and jurisdiction
        ↓
Create or update governed operational objects
        ↓
Resolve people, places, devices, accounts, property
        ↓
Build verified relationships + immutable feature snapshots
        ↓
   ◇ Operational question ◇
        ├── Case            → Case file and lifecycle
        ├── Relationship    → Network analysis / Investigation Board
        ├── Location        → Map, hotspots and patrol planning
        ├── Trend           → Analytics, forecast and backtest
        └── Natural language→ Ask DRISHTI scoped planner
        ↓  (all five converge)
   Human review
        ↓
   ◇ Officer decision ◇
        ├── Approve or act → Controlled operational action
        ├── Modify         → Record rationale and revised plan
        └── Reject         → Record rejection and feedback
        ↓  (all three converge)
   Append-only audit and evidence trail
```

Emphasise two things visually: the **five parallel question paths converge on a single Human review gate**, and **all three decision outcomes are recorded** — including rejection.

#### Slide 5B — Use-case diagram

Actors on the left, capabilities on the right, connected.

| Actor | Reaches |
|---|---|
| **State / Senior / District Command** | Command Center · Map, Hotspots & Patrol Planning · Analytics & Forecasting · Outcomes |
| **SHO / Investigating Officer** | Case Explorer & Case File · Intake · Investigation Board · Map · Investigation assistant |
| **Senior Command (analyst & cyber wings)** | Network Analysis · Investigation Board · Ask DRISHTI · Analytics & Forecasting · Money trail |
| **Emergency / Traffic Command** | Map · Emergency Response (situation, live, forecast, resources, plans) · Live Watch Wall |
| **System Admin** | Identity, roles & UI visibility · Model registry & governance · Imports & quality · Audit · Reports |

**Optional 5C — the "Send to Board" sequence** (from the README `sequenceDiagram`). Worth including if you have room; it is a concrete, verifiable governance story: Officer opens case → selects Send to Board → API loads case, parties, evidence, property, legal and lifecycle links → returns typed objects + verified relationships + source versions → preview of node/link count → officer creates board and pins → board objects, links and snapshots persisted → board creation and pin events appended to the audit trail → hydrated canvas with source provenance.

**Verified worked example:** for case `100239`, expansion produced **14 nodes and 13 verified links**.

---

### 4.6 Slide 6 — Wireframes / Mock diagrams

**Title:** keep `Wireframes/Mock diagrams of the proposed solution (optional)`.

Marked optional by the template — **include it anyway**, because it demonstrates deliberate information architecture rather than screen-by-screen invention.

**Plan:** four small wireframes in a 2 × 2 grid (each 4.40 × 1.72), redrawn as grey rectangles with 8 pt labels. Add a 9 pt caption under each. Do **not** paste the README's ASCII art.

**Panel 1 — Role-scoped sign-in** (`0.45, 1.74`)
Split screen. Left: product identity, the line `ONE OPERATIONAL PICTURE — from first signal to reviewed action`, and two workspace buttons (`Crime Intelligence` / `Emergency Response`). Right: searchable seat picker; each card shows role label, officer name, rank-facing scope label and scope blurb.
Caption: `Role selects the surface; scope selects the data. They are separate axes.`

**Panel 2 — Application shell** (`5.15, 1.74`)
Left rail: workspace switcher, then sectioned nav (Overview / Case work / Analysis / Assistant / Administration). Top bar: global search, time window, region selector, alerts, theme, language, notifications, profile. Body: breadcrumbs then the active workspace. Right: peek rail.
Caption: `18 destinations, grouped in 5 sections, filtered by workspace, admin flag and seat scope.`

**Panel 3 — Map & Hotspots** (`0.45, 3.58`)
Mode tabs: `Live Map | Hotspots | Forecast | Patrol Planning | Red-Zone Alerts | ⛶`. Left control rail: basemap, boundaries (state/districts/taluks/SHO), jurisdiction, crime filters, time window, time-of-day, severity. Canvas: district boundaries, incident markers, a selected-case popup, hotspot and station markers. Legend strip along the bottom.
Caption: `Aggregate-only seats are narrowed to Forecast; SHO-region overlay is not aggregate-safe.`

**Panel 4 — Investigation Board** (`5.15, 3.58`)
Left: filters, object palette, add sticky/frame/text, path finder. Centre: canvas with a Case node linked by a *verified link* to a Person node, plus an investigation frame grouping notes and evidence. Right: source inspector showing properties, pinned snapshot, related records, provenance. Bottom tab strip: `Table | History | Statistics | Timeline | Evidence Trail | Export`.
Caption: `Objects stay linked to governed sources; the pinned snapshot preserves what the investigator saw.`

---

### 4.7 Slide 7 — Architecture diagram

**Title:** keep `Architecture diagram of the proposed solution`.

**Primary content:** insert `docs/assets/architecture/drishti-solution-architecture-ppt.png` at `left = 0.45, top = 1.72, width = 9.10` (height auto ≈ 3.4 in at a typical 16:9-ish aspect — **verify the scaled height stays ≤ 3.66 in and re-fit by height if not**).

Add alt text (§3.1).

**Overlay a 4-item trust-boundary strip** if the image leaves room, otherwise put it on slide **7B**:

| Boundary | The rule |
|---|---|
| Browser → Catalyst | Public configuration only. No database URL, AWS credential or signing secret may enter a `VITE_*` variable or the compiled bundle — enforced by an automated bundle scan that fails the release build |
| Catalyst Auth → API Gateway | The authenticated session establishes identity. API Gateway is the only supported public API origin |
| `gateway_api` → AppSail | The gateway **strips 9 spoofable identity headers** plus every `x-drishti-*` header, then mints a **60-second HMAC-SHA256-signed** context carrying the server-derived role and scope |
| AppSail → protected analytics | Only the backend may reach PostgreSQL, private object storage or GPU inference. The browser never talks to AWS |
| Model → operational action | No model may dispatch, accuse, arrest, close a case or modify a protected record. Human review is mandatory |

**Request lifecycle** (10 steps, use as speaker notes or a numbered strip on 7B):
1. User opens the Catalyst Slate application.
2. Catalyst Authentication establishes the session.
3. The SPA sends `/api/*` requests to the Catalyst API Gateway origin.
4. API Gateway invokes the `gateway_api` Advanced-I/O function.
5. The gateway discards untrusted identity headers, derives role + scope server-side, and mints a signed short-lived context.
6. AppSail **verifies** signature, audience, scope, expiry and nonce-replay before handling any non-health request.
7. The domain service enforces role, jurisdiction, purpose, rate and payload policy.
8. Reads are served from the curated operational layer and, where authorised, the protected analytical plane.
9. Material writes and model outputs create provenance or audit evidence, transactionally with the action.
10. The UI renders the result with scope, freshness, confidence and source indicators.

**Speaker notes:** "Three things make this architecture rather than a diagram. One: the gateway is the *only* holder of the signing secret, so it is the only thing that can mint a trusted identity — the browser cannot forge a role. Two: AppSail actively rejects an unsigned request with an opaque 401 that does not reveal which check failed, so it is not an oracle. Three: the AWS plane is reachable only server-to-server behind an HMAC-signed HTTPS boundary with a circuit breaker; the browser has no path to it at all."

---

### 4.8 Slide 8 — Technologies to be used in the solution

**Title:** keep `Technologies to be used in the solution`.

**Layout:** three columns, one table each, 8.5 pt body. Content zone `y = 1.56`, height 3.84.

**Column 1 — Frontend** (`x = 0.45, w = 2.87`)

| Technology | Version / role |
|---|---|
| React | 18.3 |
| TypeScript | 5.5 |
| Vite | 5.4 |
| Tailwind CSS | 3.4 |
| React Router | 6.26 |
| TanStack Query | 5.51 |
| Zustand | 4.5 (14 stores) |
| Radix UI | 11 primitives |
| MapLibre GL 5.24 + react-map-gl 8.1 | interactive maps |
| deck.gl | 9.3 (19 layer builders) |
| Mapillary JS | 4.1 street-level |
| React Flow | 11.11 board canvas |
| Sigma.js 3.0 + Graphology 0.26 | large graphs |
| Recharts | 2.12 charts |
| cmdk | ⌘K command bar |
| react-grid-layout | 1.5 dashboard grid |
| Vitest 2.1 + Testing Library | unit / component |
| Playwright | 1.61 end-to-end |

**Column 2 — Backend, data & ML** (`x = 3.57, w = 2.87`)

| Technology | Role |
|---|---|
| Python | 3.12 |
| FastAPI | 0.115.6 typed async API |
| Uvicorn | ASGI runtime |
| Pydantic | 2.10 validation |
| PostgreSQL | 17.10 (AWS RDS) |
| PostGIS 3.5.6 | geography, boundaries, spatial index |
| pgvector 0.8.2 | embeddings, HNSW cosine |
| pgRouting 3.6.3 | governed routing |
| `pg_trgm` 1.6 | fuzzy entity matching |
| `pgcrypto`, `uuid-ossp`, `pg_stat_statements` | crypto, ids, query observability |
| psycopg2 | DB access |
| NumPy / SciPy / scikit-learn | statistics and baselines |
| NetworkX 3.4 | graph algorithms |
| Shapely 2.0 | geometry |
| PyTorch 2.2 + torch-geometric | ST-GNN (GPU worker only) |
| TabFM 1.0.0, TimesFM 2.0.2, TabPFN 2.0.9 | tabular + time-series foundation models |
| sentence-transformers | multilingual EN + Kannada embeddings |
| onnxruntime + Pillow | SCRFD detect + ArcFace 512-d descriptors |
| pytest | 52 test files, 789 test functions |

**Column 3 — Platform & operations** (`x = 6.69, w = 2.87`)

| Technology | Role |
|---|---|
| **Zoho Catalyst Slate** | production frontend hosting |
| **Catalyst Authentication** | user identity |
| **Catalyst API Gateway** | public API boundary |
| **Catalyst Serverless Functions** | 9 deployable functions (Node 20) |
| **Catalyst AppSail** | containerised FastAPI runtime |
| **Catalyst Data Store** | curated operational serving data |
| **Catalyst Stratus** | governed object storage |
| **Catalyst NoSQL / Cache** | layouts, presence, idempotency, nonce |
| **Catalyst Signals / Cron** | events and schedules |
| **Catalyst QuickML** | no-code baseline + RAG |
| **Catalyst Pipelines** | CI/CD |
| Docker | `python:3.12-slim`, linux/amd64 |
| AWS RDS PostgreSQL | protected analytical store |
| AWS S3 + KMS | private evidence and model artifacts |
| AWS Lambda (arm64) | signed model/LLM adapter |
| AWS Bedrock | `zai.glm-4.7-flash` semantic planner |
| AWS Bedrock Nova 2 Sonic + AgentCore | real-time duplex voice |
| AWS SageMaker async | scale-to-zero GPU inference |
| GitHub Actions | frontend CI + secret gate |

**Footer strip** (full width, 9 pt, `y = 5.06`):
`Version pins are locked in a reviewed toolchain manifest: Node 20.17.0 · npm 11.5.2 · Python 3.12.10 · Catalyst CLI 1.27.0 · AWS CLI 2.17.22 · Docker 29.6.1.`

**Do not claim:** `@tremor/react` (declared in `package.json` but not imported anywhere in `src/`), any i18n framework (translation is a hand-maintained key→string map; only Kannada is populated), or `torch-geometric-temporal` (deliberately not a dependency).

---

### 4.9 Slide 9 — Catalyst services used

**Title:** keep `List down Catalyst Services being used in the solution`.

**Layout:** one wide table, 8.5 pt, plus a status legend. Content zone `y = 1.56`.

Use a **Status** column and be honest about it — a reviewer who opens the repo will find the flags, and honesty here is a strength, not a weakness.

Legend: `Live ✓` = configured and exercised in the deployment · `Configured ◐` = declared and code-complete, gated off by a feature flag for cost/scope · `Declared ○` = reviewed intent recorded, activation is a console action

| Catalyst service | How DRISHTI uses it | Status | Repository evidence |
|---|---|---|---|
| **Slate** | Hosts the Vite/React SPA with SPA redirects; framework `react-vite` | **Live ✓** | `infra/catalyst/client/slate-config.toml` |
| **Authentication** | Establishes user identity and session; role resolved from directory attributes server-side | **Live ✓** | `functions/gateway_api/index.js` |
| **API Gateway** | 3 routes: `/api/*` → `gateway_api` (600/min general, 120/min per IP), `/api/channel-token` (authenticated, 120/30), `/api/public/health` (120/60). Sliding-window throttle | **Live ✓** | `infra/catalyst/api-gateway/routes.json` |
| **Serverless Functions** | **9 deployable** Node-20 / 256 MB functions: `gateway_api`, `channel_token` (Advanced I/O); `datastore_event`, `evidence_event`, `prediction_event`, `report_event`, `notify_dispatch` (event); `cron_forecast`, `cron_reconcile` (cron) — plus a `_shared` context-signing package | **Live ✓** (gateway) / **Configured ◐** (events, crons) | `infra/catalyst/functions/` |
| **AppSail** | FastAPI service `drishti-api`, custom OCI Docker runtime, port 9000, 512 MB, 256 MB disk, **pinned to exactly 1 instance** for correct in-process ID allocation and nonce-replay defence | **Live ✓** | `infra/catalyst/appsail/appsail.deploy.json` |
| **Data Store** | Curated operational serving layer, idempotent upsert on `ExternalID`. **106 import configurations**; 93 operational, 13 UI-projection, 9 analytics-only, 6 Data-Store-native; 16 search-enabled; dev row cap 5,000/table | **Live ✓** | `infra/catalyst/ds-import/` (106 configs) |
| **Data Store native tables** | **20 native tables**: 6 Investigation Board (board, node, edge, annotation, collaborator, activity) + 14 Emergency Response (hazard type/event/prediction/risk zone, readings, resources, shelters, allocations, routes, plans, tasks, feed source, ingestion run, activity) | **Live ✓** | `infra/catalyst/ds-schema/` |
| **Stratus** | 3 private, versioned buckets — evidence, import, report. 900-second pre-signed exact-object URLs. SHA-256 + size + MIME + object key + version id recorded in Data Store; bytes never cross the API or the logs | **Live ✓** | `infra/catalyst/stratus/buckets.json` |
| **Cache** | 4 bounded-TTL segments: `idempotency` 86400 s, `ratelimit` 60 s, `nonce` 180 s (cross-instance replay guard), `lookup` 300 s. Never a system of record | **Configured ◐** | `infra/catalyst/cache/namespaces.json` |
| **NoSQL** | 4 segments: BoardLayout, UiPreferences, Presence (TTL 120 s), FeedEnvelope. Any other segment is rejected in code | **Configured ◐** | `infra/catalyst/nosql/segments.json` |
| **Signals / Events** | 4 publishers, 9 rules. Exactly **one** rule is in the minimal tier: `prediction-requested` (approved `PredictionRequest` row → `prediction_event`). Retry: 20 attempts, exponential 1/2/4/8 min capped at 10, 24-hour TTL | **Configured ◐** | `infra/catalyst/jobs/signals-rules.json` |
| **Cron / Job Scheduling** | 7 schedules, timezone Asia/Kolkata. **One** in the minimal tier: `drishti-forecast-daily` at 03:00 IST. Plus nightly reconcile and weekly embedding refresh | **Configured ◐** | `infra/catalyst/jobs/cron-schedules.json` |
| **QuickML — No-code ML** | Governed baseline classifier for the aggregate **area/period workload band** — explicitly never a person, complainant, accused or FIR. Time-based holdout, leakage checks, no protected attributes, human approval required, no auto-promotion | **Configured ◐** | `infra/catalyst/quickml/nocode-experiment.json` |
| **QuickML — RAG** | Grounds SOP/policy answers over **6 approved synthetic sources**; 3 exclusions (evidence bytes, unreviewed narratives, PII); citation required, refuse-when-unsupported, 7-question fixed evaluation set. An offline deterministic implementation honours the same citation/refusal contract when RAG is off | **Configured ◐** | `infra/catalyst/quickml/rag-knowledge-base.json` |
| **QuickML — LLM Serving** | Provider-neutral alternative semantic-planner target; the deployed planner is currently AWS Bedrock GLM-4.7-Flash behind the signed adapter | **Declared ○** | `infra/catalyst/ml-placement.json` |
| **Pipelines** | **10 jobs across 6 stages**: validate (eslint, tsc, vitest, pytest, import-config drift) → build (release bundle + AppSail image to Stratus) → security (secret scan, dependency audit, static checks, no-DB-URL-in-web, route data boundary, release bundle gate) → preflight (asserts project id, synthetic marker, no duplicate services) → deploy_dev → smoke (Slate + Gateway + AppSail health + an authenticated read) | **Declared ○** | `infra/catalyst/pipelines/catalyst-pipelines.yaml` |
| **Connections** | One declared connection for the AWS model adapter. Currently authenticated by HMAC signature rather than OAuth — recorded honestly as a gap | **Declared ○** | `infra/catalyst/connections/connections.json` |
| **Billing / budget controls** | ₹1,800 planning envelope, thresholds at 50/75/90 %, duplicate-service prevention, cleanup runbook | **Declared ○** | `infra/catalyst/billing/budget.json` |

**"Component philosophy" callout box** (right side or bottom, 9 pt, Surface card):
> The active event footprint is deliberately minimal: **one** primary Signal, **one** daily forecast cron, **one** AppSail application, **one** GPU endpoint name, optional background work defaulting to off, and development imports capped at 5,000 rows per table. This controls cost and operational complexity while leaving a clear path to production scale. Two Catalyst capabilities — **Circuits** and **Zia AutoML** — are unavailable in the India data centre; idempotent Functions + Job Scheduling are used instead, and QuickML replaces Zia AutoML. That constraint is recorded in `infra/catalyst/COMPONENTS.md` from a live CLI inspection with Catalyst CLI 1.27.0.

**Project identity strip** (7.5 pt, bottom):
`Catalyst project DHRISTI · project id 48361000000030003 · environment Development (60075362708) · domain dhristi-60075362708.development · timezone Asia/Kolkata. The Catalyst project is named DHRISTI in the console; the product and repository are DRISHTI.`

---

### 4.10 Slide 10 — Estimated implementation cost

**Title:** keep `Estimated implementation cost (optional)`.

Marked optional — **include it**. Cost discipline is a differentiator most submissions omit.

**Layout:** two columns. Left = hackathon envelope + thresholds. Right = production drivers + controls.

**Left, table 1 — Hackathon operating envelope**

| Item | Planned value |
|---|---|
| Catalyst free credit | **₹300** |
| Catalyst basic-plan baseline | **₹1,500** |
| **Catalyst planning envelope** | **₹1,800** |
| Budget period | 17 Jul 2026 → 17 Aug 2026 |
| AWS monthly budget alarm | **US$25** (alerts at 80 % and 100 %) |
| AppSail instances | 1 (pinned min = max = 1) |
| Active Signals rules | 1 (`prediction-requested`) |
| Active forecast cron | 1 (daily, 03:00 IST) |
| GPU endpoint | 1 asynchronous endpoint, autoscale min 0 / max 1, **scale-to-zero**, deleted after testing |
| Dev Data Store imports | capped at 5,000 rows per table |

**Left, table 2 — Catalyst budget thresholds**

| Threshold | Amount | Action |
|---|---|---|
| 50 % | ₹900 | Review the usage report |
| 75 % | ₹1,350 | Pause non-essential feature flags |
| 90 % | ₹1,620 | Stop temporary GPU workloads, freeze new deployments |

**Right — Indicative production cost drivers** (bullets, 9.5 pt)
- Number and size of AppSail instances.
- Data Store rows, indexes and request volume.
- Stratus object storage and transfer.
- Signal, cron and workflow executions.
- QuickML training and serving usage.
- Historical PostgreSQL size, IOPS, backup and high availability.
- Private evidence volume and retention period.
- GPU inference duration and concurrency.
- Observability, security testing and support staffing.

**Right — Cost controls already in the design** (bullets, 9.5 pt, teal check glyphs)
- ✓ No duplicate AppSail apps, Signals rules, crons or GPU endpoints — asserted by an automated preflight check before deploy.
- ✓ Optional event, RAG and notification scaffolds default to **off**; a function with no configured base URL returns `not_configured` and incurs no charge.
- ✓ Development Data Store imports capped.
- ✓ Scale-to-zero GPU inference; an explicit `--teardown` command.
- ✓ Temporary object lifecycle rules (quarantine 7 days, rejected purged 24 h, async I/O 7 days).
- ✓ Budget alarms plus manual Catalyst credit checks before and after enabling any paid capability.

**Honesty footnote** (7.5 pt italic):
`These thresholds are an implementation plan, not an invoice. Catalyst usage and billing must be confirmed in the Catalyst Console, because the authenticated CLI session does not expose billing usage.`

---

### 4.11 Slide 11 — Snapshots of the prototype

**Title:** keep `Snapshots of the prototype`.

**Plan: three slides, 4 screenshots each** (11A / 11B / 11C). Twelve screenshots on one 10 × 5.625 in slide gives each about 2.2 × 1.4 in — unreadable. Three slides at 2 × 2 gives each about 4.4 × 1.7 in, which is legible.

**Grid for each slide** (2 × 2): images at `(0.45, 1.72)`, `(5.15, 1.72)`, `(0.45, 3.58)`, `(5.15, 3.58)`, each `width = 4.40` (let height scale; cap at 1.62 and re-fit by height if the scaled height exceeds it). Caption in 8 pt Ink-dim directly beneath each image.

**Slide 11A — Entry and command**

| Image | Caption |
|---|---|
| `01-landing-hero.png` | Catalyst landing: Karnataka as the area of operations, evidence-backed and human-controlled |
| `02-login-role-selection.png` | Role-scoped sign-in — role selects the surface, seat scope selects the data |
| `03-command-center.png` | Command Center: the widget set is swapped per role, not relabelled |
| `04-case-explorer.png` | Case Explorer: structured filters, free text and modus-operandi similarity |

**Slide 11B — Geospatial and case work**

| Image | Caption |
|---|---|
| `05-map-hotspots.png` | Map & Hotspots: state, district, taluk and SHO boundaries with incident layers |
| `05b-map-case-popup.png` | An incident popup carries case identity, severity, status, location, date, section and a direct case-file action |
| `06-case-file.png` | The complete case file — 18 governed sub-pages from overview to court lifecycle |
| `07-investigation-board.png` | "Send to Board" expands the governed case network; for case 100239, **14 nodes and 13 verified links** |

**Slide 11C — Analysis, assistant and response**

| Image | Caption |
|---|---|
| `08-network-analysis.png` | Network Analysis: explore, communities, hidden associations, money trail, path finder |
| `09-analytics-forecasting.png` | Analytics & Forecasting with model provenance, confidence and backtesting |
| `10-ask-drishti.png` | Ask DRISHTI: scoped, cited answers with the executed read-only SQL shown |
| `11-emergency-response.png` | Emergency Response: multi-hazard situation, forecast risk, resources and plans |

**Required note on 11C** (9 pt, Ink-dim, `y = 5.06`) unless fresh captures are added:
`Live Watch Wall (CCTV video analytics), Face Recognition search and the Admin Console shipped after this screenshot set was captured (26 Jul 2026); they are demonstrated in the video.`

Alt text pattern for every image: `Screenshot of the DRISHTI <workspace name> showing <what is visible>. Synthetic demonstration data.`

---

### 4.12 Slide 12 — Prototype performance report / Benchmarking

**Title:** keep `Prototype Performance report/Benchmarking`.

The richest slide for a technical reviewer. **Plan: 12A = validation and build; 12B = model benchmarks.** If one slide is mandatory, use 12A's validation table plus the TimesFM skill figures, and move the TabFM comparison to an appendix.

#### Slide 12A — Validation dashboard and live health

**KPI strip** (4 cards, `y = 1.54`):

| Figure | Caption |
|---|---|
| **65 / 65** | frontend tests passed (21 test files) |
| **789** | backend test functions across 52 files |
| **HTTP 200** | Slate, API Gateway and AppSail — live, 6 Sep 2026 |
| **0** | secrets found in the production bundle |

**Main table — Quality gates**

| Quality gate | Measured result | Status |
|---|---|---|
| Frontend unit / component suite | 65 tests passed across 21 executed test files | ✓ |
| Investigation-board backend suite | 27 tests passed | ✓ |
| Backend test corpus | 52 test files, 789 test functions, including dedicated gateway-authz, scope-enforcement, read-only and deployment-boundary suites | ✓ |
| TypeScript production check | `tsc --noEmit` passed | ✓ |
| Vite production build | 3,829 modules transformed, ~71 s on the validation workstation | ✓ |
| Production bundle secret scan | Passed — no blocked credential pattern in `dist/` | ✓ |
| **Catalyst Slate (primary evaluation link)** | **HTTP 200, verified 6 Sep 2026** | ✓ |
| **Catalyst Slate (secondary app)** | **HTTP 200, verified 6 Sep 2026** | ✓ |
| **Catalyst API Gateway `/api/health`** | **HTTP 200** — `status: ok`, `database: true`, extensions `postgis`, `vector`, `pg_trgm`, `pgrouting` all true | ✓ |
| **AppSail `/health/live`** | **HTTP 200** — `status: live` | ✓ |
| **AppSail `/health/ready`** | **HTTP 200** — `ready: true`; checks: config ok, environment `synthetic_hackathon`, hackathon mode on, operational datastore ok, gateway auth ok, object store ok, semantic planner ok, analytics db ok | ✓ |
| Desktop responsive width 1,536 px | Document width = viewport width; no horizontal page overflow | ✓ |
| Laptop responsive width 900 px | Document width = viewport width; no horizontal page overflow | ✓ |
| Board inspector stability | 0 blank inspector states across 12 rapid alternating node selections | ✓ |
| Board frame interaction | 4 resize handles exposed and exercised | ✓ |
| Case-network expansion example | 14 nodes and 13 verified links for case `100239` | ✓ |

**Production bundle profile** (small table, right or below)

| Artifact | Size (latest local build) |
|---|---|
| `index.html` | 1.54 kB |
| Main CSS | 273.4 kB |
| MapLibre chunk | 1,029.5 kB |
| Main JavaScript | 4,047.1 kB |

**Limitation callout** (amber, mandatory):
> These results demonstrate prototype correctness and interaction stability — **not a production service-level agreement**. The rich initial JavaScript bundle is the largest known performance opportunity; route-level code splitting and deferred map/graph loading are the first Phase-2 items. A production benchmark must add p50/p95/p99 API latency, Web Vitals, concurrency, database plans, map point volume, board graph scale, error rate and recovery testing. All data are synthetic; no operational-effectiveness claim follows from this benchmark.

**Production performance targets** (optional strip): LCP < 2.5 s · CLS < 0.1 · INP < 200 ms · read API p95 < 500 ms · search API p95 < 1,000 ms · 60 fps map with level-of-detail aggregation · smooth board pan/zoom at 500 visible nodes.

#### Slide 12B — Model benchmarks

**Left: TabFM workload task vs conventional baselines.** Dataset: 576 district-quarter rows, 10 non-protected features, **time-based** split of 352 train / 96 validation / 128 test.

| Evaluated model | Accuracy | Macro-F1 | QWK | ECE |
|---|---|---|---|---|
| Prior-period baseline | **0.6484** | **0.5998** | **0.5639** | 0.1516 |
| Histogram Gradient Boosting | 0.4922 | 0.4856 | 0.3891 | 0.4487 |
| Current in-context serving model | 0.4141 | 0.4003 | 0.3317 | **0.1469** |
| Majority-class baseline | 0.1016 | 0.0461 | 0.0000 | 0.1541 |
| **Google TabFM v1 (real GPU path)** | — | — | — | — |

**The governance point — state it plainly, it is a strength:**
> The deterministic CPU fallback does **not** beat the strong prior-period baseline, so DRISHTI **refuses to promote it**. TabFM must be evaluated on the identical time/geo split on the real CUDA path before the model registry can mark it active. That is the intended governance behaviour, not a hidden failure. The fail-closed contract is enforced in code: a requested TabFM job that cannot run on CUDA with a verified weight digest returns `CUDA_UNAVAILABLE` rather than a mislabelled CPU result.

**Right: TimesFM trajectory layer vs forecasting baselines.** Leakage-safe rolling-origin backtest: 6 walk-forward origins × 32 districts = 192 held-out district-month predictions. Lower is better for MAE, RMSE, WAPE, sMAPE.

| Forecast candidate | MAE ↓ | RMSE ↓ | WAPE ↓ | sMAPE ↓ | 80 % coverage |
|---|---|---|---|---|---|
| **TimesFM-compatible serving forecaster** | **6.327** | **8.406** | **0.1132** | **14.49 %** | 0.6094 |
| Moving average (3 periods) | 6.813 | 9.415 | 0.1219 | 14.60 % | **0.8333** |
| Seasonal naive | 7.698 | 10.018 | 0.1377 | 17.51 % | 0.7760 |

**Measured skill:** +17.81 % MAE, +16.09 % RMSE, +17.79 % WAPE versus seasonal naive; +7.13 % MAE, +10.72 % RMSE, +7.14 % WAPE versus moving average. `beats_all_baselines = true` on point-error metrics.

**Required caution note:**
> The measured backtest above executes `drishti-timesfm-seasonal`, the fast TimesFM-**compatible** statistical serving forecaster. The real `drishti-timesfm-2.5-200m` layer is separately registered and currently holds 32 district predictions over a 92-day horizon. DRISHTI does not present the fallback benchmark as proof of the foundation model; TimesFM 2.5 retains its own model version and backtest provenance.

**Why a stack beats one model** (optional third block, 6 rows, 8 pt):

| Layer | Best at | Known limitation | Used safely by |
|---|---|---|---|
| TabFM | Aggregate tabular workload / risk bands with limited labelled context | Heavy weights, GPU requirement, needs identical-split acceptance | Protected GPU path, artifact digest verification, no silent fallback, human promotion |
| TimesFM | Longer-horizon univariate count trajectories | Cannot capture street-level spatial diffusion | Produces district trajectory + uncertainty; kept separate from spatial layers |
| ST-GNN | Spatial-temporal influence between adjacent districts | Complex, graph-sensitive, hard to explain alone | Adds neighbour structure as one inspectable layer |
| Near-repeat (Hawkes/ETAS) | Short-horizon local recurrence after an event | Narrow mechanism, not a trend model | Fast 14-day event alerts on a ~275 m grid |
| KDE / ST-DBSCAN / statistical | Transparent hotspot and recurrence structure | Lower representational capacity | Visible comparators and safe CPU fallbacks |
| Fusion | Combining validated evidence across layers | Can amplify a bad layer if governance is weak | Weighted TabFM 0.4 / TimesFM 0.3 / ST-GNN 0.3, records every contributing layer, **refuses** a layer without the current policy attestation |

**Reproducibility strip** (7.5 pt):
`Reproduce read-only: /workload/evaluation?foundation_kind=served · /workload/benchmarks · /forecast/backtest?horizon=1&n_origins=6 · /forecast/layers · python scripts/database_inventory.py --exact`

---

### 4.13 Slide 13 — Links

**Title:** the existing box holds `Provide links to your:` + three label lines. **Rewrite it** so each label carries its URL. Keep 18 pt bold for labels; set URLs in 14 pt regular Primary with a real hyperlink attached (`run.hyperlink.address = url`).

```
Provide links to your:

GitHub Public Repository
    https://github.com/prajwalbr0304/DRISHTI

Demo Video Link (3 Minutes)
    https://youtu.be/cp27iqfYYyA

Deployed Link
    https://drishti-frvfpunc.onslate.in/
```

**Add a verification strip below** (9 pt, `y = 4.10`, Surface card, teal check glyphs):

| Item | Verified |
|---|---|
| Deployed Slate application | **HTTP 200**, 6 Sep 2026 |
| Catalyst API Gateway `/api/health` | **HTTP 200** — database reachable, all four PostgreSQL extensions present |
| Catalyst AppSail `/health/ready` | **HTTP 200** — `ready: true`, environment `synthetic_hackathon` |
| GitHub repository | Public |
| Demo video | Public |

**Mandatory emphasis box** (amber outline, 10 pt bold):
> The **Zoho Catalyst Slate deployment** above is the official evaluation link. DRISHTI must be evaluated using it and not a deployment on any other hosting platform.

**Secondary detail** (7.5 pt italic):
`Catalyst project name: DHRISTI (project id 48361000000030003, environment 60075362708). The product and repository are branded DRISHTI. Diagnostic service endpoints — API Gateway dhristi-60075362708.development.catalystserverless.in/api and AppSail drishti-api-50044118953.development.catalystappsail.in — are operational diagnostics, not substitutes for the Slate evaluation link.`

`[MUST-FILL check]` Confirm the demo video is (a) public, (b) ≤ 3 minutes, and (c) shows the Catalyst-deployed URL in the address bar at least once. If the video predates the Live Watch Wall, Face Recognition and Admin Console work, re-record or add a short addendum.

---

### 4.14 Slide 14 — Additional details / Future development

**Title:** keep `Additional Details/Future Development (if any)`.

**Layout:** three columns for the roadmap, then a full-width honesty block. Content zone `y = 1.75`.

**Column 1 — Near term: prototype hardening**
- Split the main JavaScript bundle by route; defer map and graph libraries.
- Add automated visual-regression baselines for every role surface.
- Add Web Vitals and p50/p95/p99 API telemetry.
- Complete keyboard-only and screen-reader audits.
- Add larger graph and map stress datasets plus recovery tests.
- Add an in-product build/version panel for evaluation traceability.
- Capture fresh screenshots for Live Watch Wall, Face Recognition and the Admin Console.
- Introduce database connection pooling (currently a fresh connection per use, chosen so `SET ROLE` / read-only session state cannot leak between callers).

**Column 2 — Medium term: operational readiness**
- Institution-managed SSO, lifecycle provisioning and fine-grained entitlements.
- Row-, field- and purpose-based access policies for real data.
- Encryption key management, evidence legal hold and redaction workflow.
- Kannada and multilingual search, dictation and explanation (the embedding space is already multilingual).
- Offline-first mobile / PWA mode for field officers.
- Cross-district collaboration with explicit disclosure approval.
- Formal model registry approval, drift monitoring and rollback.
- Structured feedback capture for accepted, modified and rejected recommendations — closing the loop from recommendation to measured outcome.
- Resilient queues, retries, idempotency and disaster recovery; raise AppSail beyond one instance once shared monotonic ID allocation lands.

**Column 3 — Long term: public-safety ecosystem**
- Standards-based exchange with police, court, forensic and emergency systems.
- Privacy-preserving federated analytics across agencies.
- Advanced multimodal evidence support, only after explicit legal approval.
- Resource-optimisation simulation for emergency response.
- Causal evaluation of operational interventions rather than correlation-only scoring.
- Independent auditing tools for model, access and decision histories.
- Statutory-clock engine for BNS / BNSS / BSA obligations and forensic mandates.

**Full-width honesty block** (`y = 4.30`, Surface card, 8.5 pt — **do not omit this; it is the most credible thing in the deck**):

**Known constraints, stated plainly**
- Every record is synthetic; the role identities are synthetic seats.
- Model outputs have **not** been validated on real operational data and must not be used for real enforcement decisions.
- The GPU plane is currently blocked by an AWS service quota: GPU endpoint quota is **0 account-wide** (checked 6 Sep 2026) with three quota-increase requests pending. Non-GPU steps are complete; only endpoint creation is gated. The system fails closed rather than substituting a CPU model labelled as a foundation model.
- **TabFM 1.0.0 carries a Non-Commercial licence** — acceptable for this evaluation, a real restriction that must be cleared before production use. TimesFM 2.0.2 is Apache-2.0.
- Catalyst billing data are console-only for the current CLI session.
- Row-level security is disabled on the base tables at explicit hackathon request; Catalyst Authentication plus the signed-context gateway is the boundary in this phase.
- Development health verification is not equivalent to production load or resilience testing.

**Responsible-use principles** (right half of the block, or a fifth column):
1. No automated coercive action. 2. No person-level predictive re-scoring for enforcement. 3. No automatic dispatch from a hotspot or forecast. 4. No hidden evidence extraction. 5. No claim that synthetic benchmark results represent production policing outcomes. 6. Human review and contestability for every operational recommendation. 7. Purpose, role and jurisdiction are part of every data-access decision. 8. Model uncertainty and provenance must remain visible.

**Production hardening required before real data** (compact list): legal, privacy and human-rights impact assessment · institution-managed identity with least privilege · field- and row-level controls per source · retention, legal hold, redaction and disclosure policy · threat modelling and independent security review · model fairness, error-distribution and feedback-loop validation · incident response, audit review and operator training.

---

### 4.15 Slide 15 — currently `Blank slide`

Two good options:

**Option A (recommended) — "Governance in one page"** appendix. Replace the title with `How DRISHTI stays accountable` and present the governance lifecycle plus the reproducible prediction envelope:

Governance lifecycle (left-to-right chain): Validated data → Immutable feature snapshot → Train / configure candidate → Temporal + geographic backtest → Model review and approval → Versioned model registry → Scoped inference → Confidence, drivers and provenance → **Human accept / modify / reject** → Drift, feedback and performance monitoring → back to backtest.

Reproducible prediction envelope (right, monospace 8 pt):
```
prediction_id        stable identifier
model_id             registered model
model_version        immutable version
feature_snapshot_id  immutable input snapshot
jurisdiction         authorised geographic scope
as_of                source cutoff timestamp
horizon              forecast window
confidence           0.0 – 1.0
explanation          human-readable drivers
source_hash          content / provenance hash
review_status        pending | accepted | modified | rejected
```

Ask DRISHTI guardrails (bottom strip, 8.5 pt): natural language becomes a **constrained query plan**, never arbitrary SQL · role and jurisdiction filters applied independently of the language model · the planner cannot grant itself scope · answers expose citations or record references · single-statement read-only guard with ~50 forbidden keywords and ~25 forbidden functions, executed under a read-only role in a read-only transaction with an enforced row cap · an unconfigured LLM degrades to a **labelled** deterministic planner, never a silent switch · voice questions below the confidence threshold require confirmation · evidence extraction, automatic document interpretation and any face-match auto-merge are disabled.

**Option B — Non-goals.** DRISHTI is explicitly not intended to: predict whether a named person will commit a crime · autonomously dispatch officers · replace legal or supervisory judgement · establish guilt from a graph relationship · ingest real protected data without institutional governance · expose raw database or model infrastructure to the browser.

Either way, remove the literal text `Blank slide`.

---

### 4.16 Slide 16 — Thank you

**Do not modify.** It is the official branded closing slide.

---

## 5. Verified fact sheet

Use these values. They are the single source of truth for this deck.

### 5.1 Code inventory (counted 6 Sep 2026, commit `198ab55`)

| Metric | Value | How counted |
|---|---|---|
| Git commits on `main` | 99 | `git rev-list --count HEAD` |
| Frontend routes with a path | **39** declared `<Route path=…>` (+2 pathless layout routes) | `web/src/App.tsx` |
| Distinct page components | 36 (33 inside the app shell + landing + login + not-found) | `web/src/App.tsx` |
| Sidebar destinations | **18** (13 Crime Intelligence, 5 Emergency Response) | `web/src/config/destinations.tsx` |
| Frontend source files | **339** `.ts` / `.tsx` | `web/src` |
| Frontend route files | 143 under `web/src/routes` | — |
| Zustand stores | 14 | `web/src/stores` |
| deck.gl layer builders | 19 (+3 helpers) | `web/src/components/map/layers.ts` |
| FastAPI routers registered | **37** `include_router` calls | `services/ml/app/main.py` |
| Router modules | 36 `router.py` files | `services/ml/app` |
| Route decorators (endpoints) | **391** | `@router.get/post/put/patch/delete` |
| Backend Python files | **296** (excluding `__pycache__`) | `services/ml/app` |
| SQL files | **54** = 3 base schema + 39 forward migrations (`001`–`037`, two duplicate numbers) + 12 `.down.sql` rollbacks | `services/ml/sql` |
| Base schema tables | 28 `CREATE TABLE` in `police_fir_schema.sql`, generated 1:1 from the Police FIR ER diagram | — |
| Data generator modules | 41 Python files | `datagen/` |
| Catalyst functions | **9** deployable + 1 `_shared` package | `infra/catalyst/functions` |
| Catalyst Data Store import configs | **106** | `infra/catalyst/ds-import/configs` |
| Data Store native tables | 20 (6 board + 14 disaster) | `infra/catalyst/ds-schema` |
| Backend test files / functions | **52** files, **789** `def test_` | `services/ml/tests` |
| Frontend unit test files | **34** | `web/src` |
| Playwright e2e specs | **7** | `web/e2e` |

**Largest router groups by endpoint count:** Investigation Board 36 · Emergency Response 31 · Intake 27 · CCTV 23 · Admin (platform ops) 23 · Identity 23 · Casework 21 · Imports 17 · Graph 16 · Evidence 16 · Geo 14 · Governance 13 · Admin Console 13 · Org 13.

### 5.2 Database (exact `COUNT(*)`, measured 26 Jul 2026)

| Measure | Value |
|---|---|
| Database / engine | `drishti` on **AWS RDS PostgreSQL 17.10**, ARM64, `db.t4g.medium` |
| Allocated storage / encryption | 30 GiB, encryption enabled |
| Current database size | **1,024,399,027 bytes = 1.02 GB / 0.95 GiB** |
| Ordinary tables | **140** (118 non-empty, 22 empty future-state contracts) |
| **Exact rows** | **3,011,145** |
| Views / materialized views | 20 / 3 |
| Columns / indexes / constraints | 1,708 / 503 / 582 |
| Table heap / index storage | 579,411,968 / 424,673,280 bytes |

**Rows by domain**

| Domain | Tables | Exact rows | Share |
|---|---|---|---|
| People, parties and organisations | 17 | 1,156,931 | 38.42 % |
| Core cases and FIR taxonomy | 14 | 987,211 | 32.79 % |
| Legal, court and lifecycle | 14 | 524,821 | 17.43 % |
| Networks and intelligence | 7 | 222,407 | 7.39 % |
| Evidence, property, digital and financial | 20 | 104,432 | 3.47 % |
| Geospatial and contextual | 14 | 12,167 | 0.40 % |
| Identity, audit, collaboration and reporting | 21 | 1,559 | 0.05 % |
| ML, forecasts and model governance | 17 | 1,335 | 0.04 % |
| Intake, import and data quality | 16 | 282 | 0.01 % |
| **Total** | **140** | **3,011,145** | **100 %** |

**Highest-volume tables:** `CaseEvent` 386,990 (94 MB) · `CasePartyRole` 374,280 (81 MB) · `CanonicalEntity` 223,161 · `CanonicalPerson` 210,890 · `EntityGraph` 206,026 (**340 MB** — 167 MB data + 173 MB indexes) · `CaseSource` 200,003 · `ActSectionAssociation` 172,374 · `Accused` 164,861 · `SourceRecord` 100,068 · `CaseMaster` **100,003** · `CaseVersion` 100,003 · `ComplainantDetails` 100,003 · `Inv_OccuranceTime` 100,000 · `ArrestSurrender` 72,762 · `Victim` 71,604 · `CourtEvent` 64,391 · `ChargesheetDetails` 37,147 · `CaseDisposition` 28,309 · `OutcomeObservation` 28,309 · `BailEvent` 27,196 · `PropertyItem` 13,766 · `Seizure` 13,642 · `Employee` 12,000 · `FinancialTransaction` 11,049 · `FinancialAccount` 9,445.

**Extensions:** PostGIS 3.5.6 · pgRouting 3.6.3 · pgvector 0.8.2 · `pg_trgm` 1.6 · `pgcrypto` 1.3 · `uuid-ossp` 1.1 · `pg_stat_statements` 1.11. All four required extensions confirmed present on the **live** deployment via `/api/health` on 6 Sep 2026.

**Why 22 tables are empty:** zero rows is not an omitted schema. `LegalHold`, `LabResult`, `MoneyAlertReview`, `RagInteraction`, `ReportSnapshot`, `NotificationDelivery` and 16 others preserve reviewed contracts for future workflows while preventing the prototype from fabricating activity that never occurred. This is a good slide-14 talking point.

### 5.3 Data generation

| Parameter | Value |
|---|---|
| Random seed | 42 (deterministic, reproducible) |
| Temporal window | 1 Jan 2021 → 31 Dec 2025 |
| FIRs | 100,000 target |
| Districts / stations / officers / courts | 32 / 1,000 / 12,000 / 500 |
| Repeat-offender pool / gangs | 18,000 / 60 |
| Embedding dimension | 768 (must match the `vector(n)` column) |
| Cases embedded / summarised | 8,000 / 6,000 |
| Max network edges | 120,000 |
| Parallelism | 4 workers, disjoint 5,000,000-wide ID blocks per worker (globally unique PKs with no coordination) |

### 5.4 Roles and organisational scope

**Six application roles** — a role answers exactly one question: which UI surface to render. How much data a seat sees is a separate axis.

| Role | Scope types | Surface | Home | Aggregate-only |
|---|---|---|---|---|
| `dgp_state_command` | state | state_command | `/command` | **yes** |
| `senior_command` | wing, range | senior_command | `/command` | yes when wing-scoped |
| `district_command` | district, commissionerate | district_command | `/command` | no |
| `sho` | station | station | `/command` | no |
| `investigating_officer` | assigned_case | case_work | `/cases` | no |
| `system_admin` | platform | platform | `/admin` | n/a |

**Nine scope types** with rank-facing labels: `state` → DGP / State Command · `wing` → ADGP / Functional Wing (state-wide, narrowed by crime head) · `range` → DIG / Range Command · `district` → SP / District Command · `commissionerate` → CP / City Commissionerate · `station` → SHO / Station · `assigned_case` → Investigating Officer · `platform` → System Admin · `unresolved` → **unposted seat, sees nothing**.

**The design insight worth saying out loud:** ADGP and DIG share the role `senior_command` because they render the same surface; only their scope differs — a functional wing versus a geographic range. A single role could not express that, which is why role and scope are orthogonal. Similarly, aggregate-only seats (state and wing) are refused `case_detail_read`, `case_write` and `intake_write`, and the six case-level destinations are removed from their sidebar rather than offered and then answered 403.

**18 capabilities:** `case_read`, `case_detail_read`, `case_write`, `intake_write`, `intake_review`, `board_use`, `board_share`, `network_analysis`, `imports_review`, `entity_review`, `jurisdiction_override`, `governance_run`, `governance_review`, `disaster_write`, `cctv_review`, `cctv_dispatch`, `cctv_admin`, `admin`.

**Seat inventory (design target, migrations `026`–`034`):** 1 DGP · 6 ADGP wings · 7 DIG ranges · 30 SP districts · 2+ CP commissionerates · 1,000 SHO · ~10,744 IO · 1 admin ≈ **11,791 seats**. Real seats live in the `users` table and are chosen through a searchable seat picker.

**Karnataka organisational structure** (verified against the official Karnataka State Police organisation page, retrieved 5 Sep 2026; content paraphrased for licensing compliance): **7 ranges** each headed by an IGP and comprising 3–6 districts, and **6 police commissionerates**. Migration `034` builds the faithful structure — 38 district-level units, 32 range districts, 6 commissionerates — rather than forcing the org chart into the generated 32 rows. Historical `CrimeNo` values are deliberately **not** rewritten, because a crime number is a permanent identifier and real reorganisations do not renumber historical FIRs; a case's current district is derived through `PoliceStationID → Unit.DistrictID`.

**Six ADGP functional wings:** Law & Order · Crime & Technical Services (absorbs the crime-analyst / SCRB function) · Intelligence · Internal Security & Cyber (absorbs the cyber cell) · Traffic & Road Safety · CID / Economic Offences.

**Role consistency is enforced across five files** — `web/src/config/roles.ts`, `services/ml/app/roles.py`, `services/ml/app/gateway_context.py`, `infra/catalyst/functions/gateway_api/index.js` and migration `028` — with a test asserting the Python and Node role sets are identical.

### 5.5 The model stack

**Forecast inventory currently registered:** TabFM 32 district predictions (30-day layer) · TimesFM 2.5 32 district predictions (92-day layer) · Near-repeat 150 event predictions (14-day layer) · ST-GNN 32 district predictions (30-day layer) · Fusion 32 district predictions (30-day layer).

| Layer | Implementation | Where it runs |
|---|---|---|
| **TabFM** | Zero-shot tabular foundation model; fits historical `(features_t → class_{t+1})` pairs, predicts a 5-class district risk class; writes `CrimePrediction` + `ModelVersion` + `ModelInference` | Protected AWS GPU worker only |
| **TimesFM 2.5-200M** | Real `TimesFM_2p5_200M_torch` with a continuous quantile head, max context 512 / max horizon 12; a SageMaker variant **fails closed** if the actual backend is not TimesFM on CUDA; a statistical `SeasonalForecaster` is the always-available labelled fallback | GPU endpoint, or labelled CPU fallback |
| **ST-GNN** | torch-geometric GCN + GRU (A3TGCN-style), Monte-Carlo-dropout uncertainty, ~80 epochs / 30 MC samples, with a numpy diffusion fallback | GPU worker; deferred |
| **Near-repeat** | Self-exciting Hawkes/ETAS point process, `λ(cell) = μ + Σ θ·exp(−dt/τ)·exp(−d²/2σ²)` on a ~275 m grid (σ = 500 m, τ = 7 d, θ = 1.0, 30-day lookback, 7-day horizon); recomputes the local 3×3 cell surface when a new FIR lands | Catalyst AppSail CPU |
| **Hotspots** | `ST-DBSCAN + gaussian_kde`; polygons built server-side with PostGIS `ST_Buffer` over geography | Catalyst AppSail CPU |
| **Graph** | Louvain community detection **validated against `GangMembership` ground truth** with pairwise precision/recall/F1; exact PageRank plus k-sampled betweenness, written back to the graph | Catalyst AppSail CPU (precomputed) |
| **Similarity** | `paraphrase-multilingual-mpnet-base-v2`, 768-dim, **English and Kannada in one space**; genuine pgvector HNSW cosine ANN; deterministic 768-dim hashing embedder as the labelled fallback | AppSail / GPU |
| **Face** | SCRFD detection + ArcFace 512-dim descriptors as plain ONNX graphs; pgvector HNSW cosine 1:N. Weights are never fetched on the request path; until they are staged the API reports `models_present=false` and falls back to an explicitly **non-biometric** duplicate-photo descriptor | AppSail |
| **Fusion** | Weighted and inspectable: **TabFM 0.4 / TimesFM 0.3 / ST-GNN 0.3**, TabFM as anchor, near-repeat contributing a `near_term_spike` flag. Every fused cell records `contributing_models` with each layer's own prediction, confidence and model-version id. **Refuses to fuse** a layer whose output lacks the current analytics-policy attestation | Catalyst AppSail CPU |

**The fail-closed contract, in code:** the GPU worker's `_require_cuda()` and weight-digest check mean a requested TabFM job that cannot run as requested returns `CUDA_UNAVAILABLE` with the warning "fail closed: requested backend could not run as requested". A mislabelled CPU fallback can never be returned as TabFM. Every result carries `actual_backend`, `actual_device`, `model_artifact_digest`, `gpu_name`, `peak_gpu_mem_mb`, `runtime_ms` and `cold_start_ms`, and is **HMAC-signed** so AppSail can verify it.

**Ask DRISHTI, end to end:** owner-bound session → language auto-detect → three composite intents short-circuit before SQL (briefing, socio-economic, project context) because one SELECT cannot answer them → plan with the configured provider (AWS Bedrock `zai.glm-4.7-flash` behind the signed adapter) or a labelled deterministic fallback → schema-hallucination validation with exactly **one** bounded correction attempt → **server-authored overrides** for four high-risk shapes (case lookup by FIR reference, case aggregates that must be sealed as policy-filtered, canonical district/region routing, reference-entity counts) → read-only guard: single statement, must start `SELECT`/`WITH`, 6,000-char cap, no dollar-quoting, ~50 forbidden keywords and ~25 forbidden functions scanned on a string-blanked copy so data values cannot trigger false positives, then wrapped in an enforced `LIMIT` → executed under the `drishti_readonly` role in a read-only transaction → grounded reply composed **only from returned rows**, with citations derived from result-set IDs, honest confidence scaled by row evidence, and a SHA-256 of the executed SQL recorded.

**Every AI endpoint returns the same contract:** `{answer, confidence 0–1, source_record_ids[], reasoning_summary, model_version}` — and `reasoning_summary` is explicitly documented as never chain-of-thought. `GET /explain/contract` audits conformance.

**Voice (Amazon Nova 2 Sonic), status 31 Aug 2026:** browser gets a signed 60-second voice ticket through the authenticated Catalyst gateway and sends it in the **first WebSocket frame, never the URL**; a SigV4-presigned 60-second AgentCore WebSocket URL whose signed runtime session id must match the ticket; each isolated runtime accepts exactly one connection; the relay exchanges the ticket over HTTPS for a 450-second owner- and role-bound tool token, and the signing secret never leaves Zoho. Audio is mono 16-bit PCM, 16 kHz in / 24 kHz out via an AudioWorklet. **Raw audio is not persisted.** Nova is forced to call `ask_drishti`, which is the same owner-bound, role-checked, read-only Ask service as text chat — no model-generated SQL escapes the existing guards. Six English voices; Kannada continues through browser speech because Nova 2 Sonic does not list Kannada. The relay is **audio transport only** and holds no data access.

### 5.6 Security and governance controls

| Control | Implementation |
|---|---|
| Gateway identity | Role resolved **server-side** from a Catalyst custom attribute, then the Catalyst role name mapped through a ~40-entry rank map, then a least-privilege default. An asserted-but-unknown role is **rejected 403**, never silently coerced |
| Header stripping | 9 spoofable identity headers plus every `x-drishti-*` header plus hop-by-hop framing headers are removed before proxying |
| Signed context | base64url JSON + **HMAC-SHA256**, `aud: drishti-appsail`, **60-second TTL**, 12-byte random nonce, request id |
| Context verification | AppSail checks signature, audience, scope, expiry **and nonce replay** before handling any non-health request; returns an **opaque 401** that does not reveal which check failed |
| Scope injection | The verified context's district, unit and scope level are injected as trusted headers after the client's are stripped, so deployed scope resolution needs no database round-trip and cannot be spoofed |
| Read-only SQL | `drishti_readonly` role + read-only transaction + single-statement guard + keyword/function deny-lists + enforced row cap — four independent layers |
| Rate limit | Per-client-IP fixed 60-second window, `429` with `Retry-After: 60`; API Gateway adds 600/min general and 120/min per IP |
| Payload limit | Declared `Content-Length` cap with **one** exact-path override for scanned-FIR OCR, bounded by the documented OCR limit. Prefix matching is deliberately avoided so a new sub-route cannot inherit a larger cap |
| CORS | Explicit origins (localhost + the exact configured demo origin), `allow_credentials=False`, explicit method and header allow-lists. **Never treated as authentication** |
| Error sanitisation | Database and unhandled errors return generic text plus a request id — never SQL, stack traces, identifiers or credentials. `/health` returns "database unavailable" rather than the driver message |
| Synthetic-environment guard | At boot, if hackathon mode is on and the database is reachable but its `synthetic_meta.app_environment` marker differs from the expected value, the service **refuses to start**. A masked, credential-free DB descriptor is logged so a mis-routed `DATABASE_URL` is obvious |
| Audit | Audit rows are written **transactionally with the action**, so a rolled-back action rolls back its audit. Sensitive keys — passwords, narratives, date of birth, phone, Aadhaar, latitude/longitude — are stripped before storage |
| Browser secret gate | The release build fails on a Postgres connection string, PEM key, `AKIA…` key id, any `*.amazonaws.com` URL, or server-only variable names in `dist/`; in release mode it also requires a valid HTTPS Catalyst API Gateway origin (no empty, http, localhost, AWS or raw AppSail URL) |
| Evidence integrity | Private versioned buckets, 900-second pre-signed **exact-object** URLs, quarantine → scan → available/rejected, SHA-256 + size + MIME + object key + version id in Data Store. Bytes never cross the API or the logs |
| Adapter boundary | AppSail holds no AWS keys; it calls a signed HTTPS adapter with HMAC over `ts|nonce|body`. The adapter has a rate limiter, a circuit breaker, structured audit and opaque error codes. Access logs redact authorization, signature and body |
| Face-recognition safety | Every probe is audited; a confirmed match raises a **reviewable entity-resolution candidate**, never an automatic merge |
| CCTV safety | The service runs **no video-frame inference in-process**; detections come from a deterministic synthetic scene generator or an external push. Analytics **proposes**, a human confirms or dismisses, and only a confirmed alert may raise a dispatch — which needs its own fresh confirmation |
| Model → action | No model may dispatch, accuse, arrest, close a case or modify a protected record |

### 5.7 Deployment facts

| Item | Value |
|---|---|
| Primary evaluation URL | `https://drishti-frvfpunc.onslate.in/` — **HTTP 200, 6 Sep 2026** |
| Secondary Slate app | `https://drishti-uryfmaue.onslate.in/` — **HTTP 200, 6 Sep 2026** |
| API Gateway | `https://dhristi-60075362708.development.catalystserverless.in/api` — `/health` **200**, `status: ok`, `database: true` |
| AppSail | `https://drishti-api-50044118953.development.catalystappsail.in` — `/health/live` **200**, `/health/ready` **200** with `ready: true` |
| Catalyst project / id | `DHRISTI` / `48361000000030003` |
| Environment / domain | Development `60075362708` / `dhristi-60075362708.development`, Asia/Kolkata |
| AppSail service | `drishti-api`, custom OCI Docker, `python:3.12-slim`, linux/amd64, port 9000, 512 MB RAM, 256 MB disk, **1 instance** |
| Env var surface | 14 required + 26 optional keys + 3 auto-injected. **No secret values are committed** — only key names |
| Semantic planner (deployed) | AWS Bedrock `zai.glm-4.7-flash`, `us-east-1`, behind the signed adapter. Direct SDK access is refused in code when the adapter is unconfigured. Claude and OpenAI models are rejected by both code and IAM |
| GPU plane | SageMaker async, `ml.g4dn.xlarge` (1× T4, 16 GB), autoscale min 0 / max 1, scale-to-zero, immutable ECR tags, KMS-encrypted model bucket. **Blocked: GPU endpoint quota is 0 account-wide as of 6 Sep 2026; three quota requests pending** |
| Acceptance checklist | 11 required checks (K1–K11): 3 verified offline, 6 held on deploy, 1 held on GPU, 1 operational teardown. Strict release mode treats a configuration-only declaration as unproven — a JSON file can never pass as a live Signal, cron, Data Store write, auth flow or GPU invocation |
| GitHub CI | Frontend build + secret scan on every push to `web/**`; Slate deploy is opt-in because the live Slate app is Git-integrated and cannot be targeted by the CLI |

### 5.8 Impact framing (proposed, with honest measurement)

| Impact area | Current friction | Proposed DRISHTI effect | How to measure |
|---|---|---|---|
| Investigation preparation | Manual search across systems | One governed case and relationship picture | Median time from case open to usable investigation board |
| Cross-case detection | Relationships found informally | Entity, network, path and similarity tools | Verified cross-case links found per reviewed case |
| Supervisory awareness | Delayed aggregated reports | Role-scoped command view with data freshness | Time from source update to supervisor visibility |
| Geospatial operations | Map disconnected from case detail | Click-through incident context, reviewable plans | Time from hotspot detection to reviewed patrol plan |
| Evidence accountability | Screenshots and detached notes | Live references plus pinned snapshots | Percentage of board objects carrying source and version |
| Model trust | Unexplained scores | Backtests, confidence, provenance, review | Percentage of recommendations with a completed human disposition |
| Emergency readiness | Hazard, resource and plan silos | Shared situation and response workspace | Time to produce an approved response picture |

**Do not state a percentage time saving.** The repo contains a golden-task harness that measures DRISHTI's own time-to-grounded-answer, but there is **no measured manual baseline and no user study**, so any "X % faster" claim would be fabricated. Describe the manual comparison qualitatively and say the baseline study is future work. This restraint is itself a credibility signal.

**Ten proposed use cases:** repeat-property-crime pattern discovery · cybercrime account/device linkage and money-trail review · cross-district vehicle and phone association · case-ageing, workload and bottleneck supervision · district hotspot and near-repeat analysis · human-reviewed patrol allocation · evidence completeness and chargesheet readiness · disaster situation awareness and resource planning · SOP/policy retrieval with grounded, cited responses · data-quality and jurisdiction repair before operational publication.

---

## 6. Honesty guardrails — read before writing a single claim

### 6.1 The repository README is partly stale. Use the code values.

`README.md` was last comprehensively updated around 26 July 2026. Significant work landed after that. Where they disagree, **the code wins**.

| Claim in `README.md` | Actual value in code (6 Sep 2026) | Use |
|---|---|---|
| "Ten operational roles" | **Six** application roles × **nine** scope types; the ten presentation seats were deliberately collapsed | **Six roles, nine scope types** |
| "33 declared frontend routes" | **39** pathed routes, 36 page components | **39** |
| "31 FastAPI router groups" | **37** registered routers, 391 endpoints | **37 routers, 391 endpoints** |
| "26 SQL schema/migration files" | **54** files (3 base + 39 forward + 12 rollbacks) | **54** |
| Role list includes DySP/ACP, Crime Analyst, Cyber Cell, Traffic Command as roles | Those fold into `district_command` and `senior_command` wings; DySP/ACP is deferred (no sub-division data model) | describe wings, not roles |
| Main JavaScript 3,836 kB | latest local build **4,047.1 kB** | quote the latest build, or omit the exact figure |
| Feature list omits CCTV, Face Recognition, Admin Console, Nova Sonic voice | All four are implemented (`/watch`, `/people/face`, `/admin`, 23 CCTV + 7 face endpoints, live Sonic voice) | **include them** |
| "QuickML LLM Serving is the primary semantic-planner target" | The deployed planner is **AWS Bedrock `zai.glm-4.7-flash`**; QuickML LLM Serving has no config file and is a documented alternative | say Bedrock GLM is deployed, QuickML LLM Serving is the Catalyst-native alternative |
| README verification dates 26 July 2026 | Health re-verified **6 Sep 2026**; GPU deployment record dated 6 Sep 2026 | use 6 Sep 2026 for live checks, 26 Jul 2026 for the database inventory |

### 6.2 Claims that would be false — never make them

| Do **not** say | Why | Say instead |
|---|---|---|
| "TabFM achieves X % accuracy" | No recorded GPU acceptance run exists; the benchmark row is deliberately blank | "The real TabFM GPU path is implemented and fails closed; a comparable accuracy score is an explicit acceptance gate that has not yet been recorded" |
| "TimesFM 2.5 beats the baselines by 17.8 %" | The measured backtest ran the TimesFM-**compatible** statistical serving forecaster, not the 200M foundation model | Quote the skill figures and attribute them to `drishti-timesfm-seasonal`, noting TimesFM 2.5 holds its own separate provenance |
| "The GPU endpoint is running" | GPU quota is **0 account-wide**; three requests pending as of 6 Sep 2026 | "Scale-to-zero GPU inference is provisioned and fail-closed; endpoint creation is blocked on a pending AWS quota increase" |
| "One Signal and one cron are live" | All 9 Signals rules are `active:false` and all 7 crons are `enabled:false` in the committed config; the acceptance checklist itself rates this evidence `config_only` | "The minimal event plane declares exactly one Signal and one cron; both are code-complete and flag-gated off for cost control" |
| "QuickML RAG and the no-code model are running" | Both configs are `enabled:false` | "Configured and code-complete, with an offline deterministic implementation honouring the same citation and refusal contract" |
| "Row-level security is enforced" | RLS is explicitly disabled on the base tables at hackathon request | "Catalyst Authentication plus the signed-context gateway is the boundary in this phase; row- and field-level policies are pre-production work" |
| "DRISHTI reduces investigation time by N %" | No manual baseline, no user study | Describe the mechanism and name the metric you would measure |
| "WCAG 2.1 AA compliant" | Authoring conformance cannot be asserted without assistive-technology testing | "Focus-visible rings, reduced-motion support, ARIA labelling and role-based e2e assertions are implemented; a full audit is scheduled" |
| "Uses Tremor for charts" | `@tremor/react` is a dependency but is imported nowhere | "Recharts, themed through a shared chart theme" |
| "Full Kannada UI" | Only the Kannada translation map is populated; there is no i18n framework | "Kannada script detection, Kannada-aware embeddings, a Kannada UI string map and a language switcher; full localisation is roadmap" |
| "Real-time WebSocket updates throughout" | The only WebSocket is the Nova Sonic voice session; everything else is interval polling, and the SSE channel is flag-gated | "Live voice over WebSocket; operational surfaces poll with a scoped SSE channel available behind a flag" |
| "No person-level risk scoring" | `/risk/entity/{id}` and `/risk/{accused_id}` exist | Either omit the absolute claim or state it precisely: "no person-level predictive re-scoring drives coercive action, and per-person risk was retired from the entity profile in favour of an aggregate case-review workload band" |
| Report PDF export is production-ready | The SmartBrowz screenshot path returns a stub payload when the service is not enabled | "Report templates, snapshots and hash verification are implemented; PDF rendering binds to Catalyst SmartBrowz when enabled" |
| Zia OCR / STT / TTS / translation are live | The Zia voice adapter methods raise `NotImplementedError`; Zia has no STT/TTS/translation in the India DC | "Scanned-FIR OCR is wired to Zia OCR behind a flag; speech uses browser Web Speech and Amazon Nova 2 Sonic, which is the labelled substitute for the unavailable regional capability" |

### 6.3 Turn each limitation into a governance strength

Every honest limitation above has a governance story. Use these framings; they are what distinguishes a mature submission.

- **The fallback scores worse than the baseline, so it is not promoted.** That is the model registry working. A submission that reported a strong number for a fallback would be the untrustworthy one.
- **The GPU path fails closed rather than degrading.** A CPU statistical model can never be returned labelled as a foundation model. That is why the benchmark cell is blank instead of filled with a plausible number.
- **22 tables are deliberately empty.** Legal holds, lab results and money-alert reviews have reviewed schemas and zero fabricated rows, because inventing activity that never happened is worse than an empty table.
- **The event plane is one Signal and one cron.** Deliberate minimalism under a ₹1,800 envelope, with duplicate-service prevention asserted by an automated preflight check.
- **The acceptance checklist refuses its own configuration as proof.** Strict release mode treats a JSON declaration as unproven. The project grades itself harder than a reviewer would.
- **Aggregate-only seats cannot read case rows.** A DGP is accountable for the whole force and has no case-level remit, so the affordance is removed rather than offered and refused — enforced server-side, mirrored in the sidebar.
- **The gateway holds the only signing secret.** The browser cannot forge a role because it has nothing to sign with.

### 6.4 Verified-versus-planned vocabulary

Use one of exactly four words for every factual claim, and be consistent:

| Word | Means | Example |
|---|---|---|
| **Measured** | A number produced by running something and recorded | "Measured: 3,011,145 rows by exact COUNT(*)" |
| **Verified** | Confirmed live by an observation | "Verified HTTP 200 on 6 Sep 2026" |
| **Implemented** | Code exists and tests cover it, but it is flag-gated or not exercised in the deployment | "Implemented: the minimal Signals rule" |
| **Planned** | Reviewed intent, no code path yet | "Planned: federated cross-agency analytics" |

---

## 7. Implementation notes for `python-pptx`

### 7.1 Setup

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

SRC = r"KSP Datathon 2026 _ Prototype Submission Template (2).pptx"
OUT = r"DRISHTI - KSP Datathon 2026 - Prototype Submission.pptx"   # never overwrite the template

prs = Presentation(SRC)   # 10.0 x 5.625 in

INK        = RGBColor(0x11, 0x18, 0x27)
INK_DIM    = RGBColor(0x4B, 0x55, 0x63)
RULE       = RGBColor(0xD1, 0xD5, 0xDB)
SURFACE    = RGBColor(0xF3, 0xF4, 0xF6)
PRIMARY    = RGBColor(0x0B, 0x6C, 0xFB)
TEAL       = RGBColor(0x0E, 0x9F, 0x8C)
AMBER      = RGBColor(0xB4, 0x53, 0x09)
```

**Save to a new filename.** Keep the original template untouched so a bad run is always recoverable.

### 7.2 Adding a slide that keeps the brand background

`python-pptx` has no `duplicate_slide`. The reliable approach is: add a slide on the `BLANK` layout, then copy the background picture's image blob from slide 2 into the new slide at the same position and send it to the back of the z-order.

```python
import copy
from pptx.util import Inches

BLANK = prs.slide_layouts[10]           # 'BLANK'

def brand_bg_blob(prs):
    """Extract the slides 2-15 background image bytes once."""
    for sh in prs.slides[1].shapes:      # slide 2, 0-indexed
        if sh.shape_type == 13:          # PICTURE
            return sh.image.blob, sh.image.ext
    raise RuntimeError("brand background picture not found on slide 2")

BG_BLOB, BG_EXT = brand_bg_blob(prs)

def add_branded_slide(prs, after_index):
    """Append a BLANK slide carrying the brand background, then move it into
    position directly after `after_index` (0-based)."""
    slide = prs.slides.add_slide(BLANK)

    import io
    pic = slide.shapes.add_picture(
        io.BytesIO(BG_BLOB), Inches(0), Inches(0),
        width=prs.slide_width, height=prs.slide_height)

    # Send the picture to the back so all content draws on top of it.
    spTree = slide.shapes._spTree
    spTree.remove(pic._element)
    spTree.insert(2, pic._element)       # index 2 = first shape after nvGrpSpPr + grpSpPr

    # Reposition the slide in the deck.
    sldIdLst = prs.slides._sldIdLst
    ids = list(sldIdLst)
    moved = ids[-1]
    sldIdLst.remove(moved)
    sldIdLst.insert(after_index + 1, moved)
    return slide
```

Then add the title text box yourself at the same geometry as the slide you are extending (§1.3), so inserted slides look native:

```python
def add_title(slide, text, left=0.21, top=0.94, width=9.51, height=0.60, size=18):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = True; r.font.color.rgb = INK
    return tb
```

**Insertion order matters.** Build back-to-front (insert the last extra slide first) or recompute indices after every insert. Recommended insertion plan, applied in this order:

| Insert | After 0-based index | Becomes |
|---|---|---|
| 3D (USP) | 2 | slide 4 |
| 3C (How it solves) | 2 | slide 4 |
| 3B (Differentiation) | 2 | slide 4 |
| 12B (Model benchmarks) | 11 → recompute | after 12A |
| 11C, 11B (snapshots) | after slide 11 → recompute | after 11A |
| 5B (use-case diagram) | after slide 5 → recompute | after 5A |
| 4B (ER + platform features) | after slide 4 → recompute | after 4A |

Simplest safe implementation: insert from the **highest** original index downwards (12B, then 11C, 11B, then 5B, then 4B, then 3D, 3C, 3B). Earlier indices stay valid that way.

### 7.3 Table helper

Tables are the workhorse of this deck. `python-pptx` tables default to an ugly banded theme; override it explicitly.

```python
def add_table(slide, rows, cols, left, top, width, height,
              col_widths=None, header=True,
              header_size=9.5, body_size=8.5):
    shape = slide.shapes.add_table(rows, cols, Inches(left), Inches(top),
                                   Inches(width), Inches(height))
    tbl = shape.table
    tbl.first_row = header
    tbl.horz_banding = False          # kill the zebra striping

    if col_widths:
        for i, w in enumerate(col_widths):
            tbl.columns[i].width = Inches(w)

    for r_i, row in enumerate(tbl.rows):
        row.height = Inches(0.24)     # let it grow; this is a floor
        for c in row.cells:
            c.margin_left = c.margin_right = Inches(0.05)
            c.margin_top = c.margin_bottom = Inches(0.02)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            c.fill.fore_color.rgb = SURFACE if (header and r_i == 0) else RGBColor(0xFF, 0xFF, 0xFF)
            for p in c.text_frame.paragraphs:
                p.font.size = Pt(header_size if (header and r_i == 0) else body_size)
                p.font.bold = bool(header and r_i == 0)
                p.font.color.rgb = PRIMARY if (header and r_i == 0) else INK
                p.font.name = "Segoe UI"
    return tbl

def fill_table(tbl, data):
    """data = list of rows, each a list of cell strings."""
    for r, row in enumerate(data):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text_frame.text = str(val)
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(9.5 if r == 0 else 8.5)
                p.font.bold = (r == 0)
                p.font.color.rgb = PRIMARY if r == 0 else INK
                p.font.name = "Segoe UI"
```

**Sizing rule of thumb at 8.5 pt with 0.24 in rows:** a table fits about **13 body rows** in 3.6 in of vertical space. If a table in §4 or §5 has more rows than that, split it across two columns or two slides — do not shrink the font.

### 7.4 Rasterising the benchmark SVGs (if you use them)

`python-pptx` cannot embed SVG. Three options, in order of reliability on this Windows workstation:

1. **Rebuild as native PowerPoint charts** from the §5 tables. Best output, no external dependency. Recommended for the two comparison charts.
2. **`cairosvg`** — `pip install cairosvg`, then:
   ```python
   import cairosvg
   cairosvg.svg2png(url="docs/assets/benchmarks/workload-model-comparison.svg",
                    write_to="tmp/workload-model-comparison.png",
                    output_width=1800)   # ~2x the placed width for crisp output
   ```
   On Windows `cairosvg` needs GTK/Cairo binaries; if the import fails, fall back to option 3.
3. **Headless Chrome/Edge** — render the SVG in a page and screenshot it. Playwright is already a dev dependency of `web/`:
   ```powershell
   # from web/
   npx playwright screenshot --viewport-size=1800,1000 `
     "file:///C:/Users/Varshith/OneDrive/Desktop/DRISHTI/docs/assets/benchmarks/workload-model-comparison.svg" `
     ../tmp/workload-model-comparison.png
   ```

Rasterise at roughly **2× the placed pixel width** (a 4.4 in placement on a 10 in slide ≈ 1,270 px at 96 dpi presentation scale, so 1,800–2,600 px wide is right).

### 7.5 Fitting images without distortion

```python
def add_image_fit(slide, path, left, top, box_w, box_h, alt=None):
    """Place an image inside a box, preserving aspect ratio, centred."""
    from PIL import Image
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(box_w / (iw / 96), box_h / (ih / 96))
    w, h = (iw / 96) * scale, (ih / 96) * scale
    l = left + (box_w - w) / 2
    t = top + (box_h - h) / 2
    pic = slide.shapes.add_picture(path, Inches(l), Inches(t), Inches(w), Inches(h))
    if alt:
        pic._element._nvXxPr.cNvPr.set('descr', alt)
    return pic
```

`Pillow` is available (it is a dependency of the ML requirements). If it is not importable in your environment, hard-code the aspect ratios: the screenshots are ordinary browser captures (roughly 16:10 to 16:9), and the architecture PNG should be measured once and reused.

### 7.6 Speaker notes

```python
slide.notes_slide.notes_text_frame.text = "..."
```

Add notes to every content slide. Slide 1 already has a notes slide; the rest will be created on first access. Notes are where the honest nuance from §6 lives — a presenter reading them will not overclaim.

### 7.7 Post-build verification checklist

Run these checks programmatically before declaring the deck done:

1. **Slide count** matches the plan (16 original + the number of inserted slides).
2. **No shape crosses the brand chrome:** for every slide 2 onwards, assert every non-background shape has `top >= Inches(0.62)` and `top + height <= Inches(5.42)`.
3. **No shape exceeds the canvas:** `left >= 0`, `left + width <= Inches(10.0)`.
4. **No font below 7.5 pt** anywhere.
5. **Every picture has alt text** (`cNvPr.get('descr')` is non-empty).
6. **Slide 16 is byte-identical** to the source — compare its shape count, picture sha1 and XML length.
7. **Every `[MUST-FILL]` marker is gone** — grep all text frames for `MUST-FILL`, `TODO`, `TBD`, `Lorem`, `Blank slide`.
8. **All three links on slide 13 are real hyperlinks**, not plain text.
9. **The synthetic-data label is present** on every slide showing data or a screenshot.
10. **Open the result in PowerPoint once** and page through it. A programmatic check cannot see text that overflows its box; PowerPoint's rendering can.

```python
from pptx.util import Inches

def audit(prs):
    problems = []
    for i, slide in enumerate(prs.slides, 1):
        for sh in slide.shapes:
            if sh.shape_type == 13 and sh.width == prs.slide_width:
                continue                     # the full-bleed background
            if sh.top is not None and i >= 2 and sh.top < Inches(0.62):
                problems.append(f"s{i} {sh.name}: top {Emu(sh.top).inches:.2f} in header band")
            if sh.top is not None and sh.height is not None and sh.top + sh.height > Inches(5.42):
                problems.append(f"s{i} {sh.name}: bottom {Emu(sh.top + sh.height).inches:.2f} in footer bar")
            if sh.has_text_frame:
                for p in sh.text_frame.paragraphs:
                    for r in p.runs:
                        if r.font.size and r.font.size < Pt(7.5):
                            problems.append(f"s{i} {sh.name}: font {r.font.size.pt} pt too small")
    return problems
```

---

## 8. Pre-submission action list for the human

Ordered by value.

| # | Action | Why |
|---|---|---|
| 1 | Fill team name, leader and size on slide 1 | The agent cannot know these; a blank slide 1 looks careless |
| 2 | Confirm the official problem-statement wording | If the datathon issued a numbered statement, quote it exactly |
| 3 | Capture fresh screenshots of `/watch`, `/people/face` and `/admin` | Three shipped feature areas have no screenshot; this is the biggest content gap |
| 4 | Confirm the demo video is public, ≤ 3 minutes, and shows the Catalyst URL on screen | An explicit template requirement |
| 5 | Re-verify all three links from an incognito window on the submission day | Deployments drift; the brief's 6 Sep 2026 checks were 200 across the board |
| 6 | Decide whether to run `scripts/load_test.py` against the gateway for real p50/p95/p99 numbers | Would materially strengthen slide 12. It hits the live deployment and consumes a small amount of credit, so it is a deliberate choice — the harness is bounded and respects the 600/min throttle |
| 7 | Decide the TabFM licence position | TabFM 1.0.0 is Non-Commercial. Fine for evaluation, must be stated |
| 8 | Confirm whether extra slides are permitted by the rubric | §4 assumes yes; §4.3 gives a single-slide fallback |
| 9 | Open the finished deck in PowerPoint and page through it | Catches text overflow that no script can see |
| 10 | Delete `tmp/inspect_ppt.py`, `tmp/inspect_ppt2.py` and `tmp/ppt-extract/` | Build scratch, not deliverables |

---

## 9. One-paragraph elevator summary (reusable anywhere in the deck)

> **DRISHTI** is a governed decision-intelligence platform for public safety, deployed on Zoho Catalyst. It connects crime records, people, property, digital and financial evidence, geography, live operational events and predictive signals into one role-scoped operational picture across two workspaces — Crime Intelligence and Emergency Response. Over a 3.01-million-row synthetic Karnataka corpus spanning 140 tables, it serves 391 governed API endpoints to 39 role-scoped application routes: case exploration and an 18-page case file, entity resolution, network analysis, an investigation board with 36 endpoints, geospatial hotspots and patrol planning, CCTV video-analytics review, face search, a five-layer forecast stack, and a natural-language assistant that answers only from read-only guarded SQL with citations. Identity is derived server-side and carried in a 60-second HMAC-signed context; client identity headers are stripped at the gateway; every model output records its version, feature snapshot, confidence and provenance; and the GPU path fails closed rather than substituting a weaker model under a stronger name. Nothing dispatches, accuses or closes a case without a named human — and every material transition leaves an append-only audit trail.

---

*Compiled from a direct read of the DRISHTI repository at commit `198ab55` (6 September 2026) plus a live probe of the Catalyst Slate, API Gateway and AppSail endpoints. Every number carries a stated source. Where the repository README and the code disagree, §6.1 records the divergence and the code value is used.*
