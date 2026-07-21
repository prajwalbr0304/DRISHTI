# DRISHTI — Catalyst capability matrix (Prompt 23 D.3/D.4/D.5)

> Honest record of which Zoho Catalyst services DRISHTI **uses**, which are
> **available but deliberately not used** (with the real fallback), and which are
> **unavailable in the India DC**. No third-party substitute is used to "tick a
> row", and no capability is claimed working without evidence. Project DHRISTI
> `48361000000030003`, org `60075362708`, India DC, Development.

## Legend
- **USED** — enabled and exercised live; evidence linked.
- **USED (fallback)** — a bounded, honest substitute is used for a specific,
  documented reason; the Catalyst service is available.
- **NOT USED** — available in the DC but intentionally hidden from the submitted
  demo; the deterministic/offline path serves the feature instead.
- **UNAVAILABLE** — not offered in the India DC; recorded, not replaced by a
  third party.

## Core platform (all USED, proven live)

| Capability | Status | Evidence |
|---|---|---|
| Data Store (operational serving) | **USED** | live ZCQL/row upsert/get/delete; `State` row imported; readiness `operational_datastore: ok` |
| Stratus (evidence/import/report buckets) | **USED** | fixture upload+download sha256 MATCH, versioning, signed-URL expiry — `artifacts/phase-23/stratus-fixture.log` |
| Functions (9: gateway_api, channel_token, 5 event, 2 cron) | **USED** | deployed at `.../server/<fn>/` |
| API Gateway (routes + auth + throttle 600/min) | **USED** | `/api/*` routes; `/api/cases` → 401; `/api/health/*` → 200 |
| AppSail (FastAPI custom container) | **USED** | live `/health/ready` 200; non-root; graceful shutdown |
| Slate (Web Client Hosting) | **USED** | `drishti-web-new-fhxgsmlo.onslate.in` serving the SPA |
| Authentication (6 functional roles) | **USED** | roles created; gateway resolves role server-side (security probe cases 3/4) |

## Bounded / conditional

| Capability | Status | Decision & evidence |
|---|---|---|
| **Cache (NoSQL/Cache)** | **USED (fallback)** | In-process cache on the **single-instance** AppSail (idempotency/nonce/rate-limit are correct for one instance). Catalyst Cache is available but needs per-segment provisioning; the code is REST-ready (`CatalystCache` + `DRISHTI_CATALYST_CACHE_SEGMENTS`) to switch on when segments exist. Not a duplicate of Data Store records. |
| **Signals** | **USED** (pending live exec, Task 9/D1) | The one mandatory `prediction.requested` Signal = `drishti_datastore` publisher, `row_inserted`, filter `table=PredictionRequest AND state=approved` → `prediction_event` (`infra/catalyst/jobs/signals-rules.json`). Fires from a Data Store row insert. Custom `drishti_app` publisher is optional (Phase 15/16 events), gated off. |
| **Cron** | **USED** (pending live exec, Task 9/D1) | Scheduled forecast → `cron_forecast` → AppSail `/internal/forecast/run` (idempotent by window, bounded 3× retry). |
| **QuickML (RAG / no-code baseline)** | **NOT USED (deferred)** | Available in IN DC (LLM serving). The "Ask DRISHTI" assistant currently uses the deterministic **OfflineRag** that refuses unless an approved-SOP KB is loaded (safe, cost-free). Enabling it requires building the approved-SOP KB + a deployed endpoint + a minimal-scope Connection (`QuickML.rag.READ`/`endpoints.READ`), then the fixed evaluation — a deliberate, separate step, not faked. |

## Unavailable in the India DC (recorded, not substituted)

| Capability | Status | DRISHTI handling |
|---|---|---|
| **Zia STT/TTS / translation** | **UNAVAILABLE** | Kannada/English **voice query** uses the browser **Web Speech API**, clearly labelled as a browser fallback (not a Catalyst service). OCR/evidence extraction stays out of scope. Voice transcription is never conflated with evidence extraction. |
| **Zia AutoML** | **UNAVAILABLE** | The eligible no-code tabular baseline is placed on **QuickML** instead (documented in `services/ml/app/quickml.py`); no third-party AutoML is substituted. |
| **Circuits** | **UNAVAILABLE** | Not used; orchestration stays in Functions + the AppSail. No third-party workflow engine substituted. |

## Deliberately hidden from the submitted demo (available, NOT USED)

| Capability | Status | Reason & fallback |
|---|---|---|
| **SmartBrowz (pdfshot)** | **NOT USED** | Report export uses a deterministic server-side path; the SDK-based `smartbrowz.py` is not REST-migrated for the custom container. Hidden from the demo; marked Not Used rather than fake a watermarked-PDF render. |
| **Mail (Email)** | **NOT USED** | Notifications are **in-app, data-minimized** records (`/internal/notify` → Data Store). No external email is sent in a synthetic-data demo (avoids mailing real addresses). Hidden. |
| **Push (web/mobile notifications)** | **NOT USED** | Same as Mail — the demo surfaces notifications in-app only. Hidden. |

## Notes
- "Hidden" means the capability is not surfaced as a control in the submitted
  demo UI, so acceptance never shows a non-functional button.
- Every "NOT USED" here has a working deterministic/offline fallback so the
  corresponding feature still functions in the demo without the paid/region
  service.
- Availability of Zia ML / Circuits reflects the India DC component list recorded
  during Phase 14/21; QuickML LLM serving is available in the India DC.
