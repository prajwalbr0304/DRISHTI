# DRISHTI — Post-Hackathon Backlog (Prompt 25 Part I)

> **Scope.** DRISHTI is a **synthetic Karnataka-Police hackathon demonstration on Zoho
> Catalyst**. This backlog is the honest boundary between what is *genuinely demonstrated*
> now and what remains for a real deployment. Nothing here is claimed as done. Every item
> is classified and given an owner, dependency and acceptance criterion.

**Classification legend**

| Class | Meaning |
|---|---|
| **Deferred** | In-scope engineering intentionally postponed to protect the working demo. |
| **Platform Unavailable** | Blocked by a Catalyst/AWS capability not available in the current DC/account. |
| **External Access Required** | Needs an official third-party feed, licence, directory or credential we do not have. |
| **Optional Future** | Enhancement, not required for the product thesis. |

---

## 0. Release-blocking remediation carried out of Prompt 25 (must close before a "secure live demo" claim)

These are the mandatory Prompt 25 items that are **NOT** proven live and keep Prompt 25 **Pending**.

| ID | Item | Class | Owner | Dependency | Acceptance criterion |
|---|---|---|---|---|---|
| RB-1 | **Live per-role authorization is not enforced at the edge.** The deployed `gateway_api` runs with `DRISHTI_DEMO_AUTH=true`, minting a full-access `super_admin` context for any sessionless caller (verified: unauthenticated `GET /api/cases` returns synthetic case data). | Deferred | catalyst-operator + backend | Console: 6 Catalyst users with `drishti_role`/`district_id`/`unit_id`; set `DRISHTI_DEMO_AUTH=false` on `gateway_api` | With demo-auth off, unauthenticated `/api/*` reads return 401; each of the 6 roles returns only its allowed scope and is denied out-of-scope, verified live through the gateway (not just offline). |
| RB-2 | **Live NL-query path returns 502** (`POST /api/ask`) — the Ask DRISHTI planner is not answering through the deployed gateway. | Deferred / Platform Unavailable | backend + catalyst-operator | QuickML LLM Serving enablement in the IN DC, or the labelled deterministic planner wired on AppSail | The exact English + Kannada vehicle-theft queries return a grounded, cited answer with a typed visual live through `/api/*`. |
| RB-3 | **Deployed AppSail → AWS adapter chain not wired** (`deployed-e2e-tabfm.log` shows `502 upstream_unavailable`). The server-side client path to AWS was proven via a driver, but the *deployed* AppSail lacks `DRISHTI_AWS_ADAPTER_URL`/`SECRET`. | Deferred | catalyst-operator | Console: set adapter URL/secret on AppSail; a live SageMaker endpoint for the run | Approved-FIR → Signal → deployed AppSail → adapter → real TabFM result appears in the UI without any driver. |
| RB-4 | **Fully-automated browser E2E stops at the interactive Zoho IAM login.** | Deferred | frontend + catalyst-operator | A scriptable test identity or IAM automation | A headless Playwright run signs in and completes a mandatory journey end-to-end against the public Slate URL. |

---

## 1. Security, privacy and governance (production hardening)

| ID | Item | Class | Owner | Dependency | Acceptance criterion |
|---|---|---|---|---|---|
| SEC-1 | Production **RLS / FORCE ROW LEVEL SECURITY** on every tenant/geo-scoped table (disabled by explicit hackathon decision; server-side authz is currently the sole enforcement). | Deferred | backend + DBA | Postgres policies + role model per station/district/tenant | Every query is RLS-constrained; a bypassed server guard still cannot read cross-scope rows. |
| SEC-2 | Real **authorization at the edge** replacing `DRISHTI_DEMO_AUTH` (see RB-1) with Catalyst Authentication + directory-sourced roles. | Deferred | backend + catalyst-operator | RB-1, SSO/directory | No anonymous data access; every request carries a verified identity. |
| SEC-3 | **Secret rotation**, a **penetration test** and an **incident-response** tabletop exercise. | External Access Required | security-auditor + owner | Rotation tooling, an authorized pentest window | Rotated secrets, a pentest report with closed findings, a documented IR run. |
| SEC-4 | Production **privacy / redaction / deletion / legal-hold** workflows (currently synthetic-only markers + retention notes). | Deferred | backend | Data-governance policy, legal input | Subject-deletion + legal-hold honoured and audited on real data classes. |

