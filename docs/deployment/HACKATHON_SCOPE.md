# DRISHTI Hackathon Scope (frozen — Prompt 18)

Frozen: 2026-07-20. This defines exactly what the submitted **synthetic hackathon
demo** on Zoho Catalyst includes, what is optional-and-hidden, and what is
explicitly excluded. It maps the Karnataka State Police organizer-session notes to
DRISHTI capabilities. Companion inventory: `CURRENT_STATE_MATRIX.md`.

Guiding rule: **do not enable every Catalyst service to fill a checklist.** A
service is in the demo only if it is actually demonstrated with real evidence;
otherwise it is hidden + disabled and recorded honestly (Not Used / Unavailable).

---

## 1. Mandatory demo set (must be Live Verified by Prompts 23–25)

1. **Catalyst-hosted platform** — public frontend (Slate/Web Client), API Gateway,
   Authentication, AppSail backend, Data Store (operational relational), Stratus
   (application objects). The browser talks only to Catalyst.
2. **Approved FIR + structured case intake** — guided FIR draft → validate →
   submit → supervisor approve → canonical case; structured import with a rejected
   row.
3. **Evidence upload with manual metadata, NO content extraction** — one digital
   synthetic file to private Stratus, hash/size/type + manual metadata, case link.
   No OCR / transcription / auto field extraction.
4. **Bilingual conversational query with follow-up + visualization** — an officer
   asks an English or Kannada text/voice question, follows up naturally, and gets a
   permission-scoped, cited answer with an appropriate auto-selected visualization
   (no hand-written SQL).
5. **Case / similar-case / graph / board / map / forecast paths** — case
   decision-support (summary, similar cases, MO, leads), link analysis, the
   Investigation Board, map/hotspots, and validated forecasts.
6. **Supervisor workload view** — real station/officer workload & performance
   metrics (replacing the "awaiting performance API" placeholder).
7. **Disaster Response** — replay a synthetic hazard feed → forecast with
   confidence/freshness → human-approved alert → proposed/approved allocation →
   safe route or explicit no-route → Board pin.
8. **One real TabFM GPU path + one real TimesFM path** — genuine AWS execution
   proving the actual backend/device (CUDA), fail-closed otherwise.
9. **Final reports, recovery and cost teardown** — watermarked report through an
   enabled Catalyst service, backup/rollback exercise, and confirmed temporary-GPU
   shutdown.

Role coverage (server-enforced): investigator, analyst, supervisor, policymaker
(aggregate-only), disaster_coordinator, super_admin — mapped from the organizer
DGP/IGP/DIG/SP/station-chief/officer hierarchy (mapping finalised in Prompt 20).

---

## 2. Organizer-note → DRISHTI mapping

| Organizer expectation (session notes) | DRISHTI capability | Scope | Disposition |
|---|---|---|---|
| Kannada + English, voice or text | Ask DRISHTI bilingual NL query; voice via Zia when available else labelled browser fallback | Mandatory | Text Implemented Locally; voice finalised P19 |
| Natural-language querying instead of SQL | NL→SQL engine (guarded, role-scoped, cited) | Mandatory | Implemented Locally (P19 makes semantic planner primary) |
| Conversational follow-ups + context retention | bounded multi-turn memory in the engine | Mandatory | Implemented Locally |
| Answers grounded + cited + visualized (not raw tables) | citations + typed visualization contract | Mandatory | citations done; typed viz P19 |
| Live crime stats / alerts / trends / hotspots / offender history / relationships | Command Center, map, analytics, network, people | Mandatory/Important | Implemented Locally |
| Similar-case & modus-operandi discovery | case similar/MO (embeddings + why-match) | Mandatory | Implemented Locally |
| Predictive hotspots / forecasts w/ confidence + freshness | forecast + geo hotspots + baselines | Mandatory | Implemented Locally; live GPU/TimesFM P24 |
| Station/officer workload for supervisors | `/workload` + supervisor Command Center | Mandatory | metrics finalised P20 |
| Maps, heatmaps, timelines, graph views, trends, Sankey | deck.gl/MapLibre + graph + charts | Mandatory | Implemented Locally; typed-viz coverage P19/P20 |
| Rank/unit → functional-role scope mapping | 6 functional roles + rank map | Mandatory | mapping documented P20 |
| Crypto / dark-web / inter-district / national / international / cross-border scenarios | synthetic scenario registry | Important | added as synthetic scenarios P20 |
| RBAC hierarchy, each role sees only permitted data | Catalyst Auth + server-side role/scope authorization | Mandatory | Implemented Locally; live P21/P23 |
| Zoho Catalyst hosting | full Catalyst plane | Mandatory | live P23 |
| Open-source LLM / semantic understanding | provider-neutral planner → Catalyst QuickML | Mandatory | P19/P23 |
| Synthetic data only | 100k synthetic Karnataka corpus | Mandatory | Implemented + labelled |
| Production-style, scalable architecture | AWS RDS analytics + Catalyst serving | Mandatory | demo-grade; scale evidence P25 |
| Knowledge graph (suspects/vehicles/phones/locations/FIRs) | canonical EntityGraph/NetworkEdge | Important | Implemented Locally |
| Multilingual voice assistant | Zia voice (when available) | Optional→Mandatory voice | P19 |
| Predictive hotspot engine (emerging, not just historical) | near-repeat + forecast | Important | Implemented Locally; live P24 |
| Explainable AI w/ supporting evidence | `/explain` + factor bars + citations | Important | Implemented Locally |
| Case timeline & replay on a map | board timeline + geo | Optional | Implemented Locally |
| Live Command Center w/ AI recommendations | Command Center + alerts | Important | freshness flow P20 |

