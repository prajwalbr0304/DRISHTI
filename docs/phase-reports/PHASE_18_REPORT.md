# PHASE 18 — Truth reconciliation, scope freeze, and baseline repair

Status date: 2026-07-20
Owner: implementation agent (Kiro)
Branch: `fix/case-overview-location-map`
Catalyst project: **DHRISTI** (`48361000000030003`), India DC, Development env.
Result of this phase: **Complete** (every Definition-of-Done item verified below).

> This phase establishes ONE evidence-backed current state, removes contradictions,
> and repairs the minimum baseline so the later cloud phases are not built on false
> assumptions. It is a **synthetic hackathon** effort — nothing here is production.
> No Catalyst/AWS deployment or credit spend was performed; that is Prompts 23–24.

---

## 0. Definition of Done — verification

| DoD item | State | Evidence |
|---|---|---|
| One current-state matrix covers every submitted route/capability | **PASS** | `docs/deployment/CURRENT_STATE_MATRIX.md` (§3–7: platform, 20 UI routes, 26 routers, ML plane, AWS plane, Catalyst services) |
| Mandatory / optional / deferred / post-hackathon scope unambiguous | **PASS** | `docs/deployment/HACKATHON_SCOPE.md` (mandatory set, hidden-optional, explicit exclusions, organizer mapping) |
| No status claims local fakes are live cloud services | **PASS** | matrix marks **0 Live Verified**; strict acceptance returns **BLOCKED**; every mandatory row is "Implemented Locally / Not deployed" |
| Every baseline failure is fixed or assigned to a later cloud-only gate | **PASS** | 4 code defects fixed + verified (§4); the one remaining timeout (risk full-calibration) is CPU-bound `@slow`, assigned to P24 GPU |
| Strict acceptance cannot pass with mandatory HELD/MANUAL/SKIP | **PASS** | `acceptance_check.py --strict` → exit 1, "RELEASE ACCEPTANCE: BLOCKED" (§5) |
| README/setup match AWS RDS + Catalyst serving | **PASS** | README/db.py/datagen/.env reconciled; Supabase retired to a labelled legacy note (§3) |

---

## 1. Part A — Preserve & inventory

- `git status --short` captured; **no existing change reverted**. Pre-existing
  dirty files preserved (user's `engine.py`, `NotificationsBell.tsx`,
  `InvestigatorHome.tsx`, untracked `briefing.py`, `JurisdictionMap.tsx`, the two
  `.ps1` helpers, `prompt3.md`).
- Tool versions re-verified (matrix §2). **Key correction:** Docker CLI **is**
  installed (29.6.1); only the Linux daemon is stopped — the phase-14 "Docker
  absent" claim was stale.
- Full inventory produced: **20** React destinations, **26** FastAPI routers
  (+health/demo), **8** Catalyst Functions, operational Data Store tables (106
  import configs) + 6 board + 14 disaster, **3** Stratus buckets, **1** minimal
  Signal, **1** minimal cron, QuickML/Zia/Mail/Push/SmartBrowz descriptors, the
  Catalyst→AWS adapter and the GPU worker.
- **`docs/deployment/CURRENT_STATE_MATRIX.md`** written with the required columns
  (capability, UI route, API route, current repo, target repo/service, local-test,
  live-cloud, scope, blocker, owning prompt) and the six-value state vocabulary
  (Implemented Locally / Deployed / Live Verified / Disabled Optional / External
  Access Required / Post-Hackathon) — never collapsed into "Complete".

## 2. Part B — Scope freeze

- **`docs/deployment/HACKATHON_SCOPE.md`** records the 9-item mandatory demo set,
  the organizer-note → capability mapping, the hidden/disabled optional services
  (QuickML/Mail/Push/SmartBrowz/SSE/Zia/OR-Tools), and the explicit exclusions.
- Excluded from the mandatory build and documented as such: OCR/extraction/
  transcription/face-object recognition, full OSINT/dark-web scraping, official
  agency gauge feeds (External Access Required), TimeGPT/Chronos/LSTM, automatic
  retraining, production RLS, directory/SSO sync, multi-tenancy, HA certification.
- Circuits and Zia AutoML recorded **Unavailable in the IN DC** (not faked).
- Voice-query vs evidence-extraction kept as **separate feature flags** so voice
  can be enabled while extraction stays off.

## 3. Part C — Documentation / status truth

- **README.md** — rewritten from Supabase-first to the true **AWS RDS analytics +
  Zoho Catalyst serving** architecture (deployed-vs-local-dev section, arch table,
  env block), with a clearly-labelled **Legacy / historical (Supabase migration)**
  section preserving the history.
