# Phase 23 Report — Live Zoho Catalyst provisioning and deployment

- **Prompt:** 23 (prompt3new.md)
- **Status:** **PENDING / IN PROGRESS** — preflight complete and green; the live
  deployment (sections B–F) requires interleaved Catalyst **Console** actions and
  **credit** authorization that only the project owner can perform. No live
  Definition-of-Done item is met yet, and none is faked.
- **Date:** 2026-07-21
- **Project:** DHRISTI `48361000000030003`, org `60075362708`, India DC, Development
- **Result label:** HACKATHON-DEMO READY is **not** yet claimable for live Catalyst;
  this phase remains open until the collaborative deployment produces real evidence.

---

## 1. Summary

Prompt 23 deploys the real submission into the existing Catalyst project and replaces
local fakes with live services. Section **A (authenticate + preflight)** is **complete
and green**. Sections **B–G** are a genuinely **interleaved CLI + Catalyst Console**
procedure: a fully autonomous CLI-only deployment is **not possible** on Catalyst,
because the platform only exposes Console/SDK paths for the server-side secrets, Slate
activation, API Gateway routes/CORS, Authentication identities/roles, Stratus buckets,
Signals rules, and cron creation that the Definition of Done depends on.

This report records exactly what was verified, why the remaining work needs the owner,
and the precise ordered runbook (also in `docs/deployment/CATALYST_LIVE_INVENTORY.md`).
It does **not** convert configuration, local fakes, or plans into live evidence.

## 2. Section A — authenticate & preflight (COMPLETE, green)

| Command | Result | Artifact |
|---|---|---|
| `python .kiro/skills/phase-runner/scripts/phase_state.py preflight --repo . --phase 23` | `dependency_ok: true` (Phase 22 complete); phase 23 `in_progress` | `artifacts/phase-23/preflight.json` |
| `python .kiro/skills/catalyst-deployment/scripts/catalyst_preflight.py --repo . --dc in --phase 23` | `ready: true` — CLI `1.27.0`; auth OK; 0 placeholders | `artifacts/phase-23/catalyst-preflight.json` |
| `python infra/catalyst/pipelines/preflight_deploy.py --require-live` | **PASS** — project=DHRISTI/`48361000000030003`, single-instance AppSail, live no-duplicate = ok | `artifacts/phase-23/preflight-deploy.json` |
| `catalyst project:list` | `DHRISTI (active) (base) 48361000000030003` (+ unrelated `Project-Rainfall`) | — |
| `catalyst apig:status` | `API Gateway: DISABLED` | — |
| `docker images drishti-api:appsail` | `81b08d8083a3`, 701 MB, linux/amd64 | — |

Confirmed: project/org/DC/env correct, synthetic marker present, exactly one DHRISTI
project (no duplicate), AppSail posture safe (single instance, `DATABASE_URL` forbidden,
no wildcard CORS), Docker + AppSail image present, no unresolved placeholders in
`infra/catalyst`.

**Tooling fix (Windows portability):** `.kiro/skills/catalyst-deployment/scripts/catalyst_preflight.py`
resolved `catalyst.cmd`/`.ps1` shims, hardened stdio, and now uses `catalyst project:list`
run from the bound `infra/catalyst` dir as the non-interactive auth probe (the CLI's
`whoami`/`login` subcommands crash this CLI version's winston file logger under captured
stdio). The script now reports `ready: true` (exit 0) instead of a false negative.

Evidence recorded (`artifacts/evidence-manifest.json`): `p23-deploy-preflight`,
`p23-catalyst-preflight` (both PASS, local).

## 3. Why B–F cannot be completed autonomously (blocker analysis)

The deployed architecture (verified in code) makes several steps **owner/Console-only**:

- **AppSail + Functions need server-side secrets.** `functions/gateway_api/index.js`
  returns HTTP 503 unless `ZOHO_APPSAIL_BASE_URL` and `ZOHO_APPSAIL_SIGNING_SECRET` are
  set in the Console; `services/ml/app/readiness.py` fails readiness without the signing
  secret and a reachable Data Store. Secrets must be set in the Console, never in the
  repo/CLI/chat.
