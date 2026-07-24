# DRISHTI — Hackathon Demo Runbook

> A new evaluator can run the complete **synthetic** demo from this file. DRISHTI is a
> synthetic Karnataka-Police crime-intelligence demonstration on **Zoho Catalyst** (with a
> bounded, protected AWS ML plane). **Not production.** No real PII. All URLs are the live
> Catalyst deployment; no local setup is required to view the app.

## 0. Live endpoints

| Surface | URL |
|---|---|
| Public app (Slate) | `https://drishti-frvfpunc.onslate.in/` (canonical; stale `drishti-uryfmaue` to be decommissioned) |
| API Gateway | `https://dhristi-60075362708.development.catalystserverless.in/api/*` |
| AppSail health | `https://drishti-api-50044118953.development.catalystappsail.in/health/ready` |

Project **DHRISTI** `48361000000030003` · India DC.

## 1. Pre-demo readiness (60 seconds)

```text
# health + boundary (expect frontend 200, health 200, direct-bypass 401, foreign-CORS rejected)
python artifacts/phase-25/_live_boundary_probe.py

# AWS cost/cleanup (expect zero SageMaker endpoints)
python .kiro/skills/aws-ml-proof/scripts/aws_inventory.py --profile drishti --phase 25
```

If a live external dependency is degraded, use the **deterministic local demo** (below) — it
runs every mandatory journey offline with a labelled deterministic provider.

## 2. Guided demo flow (~12 min)

1. **Open the app** → the role-card landing shows the six roles. *(Note: the live demo uses
   `DEMO_AUTH` so the card shows data without an IAM login; a secure demo would sign in per role.)*
2. **Ask DRISHTI (bilingual):** ask the English vehicle-theft query, then the Kannada
   equivalent, then a follow-up → grounded, cited answer + a typed visual. *(If the live NL
   edge is degraded (RB-2), show the deterministic-provider answer locally.)*
3. **Map + hotspots:** open the map → heatmap/hotspots; filter by district.
4. **Case triage:** open the case list → a case → detail → similar cases (why-match) → network.
5. **FIR journey (offline-proven):** draft → validate → submit → supervisor approve →
   canonical case; show **no prediction before approval**.
6. **Evidence:** upload a synthetic already-digital file → Stratus (hash verified, no OCR).
7. **Investigation assistant:** case-scoped → similar/MO → graph/path → facts vs hypotheses →
   **Send to Board**.
8. **Investigation Board:** create/share/annotate/lock/branch/export; replay activity.
9. **Prediction / forecast:** show the district forecast fan chart (real TimesFM T4 result,
   32 districts, intervals) and the workload/prediction-status view.
10. **Command Center:** district stats, alerts, hotspot/trend, supervisor workload.
11. **Disaster:** hazard overview (active hazards) → forecast → reviewed alert → allocation → route/no-route → Board pin.

## 3. Deterministic local demo (fallback for any live outage)

```text
# backend (DB-free, mandatory journeys) — offline provider, no external calls
cd services/ml && set DRISHTI_DISABLE_DB_TESTS=1 && python -m pytest tests -q   # 378 passed
# frontend dev server for the click-through (run manually in your terminal)
cd web && npm install && npm run dev            # then open http://localhost:5173
# browser E2E of all mandatory journeys
cd web && npm run test:e2e                       # 27 passed
```

Deterministic reset to a known state:

```text
python services/ml/seed_demo_board.py            # Investigation Board demo
# disaster fixture: POST /api/disaster/demo/seed
```

## 4. Talking points (honest)

- **Synthetic data** throughout; a boot-time marker refuses a non-synthetic DB.
- **Real ML:** TimesFM + TabFM ran on a real AWS **Tesla T4** (digests verified); the endpoint is
  torn down after proof for cost control.
- **Server-side authorization** is real and tested (34-case allow/deny matrix). *For a secure
  live demo, turn off `DEMO_AUTH` and sign in per role (POST_HACKATHON_BACKLOG RB-1).*
- We claim only: **"DRISHTI is ready for a synthetic hackathon demonstration on Zoho Catalyst."**
  Never production readiness.

## 5. Known live gaps (say them plainly if asked)

- Live per-role **deny** is not enforced at the edge yet (`DEMO_AUTH`) — RB-1.
- Live **NL query** `/api/ask` returns 502 — use the local deterministic answer — RB-2.
- Fully-automated browser E2E stops at the interactive IAM login — RB-4.

See `HACKATHON_DEMO_CHECKLIST.md` for the per-journey live/offline status.
