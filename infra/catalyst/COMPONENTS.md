# infra/catalyst — component allocation index (Phase 14 Part B)

Maps every Catalyst capability to its concrete artifact, and records what the CLI
actually exposes on the credited **DHRISTI** project (live-inspected
2026-07-18, CLI 1.27.0, IN DC).

## Live CLI inspection (credited project, not assumed)

`catalyst project:list` → `DHRISTI (active) (base)` `48361000000030003`.
`catalyst help` exposes these component commands:

- **CLI-managed:** `functions:*`, `client:*`, `appsail:add`, `slate:*`,
  `apig:*`, `ds:import` / `ds:export` / `ds:status`, `deploy`, `pull`, `serve`,
  `event:generate` / `signals:generate` (test payloads), `config:*`, `iac:*`.
- **Console/SDK-managed (no CLI verb):** QuickML, Stratus, NoSQL, Cache,
  SmartBrowz, Connections, Circuits, Zia, Mail, Push, Pipelines, billing.

So the CLI **cannot** query per-project availability for the console/SDK
components; their availability is governed by the IN-DC docs (Circuits + Zia
AutoML **unavailable**) plus the console. This is recorded honestly rather than
asserting a live gate we cannot read. `signals:generate` / `event:generate`
confirm Signals rules are console-only while event functions are the code targets.

> **Correction:** an earlier note in this repo claimed there is "no
> `catalyst ds:import` CLI". That was wrong — `ds:import`/`ds:export`/`ds:status`
> exist (verified above). Data Store import is `catalyst ds:import <csv>
> --config <cfg>` with `operation:upsert` + `find_by:ExternalID`; see `ds-import/`.

## Capability → artifact

| Capability | Artifact (contract / config) | Enable flag |
|---|---|---|
| Functions | `functions/*` (8) + `catalyst.json` | always on |
| AppSail (OCI) | `../../services/ml/Dockerfile.appsail` + `appsail/appsail.deploy.json` | — |
| Frontend | `client/` + `../../web/public/_redirects` (Slate) | — |
| Data Store + search | `../../services/ml/app/datastore/*` + `ds-import/` (106 configs) | — |
| Stratus | `../../services/ml/app/stratus.py` + `stratus/buckets.json` | `DRISHTI_USE_CATALYST_STRATUS` |
| NoSQL | `../../services/ml/app/nosql.py` + `nosql/segments.json` | `DRISHTI_USE_CATALYST_NOSQL` |
| Cache | `../../services/ml/app/cache.py` + `cache/namespaces.json` | `DRISHTI_USE_CATALYST_CACHE` |
| QuickML (RAG + no-code) | `../../services/ml/app/quickml.py` + `quickml/{rag-knowledge-base,nocode-experiment}.json` | `DRISHTI_QUICKML_RAG_ENABLED` |
| QuickML **LLM Serving** (Ask DRISHTI semantic planner, Prompt 19 §B) | `../../services/ml/app/nlsql/planner.py` (`CatalystQuickMLServingPlanner`) — hosts a governed open model (e.g. Qwen 2.5); deterministic offline planner is the labelled fallback | `SEMANTIC_PLANNER_PROVIDER=catalyst_quickml` |
| SmartBrowz | `../../services/ml/app/smartbrowz.py` | `DRISHTI_USE_CATALYST_SMARTBROWZ` |
| Authentication | `functions/gateway_api` + `../../services/ml/app/gateway_context.py` | always on |
| API Gateway | `api-gateway/routes.json` | `catalyst apig:enable` |
| Connections | `../../services/ml/app/connections.py` + `connections/connections.json` | `DRISHTI_USE_CATALYST_CONNECTIONS` |
| Job Scheduling | `jobs/cron-schedules.json` + `functions/cron_*` | per-cron (disabled) |
| Signals + Events | `jobs/signals-rules.json` + `functions/*_event` | per-rule (inactive) |
| Circuits | **Unavailable (IN DC)** → Functions + Jobs fallback (`jobs/`) | n/a |
| Mail / Push | `functions/notify_dispatch` | `DRISHTI_NOTIFY_ENABLED` |
| Pipelines | `pipelines/catalyst-pipelines.yaml` | — |
| Billing Budget/Report | `billing/budget.json` | console-only |
| Zia speech (STT/TTS) + translation — **voice query** (Prompt 19 §E) | **Not exposed in the IN DC** → browser Web Speech fallback (labelled, never called Zia); bilingual EN/KN text always works (`../../services/ml/app/zia_voice.py`) | `DRISHTI_USE_CATALYST_ZIA_VOICE` (off) |
| Zia **OCR** — scanned-FIR **intake form** reading (`../../services/ml/app/zia_ocr.py` + `app/intake/{extract,resolve,scan_service}.py`) | Reads a written/printed FIR **intake form** and PROPOSES draft fields an officer must confirm. Off by default | `INTAKE_SCAN_OCR_ENABLED` + `DRISHTI_USE_CATALYST_ZIA_OCR` |
| Zia face / object recognition / **evidence** extraction | **Not used — OUT of hackathon scope** (`EVIDENCE_EXTRACTION_ENABLED=false`) | n/a |

