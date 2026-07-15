# DRISHTI: Remaining Features and AWS Implementation Roadmap

Status: implementation roadmap  
Primary hosting decision: AWS, using the available AWS credits  
Scope: finish the current React, FastAPI, PostgreSQL/Supabase prototype safely, then deploy it as a governed investigation-support system.

## 1. Executive decision

AWS can run the current models, including Google TabFM and TimesFM, and is the better primary compute platform when AWS credits are available. Do not put the 3 GB TabFM artifact in a small always-on API container. Keep the normal application API separate from GPU prediction jobs.

Use this split:

| Concern | Initial production choice | Why |
|---|---|---|
| Web application | Existing React app, deployed as static assets through AWS Amplify Hosting or S3 + CloudFront | Cheap, scalable, simple |
| Core API | Existing FastAPI service in ECS Fargate | Keeps request/response APIs always available without GPU cost |
| Current relational source of truth | Keep Supabase PostgreSQL initially | Avoids a risky immediate database migration |
| Future relational source of truth | Amazon RDS PostgreSQL, only after a planned migration | Gives a single AWS data plane if required |
| Original FIR/evidence files | Amazon S3 with versioning, KMS encryption, lifecycle rules, and Object Lock where policy requires it | Files must not be stored in PostgreSQL |
| Background jobs | SQS + AWS Step Functions + AWS Batch | Handles long OCR, extraction, feature and GPU prediction jobs reliably |
| GPU batch inference | AWS Batch on EC2 GPU instances | Scale to zero after the job; best first use of credits |
| GPU online inference, only if needed | SageMaker asynchronous or real-time endpoint after benchmarking | Use only after there is a measured latency requirement |
| Secrets | AWS Secrets Manager or SSM Parameter Store | Removes credentials from source files and containers |
| Monitoring | CloudWatch logs, metrics, alarms, and CloudTrail audit logs | Operations and incident traceability |

Do not run three competing data platforms. In the first release, Supabase PostgreSQL remains the one database of record, AWS provides compute, evidence storage, and job orchestration, and Catalyst remains optional for the specific services described later. If RDS is adopted, migrate deliberately and retire Supabase as the source of truth; do not dual-write case records indefinitely.

## 2. Current project assessment

The repository is a capable prototype, not yet a deployable investigative system.

### Already present

- React/Vite frontend with pages for graph, geo, analytics, risk, cases, money, forecast, explain, and chat.
- FastAPI routers for those domains.
- PostgreSQL schemas for FIR/cases, intelligence, and extensions.
- TabFM integration with a saved BF16 model artifact, an optional TabPFN path, and XGBoost/HistGradientBoosting fallback.
- TimesFM integration with a seasonal fallback.
- ST-DBSCAN/KDE hotspots, near-repeat logic, graph analytics, money rules, similarity search, explainability, and chat fallbacks.
- Synthetic data-generation scripts and automated test collection; 141 tests are currently discoverable.

### Important gaps found in the current code

- Risk labels are synthetic/noisy in services/ml/app/risk/features.py. They are not verified real-world outcomes, so the current individual risk score must not be used operationally.
- Roles are supplied by an editable X-Role request header and stored in browser local storage. This is not authentication or authorization.
- Evidence is metadata only. There is no immutable original file, cryptographic hash, custody log, malware scan, extraction review, or retention/legal-hold process.
- The Admin route is still a placeholder.
- Map generation can create coordinates outside the intended jurisdiction because the synthetic coordinate jitter is not bounded by a station polygon.
- The API Docker image does not copy the local models directory and its port is hard-coded. It is not ready for AppSail or AWS production deployment.
- CORS is localhost-only and the frontend API URL is localhost-specific.
- The repository currently has no deployment infrastructure, CI/CD workflow, secrets strategy, or production observability.
- Several UI pages display analytics but do not yet provide the complete contextual data-entry workflows envisioned in the project plan.

## 3. Safety, policy, and operating boundary

DRISHTI should be an investigation-support and aggregate resource-planning system, not an autonomous criminal-justice decision system.

The application must never:

- automatically arrest, detain, deny bail, determine guilt, or assign an operational "offender risk" decision to a person;
- use protected or proxy attributes to determine a criminal-justice outcome;
- identify a person from face analysis or use emotion/demographic face attributes for enforcement decisions;
- treat unreviewed OCR text, a social-media claim, or generic evidence metadata as verified fact.

The application may support human review by:

- forecasting verified incident counts by beat/area/time period;
- prioritising data-quality review and case-link review;
- finding similar records with a visible confidence score;
- presenting explanations, source documents, model version, limitations, and a reviewer decision;
- producing aggregate hotspot and workload signals.

Every prediction must include a human-review status and must be reversible/auditable.

## 4. Target architecture

~~~mermaid
flowchart LR
    U["Officer / analyst browser"] --> W["React web app<br/>CloudFront or Amplify"]
    W --> A["FastAPI core API<br/>ECS Fargate"]
    A --> DB["Supabase PostgreSQL now<br/>RDS PostgreSQL later"]
    A --> S3["S3 evidence bucket<br/>versioned + encrypted"]
    A --> Q["SQS job queue"]
    Q --> SF["Step Functions workflow"]
    SF --> X["OCR / extraction workers"]
    SF --> B["AWS Batch GPU job<br/>TabFM / TimesFM / embeddings"]
    B --> MR["Model artefacts + model registry"]
    B --> DB
    X --> DB
    A --> CW["CloudWatch / CloudTrail"]
~~~

### Prediction flow for a newly added FIR or evidence item

~~~mermaid
flowchart TD
    I["FIR, evidence file, transaction, media, or bulk record"] --> V["Validate schema, virus-scan, hash, encrypt, record custody"]
    V --> R["Store original in S3; metadata in PostgreSQL"]
    R --> E["OCR / transcription / structured extraction"]
    E --> H["Human review and correction"]
    H --> C["Canonical entities, links, location, time, and quality checks"]
    C --> F["Build versioned feature snapshot"]
    F --> P{"Prediction type"}
    P -->|immediate CPU| G["graph, similarity, rules, geo checks"]
    P -->|queued GPU| M["Batch TabFM / TimesFM / embeddings"]
    G --> O["Save inference, explanation, model version, reviewer status"]
    M --> O
    O --> UI["Show result as decision support, not an automated decision"]
~~~

Raw files do not directly “teach” a model. A document first becomes a candidate source, then extracted fields, then human-verified canonical fields, then a versioned feature snapshot. Only verified historical outcomes may later become training labels.

## 5. Model inventory and recommended AWS runtime

| Current capability | Current implementation | Recommended use | AWS runtime | Frequency |
|---|---|---|---|---|
| TabFM | Primary tabular model where available; saved BF16 artifact is about 3.05 GiB | Aggregate case/area triage after valid labels exist; not individual criminal-justice scoring | AWS Batch on g6.xlarge (NVIDIA L4, 22 GiB) or g5.xlarge (A10G, 22 GiB) | Nightly, weekly, or approved on-demand batch |
| TabPFN / XGBoost / HistGradientBoosting | Optional/fallback tabular paths | Baselines, calibration, and small CPU tests | Fargate for small baselines; Batch CPU/GPU for benchmark | Development and scheduled evaluation |
| TimesFM 2.5 200M | Real model if dependencies load; seasonal fallback otherwise | Beat/area/day or week incident-count forecast | Batch GPU first; use CPU only after a latency/cost benchmark | Daily or weekly |
| ST-GNN | Optional with a NumPy fallback | Spatial-temporal aggregate forecast only | Batch GPU when real model is enabled | Weekly or scheduled |
| Sentence-transformer similarity | Multilingual MPNet if available; hashing fallback | Similar cases and document retrieval | Fargate for low volume; Batch GPU for large backfills | On review and nightly index refresh |
| ST-DBSCAN, KDE, Hawkes/ETAS, graph algorithms, money rules | Algorithmic/rule-based | Hotspots, near-repeat, link analysis, financial red flags | Fargate CPU worker | On new verified records or scheduled |
| Chat/RAG | Optional OpenAI-compatible LLM and deterministic fallback | Policy/SOP/document assistance with citations | Amazon Bedrock or Catalyst QuickML RAG, subject to access controls | On demand |