---

## 3. Optional / hidden & disabled (not enabled unless actually demonstrated)

These exist and are tested, but are **feature-flagged OFF and hidden** from the
submitted demo unless explicitly enabled with real evidence:

- QuickML RAG assistant (`DRISHTI_QUICKML_RAG_ENABLED`).
- Mail + Push notifications (`DRISHTI_NOTIFY_ENABLED`) — in-app notifications
  always work.
- SmartBrowz report rendering (`DRISHTI_REPORT_DELIVERY_ENABLED`).
- Scoped SSE stream channel (`DRISHTI_STREAM_CHANNEL_ENABLED`).
- Zia voice/translation — enabled only if available in the project/DC and a real
  Kannada/English voice test passes; otherwise bilingual **text** stays fully
  working and voice is marked an explicit platform limitation (browser Web Speech
  is a labelled fallback, never presented as Zia).
- OR-Tools allocation optimiser (falls back to weighted-greedy).

Platform-unavailable (documented, not faked): **Circuits** and **Zia AutoML** are
not offered in the India DC → replaced by idempotent Functions + Job Scheduling and
QuickML + the justified AWS TabFM path.

---

## 4. Explicit exclusions (NOT in the mandatory build)

Out of scope by design — never presented as implemented:

- **OCR, document/FIR field extraction, evidence-media transcription, face/object
  recognition.** (Voice **query dictation** is separate and in scope; it is never
  conflated with evidence extraction. Flags are named separately:
  `QUERY_VOICE_*` may be true; `EVIDENCE_EXTRACTION_*` stays false.)
- **Full OSINT / dark-web scraping, purchases, credential use, illegal-content
  collection.** Dark-web/crypto crime appears only as *manually classified
  synthetic scenarios*.
- **Official agency feeds** (IMD/KSNDMC/CWC/WRD/GSI/Bhuvan/NASA-FIRMS/FSI) — live
  gauge access is **External Access Required**; a versioned recorded-sample
  connector proves the contract. (Open-Meteo is a working, no-key, CC-BY weather
  feed and is the only live feed.)
- **Alternate forecasters** TimeGPT, Chronos, LSTM — not implemented for
  model-count breadth. Only TabFM + TimesFM are the enabled model paths.
- **Automatic model retraining / per-FIR fine-tuning** — models are inference-only;
  a new FIR never retrains a pretrained model.
- **Production RLS / FORCE RLS** — intentionally disabled for this synthetic
  hackathon (server-side Catalyst Auth + Gateway + role/scope authorization remain
  the boundary). Production RLS/privacy/redaction/deletion/legal-hold are
  Post-Hackathon.
- **Real directory/SSO/rank synchronization, multi-tenancy, offline mobile evidence
  capture, one-million-case / 100k-user HA certification** — Post-Hackathon.

---

## 5. Final claim discipline

The completed result is called **HACKATHON-DEMO READY on Zoho Catalyst**, never
production-ready. The strict acceptance gate must pass with no mandatory
HELD/MANUAL/SKIP/UNKNOWN state before that claim is made (owned by Prompt 25).
