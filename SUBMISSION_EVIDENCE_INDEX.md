# DRISHTI — Submission Evidence Index (Prompt 26)

> One page for an evaluator. It lists the canonical live surfaces, the exact demo script, a
> deterministic fallback for any external outage, and a capability → evidence map so every
> claim can be reproduced. **Synthetic Karnataka-Police hackathon demonstration on Zoho
> Catalyst — never production.** All data is synthetic; no real police or personal data.

Project **DHRISTI** `48361000000030003` · org `60075362708` · India DC · AWS acct `…5713` (ap-south-1).

## 1. Canonical live surfaces

| Surface | URL | Notes |
|---|---|---|
| Public app (Slate) | `https://drishti-frvfpunc.onslate.in/` | **Canonical.** Synthetic-demo badge visible. (A stale `drishti-uryfmaue` app is being decommissioned — do not use it.) |
| API Gateway | `https://dhristi-60075362708.development.catalystserverless.in/api/*` | `/api/*` → `gateway_api` → signed context → AppSail |
| AppSail health | `…catalystappsail.in/health/ready` | liveness + dependency-aware readiness |

**Login:** the demo uses an **offline role-card picker** (synthetic identities). Click a
role → the app opens with live synthetic data. Real Catalyst IAM is intentionally disabled
for the demo and is re-enabled by config when needed (see `PHASE_26_REPORT.md` §G, RB-1/RB-4).

## 2. Scripted demo (≈6 minutes)

1. Open the canonical Slate URL; confirm the **Synthetic Hackathon Demo** badge.
2. Pick **Crime Analyst** → land on Command Center: live district stats, alerts, hotspots.
3. **Ask DRISHTI** — English vehicle-theft query + a Kannada follow-up; show citations and
   the auto-selected map/trend visualization. *(If the live NL edge is unavailable — RB-2 —
   use the deterministic-local NL demo, see §4; it is labelled "local deterministic demo".)*
4. Open a related case → similar cases / MO / network graph → **Send to Investigation Board**.
5. Approve a synthetic FIR → show the aggregate update and a **reviewed TabFM/TimesFM** output
   with confidence + model version (not a person-risk score). *(Live model chain is RB-3; use
   the recorded T4 result evidence in `artifacts/phase-24/model-runs/` if the endpoint is down.)*
6. Switch to **Supervisor** → station/officer workload + data freshness.
7. Switch to **Emergency Response** → replay a synthetic hazard → human-approve an allocation
   / safe route.
8. Show the architecture/evidence screen; state that AWS is used only for justified custom
   ML, that data is synthetic, outputs are human-reviewed, and this is not production.

## 3. Roles (all six selectable via role cards)

`investigator` · `analyst` · `supervisor` · `policymaker` · `disaster_coordinator` ·
`super_admin`. Identical enum across frontend (`web/src/config/roles.ts`), gateway
(`gateway_api` `FUNCTIONAL_ROLES`) and backend (`app/org/hierarchy.py`). Rank labels
(DGP/IGP/DIG/SP/SHO/IO…) map to role + scope via the gateway `RANK_MAP`.

## 4. Deterministic reset / fallback (external-outage safe)

- **NL query outage (RB-2):** run the backend locally and use the deterministic planner —
  `cd services/ml && uvicorn app.main:app` then `POST /ask`; or use the offline E2E NL
  journey. Label any capture "local deterministic demo".
- **Model chain (RB-3):** the AWS T4 endpoint is torn down for cost. Use the recorded live
  proofs: `artifacts/phase-24/model-runs/{tabfm-run,timesfm-run,live-integration}.log`. To
  re-run live: redeploy per `PHASE_26_REPORT.md` §G (RB-3), then tear down again.
- **Demo data reset:** `python -m datagen …` / `seed_demo_board.py` + disaster demo seed
  (see `DISASTER_RECOVERY_RUNBOOK.md`). Deterministic synthetic fixtures.
- **Local full demo (no cloud):** `web/` (`npm run dev`, `VITE_AUTH_MODE=offline`) + `services/ml` — every mandatory journey runs locally against synthetic data.

## 5. Capability → evidence map

| Capability | Primary evidence |
|---|---|
| Catalyst hosting/gateway/AppSail/Data Store/Stratus live | `artifacts/evidence-manifest.json` (p23 entries); live 200 probes (`artifacts/phase-26/live-probes.log`) |
| Six-role authorization logic | `artifacts/phase-21/authorization-verification.json` (34 cases); `test_gateway_authz.py` |
| Signal + cron live | manifest `p23-signal-live`, `p23-cron-live` (exec `48361000000061010`) |
| Stratus evidence object (versioned, SHA-256) | manifest `p23-stratus-evidence-live` |
| Real TabFM on CUDA / real TimesFM | manifest `p24-tabfm-cuda-real` (`928cb350…`), `p24-timesfm-cuda-real` (`2f776efe…`) |
| AWS teardown / cost control | `artifacts/phase-26/aws-cleanup-recheck.log` (`list-endpoints=[]`) |
| Route/data boundary | `artifacts/phase-26/route-boundary-recheck.log` (336/0) |
| Local release gate 16/16 | `artifacts/phase-22/release-gate.json` |
| Load + capacity model | `artifacts/phase-25/load/{load-results,capacity-model}.json` |
| Recovery/rollback | `artifacts/phase-25/recovery/recovery-exercise.json`; `artifacts/phase-23/rollback-proof.log` |
| Screenshots/video (redacted, synthetic) | `docs/deployment/SCREENSHOT_VIDEO_EVIDENCE.md` + `artifacts/phase-25/evidence-media-hashes.json` |
| Full audit dispositions | `FINAL_IMPLEMENTATION_AUDIT.md`; `artifacts/phase-26/FINAL_AUDIT_MANIFEST.json` |

## 6. Known open items (honest)

| ID | Item | Owner | Status |
|---|---|---|---|
| RB-1/RB-4 | Demo role-card auth replaces real IAM | Prompt 23 | **Accepted deviation** (reversible; re-enable when shortlisted) |
| RB-2 | Live `/api/ask` 502 | Prompt 19/23 | **Open** — deterministic fallback documented (§4) |
| RB-3 | Deployed AppSail→AWS adapter unwired; T4 torn down | Prompt 24/25 | **Blocked by cost** — models independently proven; recorded evidence (§4) |
| Hygiene | Duplicate `uryfmaue` Slate app live | Prompt 23 | **Open** — decommission before submission |

## 7. Declaration

DRISHTI is ready for a **synthetic hackathon demonstration on Zoho Catalyst** using the
documented deterministic fallback for the live NL-query edge (RB-2) and the recorded AWS T4
model evidence (RB-3). The unconditional "every journey live through Catalyst" claim is
pending RB-2 closure. **This is never presented as production-ready.**