Start GPU benchmarking with a single g6.xlarge or g5.xlarge. Both provide 22 GiB accelerator memory, which is a safer starting point than a 16 GiB T4 for the current BF16 artifact and its runtime overhead. Do not reserve a large GPU or create a 24/7 endpoint until a benchmark proves the required throughput and latency.

## 6. Phase 0 — Freeze the baseline and establish project controls

Priority: must complete before any cloud deployment.

### Implement

- [ ] Create a private Git repository and add a strict .gitignore for .env, model files, test exports, evidence, and generated data.
- [ ] Rotate every database password/API key that has appeared in local environment files or saved chat sessions.
- [ ] Create .env.example with only variable names and safe example values.
- [ ] Record the current schema version, model hashes, dependency lock files, and known demo data sources.
- [ ] Separate synthetic/demo data from any real data using different environments and buckets.
- [ ] Add an Architecture Decision Record that selects AWS as primary cloud and explicitly states whether Supabase remains temporary or is to be migrated to RDS.
- [ ] Create development, staging, and production AWS accounts or at least separate environments, budgets, and resource tags.
- [ ] Set AWS Budgets and CloudWatch cost alarms before starting GPU workloads.

### Deliverables

- .gitignore, .env.example, SECURITY.md, docs/adr/001-cloud-data-boundary.md
- A credential-rotation record stored outside the repository
- Dev/staging/prod environment matrix

### Acceptance criteria

- No real secret is committed or present in a browser build.
- A developer can start the project with only .env.example and documented setup.
- GPU jobs can be attributed by environment, model, and cost tag.

## 7. Phase 1 — Replace prototype access control with real identity and authorization

Priority: must complete before users outside the development team can access the system.

### Implement

- [ ] Replace the editable X-Role header and local-storage role authority with signed identity tokens.
- [ ] Choose one identity provider: Amazon Cognito is the AWS-first choice; Catalyst Authentication is acceptable only if Catalyst remains the identity boundary. Do not mix two authorities without federation design.
- [ ] Add roles such as SuperAdmin, Supervisor, Investigator, Analyst, EvidenceOfficer, DataSteward, Auditor, and ReadOnly.
- [ ] Validate JWT signature, issuer, audience, expiry, and role claims in FastAPI middleware.
- [ ] Enforce permissions on every route and every database action; hiding a button is not authorization.
- [ ] Implement PostgreSQL Row-Level Security policies scoped to station/department/case assignment and role.
- [ ] Add immutable audit events: login, read of restricted record, create/update/delete, export, evidence download, model run, review/override, and administrative change.
- [ ] Add short-lived S3 pre-signed upload/download URLs after the API authorizes a request.
- [ ] Add API rate limits, request IDs, security headers, CSRF protection where relevant, and session-expiry behaviour.

### Code areas

- Add services/ml/app/auth/
- Replace services/ml/app/cases/permissions.py and services/ml/app/money/permissions.py
- Replace web/src/providers/RoleProvider.tsx
- Add services/ml/sql/005_security_rls_audit.sql
- Add web/src/routes/admin/ as a real SuperAdmin console

### Acceptance criteria

- Changing a request header or browser local-storage value cannot escalate a user’s role.
- Unauthorized users cannot read records, files, exports, or predictions through the API.
- An auditor can trace who accessed an evidence file and why.

## 8. Phase 2 — Build the FIR, case, and evidence intake foundation

Priority: highest product gap.

### Input types to support

