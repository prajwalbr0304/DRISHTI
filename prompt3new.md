# DRISHTI Remaining Hackathon Implementation Prompts — Agent/Skill Orchestrated Edition

Prepared from the repository state on 20 July 2026, `prompt2.md`, Phase 14-17
reports, the supplied Karnataka Police session notes, and local verification.

This is the authoritative continuation after the locally implemented work through
Prompt 17. Do not run the old Prompt 18 from `prompt2.md` first. Complete Prompts
18-25 below in order, then run Prompt 26 as an independent implementation audit.

The purpose of this file is not to rebuild working features. It closes the gap
between a strong local prototype and a truthful, deployed, judge-ready Catalyst
submission.

---

## 1. Current truth

The user's statement that Prompts 1-17 are done is accepted as **feature work
implemented locally**. It does not yet mean cloud acceptance is complete.

| Existing work | Truthful state at this audit |
|---|---|
| Prompts 1-13 | Implemented; retain and regression-test |
| Prompt 14 | Substantial local Catalyst/AWS scaffolding; live Catalyst deployment, operational import and real GPU proof remain incomplete |
| Prompt 15 | Admin/report/notification/RAG feature paths implemented locally; enabled Catalyst services still require live verification when included |
| Prompt 16 | Investigation Board implemented and locally tested; live Catalyst repositories/services still require verification |
| Prompt 17 | Disaster Response implemented and locally tested; live Catalyst deployment and Disaster Data Store provisioning remain incomplete |
| Old Prompt 18 | Not complete; superseded by Prompts 18-26 in this file |

Observed verification baseline:

- frontend typecheck passes and 41 Vitest tests pass;
- the current NL-to-SQL suite has 62 passes and one failing policymaker aggregate
  clarification case;
- earlier full backend evidence records six data-state-dependent failures, and a
  later targeted audit found a Board fan-out cap failure;
- a fresh full-suite audit exceeded five minutes without producing a final result;
  Prompt 18 must rerun it with durable output/per-module diagnostics rather than
  treating the timeout as a pass or failure count;
- the Catalyst acceptance runner currently reports 2 PASS, 7 HELD and 2 MANUAL;
- API Gateway, cloud Signals and scheduled jobs are not proven active;
- no real TabFM CUDA invocation is proven;
- all Prompt 18 reports, runbooks and final submission artifacts are absent.

Do not copy these counts into a new report without rerunning the commands. They are
the starting evidence, not a substitute for current results.

---

## 2. Requirements recovered from the organizer-session notes

### Hackathon-critical

- Zoho Catalyst hosts the submitted frontend and application API.
- Officers can ask questions in natural language without knowing SQL.
- Kannada and English text queries work.
- Conversational follow-ups retain bounded session context.
- Voice query input is organizer-facing scope and must be separated from deferred
  FIR/evidence OCR or document extraction.
- Answers are grounded in authorized data, cite their sources, and produce an
  appropriate visualization rather than only a raw table.
- Server-side authorization limits data by role and organizational scope.
- The demonstrated path looks production-style while being labelled only as a
  synthetic hackathon demo.
- Synthetic data is used; no real police or personal data is implied.

### Important demo coverage

- live/fresh crime statistics, alerts, trends, hotspots, offender history and
  relationship analysis;
- similar-case and modus-operandi discovery with evidence-backed explanations;
- predictive hotspots/forecasts with confidence, freshness and baselines;
- station/officer workload and performance for supervisors;
- maps, heatmaps, timelines, graph views, trend charts and Sankey flows;
- a rank/unit-to-functional-role scope mapping that represents the organizer's
  DGP/IGP/DIG/SP/station-chief/officer hierarchy without creating duplicate UI
  products for every rank;
- explicit synthetic scenarios for cryptocurrency-enabled crime, dark-web-enabled
  crime and inter-district/inter-state/national/international/cross-border scope.

### Optional differentiators, not blockers

- a unified geospatial case-timeline replay;
- optional grounded Investigation Board assistance;
- a dedicated graph database only if measured PostgreSQL graph performance is
  inadequate;
- alternate forecast families such as TimeGPT, Chronos or LSTM. Do not implement
  these merely for model-count breadth;
- fine-tuning an open-source model. Do not train on synthetic FIR narratives and
  claim police-domain validity.

### Post-hackathon/production

- real CCTNS/RMS/court/lab/official disaster-feed integrations and licensing;
- production PostgreSQL RLS, privacy, deletion, redaction, legal-hold and incident
  response controls;
- full directory/SSO integration for the real police hierarchy;
- real 100,000-user and one-million-case capacity certification;
- governed fine-tuning on approved real data;
- offline mobile evidence capture, multi-tenancy and complete board snapshot
  versioning.

---

## 3. Confirmed gaps that must not be silently omitted

### P0 release blockers

1. Catalyst cloud deployment is not proven: Slate/Web Client, Authentication, API
   Gateway, AppSail, Data Store, Stratus, live Functions, one Signal and one job
   schedule all need real evidence.
2. The proposed AppSail configuration omits `DATABASE_URL`, while many FIR, case,
   identity, evidence, casework, import, finance, geography, chat and analytics
   modules still call PostgreSQL directly. The deployed data boundary is therefore
   internally inconsistent.
3. The Catalyst gateway role mapper does not map every backend role and scoped
   assignment correctly, especially `super_admin`, `analyst`, `policymaker` and
   `disaster_coordinator`.
4. Several Event Functions are disabled/no-op scaffolds, and all declared Signal
   rules/crons are inactive.
5. The production frontend contains an intentionally invalid API URL placeholder.
6. AWS ECR/S3/IAM/adapter/SageMaker configuration still contains placeholders;
   real TabFM CUDA and TimesFM execution are not proven.
7. Current test/lint gates are not clean. The Catalyst pipeline's lint, security
   scan, working directories, smoke path and rollback behavior are not release-grade.
8. The acceptance runner can return success with mandatory HELD/MANUAL checks.
9. `infra/catalyst/ds-schema/disaster-tables.schema.json` or an equivalent
   repeatable provisioner is missing.
10. Prompt 18 release reports, checklists, runbooks, architecture evidence and
    post-hackathon backlog do not exist.

### P1 organizer-alignment gaps

1. The Ask experience exists, but its semantic LLM path is optional, the fallback
   is deterministic/keyword-oriented, the current suite has a failure, and live
   QuickML serving is not proven.
2. Browser Web Speech input/output exists but Catalyst Zia voice/translation is
   not integrated or verified. Browser speech may be a labelled fallback, not an
   unqualified substitute when Catalyst supplies the matching capability.
3. Ask responses show grounded rows but do not yet select/render the requested
   maps/charts/timelines/networks from a typed visualization contract.
4. Supervisor Home explicitly awaits the station/officer-performance API.
5. Cryptocurrency, dark-web and national/international/cross-border scenario
   coverage is not explicit in the data taxonomy/validation.
6. Existing case summary, similar-case, graph and leads capabilities are fragmented;
   one cited case-scoped investigation-assistant journey is still needed.
7. Live dashboard/event freshness is mostly local polling or disabled scaffolding,
   not a deployed new-FIR-to-updated-view proof.
8. No browser E2E or load-test harness proves the integrated product.

### Documentation/configuration drift

- `README.md` and parts of `db.py` still describe Supabase-first setup.
- `prompt2.md` status/instruction text does not fully match completed local work.
- Phase reports include stale Docker assumptions and mojibake.
- screenshots described in reports are not retained as an auditable submission set.
- single-process replay/ID behavior is not safe for two AppSail instances; either
  implement a shared allocator/replay store or pin the hackathon service to one
  instance and document the limitation.

---

## 4. Global execution contract for every Prompt 18-26 session

Paste this block before the selected phase prompt.

~~~text
You are completing the DRISHTI synthetic Karnataka Police hackathon project in:
C:\Users\Prajwal\Desktop\DRISHTI

Read completely before editing:
1. prompt3new.md (this file);
2. prompt2.md, especially Prompts 14-18 and its completeness audit;
3. docs/phase-reports/PHASE_14_REPORT.md through PHASE_17_REPORT.md;
4. C:\Users\Prajwal\.codex\attachments\df6a4c30-f597-41b5-be10-4ba957cc0ebd\pasted-text.txt;
5. README.md and relevant infra/catalyst and infra/aws documentation;
6. the current git diff/status. Existing uncommitted files belong to the user.

Execution rules:
- Continue from existing implementation. Do not regenerate or replace working
  modules merely to satisfy a prompt heading.
- Inspect before editing. Preserve unrelated user changes and never discard a dirty
  worktree.
- Use the existing Zoho Catalyst project DHRISTI, project ID 48361000000030003,
  organization 60075362708, India DC. Never create a duplicate project or AppSail
  application when the intended component already exists.
- Deployment via Zoho Catalyst is mandatory. For a capability included in the
  submission, use the organizer-designated Catalyst service when it is available.
  Mark a service Not Used or Unavailable with evidence instead of creating fake usage.
- Keep AWS only for the retained historical/analytics corpus and justified custom
  ML/GPU/geospatial workloads. The browser never accesses AWS or a database directly.
- Catalyst Data Store is the deployed operational relational serving source;
  Catalyst Stratus is the deployed application object store. AWS RDS analytics are
  accessed only through the protected server-to-server adapter.
- Keep PostgreSQL RLS/FORCE RLS disabled for this synthetic hackathon as explicitly
  requested. This does not disable Catalyst Authentication, API Gateway checks,
  server-side role/scope authorization, audit or data minimization.
- Voice questions in Kannada/English are in scope. OCR, document parsing, automatic
  extraction from FIR/evidence files, face/object recognition and evidence-media
  transcription remain out of scope. Never conflate voice query transcription with
  evidence extraction.
