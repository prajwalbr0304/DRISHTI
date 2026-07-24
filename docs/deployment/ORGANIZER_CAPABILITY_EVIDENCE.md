# DRISHTI — Organizer Catalyst Capability Evidence (Prompt 25)

> Maps each organizer-mandated Zoho Catalyst capability to DRISHTI's disposition, live
> component and evidence. Honest status: **Used** (live), **Used (offline-proven)** where the
> logic is tested but the live edge has a documented gap, **Not Used**, or **Platform
> Unavailable**. The definitive independent 26-row audit is **Prompt 26**; this is the
> Prompt-25 builder's evidence view. Synthetic hackathon demo.

| Capability | Mandated service | DRISHTI disposition | Live component / evidence | Third-party exception | Cost/cleanup |
|---|---|---|---|---|---|
| Public web hosting | Slate | **Used** | `drishti-frvfpunc.onslate.in` (canonical; SPA 200) — `live-catalyst-boundary.json` | — | hosting |
| API edge + routing | API Gateway | **Used** | `/api/*` → `gateway_api`; health routes 200; foreign-origin CORS rejected | — | usage |
| App compute | AppSail (custom OCI) | **Used** | `drishti-api` `/health/*`=200; linux/amd64; single instance | — | 1 instance |
| Authentication | Catalyst IAM | **Used (⚠ deviation)** | IAM present; **`DEMO_AUTH` currently mints super_admin for sessionless callers** — RB-1 | — | — |
| Serverless functions | Functions | **Used** | 9 functions live (gateway/event/cron) | — | per-invocation |
| Operational data | Data Store | **Used** | `PredictionRequest` `48361000000043006` + Board/Disaster/reference; live CRUD | — | usage |
| Object storage | Stratus | **Used** | `drishti-evidence` private+versioned; SHA-256 verified; signed-URL expiry | — | storage |
| Eventing | Signals | **Used** | `prediction-requested` → `prediction_event` (delivery Success, retry, idempotency) | — | per-event |
| Scheduling | Cron / Job Scheduling | **Used** | `drishti_forecast` daily → `cron_forecast` (exec `48361000000061010`) | — | per-run |
| Caching | Cache | **Used** | nonce/segment replay-guard + idempotency | — | usage |
| Generative planner | QuickML LLM Serving | **Intended (⚠ live 502)** | Ask planner; live `/api/ask` returns 502 (RB-2); labelled deterministic fallback exists | — | inference |
| Speech (STT/TTS) | Zia | **Platform Unavailable** | Not in IN DC → browser Web Speech (labelled, never "Zia") | browser Web Speech API | — |
| Translation | Zia | **Platform Unavailable** | Not in IN DC → bilingual EN/KN text always works | — | — |
| OCR / media extraction | Zia | **Not Used (out of scope)** | `EVIDENCE_EXTRACTION_ENABLED=false` (scope freeze) | — | — |
| Watermarked report | SmartBrowz | **Optional** | Enable only if a visible demo capability; else Not Used | — | — |
| Email / Push notify | Mail / Push | **Optional** | In-app notifications always work; external only if data-minimized + enabled | — | — |
| Custom GPU/foundation ML | (none in DC) | **Used via AWS (justified)** | TabFM/TimesFM on SageMaker T4 (torn down); reached server-to-server only | **AWS SageMaker** — Catalyst has no CUDA foundation-model serving in DC | ephemeral, **stopped** |
| Circuits / Zia AutoML | Circuits / Zia | **Platform Unavailable** | Not in IN DC → Functions + Jobs fallback | — | — |

**Rule check:** the only capability delegated to a third party (AWS) is one Catalyst does **not** offer in this DC (CUDA foundation-model serving); it is reached server-to-server and torn down. No Catalyst-available capability is served by a third party.

**Open items before an unqualified "all-live" claim:** RB-1 (edge authz), RB-2 (live NL query). See `POST_HACKATHON_BACKLOG.md`.