| Input family | Examples | Intake method | Processing |
|---|---|---|---|
| Structured FIR/case | FIR number, sections, complainant, accused/suspect, victims, offence, station, occurrence date/time, location | Guided form, API, CSV import | Validation, duplicate detection, geocoding review |
| Documents | FIR scan, statement, charge sheet, seizure memo, court order, lab report | PDF/image upload | Hash, malware scan, OCR, extraction, human review |
| Images/video/CCTV | Photos, screenshots, CCTV clip reference | File upload or controlled external reference | Hash, metadata extraction, object review; no automated identity decision |
| Audio | Call recording, witness audio, radio transcript | File upload | Transcription, language review, redaction |
| Digital/device material | Chat export, call detail records, device logs, IP logs | Template-driven CSV/JSON upload | Schema validation, provenance, entity review |
| Financial material | Bank transaction CSV, account/KYC reference, wallet/UPI reference | Secure structured import | Normalisation, rule-based red-flag analysis, graph links |
| Location material | GPS coordinates, beat patrol events, station boundaries | Map form, GeoJSON/CSV upload | Boundary validation and spatial indexing |
| External aggregates | Weather, public holidays, census/area aggregates | Approved connector/import | Source versioning and feature approval |

### Database objects to add

- [ ] EvidenceObject: storage key, SHA-256, byte size, MIME type, encryption key reference, retention date, legal-hold state.
- [ ] EvidenceVersion: relationship between an evidence object and each replacement/derived version.
- [ ] EvidenceCustodyEvent: actor, timestamp, action, reason, location/system, hash before/after where relevant.
- [ ] IngestionJob: source, status, owner, counts, errors, idempotency key, retry state.
- [ ] DocumentExtraction and ExtractionField: tool/model version, confidence, candidate value, reviewer decision, correction.
- [ ] EntityResolutionCandidate: suggested match, evidence, score, reviewer outcome.
- [ ] DataQualityIssue: severity, rule, affected field, owner, resolution.
- [ ] FeatureSnapshot: model input values, source versions, feature schema version, created time.
- [ ] ModelInference: model/version/hash, feature snapshot ID, output, explanation, review state, expiry.

### Code areas

- Add services/ml/sql/006_ingestion_evidence.sql
- Add services/ml/app/ingestion/
- Add services/ml/app/evidence/
- Add web/src/routes/intake/
- Expand web case explorer and evidence page rather than creating a single giant upload form.

### Acceptance criteria

- An authorized officer can create a FIR/case and attach an original file without placing the binary in PostgreSQL.
- Every file has a hash, storage location, version, custody history, and access log.
- An incomplete/invalid upload is quarantined and cannot influence an analysis.

## 9. Phase 3 — Ingestion, extraction, quality review, and entity resolution

Priority: complete before connecting new inputs to prediction.

### Implement

- [ ] Direct browser-to-S3 multipart uploads using a pre-signed URL; API creates the evidence metadata first.
- [ ] Quarantine new files and run malware scanning before they become available.
- [ ] Use Amazon Textract or an approved OCR service for scanned FIRs/documents; retain page, bounding-box, confidence, and source reference.
- [ ] Add audio transcription only after language, consent, retention, and access policies are approved.
- [ ] Present extracted fields in a review screen with side-by-side document page/source reference and a required accept/correct/reject decision.
- [ ] Use template-specific extractors for FIR, statement, transaction CSV, CDR, and seizure memo rather than one generic parser.
- [ ] Validate dates, sections, amounts, identifiers, station, and coordinates; flag impossible times/locations and duplicates.
- [ ] Implement human-approved entity resolution for people, phones, accounts, vehicles, addresses, and organisations. Never silently merge records.
- [ ] Create an import inbox for CSV/Excel/JSON bulk records with dry run, error download, duplicate report, commit approval, and rollback.
- [ ] Bound all map coordinates to authorised station/beat polygons; fix the present unbounded synthetic-coordinate behaviour.

### Workflow

1. Upload or create record.
2. Validate and quarantine.
3. Store the immutable original and custody event.
4. Extract candidate facts.
5. Human review/approve the facts.
6. Resolve candidate entity links.
7. Mark canonical records as verified.
8. Trigger eligible downstream analytic jobs.

### Acceptance criteria

- A reviewer can see exactly where each extracted fact came from.
- A corrected field has both original candidate value and correction history.
- Only verified canonical facts are eligible for live analytics or training datasets.

## 10. Phase 4 — Create the feature and prediction data contract