- Use only clearly marked synthetic records/files. Do not expose secrets, .env
  values, credentials, raw evidence or unrestricted narratives in logs/prompts.
- Do not invent a passing cloud test. Local fakes, descriptors, screenshots of
  configuration and a real deployed invocation are separate evidence categories.
- Mandatory final acceptance cannot contain HELD, SCAFFOLDED, MANUAL, UNKNOWN or
  skipped statuses. An optional disabled capability may be N/A only when hidden from
  the submitted demo and recorded honestly.
- Run targeted tests after each change and full affected suites before completion.
  Do not suppress, xfail or weaken a legitimate failing test to make a phase green.
- The agent performs CLI/SDK/API work, reads logs, fixes failures and retries. Pause
  only for unavoidable interactive Zoho/AWS browser authentication or a console-only
  consent; after the user completes it, resume all routine work automatically.
- Inspect actual cloud resources before creating anything, cap costs, avoid duplicate
  schedules/services, and tear down temporary GPU resources after proof.
- Call the result only HACKATHON-DEMO READY, never production-ready.

For the selected phase:
1. create/update its report under docs/phase-reports/;
2. include commands, current results, resource IDs/URLs without secrets, failures and
   remediation;
3. leave the phase Pending if any Definition of Done item is unverified;
4. update prompt3new.md's status table only after every mandatory gate passes.
~~~

---

## 4A. Kiro agent and reusable-skill execution contract for Prompts 19-26

This contract supplements the Global Execution Contract. Prompt 18 performs the
one-time truth reconciliation. Beginning with Prompt 19, do not reload every historical
document into every session. Use the compact execution state and retrieve historical
material only when a selected requirement or contradiction requires it.

### Installed specialist agents

- `drishti-orchestrator`: owns phase boundaries, path ownership, integration and handoff;
- `repository-auditor`: read-only route/config/dependency and drift inventory;
- `backend-engineer`: backend, repository, contract and server-side authorization work;
- `frontend-engineer`: React experience, accessibility and browser-journey work;
- `test-investigator`: read-only failure clustering and smallest-correct-fix advice;
- `security-auditor`: read-only auth, scope, secret, dependency and abuse review;
- `catalyst-operator`: the only agent allowed to mutate the existing Catalyst project;
- `aws-ml-operator`: the only agent allowed to mutate the existing AWS ML plane;
- `evidence-auditor`: fresh, read-only Prompt 26 completeness auditor.

Agent definitions and permissions are authoritative under `.kiro/agents/`. A delegated
agent may write only its explicitly assigned paths. Shared contracts, schemas, lockfiles,
generated clients and execution-state files have exactly one writer at a time. Cloud
operators run sequentially; all other parallel work must be read-only or path-disjoint.

### Installed reusable skills

- `/phase-runner`: dependency preflight, phase state, artifacts and handoff;
- `/test-triage`: bounded commands, redacted logs and failure classification;
- `/auth-matrix`: explicit role/scope/resource/action allow-deny verification;
- `/catalyst-deployment`: existing-project preflight, ordered deployment and proof;
- `/aws-ml-proof`: read-only inventory, model identity, invocation and teardown proof;
- `/evidence-capture`: redacted, hash-verified evidence manifest entries;
- `/release-audit`: strict independent release classification and artifact-integrity gate.

Skill instructions under `.kiro/skills/` are executable policy, not optional suggestions.
Never turn a failing or blocked skill result into narrative success.

### Mandatory phase lifecycle

1. Start with `/phase-runner` preflight. Read `EXECUTION_STATE.json`,
   `docs/execution/FILE_MAP.json`, `docs/execution/DECISIONS.md`,
   `docs/execution/NEXT_SESSION.md`, `docs/execution/RELEASE_REQUIREMENTS.json`, only the
   selected prompt, and `git status --short`. Prompt 18 populates stable Prompt 19-26
   requirement IDs; later phases update dispositions, never delete missing coverage.
2. Have the orchestrator freeze interfaces and assign non-overlapping path ownership.
3. Run bounded read-only audits in parallel where useful. Each specialist returns only
   findings, artifact paths, blocking risks and recommended next actions.
4. Implement contract-first in dependency order. Do not let frontend and backend agents
   independently redefine the same API, event, role or data schema.
5. Use `/test-triage` for targeted tests after each change and affected full suites at
   the phase gate. Fix root causes; do not weaken legitimate tests.
6. Use `/auth-matrix` for every authorization-bearing phase. Include negative
   cross-scope direct-API cases, not just UI visibility checks.
7. Record each material build, test, security, deployment and live claim through
   `/evidence-capture`. Live PASS requires a stable resource ID and real invocation proof.
8. Complete the phase report and run `/phase-runner` handoff. Mark Complete only when
   every mandatory Definition of Done item passes; otherwise keep it Pending/In Progress
   with one exact next action.

This setup improves continuity and reduces repeated context, but it does not enlarge the
selected model's context window or bypass Kiro/tool approval and security policy.

---

## 5. Remaining phase status

| Prompt | Phase | Status |
|---:|---|---|
| 18 | Truth reconciliation, scope freeze and baseline repair | **Complete (2026-07-20)** — see `docs/phase-reports/PHASE_18_REPORT.md` |
| 19 | Bilingual semantic conversational intelligence, voice and answer visualizations | **Complete (2026-07-21)** — see `docs/phase-reports/PHASE_19_REPORT.md` |
| 20 | Organizer domain, hierarchy, supervisor and investigation-flow closure | **Complete (2026-07-21)** — see `docs/phase-reports/PHASE_20_REPORT.md` |
| 21 | Catalyst operational data boundary and deployment correctness | **Complete (2026-07-21)** — see `docs/phase-reports/PHASE_21_REPORT.md` |
| 22 | Local release stabilization and functional CI/CD | **Complete (2026-07-21)** — see `docs/phase-reports/PHASE_22_REPORT.md` |
| 23 | Live Zoho Catalyst provisioning and deployment | **Live — core DoD proven (2026-07-23)** — see `docs/phase-reports/PHASE_23_REPORT.md`. Public frontend (Slate `drishti-uryfmaue.onslate.in`) + primary API (AppSail via API Gateway) resolve to Catalyst; Auth→Gateway→AppSail→Data Store/Stratus proven (security 11/11, exact-origin CORS, readiness all-ok); six-role allow/deny matrix; **live Signal** (`prediction-requested`→`prediction_event`, `approved→queued`, retry + idempotency) and **live daily cron** (`drishti_forecast`→`cron_forecast`); **application rollback** + additive forward recovery; Stratus evidence object (versioned, sha256 MATCH, signed-URL expiry); chat session + RDS case reads. **Board/Disaster/evidence-upload now fixed + live** (report §3.8-3.10): Board CRUD; all 12 Disaster reads + overview + a forecast write (15 Data Store tables created via the reverse-engineered Console create-table API + fixture seeded); evidence file-upload→Stratus with SHA-256 verify. Data Store fixes: ZCQL≤300 pagination, datetime format, dict/list↔json round-trip. Residual non-core (report §9): pipeline Git-link+run (F1), credit snapshot (G1), delete 2 stale Slate apps (G2), the interactive Catalyst IAM login to finish the fully-automated browser E2E (E1), FIR happy-path approval, and deploying the login-UI polish (one Slate "Create Deployment"). |
| 24 | Live AWS custom-ML plane and Catalyst-to-AWS prediction proof | Pending |
| 25 | Integrated security, scale, recovery and final hackathon release | Pending |
| 26 | Independent implementation completeness audit and submission package | Pending |

Do not skip forward because a later phase looks easier. Prompt 23 cannot produce a
working deployment until Prompt 21 closes the data/auth boundary, and Prompt 25
cannot pass until Prompts 23-24 have real cloud evidence.

---

# Prompt 18 - Truth reconciliation, scope freeze and baseline repair

Objective: establish one evidence-backed current state, remove contradictions and
repair the minimum baseline so later cloud work is not built on false assumptions.

~~~text
Implement Prompt 18 using the Global Execution Contract.

A. Preserve and inventory
1. Capture `git status --short`, changed/untracked files, active branch and relevant
   tool versions. Do not revert existing changes.
2. Inventory every React destination, FastAPI router, Catalyst Function, Data Store
   table/config, Stratus bucket, Signal rule, cron, QuickML/Zia feature, AWS adapter
   and model worker.
3. Generate `docs/deployment/CURRENT_STATE_MATRIX.md` with columns:
   capability, UI route, API route, current repository, target repository/service,
   local-test status, live-cloud status, mandatory/optional/deferred, blocker and
   owning future prompt.
4. Distinguish Implemented Locally, Deployed, Live Verified, Disabled Optional,
   External Access Required and Post-Hackathon. Never collapse them into Complete.

B. Freeze the hackathon scope
1. Record the mandatory demo set:
   - Catalyst-hosted frontend/API/auth/data/object storage;
   - approved FIR and structured case intake;
   - evidence upload with manual metadata and no content extraction;
   - bilingual conversational query with follow-up and visualization;
   - case/similar-case/graph/board/map/forecast paths;
   - supervisor workload view;
   - Disaster Response replay/forecast/approval/routing path;
   - one real TabFM GPU path and one real TimesFM path;
   - final reports, recovery and cost teardown.
2. Mark optional services/features hidden and disabled unless they are actually
   demonstrated. Do not enable every Catalyst service merely to fill a checklist.
3. Keep TimeGPT, Chronos, LSTM, automatic model retraining, production RLS, OCR,
   evidence transcription, full OSINT/dark-web scraping and official agency feeds
   out of the mandatory build.
4. Write `docs/deployment/HACKATHON_SCOPE.md` with the organizer-note mapping and
   explicit exclusions.

