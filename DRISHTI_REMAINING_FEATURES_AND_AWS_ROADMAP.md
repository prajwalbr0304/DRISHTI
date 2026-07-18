# DRISHTI: Remaining Features and AWS Implementation Roadmap

Status: implementation roadmap, updated from a read-only live Supabase and datagen audit on 2026-07-16  
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
- The current datagen geography code now uses bounded district/SHO polygons and its offline self-test passes, but the existing live Supabase dataset predates or does not reflect that correction: 6,732 cases fall outside the Karnataka state polygon and 17,653 fall outside their assigned district polygon. The live dataset must be regenerated or repaired before spatial modelling.
- The API Docker image does not copy the local models directory and its port is hard-coded. It is not ready for AppSail or AWS production deployment.
- CORS is localhost-only and the frontend API URL is localhost-specific.
- The repository currently has no deployment infrastructure, CI/CD workflow, secrets strategy, or production observability.
- Several UI pages display analytics but do not yet provide the complete contextual data-entry workflows envisioned in the project plan.

### Live Supabase audit snapshot

The live database was crawled through DATABASE_URL in transaction-level read-only mode. No row contents, credentials, secret values, auth identities, or evidence payloads were exported.

#### Schema deployment

- All 58 user tables defined across the local SQL files are deployed in the live public schema; there are no table-level local/live deployment differences.
- The public schema contains 67 relations when application views, materialized views, PostGIS catalogue objects, and the user tables are counted.
- PostgreSQL is version 17.6.
- PostGIS, pgvector, pg_trgm, pgRouting, pgcrypto, pg_stat_statements, UUID, and Supabase Vault extensions are installed.
- All declared constraints inspected are validated and every application table has a primary key.
- The application has three custom database functions: fn_casemaster_biu, fn_set_updated_at, and fn_entity_shortest_path.

#### Live data volume

| Area | Live count |
|---|---:|
| Cases/FIR-like records | 100,000 |
| Accused rows | 304,278 |
| Victim rows | 251,708 |
| Complainant rows | 121,383 |
| Arrest/surrender rows | 92,244 |
| Chargesheets | 39,925 |
| Case evidence rows | 0 |
| Entity graph nodes | 51,446 |
| Network edges | 69,206 |
| Financial accounts | 2,525 |
| Financial transactions | 13,003 |
| Model versions | 32 |
| Model inference rows | 51,380 |
| Case embeddings | 20,000 |
| Audit events | 0 |
| Saved queries | 0 |

This is enough volume for application load testing and batch-performance experiments. It is not sufficiently realistic, diverse, or correctly linked for supervised ML validation or an operational demonstration.

#### Critical live security state

- Row-Level Security is disabled on every public application table.
- There are zero public-schema RLS policies.
- The Supabase anon and authenticated roles currently hold SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, and TRIGGER privileges across 64 public relations.
- The custom five-row users table is not connected to Supabase Auth.
- Supabase Auth contains zero users, identities, sessions, or MFA factors.
- Supabase Storage contains zero buckets and zero objects.
- Supabase Vault contains zero stored secrets.
- audit_logs contains zero rows, so current database/application activity is not being captured in the application audit model.

Treat the current Supabase project as a private synthetic development database only. Do not expose its publishable key to an untrusted client until grants, RLS, authentication, storage policies, and API authorization are corrected.

#### Identity and graph integrity failures

- Accused.PersonID is generated as A1, A2, and so on inside each case. Across 304,278 accused rows there are only 26 distinct PersonID values.
- The name generator has only 2,175 distinct first-name/surname combinations. Some identical accused names occur more than 1,000 times.
- The 15,000 EntityGraph person nodes contain zero populated AccusedMasterID foreign keys.
- EntityGraph.RefID stores the generator's offender-array index rather than a real AccusedMasterID. Only 12 person nodes happen to match both a real accused primary key and the same name.
- Zero cases are connected to graph-person nodes through the intended AccusedMasterID foreign key.
- The current case-network fallback joins cases by accused name, so the limited name pool creates many false cross-case relationships.
- All 69,206 NetworkEdge rows have no EvidenceCaseID, so graph relationships are synthetic assertions rather than evidence-backed relationships.

The identity layer must be redesigned around a stable canonical person/entity identifier before graph analytics, hidden associations, repeat-offender features, or TabFM inputs are trusted.

#### Scenario and lifecycle inconsistencies

- All five case categories are generated with nearly the same child-record behaviour instead of category-specific lifecycle rules.
- UDR, NCR, PAR, Zero FIR, and normal FIR records can all receive arrests and chargesheets through the same generic probabilities.
- 5,222 cases have the status Charge Sheeted but no ChargesheetDetails row.
- 2,465 Missing Person cases exist, and 1,000 of them have a chargesheet even though the generator created no accused and no act/section rows for those records.
- Every case has a CourtID even when no court event exists.
- The profile fields known_accused and urban_bias are defined but never used by the generator.
- Gender generation uses only values 1 and 2; trans, unknown, undisclosed, and unrecorded scenarios are absent.
- There are no unknown accused, aliases, organisation accused, unidentified persons, relationship-to-case records, or reviewed entity-resolution candidates.
- There are no witness, statement, property, seizure, vehicle, weapon, device, communication/CDR, forensic, medical, court-event, bail, or case-outcome tables.

#### Geographic integrity

- The current boundary self-test passes for all 32 reference districts and simulated placement remains within the state.
- The live data does not satisfy that current generator contract.
- Exact local-polygon validation found 6,732 case coordinates outside the Karnataka state polygon.
- Exact assigned-district validation found 17,653 case coordinates outside the district linked through PoliceStationID.
- Jurisdiction/station polygons and station coordinates are not persisted in the live database, so the database cannot enforce spatial containment.

#### ML and model-governance integrity

- The current TabFM/TabPFN risk label is explicitly synthesised from the same features that are used to predict it.
- CrimeRiskScore contains 15,000 accused-level scores; these are not valid operational outcomes.
- TabFM features include career offences, juvenile flag, gang role, graph centrality, flagged financial data, hidden associations, and district crime rate. They do not currently consume a governed FIR/evidence feature snapshot.
- The risk feature builder uses rank-matching by duplicate name to manufacture an accused mapping because the true graph foreign key is empty.
- All 32 ModelVersion rows are marked active; 24 have no ArtifactURI and no TrainedAt value.
- ModelInference has JSON inputs/outputs but no separate FeatureSnapshot, source-record version set, prediction request, review, expiry, or supersession relationship.
- CrimePrediction covers all 32 districts and nine crime heads but has no unit/beat-level rows in the current table.
- The social, weather, and economic indicators each come from a single synthetic source and share a uniform monthly cadence.

### Audit conclusion

Keep the 100,000-case database as a synthetic UI/performance fixture. Do not use it as the final training/evaluation dataset. First secure Supabase, redesign canonical identity/evidence/event schemas, update the generator to use explicit scenario definitions, regenerate the data, run integrity tests, and only then benchmark or deploy predictive models.

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
- [ ] Immediately classify the current Supabase project as synthetic-development-only and block untrusted/public client access until Phase 1 is complete.
- [ ] Back up the current schema and synthetic fixture before security/schema migrations; do not classify this backup as a production or ML-validation dataset.
- [ ] Record the audited baseline: 58 deployed user tables, zero public RLS policies, zero Supabase Auth users, zero Storage buckets, zero evidence rows, and zero application audit events.
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
- The Supabase publishable/anon identity cannot write directly to unrestricted public tables.
- A developer can start the project with only .env.example and documented setup.
- GPU jobs can be attributed by environment, model, and cost tag.

## 7. Phase 1 — Replace prototype access control with real identity and authorization

Priority: must complete before users outside the development team can access the system.

### Implement

- [ ] Replace the editable X-Role header and local-storage role authority with signed identity tokens.
- [ ] Choose one identity provider. If Supabase remains the initial database/auth boundary, configure Supabase Auth and link public.users.auth_user_id to auth.users.id. If Cognito becomes the authority, validate Cognito JWTs in FastAPI and map the token subject to public.users. Do not leave the current disconnected five-row demo-user table as identity.
- [ ] Add roles such as SuperAdmin, Supervisor, Investigator, Analyst, EvidenceOfficer, DataSteward, Auditor, and ReadOnly.
- [ ] Validate JWT signature, issuer, audience, expiry, and role claims in FastAPI middleware.
- [ ] Enforce permissions on every route and every database action; hiding a button is not authorization.
- [ ] Implement PostgreSQL Row-Level Security policies scoped to station/department/case assignment and role.
- [ ] Revoke anon/authenticated INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, and TRIGGER privileges from application tables by default. Re-grant only the minimum operations needed through reviewed policies/API paths.
- [ ] Enable and FORCE RLS on case, person, evidence, financial, graph, model-input, chat, and audit tables after service/API compatibility tests are in place.
- [ ] Add restrictive S3 or Supabase Storage bucket/object policies before the first evidence object is uploaded.
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
- Supabase anon cannot directly read restricted case/person/evidence tables or mutate application tables.
- Every authenticated operation is constrained by user, role, unit/station, case assignment, and record sensitivity.
- Unauthorized users cannot read records, files, exports, or predictions through the API.
- An auditor can trace who accessed an evidence file and why.