Priority: this is the bridge between intake and safe ML.

### Implement

- [ ] Define one feature schema per prediction task. Do not share an undefined “all evidence” feature table.
- [ ] Build a feature-generation service that reads only verified, authorised canonical data.
- [ ] Store a FeatureSnapshot before every inference. Include source record IDs/versions, transformations, time window, and feature-schema version.
- [ ] Add a data-quality gate that stops prediction when required fields are missing, stale, conflicting, or unverified.
- [ ] Implement model-specific triggers:
  - FIR/case event: update aggregate crime counts, hotspots, similar-case index.
  - Verified transaction: update money graph/rules.
  - Verified entity relationship: refresh graph analytics.
  - Verified beat/day count: enqueue TimeFM forecast refresh.
  - Approved batch: enqueue TabFM aggregate prioritisation.
- [ ] Add an inference status model: queued, running, completed, failed, stale, superseded, reviewed, rejected.
- [ ] Make every screen show data-as-of time and the last model/feature version.

### Required rule

New evidence may change a live prediction only after extraction and human verification creates a new canonical value. It must never cause a direct unlogged re-score merely because a file was uploaded.

### Acceptance criteria

- A displayed prediction can be reproduced from its FeatureSnapshot and model version.
- A user can tell whether a result is stale after new information is verified.
- The API cannot run a model with raw, unauthorised, or unreviewed input.

## 11. Phase 5 — Repair and govern the prediction models

Priority: required before presenting predictive outputs as more than a synthetic demo.

### 5.1 TabFM

- [ ] Retire the current synthetic individual “offender risk” output from operational workflows.
- [ ] Define a legitimate aggregate target, for example verified incident-count band for a beat/time window or case-review workload band.
- [ ] Build a labelled dataset only from verified historical outcomes with a written data dictionary.
- [ ] Use time-based train/validation/test splits and geographic holdouts; never randomly mix future records into training.
- [ ] Check for target leakage, duplicate cases, post-outcome fields, protected/proxy features, and missing-data bias.
- [ ] Compare TabFM against simple baselines: previous-period count, regularised logistic/linear model, XGBoost/HistGradientBoosting.
- [ ] Calibrate probabilities and display confidence/abstention, not an unexplained raw score.
- [ ] Record model card, intended use, excluded use, data period, features, metrics, limitations, and approver.

### 5.2 TimesFM and ST-GNN

- [ ] Forecast only aggregate beat/area time series.
- [ ] Backtest rolling windows against seasonal-naive and simple statistical baselines.
- [ ] Report MAE, RMSE, WAPE/sMAPE, coverage of prediction intervals, and error by station/season.
- [ ] Disable or label a forecast as low-confidence when volume is insufficient or source data is incomplete.
- [ ] Update forecasts on schedule, not on every keystroke.

### 5.3 Similarity, graph, and rules

- [ ] Evaluate case similarity with human-labelled relevant/not-relevant examples.
- [ ] Display matched fields and source links; do not imply a confirmed relationship.
- [ ] Treat graph centrality as an investigative navigation signal, not evidence of culpability.
- [ ] Version and test every financial rule; include a reason code and reviewer disposition.

### 5.4 Monitoring and retraining

- [ ] Add ModelRegistry/ModelVersion tables or use SageMaker Model Registry.
- [ ] Track model latency, error rate, confidence distribution, missing features, drift, calibration, and reviewer-overturn rate.
- [ ] Retrain only through an approved pipeline using a frozen dataset snapshot.
- [ ] Require offline evaluation, approval, canary evaluation, and rollback plan before promotion.
- [ ] Keep a deterministic fallback when a model service is unavailable.

### Acceptance criteria

- Each production model has a documented purpose, target, metric threshold, owner, and rollback version.
- No model output is used as the sole basis for a decision about a person.
- A failed or low-confidence model has a safe user-visible fallback.

## 12. Phase 6 — Finish the user workflows and missing product features

Priority: build after the secure data foundation; otherwise screens will create ungoverned data.

### Case and FIR workflow