C. Repair status and documentation truth
1. Reconcile prompt2.md, phase reports and actual code/cloud state. Do not erase
   historical evidence. Add a clear note that Prompts 14, 16 and 17 are locally
   implemented but cloud acceptance is continued here.
2. Correct stale Prompt references, including the workflow dependency that should
   refer to Prompts 16-17 after reordering.
3. Update the recommended starting instruction to Prompt 18 in prompt3new.md.
4. Correct stale claims that Docker is absent: verify both the CLI and Linux daemon.
5. Replace Supabase-first current setup language in README.md/db.py with the true
   AWS-RDS plus Catalyst-serving architecture. Preserve historical migration notes
   in an explicitly labelled legacy section.
6. Normalize changed Markdown files to UTF-8 and repair visible mojibake without
   rewriting unrelated content.

D. Baseline failures
1. Rerun the full backend suite and produce a failure ledger. At minimum investigate:
   - the NL-to-SQL policymaker aggregate/clarification failure;
   - Investigation Board Search Around returning more nodes than its cap;
   - socioeconomic, hidden-association, financial and risk tests that depend on
     missing/stale derived data.
2. Repair code defects. For data-state failures, add a deterministic non-destructive
   derived-data load/refresh command and fixture validation; do not weaken assertions.
3. Rerun frontend typecheck, unit tests and production build.
4. Run JSON/YAML parsing and Node syntax checks for Catalyst infrastructure.
5. Record every remaining failure as owned by a later prompt; no unexplained failure
   may remain.

E. Truthful acceptance behavior
1. Modify the acceptance runner to support an explicit strict release mode.
2. In strict mode, any mandatory HELD, MANUAL, UNKNOWN, skipped or unconfigured
   check must make the command non-zero.
3. Offline mode may report INCOMPLETE, but must not print release success.
4. Configuration declarations cannot prove a live Signal, cron, Data Store write,
   authentication flow or GPU invocation.

F. Report
Create `docs/phase-reports/PHASE_18_REPORT.md` containing:
- current-state matrix summary and scope decisions;
- exact test results and failure remediation;
- documentation/status corrections;
- strict acceptance behavior proof;
- remaining Prompt 19-26 dependencies.
~~~

Definition of Done:

- One current-state matrix covers every submitted route/capability.
- Mandatory, optional, deferred and post-hackathon scope are unambiguous.
- No status claims local fakes are live cloud services.
- Every baseline failure is fixed or explicitly assigned to a later cloud-only gate.
- Strict acceptance cannot pass with mandatory HELD/MANUAL/SKIP states.
- README/setup documents match AWS RDS plus Catalyst serving architecture.

---

# Prompt 19 - Bilingual semantic conversational intelligence, voice and visual answers

Objective: complete the organizer's central experience: an officer asks a Kannada
or English text/voice question, follows up naturally, receives a permission-scoped,
grounded answer and sees an appropriate visualization without writing SQL.

~~~text
Implement Prompt 19 using the Global Execution Contract. Extend the existing Ask
DRISHTI implementation; do not replace its guard, citations, history or UI.

Agent/skill routing for this phase:
- Use `drishti-orchestrator` as the sole coordinator and contract owner.
- Delegate read-only baseline work to `repository-auditor`, `test-investigator` and
  `security-auditor`; use `catalyst-operator` only for read-only QuickML/Zia capability
  checks. No cloud mutation is authorized by Prompt 19.
- Assign backend semantic/guard work to `backend-engineer` and voice/visual/browser work
  to `frontend-engineer` only after the planner, answer and citation contracts are frozen.
- Invoke `/phase-runner`, `/auth-matrix`, `/test-triage` and `/evidence-capture`.
- Keep model transcripts bounded and data-minimized; artifacts hold details, chat holds
  only conclusions and paths.

A. Correct the scope contradiction
1. Update documentation/configuration so Kannada/English question dictation and
   answer speech are in hackathon scope.
2. Keep OCR, uploaded-document extraction, evidence-media transcription, face/object
   recognition and automatic FIR field extraction disabled.
3. Name feature flags separately, for example QUERY_VOICE_ENABLED versus
   EVIDENCE_EXTRACTION_ENABLED. The former may be true; the latter remains false.

B. Semantic planner
1. Preserve deterministic parsing only as a transparent outage fallback.
2. Make Catalyst QuickML LLM Serving the primary semantic planner when available
   for the project/India DC. Verify availability using current official docs and
   actual project capability; record model/deployment identifiers without secrets.
3. If QuickML LLM Serving is not available, use a small governed open-source model
   through an existing Catalyst-supported custom runtime or the justified protected
   AWS adapter. Document the exact Catalyst gap. Do not silently use an external
   commercial API for a Catalyst-listed capability.
4. Remove `gpt-4o-mini` as an implied production default. Use provider-neutral
   settings and fail closed when the semantic provider is unavailable.
5. Send the planner only the allow-listed schema/glossary, bounded conversation
   context and data-minimized question. Never send raw evidence bytes, unrestricted
   narratives, database credentials or result sets containing unauthorized fields.

C. Safe NL-to-query execution
1. Retain SELECT-only parsing, single-statement enforcement, table/column allowlists,
   statement timeout, row cap and dangerous-function/comment rejection.
2. Enforce role plus server-trusted organizational scope before execution. A model
   cannot relax scope through generated SQL.
3. Prefer a typed query plan/filters compiled server-side. If SQL is returned by the
   model, validate its AST and inject mandatory scope using trusted code.
4. Aggregate-only users must receive aggregate queries, not case/person rows.
5. Ambiguous time, place, crime or subject requests must ask a clarifying question.
6. Persist session turns, model/version, executed plan/SQL hash, citations, confidence,
   refusal and latency without storing unnecessary sensitive content.

D. Kannada/English and conversational memory
1. Support English, Kannada script and common transliterated Kannada query forms.
2. Retain only the bounded prior turns needed to resolve follow-ups.
3. Test pronouns, ellipsis, correction and narrowing, for example:
   - "Show robberies near Mysuru" -> "Only last month" -> "Show repeat offenders";
   - "Show vehicle thefts in Bengaluru South during the last 30 days";
   - Kannada equivalents reviewed for meaning, not literal word substitution.
4. Never carry a case/person scope from one user/session into another.

E. Voice and translation
1. Use Catalyst Zia voice/speech/translation services for the submitted voice
   capability when available. Add a server-side adapter and never expose a service
   credential in React.
2. Store transcript, language, confidence, provider/version and low-confidence state.
3. Require the user to confirm or edit low-confidence transcripts before executing.
4. Use Zia text-to-speech/translation when included and supported. Browser Web Speech
   and SpeechSynthesis may remain a labelled, feature-detected fallback only.
5. If Zia voice is unavailable in the project/DC, retain fully working bilingual
   text, hide unsupported claims, capture availability evidence and mark voice as an
   explicit platform limitation. Do not label browser recognition as Zia.

F. Typed answer-visualization contract
1. Extend the Ask response with a server-validated visualization specification:
   `kind`, title, dimensions, measures, units, time/geography fields, rows/reference,
   source IDs, cutoff/freshness, suppressed cells and accessible-table fallback.
2. Allow only approved kinds: table, number, bar, line/trend, choropleth/heatmap,
   timeline, network and Sankey/link-to-existing-view.
3. Select the visualization deterministically from result shape and user intent;
   never execute model-generated JavaScript, Vega code or arbitrary HTML.
4. Reuse existing chart/map/network/timeline/Sankey components and shared formatting.
5. Every visualization exposes citations, filters, as-of timestamp, scope, confidence
   where applicable and an accessible data table.
6. Large results remain server-paginated/aggregated; never send the complete database
   to the browser.

G. Evaluation and browser tests
1. Create a versioned golden evaluation set with at least:
   - 20 English questions;
   - 20 Kannada questions including transliterated forms;
   - 10 multi-turn follow-up chains;
   - role/scope denial cases;
   - ambiguity/clarification cases;
   - prompt-injection/SQL-injection/unsupported-data cases;
   - each required visualization kind.
2. Measure intent/plan correctness, execution correctness, citation validity,
   language correctness, refusal correctness and p50/p95 latency.
3. Add frontend tests for text, language switching, low-confidence voice confirmation,
   visual rendering, accessible table fallback, citations and provider-unavailable
   behavior.
4. Add browser E2E using a deterministic local provider, then retain a live-provider
   test for Prompt 23.

H. Report
Create `docs/phase-reports/PHASE_19_REPORT.md` with provider placement, capability
evidence, test/evaluation metrics, supported languages, visual types, known
limitations and exact Prompt 23 live-verification steps.
~~~

Definition of Done:

- A bilingual multi-turn query produces an authorized grounded answer with citations.
- At least one trend and one map/heatmap question render typed visual answers.
- Aggregate-only users cannot retrieve case/person detail.
- Voice uses Zia when available or is truthfully disabled with bilingual text intact.
- Low-confidence dictation never executes silently.
- Evidence/OCR extraction remains off.
- The semantic planner is primary in the live-ready contract; fallback is labelled.

---

# Prompt 20 - Organizer domain, hierarchy, supervisor and investigation-flow closure

Objective: close the remaining organizer-note feature gaps by composing existing
capabilities and adding only the missing domain/scope/performance pieces.

~~~text
Implement Prompt 20 using the Global Execution Contract.

IMPORTANT : MAKE SURE THE SUPERADMIN SHOULD CREATE CREDENTIALS TO THE ROLES AND THEN ALSO ASSIGN THE ROLES REQUIRED TO THE CREATED ROLES. 

Agent/skill routing for this phase:
- Use `drishti-orchestrator` to freeze taxonomy, hierarchy, aggregate and update contracts.
- Use `repository-auditor` for the existing domain/route inventory and
  `security-auditor` for hierarchy, role and cross-scope risks.