- **`services/ml/app/db.py`** — Supabase connection-string language replaced with
  AWS RDS PostgreSQL; note added that the deployed serving path uses Catalyst Data
  Store/Stratus and does not need `DATABASE_URL`.
- **User directive "do not use supabase — everything is on AWS" honored** with a
  repo-wide sweep:
  - `.env` — removed stale unused `SUPABASE_URL/PUBLISHABLE_KEY/SECRET_KEY/JWKS_URL`
    and the commented old Supabase `DATABASE_URL`; the **active AWS RDS
    `DATABASE_URL` preserved exactly** (`.env` is git-ignored; no secret committed).
  - `datagen/{config,db,preflight,__init__,reclaim,build}.py` — reframed
    Supabase-first framing/fallbacks to AWS RDS (verified `import datagen` OK and
    the DSN still resolves to RDS).
  - `DRISHTI_REMAINING_FEATURES_AND_AWS_ROADMAP.md` — dated correction note that
    the "Supabase source of truth" passages are stale (fully migrated to AWS RDS).
  - Kept intentionally: `hardening.py` masked-DB label (defensive, correctly labels
    `aws-rds`) and `test_hackathon.py` bundle-secret scanner (security — still
    guards against a Supabase client leaking into the browser bundle).
  - Historical phase reports / `POLICE FILES` / prompt2 Phase 1–3 left intact as
    historical evidence (PHASE_03 already documents the Supabase→AWS migration).
- **prompt2.md** — the stale "Recommended first command/session (Start with Prompt
  9)" now points to `prompt3.md` Prompt 18; the **old Prompt 18 marked SUPERSEDED**;
  the workflow-dependency off-by-one **"Prompts 17-18" → "Prompts 16-17"** (Board =
  16, Disaster = 17) corrected; reconciliation note added that Prompts 14/16/17 are
  locally implemented but cloud acceptance continues in prompt3.
- **Docker correction addenda** added to `PHASE_14_REPORT.md` and
  `PHASE_14_PARTD_REPORT.md` (CLI installed 29.6.1; only the Linux daemon is
  stopped) without rewriting the historical text.
- **UTF-8 / mojibake** — scanned all phase reports + changed markdown for U+FFFD
  and double-encoded UTF-8 sequences: **clean, valid UTF-8, no BOM**. (The mojibake
  in prompt3 §3 was console rendering of test output, not file content.)
- `prompt3.md` already recommends starting at Prompt 18 (§6); status table updated
  in §6 of this report.

## 4. Part D — Baseline failures (ledger + remediation)

Durable, per-module diagnostics were produced because the full suite mixes fast
pure-logic tests with slow remote-AWS-RDS + live-LLM integration tests (a single
run can hang on an uninterruptible DB socket read). A reusable runner
`services/ml/scripts/test_ledger.py` runs each module in its own subprocess with a
wall-clock backstop.

### 4.1 Results

| Suite | Command | Result |
|---|---|---|
| Backend offline (DB skipped) | `pytest` with `DRISHTI_DISABLE_DB_TESTS=1` | **279 passed, 0 failed, 153 skipped** (`.p18-offline.xml`) |
| Backend live DB, per-module | `python scripts/test_ledger.py` | **26/27 modules PASS** (only `test_explain` failed; now fixed) — `.p18-db-ledger.md` |
| NL→SQL (live LLM, Groq) | `pytest tests/test_nlsql.py` | **63 passed, 0 failed** |
| `@slow` money detection | `pytest -m slow tests/test_money.py::…` | **1 passed** (3.2 s) |
| `@slow` risk full-calibration | `pytest -m slow tests/test_risk.py::…` | **TIMEOUT on CPU** (real TabPFN `torch.einsum`); expected — see 4.3 |
| Frontend | `npm run typecheck && npm run test && npm run build` | typecheck OK, **41 vitest pass**, build OK (only the expected unconfigured-API-URL warning) |
| Catalyst infra syntax | JSON/YAML/`node --check` | **158 JSON valid, 1 YAML valid, 10 JS pass** |
| Derived-data fixtures | `python -m app.batch validate-fixtures` | **all required present** (SocialIndicator 32, EconomicIndicator 32, hidden_associations 2463, money_flags 72; CrimeRiskScore 0 optional) |

### 4.2 Code defects repaired (do-not-weaken; all re-verified)