## 8. Phase 2 — Build the FIR, case, and evidence intake foundation

Priority: highest product gap.

### Input types to support

| Input family | Examples | Intake method | Processing |
|---|---|---|---|
| Structured FIR/case | FIR number, sections, complainant, accused/suspect, victims, offence, station, occurrence date/time, location | Guided form, API, CSV import | Validation, duplicate detection, geocoding review |
| People and organisations | Known/unknown accused, victim, complainant, witness, informant, guardian, organisation, aliases, identity/contact/address records | Contextual case forms and entity-resolution inbox | Canonical identity, role history, restricted attributes, duplicate review |
| Documents | FIR scan, statement, charge sheet, seizure memo, court order, lab report | PDF/image upload | Hash, malware scan, OCR, extraction, human review |
| Images/video/CCTV | Photos, screenshots, CCTV clip reference | File upload or controlled external reference | Hash, metadata extraction, object review; no automated identity decision |
| Audio | Call recording, witness audio, radio transcript | File upload | Transcription, language review, redaction |
| Digital/device material | Chat export, call detail records, device logs, IP logs | Template-driven CSV/JSON upload | Schema validation, provenance, entity review |
| Financial material | Bank transaction CSV, account/KYC reference, wallet/UPI reference | Secure structured import | Normalisation, rule-based red-flag analysis, graph links |
| Property, seizure, and forensic material | Recovered property, vehicle, weapon, narcotic/contraband item, sample, fingerprint/DNA/lab reference | Guided seizure/exhibit forms plus files | Item identity, quantity/unit, seal/package, custody, lab-result linkage |
| Statements and interviews | Witness/complainant/accused statements, interview notes, translations | Guided statement form, document/audio upload | Versioning, speaker/recorder, language, review, restricted access |
| Location material | GPS coordinates, beat patrol events, station boundaries | Map form, GeoJSON/CSV upload | Boundary validation and spatial indexing |
| Court and lifecycle events | Transfer, remand, bail, hearing, chargesheet, disposal, conviction/acquittal, closure/reopen | Event form/API/import | Append-only event timeline, status derivation, outcome-label eligibility |
| Intelligence/tips | Source report, lead, external reference, confidence/reliability assessment | Restricted inbox | Source classification, corroboration, review; never treated as verified fact automatically |
| External aggregates | Weather, public holidays, census/area aggregates | Approved connector/import | Source versioning and feature approval |

### Database objects to add

- [ ] CanonicalPerson and CanonicalOrganisation: stable identity independent of a case record.
- [ ] CasePartyRole: links a canonical person/organisation to a case as accused, victim, complainant, witness, informant, guardian, or other typed role, including valid dates and verification state.
- [ ] PersonAlias, PersonIdentifier, PersonContact, PersonAddress, and EntityMergeHistory: governed identity attributes and reversible entity-resolution decisions.
- [ ] CaseSource and CaseVersion: intake source, source-system key, source document, immutable version history, correction reason, and reviewer.
- [ ] CaseEvent: append-only lifecycle events from registration through transfer, investigation, court activity, closure, and reopen.
- [ ] EvidenceObject: storage key, SHA-256, byte size, MIME type, encryption key reference, retention date, legal-hold state.
- [ ] EvidenceVersion: relationship between an evidence object and each replacement/derived version.
- [ ] EvidenceCustodyEvent: actor, timestamp, action, reason, location/system, hash before/after where relevant.
- [ ] EvidenceItem and EvidenceCaseLink: the logical item/exhibit and its possibly many case relationships, replacing the current metadata-only CaseEvidence design.
- [ ] EvidenceEntityLink: reviewed links from an evidence item/extraction to a canonical person, organisation, phone, account, device, vehicle, location, or property item.
- [ ] Statement and StatementVersion: speaker/case/evidence relationship, language, recording/transcript source, correction/redaction history, and access classification.
- [ ] Seizure, PropertyItem, Vehicle, WeaponItem, ForensicSample, and LabResult: structured exhibit-specific data instead of burying all details in Description.
- [ ] Device, DeviceArtifact, CommunicationEvent, LocationObservation, and DigitalImportBatch: structured digital/CDR/chat/IP/GPS material with provenance.
- [ ] CourtEvent, BailEvent, CaseDisposition, and OutcomeObservation: verified process/outcome records separated from the current single CaseStatusID.
- [ ] IngestionJob: source, status, owner, counts, errors, idempotency key, retry state.
- [ ] IngestionRecord and SourceRecord: row/document-level provenance, source checksum, parser version, original values, and canonical target.
- [ ] DocumentExtraction and ExtractionField: tool/model version, confidence, candidate value, reviewer decision, correction.
- [ ] EntityResolutionCandidate: suggested match, evidence, score, reviewer outcome.
- [ ] DataQualityIssue: severity, rule, affected field, owner, resolution.
- [ ] JurisdictionBoundary and UnitLocation: versioned state/district/unit/beat/SHO polygons and station coordinates so containment can be enforced in the database.
- [ ] FeatureDefinition and FeatureSchemaVersion: approved feature meaning, data type, source, time cutoff, transformation, sensitivity classification, and allowed model tasks.
- [ ] FeatureSnapshot: model input values, source record/version set, time cutoff, feature schema version, quality status, and hash.
- [ ] PredictionRequest, PredictionResult, and PredictionReview: queued request, model/version/hash, output, explanation, human disposition, expiry, supersession, and rollback relationship.
- [ ] TrainingDatasetSnapshot and OutcomeLabel: immutable training cohort, observation window, label window, verified outcome source, exclusions, and approval.
- [ ] Extend ModelVersion with image/artifact digest, training-dataset ID, feature-schema ID, approval status, approver, evaluation report, deployment environment, and rollback version.

### Code areas

- Add services/ml/sql/006_ingestion_evidence.sql
- Add services/ml/sql/007_identity_case_workflow.sql
- Add services/ml/sql/008_feature_prediction_governance.sql
- Add services/ml/sql/009_jurisdiction_external_events.sql
- Add services/ml/app/ingestion/
- Add services/ml/app/evidence/
- Add services/ml/app/identity/
- Add services/ml/app/case_events/
- Add services/ml/app/features/
- Add services/ml/app/predictions/
- Add web/src/routes/intake/
- Add web/src/routes/review/
- Expand web case explorer and evidence page rather than creating a single giant upload form.

### Acceptance criteria

- An authorized officer can create a FIR/case and attach an original file without placing the binary in PostgreSQL.
- A repeat person has one stable canonical identity and can appear in several cases/roles without name-based joining.
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
- [ ] Implement human-approved entity resolution for people, phones, accounts, devices, vehicles, addresses, and organisations. Store stable canonical IDs, match evidence, reviewer decision, merge history, and unmerge support. Never silently merge records or use name equality as identity.
- [ ] Create an import inbox for CSV/Excel/JSON bulk records with dry run, error download, duplicate report, commit approval, and rollback.
- [ ] Persist versioned station/beat/SHO polygons and station locations in PostgreSQL; validate every coordinate against both its assigned jurisdiction and the state boundary. Regenerate or quarantine the 6,732 live out-of-state and 17,653 assigned-district mismatches.

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
- [ ] Archive or clearly mark the existing 15,000 accused-level CrimeRiskScore rows as synthetic-demo-only.
- [ ] Remove the current duplicate-name rank matching between EntityGraph and Accused. No model run may proceed until graph persons link through a reviewed canonical identity/foreign key.
- [ ] Exclude juvenile status, caste, religion, gender, protected attributes, and unreviewed intelligence assertions from individual decision features. Prefer aggregate area/case-workload tasks.
- [ ] Define a legitimate aggregate target, for example verified incident-count band for a beat/time window or case-review workload band.
- [ ] Build a labelled dataset only from verified historical outcomes with a written data dictionary.
- [ ] Use time-based train/validation/test splits and geographic holdouts; never randomly mix future records into training.
- [ ] Check for target leakage, duplicate cases, post-outcome fields, protected/proxy features, and missing-data bias.
- [ ] Compare TabFM against simple baselines: previous-period count, regularised logistic/linear model, XGBoost/HistGradientBoosting.
- [ ] Calibrate probabilities and display confidence/abstention, not an unexplained raw score.
- [ ] Record model card, intended use, excluded use, data period, features, metrics, limitations, and approver.
- [ ] Ensure every active ModelVersion has a real artifact/image digest, trained timestamp, feature-schema version, dataset snapshot, evaluation report, and approval. Do not mark scaffold/fallback registrations active by default.