- Assign disjoint backend and frontend paths to `backend-engineer` and
  `frontend-engineer`; use `test-investigator` after targeted and full gates.
- Invoke `/phase-runner`, `/auth-matrix`, `/test-triage` and `/evidence-capture`.
- Cloud operators remain read-only; Prompt 20 does not authorize provisioning.

Current CLI authentication baseline (captured 21 July 2026):
~~~powershell
PS C:\Users\Prajwal\Desktop\DRISHTI> catalyst login --dc in
# Observed result: already logged in to the India DC.

PS C:\Users\Prajwal\Desktop\DRISHTI\services\ml> aws sso login --profile drishti
# Observed result: AWS SSO login completed successfully for profile drishti.
~~~
Reuse these authenticated sessions. Do not open another browser login or pause for the
user merely because a new prompt/session started. Re-authenticate only after a real CLI
command returns an authentication/expiry error. When AWS access is authorized for the
selected phase, verify it read-only with `aws sts get-caller-identity --profile drishti`.
Never save or repeat the email address, SSO start URL, one-time device code, tokens or
credentials in prompts, logs, reports or evidence. Prompt 20 still authorizes no cloud
mutation.

A. Synthetic domain coverage
1. Extend the crime taxonomy/scenario registry with clearly synthetic, legally safe
   scenarios for:
   - cryptocurrency-enabled fraud/extortion/money movement;
   - dark-web-enabled contraband/fraud as a manually classified source, with no live
     scraping, purchase, credential use or illegal-content collection;
   - inter-district and inter-state activity;
   - national/international/cross-border relationships and jurisdiction referrals.
2. Model jurisdiction scope separately from crime type. Suggested governed values:
   local, inter_district, inter_state, national, international, cross_border.
3. Connect persons, accounts/wallet references, devices, phones, vehicles, locations,
   cases and source records only through evidence-backed or explicitly hypothetical
   typed edges.
4. Add deterministic golden fixtures, validation and NL-query examples. Do not rerun
   the entire 100k dataset unless required; additive scenario fixtures are preferred.

B. Rank and organizational scope mapping
1. Keep the existing functional roles but add a documented mapping from police rank/
   assignment to role and scope, including DGP, IGP, DIG, SP, station chief/SHO and
   investigating officer.
2. Derive state/range/district/subdivision/station/assigned-case scope server-side
   from Catalyst identity plus trusted assignment records. Never trust a browser
   district header as authorization evidence.
3. Add allow/deny matrix tests covering case detail, aggregate dashboards, exports,
   Investigation Board and Disaster approvals.
4. Keep the demo mapping synthetic and label real directory/SSO synchronization as
   post-hackathon.

C. Supervisor station/officer performance
1. Replace the explicit "Awaiting the performance API" state.
2. Add aggregate, explainable metrics such as active workload, new cases, ageing,
   chargesheet throughput, disposal time, overdue reviews and workload balance.
3. Avoid simplistic punitive ranking. Show denominators, time window, data freshness,
   missing-data state and limitations.
4. Scope station chiefs to their station, SP/supervisor roles to assigned units and
   higher ranks to authorized aggregates.
5. Add backend, frontend and role tests plus empty/stale/error states.

D. Case-scoped investigation assistant
1. Build a thin orchestration surface using existing case summary, similar-case,
   modus-operandi, canonical identity, graph/path, leads, timeline and Board APIs.
2. For an authorized selected case, answer questions such as "Have similar cases
   happened before?" with related FIRs, why-similar features, reviewed identity links,
   possible leads and source-linked investigation notes.
3. Separate facts/evidence from suggestions/hypotheses visually and structurally.
4. Never claim two people are the same based only on embedding similarity.
5. Allow selected, cited objects to be sent to the Investigation Board.
6. Reuse Prompt 19's bilingual planner and answer contract; do not introduce a second
   ungoverned chatbot.

E. Live Command Center contract
1. Define the committed new-FIR event flow: approved canonical write -> projection/
   feature invalidation -> eligible analytics -> alert/dashboard refresh.
2. Make duplicate events idempotent and expose source timestamp, processed timestamp,
   freshness and last-success/failure state.
3. Use polling locally if required, but integrate through the single Catalyst Signal
   and/or scoped update channel during Prompt 23.
4. Demonstrate that a new approved FIR changes the appropriate district statistic,
   supervisor workload and eligible hotspot/near-repeat state without rescoring a
   person or auto-dispatching staff.

F. Forecast horizons
1. Audit every UI/API claim for tomorrow, next week and next month.
2. If the demo claims a one-day forecast, implement a transparent day-ahead aggregate
   baseline/near-repeat path with held-out evaluation and confidence.
3. Otherwise present only validated horizons, such as 7-day and 30-day, and list
   day-ahead forecasting as future work. Never advertise an untested horizon.

G. Visual coverage proof
1. Verify one real data-backed route for map, heatmap, timeline, network, trend and
   Sankey visualizations.
2. Add accessibility/table fallback, loading, empty, stale and error tests.
3. Do not rebuild visuals that already pass; fix integration gaps only.

H. Report
Create `docs/phase-reports/PHASE_20_REPORT.md` containing scenario counts, scope
matrix, supervisor metric definitions, investigation-assistant evidence, freshness
flow, horizon decisions and visualization coverage.
~~~

Definition of Done:

- Crypto/dark-web and cross-jurisdiction synthetic scenarios validate and are searchable.
- Police hierarchy assignments map to server-enforced functional scopes.
- Supervisor Home has real station/officer metrics with no placeholder.
- One case-scoped bilingual investigation-assistant journey is cited and permission-safe.
- A committed FIR updates the appropriate demo aggregates idempotently.
- Every advertised visualization and forecast horizon is backed by a working test.

---

# Prompt 21 - Catalyst operational data boundary and deployment correctness

Objective: make the deployed architecture internally true before provisioning it:
AppSail must work without direct PostgreSQL credentials, operational CRUD must use
Catalyst services, and justified AWS analytics must cross only the protected adapter.

~~~text
Implement Prompt 21 using the Global Execution Contract.

Agent/skill routing for this phase:
- Use `drishti-orchestrator` as sole route-classification and shared-contract owner.
- Run `repository-auditor` and `security-auditor` read-only first; their inventories are
  phase inputs, not competing edits.
- Assign repositories, adapters, route guards and contract tests to `backend-engineer`.
  Assign only contract-dependent UI changes to `frontend-engineer` after interfaces freeze.
- `catalyst-operator` may inspect existing service shapes but must not provision or deploy.
- Invoke `/phase-runner`, `/auth-matrix`, `/test-triage`, `/catalyst-deployment` in
  preflight-only mode, and `/evidence-capture`.

Current CLI authentication baseline (captured 21 July 2026):
~~~powershell
PS C:\Users\Prajwal\Desktop\DRISHTI> catalyst login --dc in
# Observed result: already logged in to the India DC.

PS C:\Users\Prajwal\Desktop\DRISHTI\services\ml> aws sso login --profile drishti
# Observed result: AWS SSO login completed successfully for profile drishti.
~~~
Reuse these authenticated sessions. Do not open another browser login or pause for the
user merely because a new prompt/session started. Re-authenticate only after a real CLI
command returns an authentication/expiry error. When AWS access is authorized for the
selected phase, verify it read-only with `aws sts get-caller-identity --profile drishti`.
Never save or repeat the email address, SSO start URL, one-time device code, tokens or
credentials in prompts, logs, reports or evidence. Prompt 21 permits Catalyst inspection
only and authorizes no provisioning or deployment.

A. Route-to-data-boundary inventory
1. Generate a machine-checkable inventory of every FastAPI route and every module
   using `db.ro_conn`, `db.rw_conn`, psycopg or `DATABASE_URL`.
2. Classify each deployed route as exactly one of:
   - CATALYST_OPERATIONAL: Data Store/Stratus repository;
   - AWS_ANALYTICS: protected server-to-server adapter with a typed read/job API;
   - DISABLED_OUT_OF_SCOPE: hidden from the submitted UI and returning an honest
     disabled response;
   - LOCAL_TOOLING_ONLY: batch/admin tooling not present in AppSail.
3. Write/update `docs/deployment/ROUTE_DATA_BOUNDARY.md`. No demo-visible route may
   be unclassified.

B. Operational repository closure
1. Convert every demo-used CRUD/read path for FIR/intake, case detail, people/entity,
   evidence metadata, statements/property/court/lifecycle, imports, chat/session,
   notifications/reports, Board and Disaster Response to explicit repository
   interfaces backed by Catalyst Data Store/Stratus.
2. Reuse existing mappings/import configs and repository abstractions. Do not create
   a second schema with different identifiers.
3. Ensure Data Store ExternalID/version/idempotency fields preserve traceability to
   the retained AWS source/history.
4. Store application evidence/report/import objects in private Stratus. AWS S3 may
   hold analytics/model artifacts, not the submitted application's primary files.
5. Make all demo routes pass with `DATABASE_URL` absent. Add a startup/CI test that
   fails if an AppSail operational route imports or opens the PostgreSQL connector.

C. AWS analytics boundary
1. Move graph-heavy, geospatial, derived historical, bulk benchmark and model tasks
   that genuinely require AWS RDS/PostGIS behind the existing protected adapter.
2. Define narrow typed operations rather than a generic SQL proxy. Enforce server
   identity, request signing, role/scope, timeout, row/byte caps and audit.
3. Board Search Around/reference hydration either uses a curated Data Store projection
   or this protected adapter; it must not connect directly from AppSail to RDS.
4. Return data-minimized aggregate/authorized objects only. Never expose AWS URLs or
   credentials to React.

D. Repeatable Data Store schema
1. Generate and validate `infra/catalyst/ds-schema/disaster-tables.schema.json` plus
   an idempotent provisioner mirroring the Board pattern.