1. **CORS wildcard regression** (`config.py`) — the current branch had hard-coded
   `cors_allow_origins() → ["*"]`, breaking two exact-origin security tests and the
   deploy posture. Restored the exact allow-list (localhost + configured origins)
   with an explicit opt-in `DRISHTI_CORS_ALLOW_ALL` for a local-only demo. →
   `test_hackathon.py` CORS tests pass.
2. **Investigation Board Search-Around fan-out cap** (`board/searcharound.py`) — the
   BFS caps fan-out **per hop**, so a 2-hop expansion could return far more than
   `max_neighbors`. Proven on the densest entity (degree ~32): raw 2-hop = **28
   neighbours** vs a cap of 10. Added a final total cap (strongest by edge weight) +
   coherent induced-edge filter. → `test_search_around_capped_and_id_based` passes
   (neighbours capped to 10).
3. **NL→SQL policymaker aggregate/clarification** (`nlsql/engine.py`) — an
   aggregate-only role could be blocked or asked to clarify when the (LLM) planner
   returned a non-aggregate/clarification. Added a deterministic guarantee: for
   aggregate-only roles, substitute the deterministic aggregate plan when needed
   (the scope guard still enforces the boundary independently). → the policymaker
   test passes deterministically with the live LLM.
4. **AI-route contract audit** (`explain/service.py`) — three new raw operational
   reads from the caseload/geo/graph enhancement (`/cases/caseload`, `/geo/coverage`,
   `/graph/path/suggestions`) were counted as AI routes. They are raw reads
   (lifecycle-stage counts, dataset date range, seed entity pairs) — added to the
   documented exempt set exactly like `/cases`, `/geo/points`, `/graph/entities`. →
   contract audit **40/40 conforming**, `test_contract_audit_every_ai_route_conforms`
   passes.

### 4.3 Data-state failures (from the old reports) — reconciled

The old reports listed six data-state failures (socioeconomic, hidden-association,
money, risk). **Re-running against the live DB shows these are already resolved**
by the current branch's data load — the prompt's warning "do not copy these counts"
was correct. Verified present: SocialIndicator 32, EconomicIndicator 32,
`drishti_hidden_associations` 2463, `FinancialTransaction` flagged 72. The
corresponding tests (`test_analytics`, `test_graph_hidden`, `test_money`) **pass**.
To keep this reproducible on a fresh DB, a deterministic, non-destructive
derived-data command **`python -m app.batch load-derived`** (+ `validate-fixtures`)
was added (matviews + hidden-associations + money flags, optional bounded risk
sample). No assertion was weakened.

### 4.4 Remaining failure assigned to a later gate

- **`test_risk.py::test_full_calibration_report_runs`** (`@slow`) — runs real
  TabPFN calibration; it does not finish on CPU (blocks in `torch.einsum`, >900 s).
  This is **expected** (marked `@slow`, deselected from the default suite; the test
  itself notes the full calibration is "too slow for the unit suite on CPU"). It is
  a **CPU-bound compute limit, not a defect**, owned by **Prompt 24** (real GPU
  plane) or the `risk-calibration` batch CLI. No submitted screen depends on it
  (the individual offender score was retired in Phase 13; the aggregate workload
  band is the approved path and passes).
- **Frontend production build warning** — the intentional unconfigured
  `VITE_API_BASE_URL` placeholder warns (does not fail). Making an unset/invalid
  production URL a hard failure is owned by **Prompt 22** (release mode) and the
  real Gateway URL is set in **Prompt 23**.

## 5. Part E — Truthful acceptance behavior (strict release mode)

`infra/catalyst/verification/acceptance_check.py` now supports `--strict`
(`--release`), backed by a `release_evidence` classification added to every item in
`acceptance-checklist.json`:

- `live` — only a real deployed invocation proves it (K1–K8).
- `local_ok` — a local source/build check is sufficient release evidence (K10).
- `config_only` — a configuration declaration that **cannot** prove the live
  capability (K9 Signal/cron) — excluded from release proof.
- `ops` — an operational teardown confirmation (K11).

Verified behavior:

- **Offline non-strict** → prints `ACCEPTANCE: INCOMPLETE` (2 PASS, 7 HELD, 2
  MANUAL), exit 0, explicitly "this is NOT a release-ready result." Never prints
  release success.