### 5.2 TimesFM and ST-GNN

- [ ] Forecast only aggregate beat/area time series.
- [ ] Regenerate or quarantine invalid coordinates before spatial/temporal training; do not train on the current jurisdiction mismatches.
- [ ] Replace the one-source synthetic monthly indicator series with source-versioned weather, holiday/event, mobility/workload, and approved area-level covariates where legally and operationally justified.
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
- [ ] Lock down the live Supabase anon/authenticated grants and enable tested RLS policies
- [ ] Configure the chosen real identity provider; remove the disconnected demo-user authority
- [ ] Create the private evidence bucket and object-access policies
- [ ] Real authentication, API authorization, and PostgreSQL RLS
- [ ] Audit logging and role/station scoping
- [ ] Stable canonical person/entity IDs; eliminate PersonID A1/A2 reuse and name-based cross-case joins
- [ ] Evidence-backed graph relationships and reviewed entity resolution
- [ ] Regenerate/quarantine live spatial mismatches using persisted jurisdiction polygons
- [ ] Category-specific case lifecycle rules and consistency constraints
- [ ] Secure evidence object storage, hashes, custody, and access control
- [ ] FIR/case/evidence contextual intake
- [ ] Validation, extraction review, canonicalisation, and quality gates
- [ ] Remove synthetic individual risk prediction from operational use
- [ ] Regenerate a scenario-complete synthetic fixture before ML benchmarking
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
2. Lock down Supabase grants, configure the chosen real JWT identity, and replace X-Role authorization.
3. Add and test RLS/audit policies before exposing the frontend to Supabase/API resources.
4. Add canonical identity and CasePartyRole; migrate graph/case logic away from duplicate-name joins.
5. Create EvidenceItem/Object/Version/Custody, IngestionJob/Record, FeatureSnapshot, PredictionResult/Review, and OutcomeLabel schemas.
6. Add a private S3 evidence bucket and direct-to-S3 upload with hash, quarantine, custody, and object policies.
7. Update datagen with stable identities, category-specific lifecycle state machines, evidence/digital/court/outcome scenarios, intentional data-quality cases, and persisted jurisdiction polygons.
8. Regenerate a smaller validation fixture first and make all scenario/integrity tests pass; then regenerate the 100,000-case performance fixture.
9. Split FastAPI API and GPU worker Docker images.
10. Only after the new feature/label contract is valid, benchmark TabFM and TimesFM on an approved synthetic dataset in AWS Batch g6.xlarge/g5.xlarge.

Do not start with a permanent GPU endpoint or with automatic scoring of individuals. First prove the secure data path and benchmark batch cost/latency; then promote only validated aggregate prediction tasks.

## 21. Exactly where SageMaker should be used in DRISHTI

SageMaker should own the managed ML lifecycle. It should not replace the main FastAPI application, PostgreSQL database, evidence store, authentication system, or ingestion workflow.

### Recommended SageMaker responsibilities

| DRISHTI requirement | SageMaker component | Recommended implementation |
|---|---|---|
| Develop and benchmark TabFM/TimesFM | SageMaker training jobs or Studio notebooks | Use only synthetic or approved de-identified datasets during early development |
| Run scheduled predictions over many records | SageMaker Batch Transform or an AWS Batch GPU job | Preferred for nightly TabFM scoring, TimesFM forecasts, and embedding backfills |
| Run a prediction requested from the application | SageMaker asynchronous endpoint | Preferred when a response can take seconds/minutes |
| Run low-latency interactive prediction | SageMaker real-time endpoint | Use only when a measured requirement justifies an always-running GPU |
| Store approved model versions | SageMaker Model Registry | Separate groups such as drishti-tabfm and drishti-timesfm |
| Track experiments and metrics | SageMaker Experiments or managed MLflow | Store dataset version, feature schema, parameters, metrics, and code commit |
| Automate training/evaluation/approval | SageMaker Pipelines | Build, validate, register, approve, and deploy without manual model copying |
| Monitor production model behaviour | SageMaker Model Monitor plus DRISHTI application metrics | Monitor input drift, missing features, latency, errors, confidence, and reviewer overturns |

### Model-by-model placement

#### TabFM

- Package TabFM, its Python dependencies, inference handler, and model-loading logic in a custom SageMaker inference container.
- Store the approved model artifact in a private S3 model bucket.
- Use Batch Transform or AWS Batch for full-dataset/nightly scoring.
- Use an asynchronous or real-time endpoint only for an approved request that genuinely needs an immediate result.
- Keep outputs aggregate or review-supporting. Do not deploy the present synthetic individual offender-risk score.

#### TimesFM

- Use a separate TimesFM container and endpoint/job definition.
- Build time-series features in FastAPI/background workers, then send a compact validated series to SageMaker.
- Run forecasts by beat/area/day or week.
- Save the forecast, interval, horizon, input-data cutoff, model version, and backtest metrics in PostgreSQL.
- Prefer a scheduled Batch Transform/AWS Batch job unless users require interactive what-if forecasting.

#### Embeddings and similarity

- Keep low-volume embedding generation in the CPU API initially.
- Move document/case embedding backfills to a SageMaker processing/batch job when volume becomes large.
- Store only approved text chunks and access-control metadata in the retrieval index.

#### ST-GNN

- Keep the NumPy fallback in the API.
- Run the full GPU ST-GNN as a SageMaker training/batch workload after spatial and temporal labels are validated.

### What must remain outside SageMaker

- React frontend and normal FastAPI routes
- FIR/case CRUD and PostgreSQL transactions
- Original evidence files and chain of custody
- Authentication, authorization, RLS, and audit events
- OCR/document extraction orchestration
- SQS/Step Functions workflows
- Rule-based financial alerts and lightweight graph operations

### Recommended runtime decision

1. Use AWS Batch GPU for the first TabFM and TimesFM benchmark.
2. Add SageMaker Model Registry and experiment tracking once the input/label contract is valid.
3. Deploy a staging SageMaker endpoint only after the custom container passes local and Batch tests.
4. Prefer an asynchronous endpoint for application-triggered predictions.
5. Add a real-time endpoint only if measured user requirements need low latency.

SageMaker Serverless Inference currently does not support GPUs. It is therefore not the correct hosting mode for GPU TabFM or TimesFM. Use a GPU-backed real-time/asynchronous endpoint, Batch Transform, a SageMaker job, or AWS Batch.

## 22. SageMaker API setup for DRISHTI

This section gives a safe setup sequence for Windows PowerShell. Replace every value inside angle brackets before running a command.

### 22.1 Prerequisites

Install and verify:

- AWS CLI v2
- Docker Desktop
- Python 3.11 or 3.12
- boto3 in the FastAPI environment
- An AWS account/region with a SageMaker GPU quota
- AWS IAM Identity Center or another short-lived credential method

Do not place an AWS access key or secret key in the repository, frontend, Docker image, .env committed to Git, or Kiro steering file.

Configure a development profile:

~~~powershell
aws configure sso --profile drishti-dev
aws sso login --profile drishti-dev
aws sts get-caller-identity --profile drishti-dev
~~~

Set session variables:

~~~powershell
$env:AWS_PROFILE = "drishti-dev"
$env:AWS_REGION = "ap-south-1"
$AccountId = aws sts get-caller-identity --query Account --output text
$Region = $env:AWS_REGION
$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$RepositoryName = "drishti-sagemaker"
$ImageUri = "$Registry/${RepositoryName}:tabfm-v1"
~~~

Use ap-south-1 only if the required SageMaker instance type and quota are available. Otherwise select the nearest approved region that satisfies data-residency requirements.

### 22.2 Create the AWS resources

Create these resources through infrastructure as code for staging/production:

- S3 bucket for model artifacts, for example drishti-models-ACCOUNT-REGION
- S3 bucket/prefix for batch inputs and outputs
- ECR repository named drishti-sagemaker
- SageMaker execution role
- DRISHTI API task role with InvokeEndpoint permission
- Kiro developer permission set/role
- CloudWatch log groups and alarms
- KMS key if a customer-managed key is required

For an initial development ECR repository:

~~~powershell
aws ecr create-repository `
  --repository-name $RepositoryName `
  --image-scanning-configuration scanOnPush=true `
  --region $Region
~~~

Authenticate Docker:

~~~powershell
aws ecr get-login-password --region $Region |
  docker login --username AWS --password-stdin $Registry
~~~

### 22.3 IAM roles

Create two different IAM roles.

#### SageMaker execution role

This role is assumed by SageMaker. Give it only:

- read access to the approved model-artifact S3 prefix;
- read/write access to the SageMaker batch input/output prefixes;
- permission to pull the DRISHTI image from its ECR repository;
- CloudWatch logging permissions;
- KMS permissions only for the relevant key, if used.

Its trust policy must allow the SageMaker service:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "sagemaker.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

#### DRISHTI API task role

The ECS/FastAPI task does not need permission to create or delete endpoints. It normally needs only:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sagemaker:InvokeEndpoint",
        "sagemaker:InvokeEndpointAsync"
      ],
      "Resource": [
        "arn:aws:sagemaker:<REGION>:<ACCOUNT_ID>:endpoint/drishti-*"
      ]
    }
  ]
}
~~~

#### Kiro developer role

Create a separate development permission set/role for Kiro. Scope it to:

- list/describe SageMaker resources;
- create/update approved drishti-* development models, endpoint configurations, endpoints, transform jobs, and model packages;
- invoke drishti-* development endpoints;
- push/pull only the drishti-sagemaker ECR repository;
- read/write only the DRISHTI model and batch S3 prefixes;
- PassRole only for the exact SageMaker execution-role ARN;
- the approved AWS region.

Do not use AdministratorAccess. Keep production mutations in a different role that requires explicit elevation/approval. Endpoint deletion and production promotion should require a separate confirmation or CI/CD approval.

### 22.4 Prepare the custom inference container

Google TabFM and TimesFM are not built-in SageMaker algorithms. Use a SageMaker-compatible custom container or extend an AWS PyTorch/Hugging Face inference image.

The custom inference container must:

- listen on port 8080;
- answer the health route /ping;
- accept prediction requests on /invocations;
- load one approved model version during startup;
- validate feature_schema_version and reject unknown schemas;
- return JSON with prediction, confidence/interval, model version, and warnings;
- avoid logging FIR text, evidence contents, personal information, or full request payloads.

Suggested new project structure:

~~~text
services/
  gpu-worker/
    Dockerfile.sagemaker
    requirements.txt
    serve.py
    handlers/
      tabfm_handler.py
      timesfm_handler.py
    tests/
      test_ping.py
      test_invocations.py
infra/
  sagemaker/
    deploy_endpoint.py
    delete_endpoint.py
    iam/
    payloads/
~~~

Build and push the image after the container is implemented:

~~~powershell
docker build `
  -f services/gpu-worker/Dockerfile.sagemaker `
  -t "${RepositoryName}:tabfm-v1" `
  .

docker tag "${RepositoryName}:tabfm-v1" $ImageUri
docker push $ImageUri
~~~

The model artifact should be a model.tar.gz file in S3. Do not add the 3 GB model artifact to Git or the normal FastAPI image.

### 22.5 Create a staging model and endpoint

The normal creation sequence is:

1. Upload the versioned model artifact to S3.
2. Create a SageMaker Model referencing the ECR image and S3 artifact.
3. Create an EndpointConfig referencing that model and an approved instance type.
4. Create the Endpoint.
5. Wait until the endpoint status is InService.
6. Invoke it with a synthetic test payload.
7. Add alarms and shut it down when it is not needed.

Example deployment logic for infra/sagemaker/deploy_endpoint.py:

~~~python
import os
import boto3

region = os.environ["AWS_REGION"]
image_uri = os.environ["SAGEMAKER_IMAGE_URI"]
model_data_url = os.environ["SAGEMAKER_MODEL_DATA_URL"]
execution_role_arn = os.environ["SAGEMAKER_EXECUTION_ROLE_ARN"]

model_name = os.getenv("SAGEMAKER_MODEL_NAME", "drishti-tabfm-v1")
endpoint_config_name = os.getenv(
    "SAGEMAKER_ENDPOINT_CONFIG_NAME",
    "drishti-tabfm-v1-config",
)
endpoint_name = os.getenv(
    "SAGEMAKER_ENDPOINT_NAME",
    "drishti-tabfm-staging",
)

sm = boto3.client("sagemaker", region_name=region)

sm.create_model(
    ModelName=model_name,
    PrimaryContainer={
        "Image": image_uri,
        "ModelDataUrl": model_data_url,
        "Environment": {
            "DRISHTI_MODEL_TYPE": "tabfm",
            "DRISHTI_MODEL_VERSION": "v1",
            "DRISHTI_FEATURE_SCHEMA_VERSION": "tabfm-aggregate-v1",
        },
    },
    ExecutionRoleArn=execution_role_arn,
    Tags=[
        {"Key": "Project", "Value": "DRISHTI"},
        {"Key": "Environment", "Value": "staging"},
    ],
)

sm.create_endpoint_config(
    EndpointConfigName=endpoint_config_name,
    ProductionVariants=[
        {
            "VariantName": "AllTraffic",
            "ModelName": model_name,
            "InitialInstanceCount": 1,
            "InstanceType": os.getenv(
                "SAGEMAKER_INSTANCE_TYPE",
                "ml.g5.xlarge",
            ),
            "InitialVariantWeight": 1.0,
        }
    ],
    Tags=[
        {"Key": "Project", "Value": "DRISHTI"},
        {"Key": "Environment", "Value": "staging"},
    ],
)

sm.create_endpoint(
    EndpointName=endpoint_name,
    EndpointConfigName=endpoint_config_name,
    Tags=[
        {"Key": "Project", "Value": "DRISHTI"},
        {"Key": "Environment", "Value": "staging"},
    ],
)

sm.get_waiter("endpoint_in_service").wait(EndpointName=endpoint_name)
print(f"Endpoint ready: {endpoint_name}")
~~~

Verify that ml.g5.xlarge is offered by SageMaker in the selected region and request a quota increase if required. Do not assume that an EC2 instance family is automatically available as the corresponding SageMaker instance type.

Set the deployment variables before running the script:

~~~powershell
$env:SAGEMAKER_IMAGE_URI = $ImageUri
$env:SAGEMAKER_MODEL_DATA_URL = "s3://<MODEL_BUCKET>/models/tabfm/v1/model.tar.gz"
$env:SAGEMAKER_EXECUTION_ROLE_ARN = "arn:aws:iam::<ACCOUNT_ID>:role/drishti-sagemaker-execution"
$env:SAGEMAKER_ENDPOINT_NAME = "drishti-tabfm-staging"
$env:SAGEMAKER_INSTANCE_TYPE = "ml.g5.xlarge"

python infra/sagemaker/deploy_endpoint.py
~~~

### 22.6 Test the SageMaker Runtime API

Create a synthetic payload. Never use raw real FIR/evidence data for the first connectivity test.

~~~json
{
  "request_id": "synthetic-smoke-test-001",
  "model_task": "aggregate-area-review",
  "feature_schema_version": "tabfm-aggregate-v1",
  "records": [
    {
      "area_id": "DEMO-BEAT-01",
      "incident_count_30d": 12,
      "incident_count_previous_30d": 10,
      "open_case_count": 4,
      "season": 2
    }
  ]
}
~~~

Invoke it with the AWS CLI:

~~~powershell
aws sagemaker-runtime invoke-endpoint `
  --endpoint-name drishti-tabfm-staging `
  --content-type application/json `
  --accept application/json `
  --body fileb://infra/sagemaker/payloads/tabfm-smoke-test.json `
  infra/sagemaker/payloads/tabfm-response.json `
  --region $Region
~~~

Check endpoint state and logs:

~~~powershell
aws sagemaker describe-endpoint `
  --endpoint-name drishti-tabfm-staging `
  --region $Region

aws logs describe-log-streams `
  --log-group-name /aws/sagemaker/Endpoints/drishti-tabfm-staging `
  --region $Region
~~~

### 22.7 Connect FastAPI to SageMaker

The browser must never call SageMaker directly and must never receive AWS credentials. Use this route:

~~~text
React -> authenticated FastAPI route -> feature snapshot/quality gate
      -> SageMaker Runtime -> validate response -> ModelInference table
      -> reviewed result returned to React
~~~

Configure the lightweight API client as follows.

Add boto3 to services/ml/requirements.txt or the future API-only requirements file:

~~~text
boto3
~~~

Add these fields to the existing Settings class in services/ml/app/config.py:

~~~python
aws_region: str = "ap-south-1"
sagemaker_tabfm_endpoint: str = ""
sagemaker_timesfm_endpoint: str = ""
sagemaker_invocation_enabled: bool = False
~~~

Configure them through environment variables:

~~~text
AWS_REGION=ap-south-1
SAGEMAKER_TABFM_ENDPOINT=drishti-tabfm-staging
SAGEMAKER_TIMESFM_ENDPOINT=drishti-timesfm-staging
SAGEMAKER_INVOCATION_ENABLED=false
~~~

Keep SAGEMAKER_INVOCATION_ENABLED false until staging validation is complete.

Suggested services/ml/app/inference/sagemaker_client.py:

~~~python
import json
from functools import lru_cache

import boto3

from app.config import get_settings


@lru_cache(maxsize=1)
def get_runtime_client():
    settings = get_settings()
    return boto3.client(
        "sagemaker-runtime",
        region_name=settings.aws_region,
    )


def invoke_endpoint(endpoint_name: str, payload: dict) -> dict:
    settings = get_settings()
    if not settings.sagemaker_invocation_enabled:
        raise RuntimeError("SageMaker invocation is disabled")

    response = get_runtime_client().invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Accept="application/json",
        Body=json.dumps(payload).encode("utf-8"),
    )

    return json.loads(response["Body"].read().decode("utf-8"))
~~~

The prediction route must:

- authenticate and authorize the user;
- load verified canonical records;
- run the data-quality gate;
- create and persist a FeatureSnapshot;
- send only the approved feature payload to SageMaker;
- validate the returned model/schema version;
- persist ModelInference and explanation metadata;
- return a human-review state, not an automatic operational decision;
- use request IDs, timeouts, retries with idempotency, and a circuit breaker;
- fall back to a safe baseline or show unavailable when SageMaker fails.

The ECS task role supplies temporary AWS credentials automatically. Do not configure AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY in the FastAPI environment.

### 22.8 Endpoint shutdown

Development endpoints continue to cost money while running. Delete the staging endpoint when the test session is finished:

~~~powershell
aws sagemaker delete-endpoint `
  --endpoint-name drishti-tabfm-staging `
  --region $Region
~~~

Delete old endpoint configurations/models only after confirming they are not used. Keep the approved artifact and Model Registry version for reproducibility.

## 23. Connect SageMaker and AWS to Kiro chat

### Important command distinction

In Kiro CLI, /chat manages saved chat sessions and checkpoints. It does not connect to or invoke SageMaker.

To control AWS from a Kiro conversation:

1. Start Kiro chat in the DRISHTI workspace.
2. Connect the managed AWS MCP Server.
3. Sign in to AWS with the scoped DRISHTI development role.
4. Ask Kiro in normal language to inspect or operate SageMaker.
5. Optionally create a manual /sagemaker steering command.

### 23.1 Start Kiro in the correct workspace

~~~powershell
Set-Location "C:\Users\Prajwal\Desktop\DRISHTI"
kiro-cli chat
~~~

Kiro can read and edit files in the current workspace through its normal read/write tools. AWS resource access is separate and is controlled by MCP plus AWS IAM.

### 23.2 Add the managed AWS MCP Server

For Kiro CLI:

~~~powershell
kiro-cli mcp add `
  --name aws-mcp `
  --url https://aws-mcp.us-east-1.api.aws/mcp
~~~

For Kiro IDE, create or update:

~~~text
C:\Users\Prajwal\Desktop\DRISHTI\.kiro\settings\mcp.json
~~~

Use:

~~~json
{
  "mcpServers": {
    "aws-mcp": {
      "url": "https://aws-mcp.us-east-1.api.aws/mcp?oauth=initialize",
      "disabled": false,
      "autoApprove": []
    }
  }
}
~~~

Restart Kiro. The first AWS tool invocation should open AWS Sign-in. Sign in using the DRISHTI development permission set, not a root account or administrator role.

Keep autoApprove empty. Review every infrastructure mutation until the workflow is stable.

### 23.3 Verify Kiro tools and permissions

Inside Kiro CLI chat:

~~~text
/tools
~~~

Recommended permissions:

- read: trusted for the DRISHTI workspace;
- write: trusted only for the DRISHTI workspace while actively implementing;
- shell: per-request approval;
- AWS/MCP mutation tools: per-request approval;
- production role: unavailable during normal development.

Do not use /tools trust-all for a session connected to AWS.

The phrase “read, edit, create anything” should mean:

- read/edit/create files inside the DRISHTI workspace;
- read/create/update/invoke only DRISHTI development AWS resources;
- no unrestricted access to other folders, AWS projects, accounts, or production resources;
- destructive AWS actions require explicit confirmation.

### 23.4 Create a reusable /sagemaker Kiro command

Create this manual steering file:

~~~text
C:\Users\Prajwal\Desktop\DRISHTI\.kiro\steering\sagemaker.md
~~~

Suggested contents:

~~~markdown
---
inclusion: manual
name: sagemaker
description: Safely build, inspect, deploy, invoke, and troubleshoot DRISHTI SageMaker resources.
---

# DRISHTI SageMaker operating rules

- Work only in the current DRISHTI workspace.
- Operate only on AWS resources prefixed or tagged DRISHTI/drishti.
- Use the configured development AWS identity and approved region.
- Never print or store AWS credentials.
- Never send raw FIR/evidence content or personal data unless explicitly approved for the environment.
- Before a write, deployment, update, or deletion, show the intended AWS operations, resource names, region, estimated always-on cost risk, and rollback.
- Ask for confirmation before mutations.
- Never delete a production resource.
- Prefer infrastructure as code and edit files in infra/sagemaker before executing changes.
- Run local tests and a synthetic smoke test before invoking an endpoint.
- Record model version, image digest, model artifact URI, feature schema, and endpoint configuration.
- Keep SageMaker Serverless out of GPU TabFM/TimesFM deployment plans.
- Delete temporary development endpoints after verification.
~~~

After saving it, type this inside Kiro chat:

~~~text
/sagemaker
~~~

Then provide the task. The slash command adds the DRISHTI SageMaker rules to the conversation; the AWS MCP tools perform AWS operations after approval.

### 23.5 Useful Kiro chat prompts

Read-only inventory:

~~~text
/sagemaker List all SageMaker models, model packages, endpoint configurations,
endpoints, transform jobs, and training jobs whose names or tags contain DRISHTI.
Use read-only calls and summarise status, region, instance type, and cost risk.
~~~

Inspect project and create implementation files:

~~~text
/sagemaker Read the DRISHTI model-loading code and requirements. Create the
services/gpu-worker SageMaker container, /ping and /invocations handlers,
container tests, and infra/sagemaker deployment scripts. Do not deploy yet.
~~~

Build deployment plan:

~~~text
/sagemaker Inspect the TabFM artifact and current Docker setup. Propose a
staging SageMaker deployment using a custom ECR image and S3 model artifact.
Show all files and AWS API calls you intend to use, then wait for approval.
~~~

Create staging resources:

~~~text
/sagemaker Using the approved infra/sagemaker files, create only the missing
DRISHTI staging resources. Use the development role, approved region, drishti-*
names/tags, and per-operation approval. Do not modify production.
~~~

Invoke a test:

~~~text
/sagemaker Invoke drishti-tabfm-staging with the synthetic smoke-test payload.
Validate the response schema, show latency and CloudWatch errors, and do not
send any real FIR, evidence, or personal data.
~~~

Connect the FastAPI route:

~~~text
/sagemaker Read the FastAPI configuration and prediction routers. Implement a
SageMaker Runtime client using the ECS task role, add a disabled-by-default
feature flag, persist FeatureSnapshot and ModelInference records, and add unit
tests with boto3 calls mocked. Do not place AWS credentials in code.
~~~

Update an endpoint:

~~~text
/sagemaker Compare the currently deployed staging model with the approved Model
Registry version. Prepare a new endpoint configuration and an update/rollback
plan. Wait for approval before calling UpdateEndpoint.
~~~

Stop costs after testing:

~~~text
/sagemaker Show all running DRISHTI development endpoints and jobs. Prepare the
commands to stop or delete temporary staging compute while retaining model
artifacts and registry versions. Wait for confirmation before executing.
~~~

### 23.6 Kiro session management

Use /chat only for Kiro session operations such as listing, saving, loading, or switching conversations. A normal flow is:

~~~text
kiro-cli chat
> /chat
> /sagemaker
> List the current DRISHTI SageMaker staging resources using read-only calls.
~~~

The first line starts Kiro, /chat manages the Kiro session, /sagemaker loads the project-specific operating rules, and the natural-language request causes Kiro to select the AWS MCP tools.

## 24. SageMaker and Kiro security checklist

- [ ] AWS root credentials are never used in Kiro.
- [ ] Kiro signs in through AWS Identity Center/OAuth with short-lived credentials.
- [ ] The Kiro development role is restricted to the approved account, region, prefixes/tags, S3 prefixes, ECR repository, and PassRole target.
- [ ] autoApprove is empty for AWS MCP mutations.
- [ ] Kiro read/write permission is limited to the DRISHTI workspace.
- [ ] Production deployment requires CI/CD or an elevated approval role.
- [ ] Real FIR/evidence/PII is not pasted into chat or sent in a connectivity test.
- [ ] CloudTrail records resource-management API calls.
- [ ] CloudWatch records endpoint health without logging sensitive payloads.
- [ ] Temporary GPU endpoints are deleted after tests.
- [ ] Model artifacts remain private, encrypted, versioned, and reproducible.
- [ ] Every deployment records container image digest, artifact hash, feature schema, model version, approver, and rollback target.

## 25. Additional SageMaker and Kiro references

- SageMaker custom inference-container contract: https://docs.aws.amazon.com/sagemaker/latest/dg/adapt-inference-container.html
- SageMaker CreateModel and batch-transform relationship: https://docs.aws.amazon.com/cli/latest/reference/sagemaker/create-model.html
- SageMaker endpoint creation: https://docs.aws.amazon.com/cli/latest/reference/sagemaker/create-endpoint.html
- SageMaker Runtime InvokeEndpoint API: https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_InvokeEndpoint.html
- SageMaker inference hosting options: https://docs.aws.amazon.com/sagemaker/latest/dg/model-deploy-feature-matrix.html
- SageMaker Serverless limitations: https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html
- SageMaker Model Registry concepts: https://docs.aws.amazon.com/sagemaker/latest/dg/model-registry-models.html
- Managed AWS MCP Server setup: https://docs.aws.amazon.com/agent-toolkit/latest/userguide/getting-started-aws-mcp-server.html
- Kiro MCP setup: https://kiro.dev/docs/cli/mcp/
- Kiro slash commands: https://kiro.dev/docs/chat/slash-commands/
- Kiro CLI tool permissions: https://kiro.dev/docs/cli/chat/permissions/

## 26. Datagen sufficiency verdict

### Final verdict

The current generator is strong for volume, deterministic replay, broad crime-head distribution, temporal seasonality, district allocation, application demos, and stressing PostgreSQL/analytics. It is not yet sufficient for:

- canonical identity/entity-resolution testing;
- evidence ingestion and chain-of-custody testing;
- realistic case-category/lifecycle testing;
- supervised outcome-label generation;
- graph truth/evidence testing;
- multimodal input testing;
- data-quality and late-arriving-data workflows;
- spatial model validation against the current live fixture;
- operational model evaluation.

Do not throw the generator away. Refactor it into a scenario-driven generator and regenerate the database.

### What the generator already covers well

| Area | Existing coverage |
|---|---|
| Scale | 100,000 cases and large child/analytics tables |
| Reproducibility | Seeded deterministic generation |
| Geography code | Current version has real Karnataka district/taluk polygons, station planning, SHO cells, bounded incident sampling, and a passing offline self-test |
| Temporal distribution | Hour, weekday, month/season templates |
| Crime taxonomy | 9 major heads, 26 subheads, 8 acts, 45 sections |
| Case categories/statuses | All current lookup values appear |
| Core persons | Accused, victims, complainants with varied cardinality |
| Operational records | Arrests, chargesheets, act/section links, occurrence rows |
| Analytics fixtures | Graph, gang, financial, indicators, embeddings, summaries, alerts, predictions, chat |
| Financial patterns | Structuring, fan-in/consolidation, layering, and background transfers |

### What must be corrected

| Finding | Why it matters | Required correction |
|---|---|---|
| Only 26 distinct Accused.PersonID values | PersonID is an intra-case sequence, not identity | Create stable CanonicalPersonID; CasePartyRole links a person to each case |
| Only 2,175 distinct generated names | Name collisions create false joins | Treat names as attributes/aliases, never identifiers; deliberately test same-name/different-person scenarios |
| EntityGraph person AccusedMasterID is empty | Graph cannot prove which case person a node represents | Link graph nodes to CanonicalEntityID and reviewed case-party records |
| Graph RefID stores offender-array index | Accidental rather than referential linkage | Persist generator canonical IDs first; use true FKs |
| Case network joins by name | Produces false shared-accused cases | Join only through canonical identity/case-role tables |
| All NetworkEdge.EvidenceCaseID values are null | Graph links have no provenance | Generate EvidenceEntityLink/SourceRecord-backed relationships and confidence/review state |
| All case categories share generic probabilities | UDR/NCR/PAR/Zero FIR lifecycles are unrealistic | Use category-specific state machines approved by domain experts |
| Missing Person cases can have chargesheets | Contradictory scenario | Add missing-person-specific events; only allow a different lifecycle after an explicit conversion/reclassification event |
| 5,222 Charge Sheeted statuses lack a chargesheet row | Status/document inconsistency | Derive status from append-only events or validate state-transition prerequisites |
| Every case has a CourtID | No pre-court/no-court scenario | Make court assignment an event/result, not a mandatory generated field |
| known_accused and urban_bias are unused | Intended diversity never reaches data | Either implement and test them or remove them from the profile contract |
| Gender only uses two values | Missing unknown/undisclosed/trans/not-recorded data paths | Add governed configurable values and missingness; never use protected attributes as criminal-justice prediction features |
| Evidence rows and storage objects are zero | Cannot test the requested input workflow | Generate evidence metadata, safe synthetic files/manifests, extraction results, review, custody, and failures |
| Current live spatial data fails containment | Invalid spatial training/evaluation | Regenerate from current boundary code and persist jurisdictions |
| Current labels are generated from current features | Circular task with misleading metrics | Generate outcome events in a later label window independent of feature construction |
| All ModelVersion rows are active | No real lifecycle/approval | Generate staged/approved/retired/shadow states and complete metadata |

## 27. Datagen v2 implementation plan

### 27.1 Generator architecture

Refactor datagen into explicit domains:

~~~text
datagen/
  config.py
  engine.py
  scenario_registry.py
  identity.py
  organisation.py
  geography.py
  cases.py
  case_events.py
  people_roles.py
  evidence.py
  statements.py
  property_seizure.py
  digital.py
  financial.py
  court_outcomes.py
  external_context.py
  intelligence.py
  labels.py
  quality_scenarios.py
  validation.py
  fixtures/
~~~

Recommended load order:

1. Reference data and versioned jurisdiction boundaries.
2. Canonical people, organisations, addresses, contacts, devices, vehicles, accounts, and aliases.
3. Cases plus source/version metadata.
4. Case-party roles.
5. Append-only case events and category-specific workflow.
6. Evidence items/objects, synthetic file manifests, custody, statements, property/seizure, digital and financial inputs.
7. Extraction candidates, reviewer decisions, entity-resolution candidates, and data-quality issues.
8. Verified canonical links.
9. Outcome events after the feature observation cutoff.
10. Training labels and feature snapshots.
11. Graph/embedding/forecast/demo analytics derived from verified inputs.

### 27.2 Stable identity rules

- Generate CanonicalPersonID once per synthetic person.
- Reuse that ID when a repeat person appears in multiple cases.
- Generate a separate CasePartyRole row for every appearance and role.
- Keep AccusedMasterID/VictimMasterID/ComplainantID as case-role record IDs if backward compatibility is needed.
- Add CanonicalPersonID foreign keys to the legacy person tables during migration.
- Generate same-name/different-person and alias/same-person scenarios intentionally.
- Generate unknown/unidentified parties without inventing a false identity.
- Store merge/split decisions in EntityMergeHistory.
- EntityGraph must reference CanonicalEntityID; case relationships must come from reviewed junction tables.
- Do not use names, phone strings, or array indexes as identity keys.

### 27.3 Case-category lifecycle scenarios

Create a state machine per category rather than applying one global arrest/chargesheet rate. The allowed transitions must be reviewed by a Karnataka police/legal domain expert.

At minimum generate:

- standard FIR investigation paths with and without identified accused;
- Zero FIR creation, origin jurisdiction, transfer, receiving-unit acknowledgement, and linkage to the continuing case;
- UDR/inquest/postmortem/closure paths and explicit conversion to another case type when applicable;
- NCR/PAR enquiry paths, closure, escalation, transfer, and conversion events;
- missing-person report, last-seen data, search events, trace/recovery/closure, and explicit reclassification where applicable;
- transferred cases with source and destination units;
- reopened and corrected cases;
- cases with no arrest, no chargesheet, no court assignment, or unresolved status;
- multiple chargesheet/supplementary-document scenarios if the final schema supports them;
- late court/disposition outcomes occurring after the model observation window.

Do not encode legal assumptions only in Python comments. Put transition rules in a versioned scenario definition and validate them with tests.

### 27.4 Crime-domain input scenarios

| Crime/domain | Additional structured synthetic inputs |
|---|---|
| Property offences | PropertyItem, ownership, serial/identifier, value, recovery, seizure, disposal |
| Vehicle theft/traffic | Vehicle, registration/chassis/engine synthetic tokens, driver role, road segment, collision/event data, recovery |
| Cyber/economic | Device, account/wallet, transaction, phone/email/IP synthetic tokens, complaint document, communication events |
| Body/women/child-sensitive cases | Restricted statement, medical/forensic reference, support-person/guardian role, redaction/access classification |
| Drug/smuggling/excise | Seized item, substance/category, quantity/unit, package/seal, sample, lab-result event |
| Public order | Event/location/time window, group/organisation roles, property damage; aggregate analytics only |
| Missing person | Canonical missing person, aliases/photo reference, last-seen event/location, search lead, trace/recovery status |
| Financial network | KYC/source record, transaction reference, currency, channel, account owner resolution, reviewed case link |

All identifiers must be unmistakably synthetic and must never resemble copied real identifiers.

### 27.5 Evidence scenarios

Generate logical evidence separately from storage objects.

Evidence types:

- FIR/complaint document;
- statement/interview;
- image/photo/screenshot;
- CCTV/video reference;
- audio/voice recording;
- physical exhibit;
- property/vehicle/weapon/substance item;
- medical/forensic/lab report;
- device export/chat/CDR/IP/location file;
- transaction/KYC/bank statement dataset;
- court/order/chargesheet document;
- external intelligence/source reference.

For each applicable evidence type generate:

- logical EvidenceItem;
- zero or more EvidenceObject versions;
- SHA-256 and byte-size metadata;
- storage key pointing to a development-only synthetic fixture bucket or manifest;
- case/entity relationships;
- custody events;
- extraction job/results;
- confidence by field/page/segment;
- human accept/correct/reject review;
- redaction/access classification;
- retention/legal-hold state.

Intentionally include:

- quarantined/malware-test fixture;
- unsupported or corrupt file;
- duplicate file/hash;
- revised/replaced document;
- low-confidence OCR/transcription;
- Kannada/English/mixed-language text;
- conflicting extracted date/amount/name;
- evidence linked to multiple cases;
- custody transfer and custody-break alert;
- unauthorised access attempt in the audit fixture;
- late-arriving evidence that supersedes an old prediction.

### 27.6 Data-quality scenarios

Natural-frequency generation alone will rarely exercise important failure paths. Create a deterministic golden fixture that deliberately covers:

- missing optional values;
- missing required values rejected at staging;
- wrong type/format;
- duplicate FIR/source key;
- conflicting person identifiers;
- same name but different people;
- same person with aliases;
- unknown accused;
- impossible temporal order;
- coordinate outside assigned jurisdiction;
- source/canonical value disagreement;
- low extraction confidence;
- stale source version;
- deleted/retracted source;
- partial batch import;
- retry/idempotency duplication;
- model feature missing/stale;
- unapproved source attempting to trigger prediction.

Keep these records in staging/quarantine or a synthetic_meta schema where appropriate. Do not mix deliberately invalid rows into canonical production tables unless the table is specifically designed to hold invalid/staged data.

### 27.7 Fixture sizes

Maintain three fixtures:

| Fixture | Purpose | Suggested size |
|---|---|---:|
| Golden scenario fixture | Deterministic tests; every branch/error represented | 1,000–5,000 cases |
| Statistical ML fixture | Distribution, backtesting, feature/label experiments | 50,000–200,000 cases |
| Performance fixture | Database/UI/queue/load testing | 100,000+ cases plus large evidence/transaction objects |

Every named scenario must have an explicit minimum count in the golden fixture. Rare/error scenarios may be intentionally oversampled for tests; they must be excluded or reweighted when estimating real-world model metrics.

### 27.8 Generator validation gates

Add datagen/validation.py and tests that fail generation when:

- a canonical person is represented by multiple unrelated IDs without a reviewed split;
- a graph person lacks CanonicalEntityID;
- a graph edge lacks a source/evidence relationship or an explicit synthetic-unverified status;
- a status transition lacks its prerequisite event/document;
- a case category violates its scenario state machine;
- a coordinate is outside its assigned jurisdiction/state;
- a non-converted missing-person/UDR scenario receives an incompatible downstream event;
- a model label occurs before the end of the label window;
- a feature uses post-outcome data;
- a protected/restricted field enters an unauthorised feature schema;
- an evidence object lacks hash/custody/storage metadata;
- an extraction influences canonical data without review;
- scenario minimum coverage is not met.

## 28. Where to implement every input feature

### Frontend placement

Do not build one enormous form. Put actions in the case context where users need them.

| UI location | Features |
|---|---|
| web/src/routes/intake/fir/ | New FIR/case wizard, source/import choice, draft, validation, duplicate review, jurisdiction map |
| web/src/routes/intake/imports/ | CSV/JSON/document batch upload, dry run, mapping, errors, commit approval |
| web/src/routes/review/extractions/ | OCR/transcription field review with source page/segment |
| web/src/routes/review/entities/ | Match/merge/split candidates with supporting records |
| web/src/routes/review/quality/ | DataQualityIssue queue and resolution |
| web/src/routes/cases/subpages/PeoplePage.tsx | Canonical people/organisations, case roles, aliases, identifiers, contacts, addresses |
| existing EvidencePage.tsx | Replace metadata-only form with upload/intake, quarantine, processing state, versions, custody, review, legal hold |
| web/src/routes/cases/subpages/StatementsPage.tsx | Statements/interviews, transcript, language, version, redaction |
| web/src/routes/cases/subpages/PropertyPage.tsx | Seizures, exhibits, property, vehicle, weapon, forensic sample/lab result |
| web/src/routes/cases/subpages/DigitalPage.tsx | Devices, chats, CDR/IP/location imports and processing |
| existing MoneyMode/case money page | Financial accounts, transaction imports, reviewed links and reason codes |
| existing TimelinePage.tsx | Append-only CaseEvent/CourtEvent/Outcome timeline |
| web/src/routes/admin/ | Users/auth mappings, roles, units, boundaries, source systems, retention, models, feature schemas, audits |

### Backend placement

~~~text
services/ml/app/
  auth/
  intake/
  ingestion/
  evidence/
  extraction/
  identity/
  entity_resolution/
  case_events/
  statements/
  property/
  digital/
  financial_import/
  data_quality/
  features/
  predictions/
  model_registry/
  audit/
  jobs/
~~~

Responsibilities:

- intake validates the request and creates a draft/source record;
- ingestion manages idempotent jobs and staging records;
- evidence manages S3 metadata, hashes, versions, custody, access, retention, and legal hold;
- extraction stores candidate fields only;
- identity/entity_resolution creates canonical entities only after review;
- case_events derives/validates lifecycle state;
- data_quality blocks invalid canonicalisation/prediction;
- features builds versioned snapshots from approved sources;
- predictions invokes CPU/AWS Batch/SageMaker and persists reviewable results;
- audit records every sensitive read/write/export/model action.

### Database migration placement

| Migration | Main contents |
|---|---|
| 005_security_rls_audit.sql | auth_user_id mapping, grants, RLS, policies, assignments, sensitivity, audit events/triggers |
| 006_ingestion_evidence.sql | source systems, ingestion jobs/records, evidence items/objects/versions/custody, extraction/review |
| 007_identity_case_workflow.sql | canonical people/organisations/entities, aliases/identifiers/contacts/addresses, case roles, events, statements, property/digital/court/outcomes |
| 008_feature_prediction_governance.sql | feature definitions/schemas/snapshots, dataset snapshots, outcome labels, prediction requests/results/reviews, ModelVersion extensions |
| 009_jurisdiction_external_events.sql | versioned state/district/unit/beat/SHO boundaries, unit locations, holidays/events and approved external source versions |

Use backward-compatible views while migrating existing screens. Do not immediately delete legacy Accused/Victim/ComplainantDetails/CaseEvidence tables; add canonical foreign keys/views, migrate readers/writers, verify, then retire obsolete fields.

## 29. How newly added inputs reach predictions

### Core rule

Adding a new database column or uploading a file does not automatically make an existing model use it.

A new input becomes usable only after:

1. storage and provenance are implemented;
2. validation/extraction is implemented;
3. human review creates a verified canonical value;
4. a FeatureDefinition is approved;
5. a new FeatureSchemaVersion includes it;
6. a training dataset is rebuilt with the correct observation/label windows;
7. the candidate model is retrained or re-evaluated;
8. metrics, leakage, bias, security, and safety checks pass;
9. a new ModelVersion is approved and deployed;
10. the endpoint/job accepts that exact feature-schema version.

An old model must reject or ignore a newly added unrecognised feature according to a strict schema contract. It must never silently change behaviour because a table acquired a column.

### Input-to-feature/model mapping

| Verified input | Canonical representation | Permitted derived features | Consumers |
|---|---|---|---|
| FIR/case registration | CaseVersion + CaseEvent + taxonomy + jurisdiction | aggregate counts, time-of-day/day/week, verified category/head, reporting delay, beat/area | TimesFM, ST-GNN, hotspots, workload TabFM |
| Statements/documents | Evidence/Statement + reviewed extracted fields | approved text chunks, MO terms, entity/time/location candidates with provenance | Similar-case embeddings, RAG, graph candidate review |
| Image/video/audio | EvidenceObject + reviewed metadata/transcript | reviewed object/event/transcript attributes, not automatic identity/guilt | Search/retrieval and human review |
| Person/organisation links | CanonicalEntity + CasePartyRole + resolution decision | case counts/relationships within approved cutoff; no name matching | Graph analytics and reviewed case linkage |
| CDR/chat/IP/device data | DeviceArtifact + CommunicationEvent | aggregated communication counts/time windows and reviewed links | Graph/near-repeat/rule analytics subject to authority/access |
| Financial data | Account + transaction + source record + reviewed owner/case link | amount/channel/time aggregates, fan-in/out, cycles, structuring rule facts | Money rules/graph; aggregate reviewed model features |
| GPS/location observations | LocationObservation + jurisdiction | validated cell/beat/time aggregates | Hotspots, near-repeat, spatial forecast |
| Property/seizure/lab | PropertyItem/Seizure/LabResult | item category, recovery/status, reviewed forensic result | Case search, graph candidate links, workload/triage |
| Court/disposition/outcome | CaseEvent + CaseDisposition + OutcomeObservation | training labels after a separate label window; never future leakage into current features | Model training/evaluation only |
| Weather/holiday/external aggregate | SourceVersion + area/time observation | approved area/time covariates | TimesFM/ST-GNN/aggregate TabFM |
| Data-quality/reviewer events | QualityIssue + PredictionReview | missingness/staleness flags, overturn/abstention monitoring | Quality gate and model monitoring |

### Online prediction flow

~~~mermaid
flowchart TD
    A["New input received"] --> B["Staging/source record"]
    B --> C["Schema/file/security validation"]
    C --> D["Original stored + hash + custody"]
    D --> E["Extraction/normalisation candidate"]
    E --> F["Human review"]
    F --> G["Canonical records + entity links"]
    G --> H["Quality and authorization gate"]
    H --> I["FeatureSnapshot with source versions and cutoff"]
    I --> J{"Approved task/runtime"}
    J -->|CPU immediate| K["Rules / graph / similarity / geo"]
    J -->|Batch| L["AWS Batch or SageMaker job"]
    J -->|Near real time| M["SageMaker async/real-time endpoint"]
    K --> N["PredictionResult"]
    L --> N
    M --> N
    N --> O["Explanation + reviewer state + expiry"]
    O --> P["UI decision support"]
~~~

### Trigger rules

- A raw upload triggers ingestion, scanning, and extraction only.
- An accepted extraction or canonical edit may invalidate existing FeatureSnapshots.
- A verified case/area event updates lightweight aggregates immediately.
- TimesFM/ST-GNN forecasts run on a schedule or approved aggregate refresh.
- TabFM runs only for its approved aggregate task and feature schema.
- Graph updates create candidate relationships first; sensitive/high-impact links require review before downstream use.
- A late/revised source supersedes old predictions instead of overwriting history.
- Retraining is a separate approved pipeline; inference never trains directly on a new upload.

## 30. Immediate Supabase migration order

Complete these before SageMaker deployment:

1. Rotate database/secret keys that have been shared outside the intended secret store.
2. Back up schema and synthetic fixture.
3. Create a separate staging Supabase project if possible.
4. Implement real Auth mapping and server-side JWT verification.
5. Revoke broad anon/authenticated DML privileges.
6. Add unit/case assignments and sensitivity classifications.
7. Enable/test RLS table by table, then FORCE RLS where appropriate.
8. Add audit events/triggers and verify that sensitive reads/writes are recorded.
9. Create the private S3 evidence bucket; Supabase Storage is currently empty and should not become a second authoritative evidence store unless deliberately chosen.
10. Add canonical identity and migrate graph/case linking.
11. Add intake/evidence/event/feature/prediction migrations.
12. Regenerate the golden fixture and pass all validations.
13. Regenerate the statistical/performance fixtures.
14. Re-run embeddings, graph materialisation, forecasts, and approved aggregate models.
15. Only then connect AWS Batch/SageMaker to the new FeatureSnapshot/PredictionResult contract.

## 31. Go/no-go validation checks

The release is blocked until:

- [ ] Public-schema RLS policies exist and have automated allow/deny tests.
- [ ] anon cannot mutate public application tables.
- [ ] Supabase Auth/Cognito identity maps to one application user and role scope.
- [ ] Audit events are generated for sensitive API/database actions.
- [ ] Evidence files are private, hashed, versioned, scanned, and custody-tracked.
- [ ] CanonicalPersonID is stable across cases; PersonID is not A1/A2-style intra-case identity.
- [ ] Duplicate names do not create cross-case links.
- [ ] 100% of graph-person nodes link to a canonical entity or are explicitly unverified candidates.
- [ ] Graph edges have provenance/evidence or an explicit synthetic/unverified status.
- [ ] Zero canonical case coordinates fall outside their assigned jurisdiction/state.
- [ ] Category-specific state-transition tests pass.
- [ ] Charge Sheeted status cannot exist without the required event/document.
- [ ] Missing-person and other special scenarios follow their reviewed workflow.
- [ ] Every active ModelVersion has artifact digest, dataset snapshot, feature schema, metrics, approval, and rollback metadata.
- [ ] FeatureSnapshot contains source versions, cutoff time, quality status, and hash.
- [ ] Outcome labels occur after the observation window and do not leak into features.
- [ ] Protected/restricted attributes are blocked from unauthorised model schemas.
- [ ] New inputs cannot trigger model inference before verification.
- [ ] Existing predictions become stale/superseded when source data changes.
- [ ] The 1k–5k golden scenario fixture passes before generating the 100k+ fixture.

## 32. Revised implementation sequence after the live audit

1. Security emergency: secrets, grants, Auth, JWT validation, RLS, audit.
2. Canonical identity: people/organisations/case roles, graph foreign keys, remove name joins.
3. Case workflow: source/version/event/state machines and category-specific consistency.
4. Evidence platform: S3, evidence objects, custody, extraction, review, retention.
5. Structured domains: statements, property/seizure, digital/CDR, financial imports, court/outcomes.
6. Jurisdiction data: persist polygons/stations and validate/regenerate geography.
7. Datagen v2: golden scenarios, validation gates, statistical/performance fixtures.
8. Feature/prediction governance: definitions, snapshots, labels, result/review/supersession.
9. Rebuild derived analytics: embeddings, graph, money rules, hotspots, forecasts.
10. Validate aggregate model tasks and baselines.
11. AWS Batch/SageMaker benchmarking and deployment.
12. Full UI/admin workflows, end-to-end security/load/recovery tests, controlled release.
