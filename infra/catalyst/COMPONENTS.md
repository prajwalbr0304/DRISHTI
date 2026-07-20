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
| Zia OCR / face / object recognition / evidence extraction | **Not used — OUT of hackathon scope** (`EVIDENCE_EXTRACTION_ENABLED=false`) | n/a |

Every component client is a narrow interface with an in-memory fake (default,
cost-free) and a Catalyst-SDK implementation selected by its enable flag, so
nothing here spends credits until deploy + explicit enablement.

## Prompt 19 scope correction — voice vs evidence extraction

Voice **dictation of a question** and spoken **read-back of the answer** are IN
hackathon scope and named by the independent flag `QUERY_VOICE_ENABLED` (true).
This is strictly separate from `EVIDENCE_EXTRACTION_ENABLED` (false): OCR,
uploaded-document parsing, automatic FIR field extraction, evidence-media
transcription and face/object recognition stay OFF. The two flags are distinct so
enabling voice query can never silently enable evidence extraction.

The Catalyst **Zia Services** catalogue in the IN DC (OCR, Face Analytics,
Identity Scanner, Image Moderation, Object Recognition, Barcode Scanner, AutoML,
Text Analytics — see
`https://docs.catalyst.zoho.com/en/zia-services/getting-started/components-of-zia-services/`)
exposes **no** speech-to-text / text-to-speech / translation component, so the
submitted voice capability is the browser Web Speech API (labelled as such), with
`app/zia_voice.py` holding a ready, env-gated Zia adapter contract for the day it
is exposed. Catalyst **QuickML LLM Serving** *is* available and is the primary
Ask DRISHTI semantic planner (verified live in Prompt 23).