2. Verify every mandatory table/index/search field required by Prompts 2-20.
3. Produce a dependency-ordered provisioning/import manifest and bounded demo subset.
4. Empty optional source tables are allowed only with explicit empty-state behavior;
   mandatory golden journey tables must have deterministic rows.

E. Catalyst identity and authorization
1. Fix the Function/Gateway role mapper to emit the exact backend roles:
   investigator, analyst, supervisor, policymaker, disaster_coordinator and
   super_admin.
2. Resolve organizational assignment server-side from trusted Data Store records or
   Catalyst custom attributes. Reject unknown/ambiguous role or scope.
3. Sign and verify role, actor, assignment/scope, audience, expiry, nonce and request
   correlation. Never trust browser-provided role/district headers in deployed mode.
4. Run an allow/deny matrix for every role against cases, exports, admin, Board and
   Disaster actions.

F. Functions/events/jobs
1. Replace no-op/disabled Function bodies required by the mandatory demo with real,
   idempotent adapters. Keep unused functions undeployed or explicitly disabled.
2. Implement exactly one mandatory `prediction.requested` Signal/Event Function and
   one scheduled forecast job. They remain disabled until Prompt 23 deploys them.
3. Persist authoritative Data Store state before emitting any Signal.
4. Add retry, bounded timeout, terminal failed state and replay/repair procedure.
5. A configuration file marked active is not test evidence; add executable local
   contract tests.

G. Instance correctness and readiness
1. For hackathon simplicity, either:
   - implement shared nonce replay and ID allocation using Catalyst Cache/Data Store;
     or
   - pin AppSail to exactly one instance, prove the setting and place multi-instance
     behavior in the backlog.
2. Readiness must fail when mandatory Data Store/repository/auth dependencies are
   unavailable. Liveness must remain a shallow process check.
3. Direct AppSail application routes must not bypass Gateway authorization. If a
   health endpoint is direct, keep it non-sensitive and rate-limited.

H. Tests and report
1. Run every mandatory API journey with `DATABASE_URL` removed.
2. Add a static deployment-boundary check that rejects direct DB use from
   CATALYST_OPERATIONAL modules.
3. Test role mapping, scope spoofing, adapter signing, timeouts, idempotency, readiness
   failure and one-instance/shared-state behavior.
4. Create `docs/phase-reports/PHASE_21_REPORT.md` with route counts by class,
   migrated repositories, remaining local/disabled routes, schema counts and tests.
~~~

Definition of Done:

- Every submitted UI route has a deployable data path with no architecture ambiguity.
- AppSail's mandatory journeys work without `DATABASE_URL`.
- Data Store/Stratus own operational records/objects; AWS RDS is adapter-only analytics.
- All six product roles and trusted organizational scopes work through Gateway.
- Mandatory Functions have real logic and repeatable tests.
- Disaster tables have a versioned, idempotent Catalyst provisioner.
- Readiness cannot pass for a broken operational data plane.

---

# Prompt 22 - Local release stabilization and functional Catalyst CI/CD

Objective: produce a reproducible local release candidate and a pipeline that
actually blocks deployment on failures before spending cloud credits.

~~~text
Implement Prompt 22 using the Global Execution Contract.

Agent/skill routing for this phase:
- Use `drishti-orchestrator` to own the release command, generated contracts and gate order.
- Use `test-investigator` for failure clustering, `repository-auditor` for CI/config drift,
  and `security-auditor` for image, dependency, secret and browser-release checks.
- Route fixes to `backend-engineer` or `frontend-engineer` with non-overlapping ownership.
- Invoke `/phase-runner`, `/test-triage`, `/auth-matrix` and `/evidence-capture`.
- Catalyst/AWS agents may perform read-only validation only; live proof belongs to 23/24.

Current CLI authentication baseline (captured 21 July 2026):
~~~powershell
PS C:\Users\Prajwal\Desktop\DRISHTI> catalyst login --dc in
# Observed result: already logged in to the India DC.

PS C:\Users\Prajwal\Desktop\DRISHTI\services\ml> aws sso login --profile drishti
# Observed result: AWS SSO login completed successfully for profile drishti.
~~~
Reuse these authenticated sessions. Do not open another browser login or pause for the
user merely because a new prompt/session started. Re-authenticate only after a real CLI
command returns an authentication/expiry error. When AWS access is authorized for the
selected phase, verify it read-only with `aws sts get-caller-identity --profile drishti`.
Never save or repeat the email address, SSO start URL, one-time device code, tokens or
credentials in prompts, logs, reports or evidence. Prompt 22 authorizes read-only cloud
validation only.

A. Toolchain and deterministic builds
1. Verify Docker Desktop's Linux daemon; start it if installed but stopped.
2. Pin Node, npm, Python, Java/CLI and container runtime versions used by CI.
3. Restore/install ESLint with a compatible locked version and configuration. Do not
   remove lint from the pipeline because it currently fails.
4. Build the Linux AMD64 AppSail image and run it locally as a non-root user on the
   Catalyst port contract. Test liveness, dependency-aware readiness and shutdown.
5. Build the separate GPU-worker image only for static/unit/contract checks in this
   phase; real GPU proof belongs to Prompt 24.

B. Zero unexplained local failures
1. Run the complete backend suite against the deterministic synthetic development
   dataset and disposable fakes where appropriate.
2. Refresh/load required derived socioeconomic, hidden-association, money-alert and
   risk fixtures non-destructively. Record row counts and source versions.
3. Fix fan-out, NL-query and any newly exposed defects. Never label a pre-existing
   failure harmless if it affects a submitted screen.
4. Run frontend lint, typecheck, all unit/component tests and the full production
   build, including bundle-secret/API-placeholder checks.
5. A production build must fail if its API Gateway URL is unset/invalid; warning-only
   behavior is not acceptable for release mode.

C. Browser E2E harness
1. Add Playwright or an equivalent maintained browser E2E tool.
2. Create deterministic local E2E smoke journeys for login/role context, FIR intake,
   evidence metadata, Ask DRISHTI, case investigation, Board and Disaster Response.
3. Test loading, empty, error, stale, unauthorized and responsive states.
4. Include keyboard navigation, focus visibility, labels, table fallbacks and reduced
   motion. Do not require pixel-perfect visual snapshots for dynamic maps.
5. Parameterize the same suite to run against the live Catalyst URL in Prompt 23.

D. Real security/build gates
1. Replace echo-only secret scanning with an executable scanner plus explicit bundle
   inspection. Never print `.env` values.
2. Run dependency vulnerability/licence checks and make agreed high/critical findings
   blocking; document accepted exceptions with expiry/owner.
3. Run Python/TypeScript static checks, container scan and IaC/config validation.
4. Validate every JSON/YAML, Function syntax, Dockerfile and environment-key schema.
5. Fail on wildcard production CORS, embedded AWS/private URLs, direct browser DB
   clients, static credentials and production synthetic-marker omission.

E. Fix Catalyst Pipelines
1. Correct working directories and artifact paths: frontend build comes from `web`,
   Catalyst binding/config comes from `infra/catalyst`, and AppSail uses the intended
   image/source.
2. Implement the lean sequence:
   install -> lint/type/test -> build -> security scans -> deploy development ->
   Auth/Gateway/AppSail/Slate/Data Store/prediction smoke -> retain rollback version.
3. Do not use `|| true` for mandatory audits, deploy, smoke or rollback steps.
4. Smoke through Authentication and API Gateway, not only a direct AppSail URL.
5. Make environment/project verification, synthetic marker and no-duplicate checks
   mandatory before deploy.
6. Keep GPU-worker deployment separate and invoke only its immutable registered
   endpoint/config after Prompt 24.

F. Strict local release gate
Create one command/script that runs the complete local release gate and produces a
machine-readable summary. It must exit non-zero for any mandatory failure, skipped
gate, invalid production URL, missing artifact or unclassified route.

G. Report
Create `docs/phase-reports/PHASE_22_REPORT.md` with tool versions, build digests,
test counts, scan results, E2E matrix, pipeline corrections and remaining cloud-only
checks.
~~~

Definition of Done:

- Backend, frontend, lint, build and mandatory static/security checks are green.
- AppSail Linux AMD64 image runs locally without direct operational PostgreSQL.
- Browser E2E covers every mandatory local demo journey.
- Release build cannot contain an invalid API URL or secret.
- Catalyst Pipeline uses correct paths and cannot pass failed mandatory stages.
- The strict local release command returns zero only for a genuine candidate.

---

# Prompt 23 - Live Zoho Catalyst provisioning and deployment

Objective: deploy the real submission through the existing Zoho Catalyst project and
replace local Catalyst fakes with live services for every enabled capability.

~~~text
Implement Prompt 23 using the Global Execution Contract. This prompt authorizes
bounded deployment into the existing hackathon Catalyst project and use of its
credits. Inspect before creating resources and avoid duplicates.

Agent/skill routing for this phase:
- Use `drishti-orchestrator` for the deployment plan and evidence gate, but make
  `catalyst-operator` the only writer to Catalyst resources.
- Run `repository-auditor`, `security-auditor` and `test-investigator` read-only against
  the candidate before deployment. Route code corrections back to their owning agent;
  never patch application code concurrently with a deployment mutation.
- Invoke `/phase-runner`, `/catalyst-deployment`, `/auth-matrix`, `/test-triage` and
  `/evidence-capture`.
- Inventory before every create/update, target only project `48361000000030003`, org
  `60075362708`, India DC, and retain exact rollback state. Never create duplicates.

Current CLI authentication baseline (captured 21 July 2026):
~~~powershell
PS C:\Users\Prajwal\Desktop\DRISHTI> catalyst login --dc in
# Observed result: already logged in to the India DC.