## 2. Official data integration and localisation

| ID | Item | Class | Owner | Dependency | Acceptance criterion |
|---|---|---|---|---|---|
| DATA-1 | Official **CCTNS / RMS / court / lab / disaster** feeds and their **data-sharing licences**. | External Access Required | owner + integrations | Government MoUs, feed credentials/schemas | Live ingest from at least one official feed with schema-validated lineage. |
| DATA-2 | Production **speech + translation** (currently browser Web Speech; Catalyst Zia STT/TTS/translation is unavailable in the IN DC). | Platform Unavailable | frontend + backend | Zia speech in DC, or a licensed provider | Server-side EN/KN speech + translation with confidence gating. |
| DATA-3 | Full **UI localisation review** (Kannada) beyond the demo strings. | Deferred | frontend + linguist | Professional Kannada review | Localisation QA sign-off across all mandatory routes. |
| DATA-4 | **OCR / document / evidence-media extraction** pilots (kept OFF by scope: `EVIDENCE_EXTRACTION_ENABLED=false`). | Optional Future | backend + ML | Extraction pilot + accuracy/eval bar | A scoped pilot with measured accuracy and a human-review gate. |
| DATA-5 | Real **directory / SSO / rank synchronisation**. | External Access Required | owner + backend | Police directory / IdP access | Roles + ranks provisioned from the real directory, not synthetic attributes. |
| DATA-6 | **Offline encrypted mobile** field/evidence capture. | Optional Future | mobile | Mobile app + device-encryption design | Encrypted offline capture with tamper-evident sync. |

## 3. Model, scale and platform

| ID | Item | Class | Owner | Dependency | Acceptance criterion |
|---|---|---|---|---|---|
| ML-1 | **Real historical validation** + **approved-data model fine-tuning** (TabFM weights are Non-Commercial licence — evaluation only). | External Access Required | ML | Approved real historical data + a commercial/again-licensed model | Backtest on real data; a compliant fine-tuned model with an accuracy floor. |
| ML-2 | **Governed RAG expiry / evaluation** and **model-drift review** cadence. | Deferred | ML | Eval harness + drift monitors | Scheduled drift/eval reports with rollback triggers. |
| SCALE-1 | **1,000,000-case / 100,000-user HA / capacity certification** (only a transparent, bounded *model* exists — see `docs/deployment/FINAL_TEST_SUMMARY.json` + `artifacts/phase-25/load/capacity-model.json`). | Deferred | SRE + backend | Multi-instance AppSail (see SCALE-2), read replicas, load rig | A genuinely executed target-scale load test meeting SLOs — **not** extrapolation. |
| SCALE-2 | Remove the **single-instance AppSail pin** (`min=max=1`) — needs shared monotonic ID allocation (Data Store sequence / Cache incr) for board/disaster PKs + distributed nonce replay. | Deferred | backend | Shared sequence design | `max>1` with correct IDs + replay protection under concurrency. |
| SCALE-3 | Optimise **slow aggregations** (measured: `performance_overview` ~1.6s, `cases` list ~1.2s, `forecast_freshness` p50 ~13s with 504s under load) via materialized views + indexing + caching. | Deferred | backend | `app/matviews.py` rollout, cache | p95 < 1s for dashboard/list reads at target row counts. |

## 4. Collaboration, multi-tenancy and optional analytics

| ID | Item | Class | Owner | Dependency | Acceptance criterion |
|---|---|---|---|---|---|
| BOARD-1 | Full **Investigation Board snapshot versions**, **multi-instance real-time collaboration** and **multi-tenancy**. | Optional Future | backend + frontend | Snapshot store + presence service | Versioned snapshots, concurrent editing, tenant isolation. |
| OPT-1 | Optional **geospatial case replay**, **board assist** and a **graph-database benchmark** (offered as alternatives, not missing duplicates). | Optional Future | ML + backend | — | Documented alternative implementations with comparative evidence. |

---

*Owners are role labels (the DRISHTI specialist agents / project owner), not individuals.
No credentials or personal data appear in this backlog.*