- **Offline `--strict`** → lists **10 mandatory checks NOT release-proven**
  (K1–K8 HELD/MANUAL, **K9 "config declaration only — a live invocation is
  required"**, K11 MANUAL), prints `RELEASE ACCEPTANCE: BLOCKED`, **exit 1**.
- A configuration declaration (Signals/cron JSON) can never satisfy strict mode —
  it demands a live Signal delivery, cron execution, Data Store write,
  authentication flow or GPU invocation.

## 6. Remaining Prompt 19–26 dependencies

| Prompt | Depends on (from this phase) |
|---|---|
| **19** Bilingual semantic query + voice + typed visuals | extend the NL→SQL engine (policymaker guarantee already deterministic); make QuickML the primary planner; add typed visualization contract; integrate Zia voice or label the fallback. |
| **20** Domain/hierarchy/supervisor/investigation closure | add crypto/dark-web/cross-jurisdiction synthetic scenarios; rank→role/scope map; real supervisor performance metrics; case-scoped investigation assistant; committed-FIR freshness flow. |
| **21** Catalyst operational data boundary | migrate operational routes off direct AWS RDS to Data Store/Stratus (matrix "current → target" column is the worklist); make mandatory journeys pass with `DATABASE_URL` absent; fix the Gateway role mapper; repeatable disaster Data Store schema. |
| **22** Local release stabilization + CI/CD | start Docker Desktop's Linux daemon (CLI already present) and build the AppSail image; restore ESLint; make an unset/invalid prod API URL a hard failure; Playwright E2E; fix Catalyst Pipelines paths. |
| **23** Live Catalyst provisioning + deploy | deploy Slate/Auth/Gateway/AppSail/Data Store/Stratus; import the curated serving subset; enable + prove the one Signal and one cron; flip strict acceptance K1–K5/K7–K9 to Live Verified. |
| **24** Live AWS custom-ML plane | build/push the GPU worker to ECR; SageMaker async TabFM (CUDA) + a real TimesFM path; prove Catalyst→AWS→Catalyst→UI; run the risk full-calibration on GPU; tear down temporary GPU. |
| **25** Integrated security/scale/recovery/release | full separated suites, live journeys, load/recovery, all required artifacts; strict acceptance must return zero. |
| **26** Independent audit | four-way evidence audit; confirm no local fake is presented as live. |

---

## 7. Commands run (evidence; no secrets)

```text
git status --short                                  # dirty state preserved
python --version / node --version / catalyst --version / aws --version / docker --version / docker info
python -m pip install pytest-timeout==2.3.1
# offline baseline
$env:DRISHTI_DISABLE_DB_TESTS="1"; python -m pytest -q --timeout=120 --junitxml=.p18-offline.xml
#   -> 279 passed, 0 failed, 153 skipped
# live-DB per-module ledger
python scripts/test_ledger.py --test-timeout 90 --module-timeout 480    # 26/27 PASS
# targeted fix verification (live DB + live LLM)
python -m pytest tests/test_board_api.py::test_search_around_capped_and_id_based \
  tests/test_nlsql.py::test_engine_policymaker_answer_is_aggregate_not_blocked \
  tests/test_analytics.py tests/test_graph_hidden.py::test_materialized_feed_has_ranked_rows \
  tests/test_money.py::test_flagged_feed_reads_persisted_flags -v   # 8 passed
python -m pytest tests/test_explain.py::test_contract_audit_every_ai_route_conforms   # 1 passed (40/40)
python -m app.batch validate-fixtures                               # all required present
# frontend
npm run typecheck && npm run test && npm run build                  # OK / 41 pass / build OK
# infra syntax: 158 JSON valid, 1 YAML valid, 10 JS node --check OK
# strict acceptance
python infra/catalyst/verification/acceptance_check.py              # INCOMPLETE (exit 0)
python infra/catalyst/verification/acceptance_check.py --strict     # BLOCKED (exit 1)
```

Working artifacts were transient and have been cleaned up; all results are
captured inline above. The per-module ledger is reproducible on demand via
`python services/ml/scripts/test_ledger.py` (writes `.p18-db-ledger.{md,json}`),
and the offline baseline via `pytest --junitxml=...` with `DRISHTI_DISABLE_DB_TESTS=1`.

---

## 8. Honest limitations

- No Catalyst/AWS deployment was performed this phase; **0 capabilities are Live
  Verified**. Every "Implemented Locally" row awaits Prompts 23–24.
- The live-LLM NL→SQL tests use the configured provider (Groq); the deployed
  submission's primary semantic path (Catalyst QuickML) is finalised in Prompt 19.
- Real TabFM CUDA and TimesFM execution remain unproven (Prompt 24).
- The Signal + cron are declared in config only; strict acceptance correctly
  refuses to count them as live.