PS C:\Users\Prajwal\Desktop\DRISHTI\services\ml> aws sso login --profile drishti
# Observed result: AWS SSO login completed successfully for profile drishti.
~~~
Reuse these authenticated sessions. Do not open another browser login or pause for the
user merely because a new prompt/session started. Re-authenticate only after a real CLI
command returns an authentication/expiry error. AWS identity verification is unnecessary
for Catalyst-only work unless this prompt reaches an explicitly documented AWS adapter
check. Never save or repeat the email address, SSO start URL, one-time device code,
tokens or credentials in prompts, logs, reports or evidence.

A. Authenticate and preflight
1. Use the Catalyst CLI. If login expires, open the Zoho browser login/consent page,
   pause for the user, then resume automatically.
2. Confirm project ID 48361000000030003, org 60075362708, India DC and Development
   environment before every mutation.
3. Record the current component/resource inventory, plan credit balance manually when
   necessary, quotas and rollback/export baseline. Do not record tokens.
4. Fail if the project/synthetic marker is wrong or a duplicate named service exists.

B. Provision operational services
1. Apply the versioned Data Store schema/provisioners in dependency order.
2. Import the bounded curated serving subset with idempotent upserts. Record source
   hashes, imported/rejected counts and reconciliation against AWS source exports.
3. Create/reuse private versioned Stratus buckets for evidence, imports and reports;
   copy at least one synthetic evidence fixture and verify hash/version/access expiry.
4. Configure only the bounded NoSQL/Cache uses required by enabled features. They
   must not duplicate authoritative Data Store records.
5. Configure Catalyst Authentication demo identities/roles/assignments and test all
   role mappings.

C. Deploy application components
1. Deploy the required Functions with real environment configuration and secrets in
   server-side facilities, not VITE variables.
2. Enable/configure API Gateway routes, throttling and authentication.
3. Deploy the tested AppSail immutable artifact/image and verify liveness/readiness.
4. Set the real Gateway URL in the frontend build, rebuild once, scan, then deploy
   the exact artifact to Slate/Web Client Hosting.
5. Verify no AWS service hosts the public frontend or primary API and no direct
   AppSail CRUD path bypasses Gateway.
6. Use the default Catalyst domain unless the user supplies an owned custom domain;
   custom domain is not a blocker.

D. Enable matching Catalyst capabilities
1. Enable exactly one working `prediction.requested` Signal/Event Function and one
   scheduled forecast job. Prove actual delivery/execution, retry and idempotency.
2. Enable QuickML semantic/RAG services required by Prompt 19 when available and run
   its fixed evaluation.
3. Enable Zia query voice/translation only if included and available; run a real
   Kannada/English voice test. OCR/evidence extraction stays disabled.
4. Enable SmartBrowz, Mail and Push only if they are visible demo capabilities; test
   a synthetic watermarked report and data-minimized notification. Otherwise hide
   them and mark Not Used, not fake-success.
5. Record Circuits/Zia AutoML availability; do not replace unavailable Catalyst
   services with third parties merely to tick a row.

E. Live service tests
1. Run the parameterized browser E2E suite against the Catalyst URL.
2. Prove Authentication -> Gateway -> Function/AppSail -> Data Store for an authorized
   read/write and prove denied roles/scopes fail.
3. Prove one FIR draft/approval, one evidence upload/manual metadata link, one chat
   query/session, one Board operation and one Disaster operation with live services.
4. Verify actual Data Store rows and Stratus object metadata, then confirm the browser
   has no direct database/AWS access.
5. Verify exact-origin CORS, rate limits, signed context, replay/expiry and direct-
   AppSail bypass protection.

F. Pipeline and rollback
1. Link/run the corrected Catalyst Pipeline for the development deployment.
2. Run post-deploy smokes through the public Catalyst endpoints.
3. Exercise application artifact rollback to the prior compatible version without
   destructively reversing Data Store schema.
4. Preserve import/export hashes and use additive forward recovery for serving data.

G. Cost and evidence
1. Capture component IDs, public URLs, immutable digests, table/object counts, Signal/
   job execution IDs, test timestamps and credit snapshots without secrets.
2. Disable unused/canary resources and duplicate schedules immediately.
3. Update Phase 14-17 reports with live-evidence addenda; do not rewrite historical
   local results.
4. Create `docs/phase-reports/PHASE_23_REPORT.md` and
   `docs/deployment/CATALYST_LIVE_INVENTORY.md`.
~~~

Definition of Done:

- Public frontend and primary API resolve to Zoho Catalyst.
- Auth/Gateway/AppSail/Data Store/Stratus paths work with real services.
- All six functional roles map and scope correctly.
- One real Signal and one real scheduled job execute successfully.
- Enabled QuickML/Zia/SmartBrowz/Mail/Push features have real evidence; disabled
  features are hidden and documented.
- Mandatory live Catalyst acceptance has no HELD/SCAFFOLDED/MANUAL status.
- Pipeline deployment and application rollback are proven.

---

# Prompt 24 - Live AWS custom-ML plane and Catalyst-to-AWS prediction proof

Objective: use the retained AWS credits only for justified custom ML/analytics,
prove real TabFM and TimesFM execution, integrate them through Catalyst and stop
temporary GPU resources after testing.

> **Auth-model note (Option B, added post-Prompt-23):** the deployed demo replaces
> the embedded Catalyst IAM login with an offline **role-card picker** + a gateway
> **demo-auth** mode (`DRISHTI_DEMO_AUTH=true`; `/api/*` route auth = Optional) that
> mints a full-access synthetic signed context server-side. **Prompt 24 does NOT
> depend on real IAM login** — its user-facing steps (approve a synthetic FIR, review
> the reviewed UI result) run under the demo super_admin context selected via the role
> cards, and the prediction path (approved Data Store row → Signal → event/cron →
> protected AWS adapter → real TabFM/TimesFM → Data Store → UI) is service-scope /
> server-to-server and is unchanged. Only Catalyst *Authentication* is dropped; Data
> Store, Functions, Signals, cron, AppSail, Stratus and API Gateway all remain. The
> draft/unapproved/evidence "zero AWS invocation" guards and idempotency are enforced
> server-side and are unaffected. See
> `docs/deployment/CATALYST_CAPABILITY_MATRIX.md` → "Demo login (Option B)".

~~~text
Implement Prompt 24 using the Global Execution Contract. This prompt authorizes
bounded AWS resource creation in the existing account for the documented DRISHTI
model plane. Reuse resources and enforce budget/teardown controls.

Agent/skill routing for this phase:
- Use `drishti-orchestrator` for interfaces and phase gating; make `aws-ml-operator` the
  only writer to AWS resources and run it sequentially with profile `drishti`.
- Use `security-auditor` for IAM, network, artifact and data-minimization review and
  `test-investigator` for invocation/contract failure analysis; both remain read-only.
- Route adapter code changes to `backend-engineer` only after the prediction contract is
  frozen. `catalyst-operator` may perform only the bounded integration update required
  to invoke the protected AWS adapter after AWS proof exists.
- Invoke `/phase-runner`, `/aws-ml-proof`, `/test-triage` and `/evidence-capture`.
- Inventory/reuse first, cap cost, and prove teardown of temporary GPU resources.

Current CLI authentication baseline (captured 21 July 2026):
~~~powershell
PS C:\Users\Prajwal\Desktop\DRISHTI> catalyst login --dc in
# Observed result: already logged in to the India DC.

PS C:\Users\Prajwal\Desktop\DRISHTI\services\ml> aws sso login --profile drishti
# Observed result: AWS SSO login completed successfully for profile drishti.
~~~
Reuse these authenticated sessions. Do not open another browser login or pause for the
user merely because a new prompt/session started. First verify AWS read-only with
`aws sts get-caller-identity --profile drishti`; re-authenticate only if that or another
real CLI command returns an authentication/expiry error. Never save or repeat the email
address, SSO start URL, one-time device code, tokens or credentials in prompts, logs,
reports or evidence.

A. Authenticate, inventory and finalize configuration
1. If AWS SSO/session is expired, open the required login flow, pause for the user and
   then resume automatically.
2. Inventory existing ECR, S3, KMS, IAM, VPC/security groups, SQS/DLQ, SageMaker,
   Batch, Lambda/API Gateway and CloudWatch resources before creating anything.
3. Replace every `<ACCOUNT_ID>`, region, subnet, security-group, role, bucket, KMS,
   model and digest placeholder through generated environment-specific configuration;
   never commit credentials.
4. Prefer ap-south-1 unless an existing compatible resource/instance availability
   requires another documented region.

B. Secure model artifacts and worker
1. Validate the TabFM and TimesFM code/weight licences for hackathon use. Record
   versions and SHA-256 digests; never claim a production licence.
2. Build/scan the separate GPU worker, push it to private ECR and reference it by
   immutable digest.
3. Store model/context artifacts and async inputs/outputs in private encrypted S3
   prefixes with least-privilege IAM/KMS roles and lifecycle cleanup.
4. Remove the TimesFM "not runnable" scaffold. Implement a genuine version-pinned
   TimesFM inference path, or remove TimesFM from enabled demo claims and leave the
   phase Pending because this roadmap treats it as mandatory.

C. Minimal execution plane
1. Deploy one SageMaker asynchronous-inference GPU mechanism for TabFM; do not also
   build real-time, Serverless and multiple Batch modes without a measured need.
2. Run TimesFM on the least-cost compatible AWS compute. It may share the versioned
   worker/async contract or use a bounded batch job; GPU is required only when the
   actual model/runtime requires it.
3. Deploy/reuse the protected AWS adapter with signed requests, narrow typed
   operations, private networking where applicable, SQS/DLQ for async state and
   CloudWatch logs/metrics without sensitive payloads.