Every component client is a narrow interface with an in-memory fake (default,
cost-free) and a Catalyst-SDK implementation selected by its enable flag, so
nothing here spends credits until deploy + explicit enablement.

## Scope: three independent flags, not one

Three capabilities are often lumped together as "extraction". They are governed by
three separate flags precisely so enabling one can never silently enable another.

| Flag | Default | What it governs |
|---|---|---|
| `QUERY_VOICE_ENABLED` | true | Dictating a **question** and hearing the answer read back. |
| `INTAKE_SCAN_OCR_ENABLED` | **false** | Reading a written/printed **FIR intake form** to pre-fill the draft wizard. |
| `EVIDENCE_EXTRACTION_ENABLED` | **false** | Parsing uploaded **case material** — evidence OCR, media transcription, face/object recognition. |

Why the middle one is acceptable while the third is not:

* An intake scan is a form the complainant/officer has just written, read back to
  that same officer for confirmation. It is a typing shortcut with a human on
  every field.
* Its output lands only in staging (`IntakeScan` + `IntakeDraft.Payload`). A
  `CaseMaster` row is still created exclusively by the human approve transition in
  `app/intake/service._approve`, so a bad read produces a corrected draft, never a
  wrong registered FIR.
* Per-field provenance is recorded in `IntakeScanField` (proposed value, derived
  confidence, accepted value, whether it was edited), so machine-derived values
  stay distinguishable from typed ones for the life of the case.
* Evidence extraction would mean the system asserting facts about case material
  with no reviewer in the loop. That remains out of scope. Files uploaded through
  the `/evidence` custody path are hashed and stored, never interpreted.

Note on the upstream service: Zia OCR returns plain text plus a single
document-level confidence score — no per-field values and no bounding boxes. All
field-level confidence in DRISHTI is derived by `app/intake/extract.py` and is
never presented as if Zia asserted it. Zia recognises handwriting only when it is
legible and close to a standard character shape, so the manual lane is always
available and extraction is treated as advisory.

The Catalyst **Zia Services** catalogue in the IN DC (OCR, Face Analytics,
Identity Scanner, Image Moderation, Object Recognition, Barcode Scanner, AutoML,
Text Analytics — see
`https://docs.catalyst.zoho.com/en/zia-services/getting-started/components-of-zia-services/`)
exposes **no** speech-to-text / text-to-speech / translation component, so the
submitted voice capability is the browser Web Speech API (labelled as such), with
`app/zia_voice.py` holding a ready, env-gated Zia adapter contract for the day it
is exposed. Catalyst **QuickML LLM Serving** *is* available and is the primary
Ask DRISHTI semantic planner (verified live in Prompt 23).