- [ ] FIR wizard with draft, validation, submit, correction, duplicate check, and supervisor review.
- [ ] Case lifecycle: registration, assignment, investigation tasks, arrest, chargesheet, court milestones, closure/reopen.
- [ ] Victim/witness safeguards, redaction, consent/notice fields where legally applicable, and tightly restricted visibility.
- [ ] Case timeline populated from real audit/domain events, not static demo entries.
- [ ] Station/beat/geofence selector with boundary validation.

### Evidence workflow

- [ ] Evidence intake inbox, upload progress, quarantine state, OCR/extraction review, custody timeline, download/export authorization.
- [ ] Batch import review and error-repair screen.
- [ ] Evidence expiry/retention/legal-hold administration.
- [ ] Hash verification and an evidence-package export manifest.

### Investigation and analysis workflow

- [ ] Link-analysis review queue with accept/reject/needs-more-information decisions.
- [ ] Similar-case search with source evidence and similarity explanation.
- [ ] Map layers for verified cases, calls, hotspots, station/beat boundaries, and time slider.
- [ ] Correct invalid map data and differentiate synthetic/demo records visually.
- [ ] Forecast screen with time horizon, interval, source data freshness, backtest metric, and download.
- [ ] Explainability screen with model version, top contributing authorised features, limitations, and reviewer sign-off.
- [ ] Report builder with access-controlled PDF export and report watermark/audit event.

### Administration and governance

- [ ] Replace the Admin placeholder with users, roles, stations/beats, source systems, retention policies, model registry, feature flags, and audit search.
- [ ] Add data-quality dashboard, queue health, ingestion errors, model job status, and budget/usage dashboard.
- [ ] Add notification preferences and task assignment/escalation.

### Chat/RAG

- [ ] Restrict retrieval by the same case/station/role permissions as the normal API.
- [ ] Return citations to approved source snippets and refuse when source access is absent.
- [ ] Keep RAG for policies, SOPs, approved knowledge and optionally authorised case summaries; do not allow it to invent investigative facts.
- [ ] Log prompts/responses with PII-minimising retention controls.

## 13. Phase 7 — AWS deployment implementation

Priority: do this after Phases 0–2 are complete.

### 7.1 Package the application

- [ ] Split the current service into a small API image and a separate GPU worker image:
  - services/api: FastAPI, auth, case/evidence APIs, lightweight algorithms.
  - services/gpu-worker: TabFM, TimesFM, heavy embeddings, batch interfaces.
- [ ] Split dependency files into API and worker requirements so the API image does not install every ML package.
- [ ] Fix the current Dockerfile: copy only required code, do not bundle the 3 GB model by default, read the PORT environment variable, run as a non-root user, add health checks, and log JSON.
- [ ] Store versioned model artifacts in a private S3 model bucket. The worker downloads/caches the exact approved version.
- [ ] Build/push images to Amazon ECR using CI, never from a manual production laptop.

### 7.2 Deploy core services

- [ ] Deploy the React application through Amplify Hosting or S3 + CloudFront.
- [ ] Deploy FastAPI as an ECS Fargate service behind an Application Load Balancer.
- [ ] Put API, worker, database, and S3 access in a VPC with least-privilege security groups and IAM roles.
- [ ] Use AWS WAF/rate controls at the public edge.
- [ ] Store API/database keys in Secrets Manager; inject them at runtime.
- [ ] Configure allowed production origins; remove localhost CORS from production.
- [ ] Add CloudWatch dashboards, alarms, structured logs, tracing, and CloudTrail.

### 7.3 Run prediction workloads

- [ ] Create an SQS queue for prediction requests and a dead-letter queue for failures.
- [ ] Create a Step Functions workflow: validate request -> create feature snapshot -> select job -> run job -> validate output -> save ModelInference -> notify UI.
- [ ] Create AWS Batch job definitions for tabular, time-series, and embedding workloads.
- [ ] Start with EC2 g6.xlarge or g5.xlarge GPU compute environments that scale down to zero after work completes.
- [ ] Use Spot only for restartable, non-urgent, non-sensitive batch jobs with checkpoints; use on-demand for critical jobs.
- [ ] Add idempotency keys so retries do not write duplicate predictions.
- [ ] Keep baseline/rule/graph jobs on CPU Fargate where practical.