4. Do not expose SageMaker/S3/RDS endpoints to the browser. Catalyst AppSail/Function
   is the only application caller.

D. Model contracts
1. TabFM receives only approved aggregate station/area features and labelled context;
   it never receives complete FIR JSON, narratives, raw evidence or person attributes.
2. TimesFM receives a versioned, gap-handled aggregate time series with frequency,
   horizon, cutoff and approved covariates.
3. Return request ID, actual backend/device, artifact/schema/context digests,
   predictions, probabilities/intervals, confidence/abstention, cutoff/freshness,
   runtime/memory/cost and warnings.
4. A new FIR changes a later approved aggregate snapshot; it does not fine-tune or
   update either pretrained model per FIR.
5. Fail closed on missing CUDA/weights/schema mismatch. A CPU/XGBoost fallback must
   have a distinct backend/model label.

E. Required real demonstrations
1. Approved synthetic FIR -> committed Catalyst Data Store record -> Signal/feature
   update -> idempotent PredictionRequest -> protected AWS adapter -> real TabFM on
   CUDA -> validated PredictionResult -> Catalyst Data Store -> reviewed UI result.
2. One scheduled aggregate series -> real TimesFM -> interval/freshness result -> UI.
3. Draft, submitted-but-unapproved FIR and raw evidence upload produce zero AWS model
   invocations.
4. Duplicate Signal/retry produces one logical request/result.
5. Missing CUDA/TabFM weights fails without masquerading as TabFM; separately invoke
   and label the approved baseline fallback.
6. Compare enabled models against the same held-out baseline/split and record latency,
   quality and indicative cost. Do not require ST-GNN/fusion if disabled from scope.

F. Cost, monitoring and shutdown
1. Configure AWS Budget/CloudWatch alarms and bounded concurrency/timeouts.
2. Record cold start separately from inference latency.
3. After collecting evidence, scale the async endpoint to zero where supported or
   delete/tear down the temporary endpoint/job exactly as the runbook specifies.
4. Confirm no chargeable temporary GPU job/endpoint remains. Retain only intended
   encrypted artifacts/images and the documented deployment recipe.

G. Report
Create `docs/phase-reports/PHASE_24_REPORT.md` and update
`docs/model-cards/tabfm-workload-band.md` plus a TimesFM model card. Include real job/
endpoint IDs, image/model digests, device evidence, metrics, failures, fallback and
teardown state without secrets.
~~~

Definition of Done:

- A real TabFM result proves the actual backend and CUDA device.
- A real TimesFM forecast proves its actual backend, cutoff and intervals.
- Catalyst-to-AWS-to-Catalyst-to-UI works without browser AWS access.
- Draft/evidence/no-approval guards and idempotency pass live.
- Fallbacks are unmistakably labelled and model failures fail closed.
- Temporary GPU resources are stopped and costs/evidence are recorded.

---

# Prompt 25 - Integrated security, scale, recovery and final hackathon release

Objective: replace the old Prompt 18 with one strict final release phase that tests
the complete live system, exercises recovery and produces every required artifact.

~~~text
Implement Prompt 25 using the Global Execution Contract. Run only after Prompts
18-24 are Complete. Do not use local fakes as evidence for live mandatory journeys.

Agent/skill routing for this phase:
- Use `drishti-orchestrator` as the only release integrator and gate owner.
- Run `security-auditor`, `repository-auditor` and `test-investigator` read-only. Assign
  narrowly scoped fixes to `backend-engineer` or `frontend-engineer`, then rerun the
  affected gate. Do not perform broad refactors during stabilization.
- Use `catalyst-operator` and `aws-ml-operator` sequentially only for required live
  verification, rollback/recovery, and cleanup in their existing environments.
- Invoke every applicable skill: `/phase-runner`, `/test-triage`, `/auth-matrix`,
  `/catalyst-deployment`, `/aws-ml-proof`, `/evidence-capture`, and `/release-audit`.
- A failed mandatory audit keeps Prompt 25 Pending even if the demo appears to work.

Current CLI authentication baseline (captured 21 July 2026):
~~~powershell
PS C:\Users\Prajwal\Desktop\DRISHTI> catalyst login --dc in
# Observed result: already logged in to the India DC.

PS C:\Users\Prajwal\Desktop\DRISHTI\services\ml> aws sso login --profile drishti
# Observed result: AWS SSO login completed successfully for profile drishti.
~~~
Reuse these authenticated sessions. Do not open another browser login or pause for the
user merely because a new prompt/session started. Verify AWS read-only with
`aws sts get-caller-identity --profile drishti` before AWS checks and use a bounded
Catalyst inventory command before Catalyst verification. Re-authenticate only after an
actual authentication/expiry error. Never save or repeat the email address, SSO start
URL, one-time device code, tokens or credentials in prompts, logs, reports or evidence.

A. Full test separation
Run and report separately:
- unit/component;
- backend API and repository contract;
- disposable integration;
- live Catalyst integration;
- live AWS model integration;
- browser E2E against the public Catalyst URL;
- authorization/security;
- synthetic data quality and lineage;
- performance/load;
- backup/recovery/rollback;
- cost and cleanup.

B. Mandatory end-to-end journeys
1. Public Catalyst frontend -> Catalyst Authentication -> API Gateway -> Function/
   AppSail -> Data Store health and authorized API.
2. Login as representative investigating officer, analyst, station/SP supervisor,
   policymaker, disaster coordinator and super admin; verify allowed and denied scope.
3. Create FIR draft -> validate -> submit -> supervisor approve -> canonical case;
   prove no prediction before approval.
4. Add/review person/party and resolve a candidate identity with audited decision.
5. Upload one already-digital synthetic evidence file to private Stratus -> hash/
   malware-safe fixture check -> manual metadata -> case link; prove no OCR/extraction.
6. Add typed statement/property/lab/court/lifecycle and one structured import with a
   rejected row.
7. Ask the exact English vehicle-theft query, a Kannada equivalent and a multi-turn
   follow-up; verify safe plan/query, citations and an appropriate visual.
8. Run the case-scoped investigation assistant -> similar cases/MO -> graph/path ->
   evidence versus hypothesis -> Send to Board.
9. Create/share/edit/lock/branch/export an Investigation Board and replay missed
   activity with source provenance.
10. Approved FIR -> aggregate change -> live Signal -> real TabFM result -> review;
    run one TimesFM scheduled forecast and verify freshness/intervals.
11. Correct an approved structured input -> prior result stale/superseded -> controlled
    idempotent rerun; preserve historical result.
12. Show Command Center alerts, district statistics, hotspot/trend and supervisor
    workload updating from committed state.
13. Replay a synthetic hazard feed -> forecast -> human-reviewed alert -> proposed/
    approved allocation -> safe route or explicit no-route -> Board pin.
14. Generate a watermarked structured report through enabled Catalyst services and
    verify audit/object hash; send only a data-minimized notification if enabled.
15. Complete every journey with no OCR/evidence transcription and no direct browser
    database/AWS access.

C. Security and authorization
1. Run the full role/rank/unit/resource/action allow/deny matrix.
2. Test expired/tampered tokens, nonce replay, scope spoofing, IDOR, injection, query
   complexity/timeout, upload type/size/hash, signed URL expiry, direct AppSail bypass,
   exact-origin CORS and API throttling.
3. Verify no secrets/private endpoints/raw evidence/PII appear in frontend bundles,
   logs, Signal payloads, notifications or model requests.
4. Verify RLS/FORCE RLS remains disabled as required for this synthetic hackathon and
   clearly state that server authorization is therefore mandatory.
5. Run dependency, secret, SAST, container and IaC/config scans and resolve blocking
   findings.

D. Data and model integrity
1. Reconcile Catalyst serving counts/hashes with the curated AWS export and explain
   expected exclusions.
2. Verify stable canonical identity, zero required spatial-containment failures,
   category/lifecycle consistency, evidence version/activity completeness,
   synthetic markers and source/model/schema lineage.
3. Verify no individual synthetic person-risk prediction is presented as operational.
4. Verify baseline comparisons, confidence/abstention, stale behavior, reviewer state,
   backend/device and model/artifact digests.

E. Performance and scale evidence
1. Run bounded load tests on the actual Catalyst/API paths using synthetic users and
   the 100k-case fixture/serving subset. Record concurrency, throughput, p50/p95/p99,
   error rate, cache behavior and slow query/adapter operations.
2. Test representative map, graph/Search Around, NL query, FIR write, dashboard and
   prediction-status workloads.
3. Verify server-side pagination/aggregation, bounded graph fan-out and browser memory/
   rendering responsiveness.
4. Produce a transparent capacity model toward approximately 2,000 stations,
   100,000 users and 1,000,000 cases. Do not claim certification from extrapolation.
5. Full target-scale/HA certification belongs in the post-hackathon backlog unless it
   is genuinely executed and evidenced.

F. Investigation-time demo metric
1. Define 3-5 golden tasks representing manual search/dashboard comparison/reporting.
2. Measure DRISHTI time-to-grounded-answer for the scripted synthetic workflows.
3. Report methodology and observed time only; do not fabricate a percentage reduction
   without a valid baseline/user study.

G. Backup, recovery and rollback
1. Export/hash the affected Data Store rows and Stratus manifests/versions.
2. Exercise recovery of one serving record, one evidence/report object version and one
   failed import/reconciliation item.
3. Exercise application rollback through Catalyst while retaining compatible data.
4. Exercise model-version/fallback rollback and queue/failed-job replay.
5. Verify retention/legal-hold protection and deterministic synthetic demo reset.
6. Run shutdown/cleanup and confirm temporary AWS GPU resources are stopped.

