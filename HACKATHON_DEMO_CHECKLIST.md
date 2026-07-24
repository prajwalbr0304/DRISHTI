# DRISHTI — Hackathon Demo Checklist (Prompt 25 Part B journeys)

> The 15 mandatory end-to-end journeys with honest status. **Live** = proven through the
> public Catalyst path this phase; **Offline-proven** = real code + automated tests pass, live
> edge has a documented gap; **Gap** = open remediation (see `POST_HACKATHON_BACKLOG.md`).
> Synthetic hackathon demo — never production.

| # | Mandatory journey | Status | Evidence / note |
|--:|---|---|---|
| 1 | Public frontend → Auth → Gateway → Function/AppSail → Data Store health + authorized API | **Live (partial)** | Frontend SPA 200; gateway health route 200; AppSail `/health/*` 200; **authorized-scope edge = Gap (RB-1, `DEMO_AUTH`)** — `live-catalyst-boundary.json` |
| 2 | Login as 6 roles; verify allowed **and denied** scope | **Offline-proven; live Gap** | 34-case allow/deny matrix PASS through real `app.org.scope`; live per-role deny not enforced (RB-1) |
| 3 | FIR draft → validate → submit → supervisor approve → canonical case; **no prediction before approval** | **Offline-proven** | `test_intake`, `test_casework`, `test_predict_runtime` (draft/evidence invoke no model); happy-path approval offline |
| 4 | Add/review person/party → resolve candidate identity with audited decision | **Offline-proven** | `test_identity`, `EntityResolution.test.tsx` |
| 5 | Upload digital synthetic evidence → Stratus → hash/malware-safe fixture → manual metadata → case link; **no OCR** | **Live** | Phase 23 evidence-upload → Stratus SHA-256 verified; `EVIDENCE_EXTRACTION_ENABLED=false` |
| 6 | Typed statement/property/lab/court/lifecycle + structured import with a **rejected row** | **Offline-proven** | `test_casework`, `test_imports`; rejected-row recovery in `recovery-exercise.json` |
| 7 | English + Kannada vehicle-theft query + multi-turn follow-up → safe plan, citations, visual | **Offline-proven; live Gap** | `test_nlsql*`, `test_prompt19`, `AnswerVisualization.test.tsx`; live `/api/ask` 502 (RB-2) |
| 8 | Case-scoped investigation assistant → similar/MO → graph/path → evidence vs hypothesis → Send to Board | **Offline-proven** | `AssistantPage.test.tsx`, `test_investigate`, `test_graph_queries` |
| 9 | Create/share/edit/lock/branch/export Investigation Board + replay activity with provenance | **Live** | Phase 23 live Board CRUD; `test_board_api`, `test_board_datastore` |
| 10 | Approved FIR → aggregate change → live Signal → **real TabFM** result → review; TimesFM scheduled forecast + freshness/intervals | **Live (model) + Gap (deployed chain)** | Live Signal + cron (Phase 23); real T4 TabFM (`928cb350…`) + TimesFM (32 districts, intervals); deployed AppSail→adapter not wired (RB-3) |
| 11 | Correct approved input → prior result stale/superseded → idempotent rerun; preserve history | **Offline-proven** | `test_governed_forecast_persistence`; `recovery-exercise.json` idempotent rerun |
| 12 | Command Center alerts, district stats, hotspot/trend, supervisor workload from committed state | **Live** | `/api/performance/overview`, `/api/workload/predictions`, `/api/geo/hotspots`, `/api/disaster/overview` 200 |
| 13 | Hazard feed → forecast → reviewed alert → proposed/approved allocation → safe route or explicit no-route → Board pin | **Live/Offline** | Live disaster overview + forecast write (Phase 23); `test_disaster`, allocation/route logic |
| 14 | Watermarked structured report via Catalyst services + audit/object hash; data-minimized notification if enabled | **Offline-proven / Optional** | Report object hashing; SmartBrowz/Mail optional (in-app notify always works) |
| 15 | Every journey with **no OCR/transcription** and **no direct browser DB/AWS access** | **Live** | Route/data-boundary check (336 routes, 0 violations); `check_no_db_url_in_web` (270 files, 0 leaks); extraction off |

## Summary

- **Live (full or partial):** 1, 5, 9, 10 (model), 12, 13, 15.
- **Offline-proven (logic + tests green; live edge gap):** 2, 3, 4, 6, 7, 8, 11, 14.
- **Open live gaps:** RB-1 (edge authz / journeys 1,2), RB-2 (live NL query / journey 7), RB-3 (deployed model chain / journey 10). See `POST_HACKATHON_BACKLOG.md`.

**Local fallback for any journey:** the deterministic offline demo (backend 378 passed DB-free; browser E2E 27 passed) covers every mandatory journey — see `HACKATHON_DEMO_RUNBOOK.md` §3.