### 7.4 When to use SageMaker

Use AWS Batch first for training, backfills, scheduled forecasts, and approved re-scoring. Add SageMaker asynchronous inference or a real-time endpoint only when measured demand requires a response within seconds/minutes and the model passes operations/security review. A continuously running GPU endpoint costs credits even when no one is requesting a result.

### Acceptance criteria

- A new commit can be promoted dev -> staging -> production through CI/CD.
- The GPU worker can run one model job from an SQS request and write a versioned result.
- No model, evidence file, database secret, or private API is publicly reachable.
- Scaling GPU workers to zero does not lose queued jobs.

## 14. Phase 8 — Optional Zoho Catalyst use with the AWS plan

AWS should be the primary deployment path now. Use Catalyst credits only where they add a clear benefit; do not duplicate authoritative data.

| Catalyst service | Recommended DRISHTI use | AWS-first alternative | Decision |
|---|---|---|---|
| AppSail | Lightweight staging API or demo container | ECS Fargate | Optional |
| Web Client Hosting / Slate | Demo frontend | Amplify or S3 + CloudFront | Optional |
| Authentication | Only if it becomes the one chosen identity boundary | Cognito | Choose one, not both |
| Stratus | Evidence-object storage if available in the account | S3 | Choose one authoritative file store |
| Zia OCR/Text Analytics | Trial OCR/extraction for non-sensitive pilot documents | Textract | Optional pilot |
| QuickML RAG | Policy/SOP knowledge assistant | Bedrock Knowledge Bases/RAG | Optional |
| Functions / Signals / Circuits | Demo workflow automation | Lambda/EventBridge/Step Functions | Optional |
| Job Scheduling | Lightweight scheduled jobs | EventBridge Scheduler / Batch schedule | Optional |
| Data Store / NoSQL | Avoid duplicating case database | RDS/Supabase + DynamoDB only when needed | Not initially |
| Zia AutoML | Do not plan on it for an India deployment | SageMaker/your model pipeline | Not available in India |

Avoid legacy Catalyst File Store and legacy Cron for new work; the announced end-of-life date was 30 April 2026. If you use Catalyst, confirm the services available in your specific account/region before designing around them.

## 15. Phase 9 — Testing, security verification, and release readiness

### Implement

- [ ] Keep fast unit tests separate from database integration tests so a local command cannot write to production Supabase.
- [ ] Use disposable test database/S3 buckets and synthetic fixtures.
- [ ] Add API authorization tests for every role/resource combination.
- [ ] Add upload security, file type, size, hash, and custody tests.
- [ ] Add migration tests from an empty database and from a prior schema.
- [ ] Add end-to-end browser tests for FIR intake, evidence review, case search, and prediction review.
- [ ] Add model reproducibility tests using frozen feature snapshots and expected outputs/ranges.
- [ ] Add load tests for upload, queue, and forecast workloads.
- [ ] Run dependency, container, IaC, secret, and SAST scans in CI.
- [ ] Perform access-control and evidence-chain audit with a security reviewer.
- [ ] Test backup restore, job retry, model rollback, S3 recovery, and incident response runbooks.

### Acceptance criteria

- Deployment is blocked if tests, scans, migrations, or authorization checks fail.
- A staging demonstration runs entirely with synthetic data.
- Disaster recovery and model rollback have been exercised, not merely documented.

## 16. Phase 10 — Future implementations after the core launch

These are valuable, but should not delay the security/data/ML foundation.