- **Console-only components (no CLI verb):** Stratus buckets, NoSQL, Cache, QuickML,
  Signals rules, Job Scheduling crons, Authorized Domains/CORS, Authentication users +
  role attributes, budget alerts (see `infra/catalyst/COMPONENTS.md`).
- **Slate** needs a one-time Console activation before `catalyst deploy client`.
- **Data Store table creation** uses the Admin SDK (`provision_*_tables.py --apply`),
  which needs SDK credentials from the Console or the deployed AppSail runtime; the CLI
  `ds:import` can only load data **after** tables exist.
- **Real credits:** deploying AppSail starts continuous billing against a finite
  ~INR 1,800 budget; several stages are hard to reverse. Prompt 23 authorizes bounded
  credit use, but the sequence is interleaved with the owner's Console steps, so firing
  the credit-spending deploys before the Console prerequisites would waste budget on a
  non-functional (503) deployment.

The complete ordered, interleaved runbook (`[AGENT]` CLI vs `[OWNER]` Console) is in
`docs/deployment/CATALYST_LIVE_INVENTORY.md` §3.

## 4. Definition of Done — status

| DoD item | Status | What remains (owner unless noted) |
|---|---|---|
| Public frontend + primary API resolve to Catalyst | **PENDING** | Slate activate → build with Gateway URL → `catalyst deploy client`; `apig:enable` + routes |
| Auth/Gateway/AppSail/Data Store/Stratus paths work live | **PENDING** | deploy functions+AppSail (agent), set secrets + provision Data Store/Stratus (owner), then smoke (agent) |
| All six functional roles map + scope correctly (live) | **PENDING** | create 6 demo users + `drishti_role` attrs (owner); agent runs live allow/deny matrix |
| One real Signal + one real scheduled job execute | **PENDING** | create `prediction-requested` Signal + `drishti-forecast-daily` cron (owner); agent proves delivery/retry/idempotency |
| Enabled QuickML/Zia/SmartBrowz/Mail/Push have real evidence; disabled hidden+documented | **PARTIAL** | Zia voice = Not Used/Unavailable (documented); QuickML/SmartBrowz/Mail/Push enable+prove or mark Not Used |
| Mandatory live acceptance has no HELD/SCAFFOLDED/MANUAL | **PENDING** | run live acceptance after deployment |
| Pipeline deployment + application rollback proven | **PENDING** | link runner + variables (owner); agent runs pipeline + rollback |

No item is marked complete. Section D partial: the **Zia voice** disposition (Not Used —
Unavailable in IN DC, browser Web Speech labelled fallback) and **Circuits/Zia AutoML**
(Unavailable in IN DC) are already documented honestly with evidence basis in
`CATALYST_LIVE_INVENTORY.md` §4 and `COMPONENTS.md`.

## 5. Enabled-vs-not-used capability decisions (recorded now)

- **Enable (mandatory):** Functions, API Gateway, AppSail, Data Store, Stratus,
  Authentication; **one** Signal (`prediction-requested`); **one** cron
  (`drishti-forecast-daily`); Cache (bounded nonce/segment).
- **Enable if available:** QuickML LLM Serving (Ask DRISHTI planner; else labelled
  deterministic fallback).
- **Not Used — Unavailable (IN DC):** Zia STT/TTS/Translation (→ labelled browser Web
  Speech), Circuits, Zia AutoML.
- **Not Used — out of scope:** Zia OCR/face/object/evidence extraction.
- **Enable only if a visible demo capability, else Not Used:** SmartBrowz, Mail, Push.

## 6. Exact next actions (collaborative live deployment)

Follow `docs/deployment/CATALYST_LIVE_INVENTORY.md` §3 stages 1–8. First blocking owner
action: **Stage 1** — activate Slate in the Console and choose the
`ZOHO_APPSAIL_SIGNING_SECRET`. Then the agent runs Stage 2 (`apig:enable`, deploy
functions), and the deployment proceeds stage-by-stage with evidence capture at Stage 7.

## 7. Honesty notes

- Local fakes, config declarations, and this runbook are **not** live evidence.
- No secrets, tokens, credentials, emails, or raw evidence are recorded in this phase's
  artifacts.
- Phase 23 stays **Pending** in `EXECUTION_STATE.json` / `prompt3new.md` until real
  deployed invocation evidence exists for every mandatory DoD item.