H. Required final artifacts
Create/update all of the following:
- `docs/phase-reports/PHASE_25_REPORT.md`;
- `HACKATHON_DEMO_CHECKLIST.md`;
- `HACKATHON_DEMO_RUNBOOK.md`;
- `DISASTER_RECOVERY_RUNBOOK.md`;
- `MODEL_RELEASE_CHECKLIST.md`;
- `POST_HACKATHON_BACKLOG.md`;
- `docs/deployment/FINAL_ARCHITECTURE.md` with Mermaid diagrams;
- `docs/deployment/CATALYST_AWS_SERVICE_INVENTORY.md`;
- `docs/deployment/ORGANIZER_CAPABILITY_EVIDENCE.md`;
- `docs/deployment/ORGANIZER_NOTES_COVERAGE.md`;
- `docs/deployment/FINAL_TEST_SUMMARY.json`;
- a redacted screenshot/video evidence manifest with capture instructions and hashes.

I. Post-hackathon backlog minimum
Classify every item as Deferred, Platform Unavailable, External Access Required or
Optional Future, and give owner/dependency/acceptance criteria. Include:
- production RLS/authorization/privacy/redaction/deletion/legal hold;
- secret rotation, penetration test and incident-response exercise;
- official CCTNS/RMS/court/lab/disaster feeds and licensing;
- production speech/translation and full UI localization review;
- OCR/document/evidence-media extraction pilots;
- real directory/SSO/rank synchronization;
- offline encrypted mobile field/evidence capture;
- real historical validation and approved-data model fine-tuning;
- one-million-case/100,000-user HA/capacity certification;
- governed RAG expiry/evaluation and model drift review;
- full Board snapshot versions, multi-instance collaboration and multi-tenancy;
- optional geospatial case replay, board assist and graph-database benchmark.

J. Release declaration
Run the strict release acceptance mode. If any mandatory check fails, is skipped,
HELD, MANUAL or UNKNOWN, leave Prompt 25 Pending and record exact remediation. If all
pass, declare only: "DRISHTI is ready for a synthetic hackathon demonstration on
Zoho Catalyst." Never declare production readiness.
~~~

Definition of Done:

- Every mandatory live journey passes through actual Catalyst services.
- TabFM and TimesFM have genuine AWS execution evidence and cleanup proof.
- Full local/live/browser/security/recovery suites are green with no unexplained skip.
- Load results are measured and scale claims are honest.
- Pipeline deployment, rollback and data/object/model recovery are exercised.
- Every required report/runbook/checklist/evidence file exists and is internally consistent.
- Strict acceptance returns zero with no mandatory HELD/MANUAL/UNKNOWN state.

---

# Prompt 26 - Independent implementation completeness audit and submission package

Objective: independently verify implementation rather than prompt wording, close
minor evidence defects and prevent any unsupported claim from reaching judges.

~~~text
Implement Prompt 26 using the Global Execution Contract. Treat all previous reports
as claims requiring evidence. Do not implement a new feature in this audit unless it
is a small correction; route substantial failures back to their owning prompt.

Agent/skill routing for this phase:
- Start a fresh `evidence-auditor` as the primary, read-only auditor. Do not reuse an
  implementation agent's conclusions as proof.
- Invoke `/phase-runner`, `/release-audit`, `/evidence-capture` (only for audit outputs),
  `/auth-matrix`, `/catalyst-deployment` and `/aws-ml-proof` in verification modes.
- Cloud operators may inventory and invoke bounded existing test paths but must not add
  features or silently repair resources during the independent audit.
- Classify absent evidence as NOT_RUN and contradictions as FAIL. Route substantial
  remediation to Prompt 19-25 and keep Prompt 26 Pending until re-audited.

Current CLI authentication baseline (captured 21 July 2026):
~~~powershell
PS C:\Users\Prajwal\Desktop\DRISHTI> catalyst login --dc in
# Observed result: already logged in to the India DC.

PS C:\Users\Prajwal\Desktop\DRISHTI\services\ml> aws sso login --profile drishti
# Observed result: AWS SSO login completed successfully for profile drishti.
~~~
Reuse these authenticated sessions for bounded read-only audit calls. Do not open another
browser login or pause for the user merely because Prompt 26 uses a fresh chat. Verify
AWS with `aws sts get-caller-identity --profile drishti` only when live AWS state is being
audited, and re-authenticate only after an actual authentication/expiry error. Never save
or repeat the email address, SSO start URL, one-time device code, tokens or credentials
in prompts, logs, reports or evidence.

A. Four-way evidence audit
For every requirement compare:
1. source code/configuration;
2. automated test result;
3. actual live Catalyst/AWS state;
4. user-visible behavior/artifact.

Create a row only as PASS when all evidence required for that capability exists.

B. Organizer Catalyst matrix
Audit all 26 organizer capability rows. For each record:
- capability and mandated Catalyst service;
- whether DRISHTI exposes the capability;
- Used, Not Used or Platform Unavailable;
- exact live component ID/URL when Used;
- automated/manual-visible evidence;
- third-party/AWS exception and justification;
- cost/cleanup state.

Using a third-party service for a capability available in Catalyst is a failure until
corrected or removed from submitted scope.

C. Organizer-session-notes matrix
Audit every requirement in the supplied notes, including:
- English/Kannada text and voice;
- semantic multi-turn intent/context/clarification;
- NL query -> authorized data -> answer -> visualization;
- maps/heatmaps/timeline/network/trend/Sankey;
- real-time stats/alerts/workload;
- trends/clustering/hotspots/repeat offenders;
- forecasting, graph and similar cases;
- investigation assistant;
- crime/jurisdiction scenario coverage;
- rank/scope authorization;
- production-style architecture and scale evidence;
- synthetic-data declaration.

Mark optional algorithms as alternatives, not missing duplicates.

D. Architecture consistency
1. Re-run the route/data-boundary checker.
2. Prove Catalyst owns public hosting and operational serving data/object storage.
3. Prove AWS is limited to the documented historical/analytics and custom model plane.
4. Prove no browser/direct AppSail path bypasses Gateway or reaches AWS/RDS directly.
5. Prove AppSail mandatory routes start/work without `DATABASE_URL`.
6. Prove identity role/scope mapping matches frontend, gateway and backend enums.

E. Reports, docs and presentation hygiene
1. Validate links, commands, component names, URLs, table counts, model names, versions
   and status terms across README, prompt2, prompt3 and all phase reports.
2. Repair mojibake and stale Supabase/Docker/Prompt-number statements.
3. Ensure screenshots/videos are recent, synthetic, redacted and correspond to the
   deployed Catalyst URL.
4. Ensure no token, password, private URL, AWS account-sensitive data or real PII is
   present in artifacts.
5. Make the demo runbook executable by a new evaluator and provide a deterministic
   reset/fallback path for external outages.

F. Final audit outputs
Create:
- `docs/phase-reports/PHASE_26_REPORT.md`;
- `FINAL_IMPLEMENTATION_AUDIT.md`;
- `SUBMISSION_EVIDENCE_INDEX.md`;
- final updated status tables in prompt3new.md and, where historically appropriate,
  an addendum/status correction in prompt2.md;
- a final PASS/FAIL machine-readable manifest.

G. Completion rule
No mandatory item may be silently omitted, described only in future tense or marked
PASS using a fake. If a mandatory item is incomplete:
1. mark Prompt 26 Pending;
2. identify the owning Prompt 18-25;
3. give the exact command/resource/test required;
4. do not declare the submission ready.
~~~

Definition of Done:

- Catalyst's 26-row matrix and every organizer-note requirement have evidence-backed dispositions.
- Code, tests, cloud state and visible behavior agree.
- No mandatory fake/placeholder/disabled service is presented as implemented.
- All documentation and evidence are redacted, current and internally consistent.
- The final submission index lets a judge reproduce the complete synthetic demo.
- Final declaration remains hackathon-demo ready, never production-ready.

---

## 6. How to execute this file

For each new Kiro/Codex session:

1. Open `C:\Users\Prajwal\Desktop\DRISHTI`.
2. Select `drishti-orchestrator` for Prompts 19-25 or a fresh `evidence-auditor` for
   Prompt 26. Prompt 18 may use the primary agent for the one-time reconciliation.
3. Ask it to invoke `/phase-runner` and execute only the next Pending prompt from this
   file. The phase preflight loads the compact state; do not paste all prior prompts.
4. Let the coordinator delegate only the named specialist work and preserve one writer
   for shared files and each cloud environment.
5. Complete unavoidable Zoho/AWS browser authentication if requested. Existing CLI
   sessions should be reused and are not implementation evidence by themselves.
6. Do not move to the next prompt until its report, evidence manifest entries and every
   Definition of Done gate pass.
7. End with `/phase-runner` handoff so the next session reads a small deterministic state.

Start with Prompt 19; Prompt 18 is complete. Prompt 26 is the final independent gate.

---

## 7. Minimum judge-facing demonstration after completion

The final scripted demonstration should be short and cohesive:

1. Open the Catalyst-hosted application and sign in as a scoped officer.
2. Ask the Kannada or English vehicle-theft question and a follow-up; show citations
   and an automatically selected map/trend visualization.
3. Open a related case, show similar MO/canonical links and send evidence-backed
   objects to the Investigation Board.
4. Approve a synthetic FIR and show the resulting aggregate update plus a real,
   reviewed TabFM/TimesFM output with confidence/version—not a person-risk score.
5. Switch to the supervisor view and show workload/freshness.
6. Switch to Emergency Response, replay a synthetic hazard and human-approve an
   allocation/safe route.
7. Show the Catalyst architecture/evidence screen and explain that AWS is used only
   for justified custom analytics/ML.
8. End with the synthetic-data, human-review and non-production limitations.

This demonstrates the organizer's core value—faster, conversational, visual and
evidence-backed investigation—without trying to showcase every screen.