- [ ] Multilingual FIR and evidence interface with reviewed translation.
- [ ] Offline-first field capture with encrypted local queue and controlled sync.
- [ ] Mobile companion for authorised evidence capture, including time/location/device provenance.
- [ ] Configurable reports/dashboards by station, district, and leadership role.
- [ ] External system connectors for approved RMS/CCTNS/court/lab sources, with source contracts and reconciliation.
- [ ] Event-driven notifications, escalation SLAs, and workload assignment.
- [ ] Data retention, archival, deletion, legal-hold, and privacy request workflows.
- [ ] Differential access/redaction views for witnesses, victims, juveniles, and sensitive cases.
- [ ] Knowledge-base governance, document expiry, and evaluation set for RAG.
- [ ] Model-drift dashboard and periodic independent model review.
- [ ] Multi-tenant architecture only if there is a real requirement and formal data-isolation design.

## 17. Complete remaining-feature checklist

### Non-negotiable before deployment

- [ ] Secret rotation and Git hygiene
- [ ] Real authentication, API authorization, and PostgreSQL RLS
- [ ] Audit logging and role/station scoping
- [ ] Secure evidence object storage, hashes, custody, and access control
- [ ] FIR/case/evidence contextual intake
- [ ] Validation, extraction review, canonicalisation, and quality gates
- [ ] Remove synthetic individual risk prediction from operational use
- [ ] Valid aggregate targets, model evaluation, monitoring, and human-review workflow
- [ ] Deployment/IaC/CI/CD, monitoring, backups, and incident procedures
- [ ] Production CORS, HTTPS, rate limits, WAF, secret management

### High-value product gaps

- [ ] Real Admin/governance console
- [ ] Full FIR and case lifecycle
- [ ] Evidence upload/review/custody/export
- [ ] Bulk import and source reconciliation
- [ ] Entity-resolution review queue
- [ ] Correct jurisdiction-bounded map data
- [ ] Real timelines/tasks/notifications
- [ ] Case similarity evidence/explanation
- [ ] Forecast confidence, freshness, and backtests
- [ ] Role-filtered RAG with citations
- [ ] Reports and audited exports

### AWS work

- [ ] ECR images for API and GPU worker
- [ ] ECS Fargate API
- [ ] S3 evidence/model buckets with encryption/versioning/retention
- [ ] SQS + Step Functions orchestration
- [ ] AWS Batch GPU queue/environment/job definitions
- [ ] Cognito, Secrets Manager, CloudWatch, CloudTrail, WAF
- [ ] CI/CD and dev/stage/prod environment isolation
- [ ] Cost budgets, tags, quotas, and GPU benchmark report

## 18. Suggested implementation order

1. Phase 0: secrets, repository hygiene, environment and cost controls.
2. Phase 1: real identity, authorization, RLS, and audit.
3. Phase 2: FIR/case/evidence schemas and secure intake.
4. Phase 3: extraction, review, data quality, and entity resolution.
5. Phase 4: feature snapshots and prediction triggers.
6. Phase 5: valid aggregate models, evaluation, and governance.
7. Phase 6: complete the analyst/admin workflows.
8. Phase 7: AWS infrastructure, Batch GPU jobs, CI/CD, observability.
9. Phase 9: security, load, recovery, and release verification.
10. Phase 10: only then add advanced integrations and mobile/offline features.

## 19. AWS reference links

- AWS GPU instance families and accelerator memory: https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html
- AWS Batch job definitions: https://docs.aws.amazon.com/batch/latest/userguide/job_definitions.html
- Amazon S3 overview: https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html
- S3 Object Lock: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html
- Amazon Bedrock overview: https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html

## 20. First implementation sprint

The first practical sprint should deliver only the foundation:

1. Rotate secrets and create .env.example/.gitignore.
2. Replace X-Role with real JWT authentication and route-level authorization.
3. Add RLS/audit migration.
4. Create the EvidenceObject, EvidenceCustodyEvent, IngestionJob, FeatureSnapshot, and ModelInference schema.
5. Add direct-to-S3 evidence upload with hash/custody record.
6. Split FastAPI API and GPU worker Docker images.
7. Run a benchmark of TabFM and TimesFM on a small approved synthetic dataset in AWS Batch g6.xlarge/g5.xlarge.

Do not start with a permanent GPU endpoint or with automatic scoring of individuals. First prove the secure data path and benchmark batch cost/latency; then promote only validated aggregate prediction tasks.
