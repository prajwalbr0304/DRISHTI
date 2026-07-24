# DRISHTI Phase-Wise Implementation Prompt Library - Hackathon Mode

> **Hackathon-only configuration:** This plan intentionally keeps PostgreSQL Row
> Level Security (RLS) disabled on every remaining AWS PostgreSQL table. Use only
> synthetic demonstration data. The browser must never connect directly to a
> database; all reads and writes must go through Catalyst API Gateway and
> Functions/AppSail. This is not a production security design.

> **Submission architecture override (18 July 2026):** the organizer requires a
> matching Catalyst service whenever Catalyst provides the capability. Therefore
> the deployed DRISHTI application uses Catalyst Data Store as its operational
> relational database, Stratus as its application object store, NoSQL for selected
> semi-structured/ephemeral state, Cache for short-lived cache/idempotency, React
> on Slate/Web Client Hosting and FastAPI on AppSail. The existing full AWS RDS
> dataset is retained for history, feature engineering and advanced analytics;
> S3 remains for AWS model staging/retained artifacts. Neither is the deployed
> app's primary operational database/blob store. AWS remains only for custom
> PostGIS/pgvector/pgRouting analytics where a verified Catalyst gap exists and
> for ECR/SageMaker/AWS Batch GPU/custom-model workloads. Any Supabase wording in
> completed Prompts 1-8 is historical context.

> **Credited Catalyst project:** India data center project **DHRISTI**, project ID
> `48361000000030003`. Screenshot dated 18 July 2026 shows a current plan from
> 17 July-17 August 2026 with INR 1500 Basic plus INR 300 Free usable credit
> (INR 1800 total shown). Prompt 14 must verify these details through the CLI/API
> after login and use this existing project rather than creating a duplicate.

This file is the execution companion to:

- DRISHTI_REMAINING_FEATURES_AND_AWS_ROADMAP.md
- POLICE FILES/00_MASTER_PLAN.md
- POLICE FILES/01_UX_UI_ARCHITECTURE.md
- POLICE FILES/02_ADVANCED_TECHNOLOGY.md
- POLICE FILES/03_DATA_VISUALIZATION.md
- POLICE FILES/04_NETWORK_GRAPH_ANALYSIS.md
- POLICE FILES/05_GEOSPATIAL_CRIME_ANALYTICS.md
- C:\Users\Prajwal\Desktop\06_INVESTIGATION_BOARD.md
- C:\Users\Prajwal\Desktop\07_DISASTER_RESPONSE.md
- [Palantir Gotham G-Cloud 14 service definition](https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-14/documents/92736/801146272055049-service-definition-document-2024-05-02-1537.pdf)
  as an interaction-pattern reference only; do not copy branding or proprietary assets.

Use these prompts one at a time and in order. Do not paste every prompt into one session.

For a new Kiro/Codex/Claude/Cursor session:

1. Open C:\Users\Prajwal\Desktop\DRISHTI as the workspace.
2. Paste the Global Execution Contract below.
3. Paste only the next incomplete phase prompt.
4. Do not start the following phase until the current Definition of Done passes.
5. Keep the generated phase report for the next session.

## Phase status

| Prompt | Phase | Status |
|---:|---|---|
| 1 | Datagen v2, schema completion, and live development Supabase load | Complete |
| 2 | FIR/case/people input UI and APIs | Complete |
| 3 | Hackathon access mode, API-only database access, RLS disabled, and audit | Complete |
| 4 | Canonical identity and entity-resolution workflows | Complete |
| 5 | Digital evidence upload, S3 storage, manual metadata, and evidence UI | Complete |
| 6 | Optional OCR/transcription/extraction | Deferred (post-hackathon) |
| 7 | Structured digital statements, property metadata, court, and lifecycle inputs | Complete |
| 8 | Digital/CDR/device/media and financial imports | Complete |
| 9 | Jurisdiction boundaries, station geography, maps, and spatial repair | Complete |
| 10 | Feature schemas, snapshots, labels, prediction requests/results/reviews | Complete |
| 11 | Embeddings, similar cases, graph rebuilding, and evidence-backed analytics | Complete |
| 12 | TimesFM/ST-GNN/hotspot/near-repeat forecasting | Complete |
| 13 | TabFM aggregate prediction task and model validation | Complete |
| 14 | Catalyst-native app/data deployment with external AWS custom ML | Pending |
| 15 | Demo admin/governance, notifications, reports, and optional RAG | Complete |
| 16 | Palantir-style Investigation Board on Catalyst with AWS analytics | Pending |
| 17 | Disaster Response forecasting, readiness, allocation, and maps | Pending |
| 18 | Final hackathon testing, CI/CD, recovery, and demo release | Pending |

Prompt 8 is marked Complete from the user's confirmed working implementation.
If docs/phase-reports/PHASE_08_REPORT.md is still missing, create that report from
the existing code, migration and test evidence before starting Prompt 9; do not
rebuild or rerun the completed phase merely to create the report.

---

## Global Execution Contract

Paste this at the start of every new implementation session before the selected phase prompt.

~~~text
You are implementing one phase of DRISHTI in:
C:\Users\Prajwal\Desktop\DRISHTI

Before changing anything:

1. Read DRISHTI_REMAINING_FEATURES_AND_AWS_ROADMAP.md completely, especially
   the historical database audit, current AWS/RDS architecture, Datagen v2,
   input placement, prediction flow,
   migration order, and go/no-go checks.
2. Read the phase-relevant files under POLICE FILES/.
3. Inspect the current code, SQL migrations, tests, and the previous phase report.
4. Preserve all existing user changes. Do not rebuild working modules without
   evidence that replacement is necessary.
5. Use C:\Users\Prajwal\Desktop\DRISHTI\.env when database access is needed, but
   never print, log, return, commit, or copy secret values.
6. Treat Catalyst Data Store/Stratus and the retained AWS RDS/S3 analytics/model
   systems as synthetic development systems.
   Start every database investigation in read-only mode.
   Never enter, upload, import, or retain real FIRs, evidence, names, phone
   numbers, identifiers, biometrics, or other operational/PII data.
7. Do not DROP/TRUNCATE/replace live data unless this exact phase explicitly
   requires a synthetic reload, a backup exists, and the target is confirmed
   to contain no real operational data.
8. Use additive, numbered, idempotent SQL migrations. Never edit production
   state manually when a migration or repeatable script should own it.
9. No AWS keys, legacy Supabase key, database password, or model token
   may appear in frontend code, committed files, Docker images, logs, or reports.
10. Predictions are investigation support only. Do not implement automatic
    arrest, detention, guilt, bail, or person-level criminal-justice decisions.
11. Do not operationalize the current synthetic offender-risk labels/scores.
12. Caste, religion, gender, juvenile status, protected attributes, and
    unreviewed intelligence assertions must not enter unauthorized/high-impact
    model feature schemas.
13. Hackathon input is digital and structured: React forms, CSV/JSON imports,
    and already-digital files with metadata entered manually. Do not add OCR,
    speech-to-text, document extraction, image recognition, barcode scanning,
    ID scanning, or automated evidence parsing in the hackathon phases.
14. A file upload never directly changes a prediction. Only validated structured
    form/import fields or manually reviewed metadata may be canonicalized and
    included in a versioned FeatureSnapshot.
15. Match the existing React/FastAPI/PostgreSQL style and exact quoted database
    identifiers. Use typed request/response models and parameterized SQL.
16. Keep RLS disabled on every remaining AWS PostgreSQL analytics/migration table
    for this hackathon.
    Maintain an idempotent migration/check that executes ALTER TABLE ... DISABLE
    ROW LEVEL SECURITY and verifies relrowsecurity=false. Do not create RLS
    policies in the hackathon implementation.
17. The React browser client must never contain an AWS secret key, legacy
    Supabase secret/service key,
    DATABASE_URL, or direct table query. Browser -> Catalyst API Gateway/Web
    Client -> API Gateway -> Function facade -> AppSail where needed -> Data
    Store/Stratus is the application path.
    AppSail/Functions may call a protected external AWS analytics/model API.
    Supabase clients are not part of the current architecture.
18. Add HACKATHON_MODE=true and DEMO_DATA_ONLY=true server configuration. Refuse
    server startup if hackathon mode is enabled against a database that is not
    explicitly marked synthetic. Show a persistent "Synthetic Hackathon Demo"
    badge in the UI.
19. Use Catalyst Authentication for the deployed hackathon login/session because
    the application has user access. RLS may remain disabled; AppSail/Functions
    must validate the Catalyst identity and map it to synthetic demo roles. A
    local role switcher may remain only as clearly labelled presentation state.
20. Restrict CORS to localhost and the exact Catalyst Slate/Web Client origin.
    Never expose the RDS port or legacy Supabase secret credentials to the public.
21. Zoho Catalyst is the mandatory application platform. Host React
    through Catalyst Slate or Web Client Hosting, host the FastAPI OCI service on
    Catalyst AppSail, use Data Store/NoSQL/Stratus/Cache for matching application
    data capabilities, map domains/SSL through Catalyst, and use Catalyst
    Pipelines for CI/CD. Do not deploy the public app or its primary operational
    database/blob store to AWS.
22. Prompt 14 must use the Zoho Catalyst CLI autonomously. The agent installs or
    updates `zcatalyst-cli`, runs `catalyst login --dc in`, and pauses only while
    the user completes the Zoho browser login/consent page. After login, the
    agent handles project discovery/selection, initialization, configuration,
    deployment, smoke tests and reports without asking the user to run commands.
23. Use the granted INR 1800 shown Catalyst credit deliberately. Prefer the
    organizer-mandated matching services and add usage/budget checks. Load a
    curated synthetic hackathon serving dataset into Data Store/Stratus rather
    than paying to duplicate the full AWS performance corpus.
24. AWS is external custom analytics/ML only: retain the complete synthetic RDS
    corpus for history, feature engineering, PostGIS/pgvector/pgRouting and model
    evaluation, but do not use it for submitted operational CRUD. Use S3 only for
    retained AWS artifacts and SageMaker/Batch staging, plus ECR, SageMaker, AWS
    Batch and protected integration endpoints. AppSail accesses AWS only through
    TLS, Catalyst Connections/compatible OAuth where possible, and least
    privilege. Never make RDS public to 0.0.0.0/0.
25. Implement the phase fully, run proportionate tests, and verify the actual
    result. Do not only write a plan.
26. Do not run database-integrated tests against the live development database
    if they can mutate it. Use a disposable test database/schema and synthetic
    buckets/fixtures.
27. At completion create docs/phase-reports/PHASE_<NUMBER>_REPORT.md containing:
    - files and migrations changed;
    - database objects/endpoints/screens added;
    - commands/tests run and their result;
    - row counts/coverage where applicable;
    - security and data-quality checks;
    - known limitations;
    - exact next-phase prerequisites.
28. Mark the phase Complete in prompt2.md only when every Definition of Done
    item is verified. Otherwise leave it Pending and report the blocker.

Proceed autonomously within this scope. Ask only when a missing decision would
materially change the architecture or cause destructive/external production state.
~~~

---

# Prompt 1 - Datagen v2, schema completion, and live development Supabase load

Objective: rebuild the synthetic-data foundation so it has stable identities,
valid case lifecycles, the structured digital input domains needed for the demo,
digital evidence fixtures with manual metadata, valid geography, outcome labels,
and a safe repeatable loader connected to the development Supabase.

~~~text
Implement Phase 1: DRISHTI Datagen v2 and load the verified synthetic dataset
into the development Supabase referenced by .env.

Read first:
- DRISHTI_REMAINING_FEATURES_AND_AWS_ROADMAP.md sections 2, 26, 27, 30, 31, 32
- existing police_fir_schema.sql
- police_fir_intelligence.sql
- police_fir_extensions.sql
- services/ml/sql/*.sql
- all files under datagen/
- generate.py and verify_*.py

Important known live facts that must be fixed:
- 100,000 CaseMaster rows already exist.
- Accused has 304,278 rows but only 26 distinct PersonID values.
- EntityGraph has 15,000 person nodes and zero valid AccusedMasterID links.
- current case linking falls back to duplicate names.
- CaseEvidence, audit_logs, and SavedQuery are empty.
- 6,732 live cases are outside the Karnataka polygon and 17,653 outside their
  assigned district polygon.
- 5,222 Charge Sheeted cases lack ChargesheetDetails.
- 1,000 Missing Person cases incorrectly have chargesheets.
- Supabase Auth and Storage are currently empty and are not required for the
  hackathon data path.
- current TabFM labels are synthetic and circular.

Implement:

A. Safe database preflight
1. Connect through DATABASE_URL in read-only mode and reproduce the schema/count
   baseline without printing row contents or credentials.
2. Confirm all current data is synthetic development data.
3. Create a documented backup/restore procedure and require a backup marker
   before any destructive reload command can execute.
4. Add a --confirm-synthetic-dev-target flag. Refuse --truncate/replace without it.
5. Add --dry-run, --validate-only, --mode golden|statistical|performance,
   --run-id, --workers, --seed, --firs, and --load-derived switches.

B. Add numbered additive migrations
Create and validate:
- services/ml/sql/005_security_rls_audit.sql (hackathon implementation: RLS
  disable/NO FORCE verification plus grant and audit setup; no RLS policies)
- services/ml/sql/006_ingestion_evidence.sql
- services/ml/sql/007_identity_case_workflow.sql
- services/ml/sql/008_feature_prediction_governance.sql
- services/ml/sql/009_jurisdiction_external_events.sql

For this phase, create the data structures required by the generator. Keep RLS
disabled everywhere as required by hackathon mode, but do not give the browser or
Supabase anon/authenticated roles direct table access. Prompt 3 finalizes the
API-only demo access path and provides a repeatable RLS-disabled verification.

Required schema groups:
1. SyntheticDataRun/synthetic_meta scenario metadata kept separate from model features.
2. SourceSystem, SourceRecord, IngestionJob, IngestionRecord, DataQualityIssue.
3. CanonicalPerson, CanonicalOrganisation, CanonicalEntity, CasePartyRole,
   PersonAlias, PersonIdentifier, PersonContact, PersonAddress,
   EntityResolutionCandidate, EntityMergeHistory.
4. CaseSource, CaseVersion, CaseEvent and category/workflow metadata.
5. EvidenceItem, EvidenceCaseLink, EvidenceEntityLink, EvidenceObject,
   EvidenceVersion and a simple EvidenceActivityEvent/audit trail. Store manual
   metadata only; DocumentExtraction, ExtractionField and ExtractionReview are
   optional future tables and are not required for the hackathon.
6. Statement/StatementVersion.
7. Seizure and PropertyItem metadata, with optional Vehicle/WeaponItem typed
   fields when entered through digital forms. ForensicSample/LabResult are
   deferred unless the demo explicitly needs manually entered lab metadata.
8. Device, DeviceArtifact, CommunicationEvent, LocationObservation,
   DigitalImportBatch.
9. CourtEvent, BailEvent, CaseDisposition, OutcomeObservation.
10. JurisdictionBoundary and UnitLocation with PostGIS indexes and versioning.
11. FeatureDefinition, FeatureSchemaVersion, FeatureSnapshot,
    TrainingDatasetSnapshot, OutcomeLabel, PredictionRequest,
    PredictionResult, PredictionReview.
12. Extend ModelVersion with artifact/image digest, dataset/feature schema,
    approval, approver, evaluation report, environment, and rollback metadata.

Keep legacy tables available. Add migration/backward-compatible columns/views
instead of immediately deleting Accused, Victim, ComplainantDetails,
CaseEvidence, CrimeRiskScore, ModelInference, or EntityGraph.

C. Refactor datagen
Create the domain modules specified in roadmap section 27:
- scenario_registry.py
- identity.py
- case_events.py
- people_roles.py
- evidence.py
- statements.py
- property_seizure.py
- digital.py
- financial.py
- court_outcomes.py
- external_context.py
- labels.py
- quality_scenarios.py
- validation.py

D. Stable identity
1. Generate one stable CanonicalPersonID per synthetic person.
2. Reuse it across cases for repeat people.
3. Create CasePartyRole for accused, victim, complainant, witness, informant,
   guardian, organisation, and unknown/unidentified roles.
4. Generate controlled same-name/different-person and alias/same-person cases.
5. Never use names, A1/A2 sequences, phone strings, or array indexes as identity.
6. Link EntityGraph people through CanonicalEntityID and true foreign keys.
7. Every graph relationship must have source/provenance or explicit
   synthetic-unverified status.

E. Scenario-driven case lifecycles
Implement versioned, testable state machines for FIR, Zero FIR, UDR, NCR, PAR,
Missing Person, transfer, reopen, correction, court/disposition and conversion
flows. Have the rules represented as data/configuration, not scattered random
if-statements.

Generate category-valid combinations:
- known and unknown accused;
- cases with and without arrest;
- cases with and without chargesheet/court;
- transfer/receiving acknowledgement;
- missing-person trace/recovery/closure;
- UDR/inquest/postmortem and explicit conversion;
- supplementary/revised documents where the schema permits;
- late outcomes after the observation window.

Status must be derived from events or pass prerequisite validation.

F. Structured digital input-domain synthetic scenarios
Generate structured, unmistakably synthetic records for:
- FIR/case fields and legal sections;
- people/organisations and roles;
- typed statements/interviews;
- already-digital document, image, video and audio references with manually
  entered title/type/source/date/description/tags;
- property, vehicle, weapon and seizure metadata entered through forms;
- devices, chats, CDR/IP/location observations;
- financial accounts, KYC/source records, transactions and reviewed links;
- court, bail, disposition and outcome events;
- approved weather/holiday/event/area context.

Generate small safe, already-digital local fixture files/manifests under a
gitignored datagen fixture output directory. Calculate real SHA-256 and size
metadata. Do not generate scanned-document/OCR fixtures. Do not upload to S3 yet
and do not commit large/generated files. Record storage status as a fixture
pending cloud upload.

G. Intentional quality/error scenarios
The golden fixture must deliberately include:
- missing/invalid required input kept in staging, not canonical tables;
- duplicate source/FIR;
- same-name different persons;
- aliases;
- unknown accused;
- conflicting dates/identifiers;
- invalid jurisdiction;
- duplicate/corrupt/unsupported file;
- evidence version replacement;
- missing or conflicting manually entered evidence metadata;
- late-arriving/retracted source;
- partial/retried idempotent import;
- demo actor/action represented in audit test fixtures.

H. Geography
1. Persist state/district/unit/beat/SHO boundaries and station coordinates.
2. Use the current bounded polygon implementation.
3. Validate every incident against state and assigned jurisdiction.
4. Current generator self-test must continue to pass.
5. New canonical fixture must have zero spatial containment failures.

I. Labels and ML separation
1. Generate OutcomeObservation after a separate label window.
2. Generate labels from verified outcome events, not from the input feature formula.
3. Store observation cutoff and label window.
4. Add time/geographic dataset splits.
5. Keep protected/restricted fields out of model feature schemas.
6. Mark all current person-risk outputs synthetic-demo-only. Do not rerun them.

J. Fixture modes
- golden: 1,000-5,000 cases with every branch/error scenario minimum covered;
- statistical: configurable 50,000-200,000 cases;
- performance: 100,000+ cases and large child/evidence/transaction volumes.

K. Validation and load
1. Run offline dry-run and validation first.
2. Apply migrations to the development Supabase.
3. Load the golden fixture and run all integrity tests.
4. Only after golden passes, back up the current synthetic fixture and load the
   100,000-case statistical/performance fixture.
5. Use transactions/idempotency and safe retry behaviour.
6. Do not run derived model batches until core integrity passes.

Required validation failures = zero:
- orphan foreign keys;
- duplicate CrimeNo/source key;
- unstable canonical identity;
- name-based identity links;
- unlinked graph-person nodes;
- unprovenanced graph edges unless explicitly unverified;
- invalid category transitions;
- Charge Sheeted without prerequisite event/document;
- invalid Missing Person/UDR lifecycle;
- out-of-state/out-of-jurisdiction canonical coordinates;
- evidence object without hash/version/manual provenance metadata;
- unvalidated manual file metadata changing canonical data;
- outcome before observation cutoff;
- post-outcome feature leakage;
- scenario minimum not met.

Run relevant tests and provide actual row counts by domain and scenario. Create
docs/phase-reports/PHASE_01_REPORT.md. Do not declare complete until the golden
fixture and 100k load both pass the integrity gates.
~~~

Definition of Done:

- Datagen v2 exists and is scenario-driven.
- Stable canonical identity replaces A1/A2/name matching.
- Migrations 005-009 apply cleanly.
- Golden fixture covers every required scenario.
- 100k synthetic fixture loads into development Supabase.
- Zero canonical spatial, lifecycle, identity, evidence, and FK integrity failures.
- No current synthetic individual-risk batch is rerun.

---

# Prompt 2 - FIR, case, people, and lifecycle input UI

Objective: create the complete contextual UI and API for entering structured FIR/case data and case parties. Evidence file upload comes in Prompt 5.

~~~text
Implement Phase 2: complete structured FIR/case input in the React UI and FastAPI.

Verify Prompt 1 is complete and inspect the new schema/migration/report first.
Read POLICE FILES/01_UX_UI_ARCHITECTURE.md and reuse the existing Calm Authority
design system, routing, query layer, form components, role-aware navigation,
case explorer, case file, map controls, and API conventions.

Do not create one giant form. Implement contextual flows:

A. Intake routes
- web/src/routes/intake/fir/
- web/src/routes/intake/imports/
- web/src/routes/review/quality/
- navigation entry for New FIR / Intake Inbox.

B. FIR wizard steps
1. Source and category:
   source system/method, external source ID, FIR/Zero FIR/UDR/NCR/PAR/Missing
   Person category, originating unit and receiving unit where applicable.
2. Registration:
   CrimeNo/CaseNo rules, registration date/time, registering officer, station,
   district, assigned IO, sensitivity/classification.
3. Incident:
   from/to time, information-received time, location/map, address/landmark,
   beat/SHO jurisdiction, occurrence description.
4. Classification:
   major/minor crime head, gravity, acts/sections, case category-specific fields.
5. People/organisations:
   complainant, victim, accused/suspect, witness, informant, guardian and
   organisation roles using CanonicalPerson/CasePartyRole APIs.
6. Narrative:
   brief facts, language, source/reviewer notes, restricted fields.
7. Review:
   validation errors/warnings, duplicate candidates, jurisdiction mismatch,
   missing prerequisites, save draft, submit for review.

C. Category-specific behavior
- Render fields and valid transitions from server-provided workflow metadata.
- Do not hardcode one lifecycle for all categories.
- Missing Person/UDR/Zero FIR/etc. must show their relevant event/source fields.
- Invalid combinations must be blocked by the backend, not only hidden in UI.

D. APIs
Implement typed endpoints for:
- create/update/get/list intake draft;
- validate draft;
- duplicate/source-key check;
- create/update case version;
- add/update/remove draft case-party roles;
- submit intake for review;
- approve/reject/return-for-correction;
- case event creation subject to workflow rules;
- lookup/options endpoints for units, boundaries, categories, status metadata,
  acts/sections, crime taxonomy and party roles.

Use database transactions and idempotency keys. Every write must return the
created version/event IDs and validation state.

E. UX requirements
- autosave draft with visible state;
- unsaved-change protection;
- keyboard accessible and responsive;
- inline field errors plus page-level summary;
- explicit distinction between blocking errors and review warnings;
- map-based location with jurisdiction display;
- source/provenance visible on review;
- no model prediction on the intake screen;
- after case creation, offer Continue to Evidence, People, Timeline, or Case File.

F. Hackathon access staging rule
Prompt 3 will establish the API-only hackathon path. Until Prompt 3 is complete:
- keep writes limited to localhost;
- use synthetic data only;
- never connect React directly to Supabase;
- treat editable X-Role/demo role selection only as presentation state, not
  authentication or authorization;
- do not expose the intake API publicly.

G. Tests
Add:
- API schema/validation/transaction/idempotency tests;
- category state-machine tests;
- duplicate and jurisdiction validation tests;
- React component/form validation tests;
- end-to-end golden paths for FIR, Zero FIR, UDR and Missing Person;
- backend rejection tests for invalid lifecycle combinations.

Create docs/phase-reports/PHASE_02_REPORT.md with screenshots/routes/endpoints,
test results and any fields intentionally deferred to evidence/digital phases.
~~~

Definition of Done:

- Users can create, validate, save, review, approve, and open a structured case.
- All case-party roles use canonical identity records.
- Category-specific workflows are server validated.
- UI submit is enabled only after Prompt 3 verifies hackathon mode, API-only
  database access, synthetic-data guards, restricted CORS, and RLS disabled.
- Tests cover normal and invalid intake paths.

---

# Prompt 3 - Hackathon access mode, API-only database access, RLS disabled, and audit

Objective: enable a simple synthetic-data hackathon demo while keeping Supabase
out of the browser and explicitly disabling RLS on every application table.

~~~text
Implement Phase 3: DRISHTI hackathon access mode.

This is an intentionally non-production setup. Do not implement Supabase Auth,
JWT verification, RLS policies, or production case/unit authorization in this
phase. Record all of them as post-hackathon work.

Read the live security findings in the roadmap and re-audit before changes:
- identify every DRISHTI application table in exposed schemas;
- list current relrowsecurity/relforcerowsecurity values;
- list grants held by anon and authenticated;
- confirm that the target database contains synthetic demo data only.

Implement:

1. Explicit hackathon configuration
- add HACKATHON_MODE=true and DEMO_DATA_ONLY=true to documented server config;
- add a non-secret database marker such as app_environment=synthetic_hackathon;
- refuse FastAPI startup when HACKATHON_MODE=true and the database marker is
  missing or different;
- show a persistent "Synthetic Hackathon Demo - Not for Operational Use" badge;
- do not claim that the local demo role selector provides security.

2. RLS disabled everywhere
- create an additive, idempotent hackathon migration/check that enumerates all
  DRISHTI application tables and executes ALTER TABLE ... DISABLE ROW LEVEL SECURITY;
- also execute ALTER TABLE ... NO FORCE ROW LEVEL SECURITY where applicable;
- do not create any RLS policies for hackathon mode;
- verify pg_class.relrowsecurity=false and relforcerowsecurity=false for every
  application table after all migrations;
- make the verification fail if a later migration accidentally enables RLS;
- document a future production task to re-enable RLS; do not implement it now.

3. Remove direct browser database access
- React must call only typed FastAPI endpoints;
- remove/disable browser-side Supabase table queries and realtime subscriptions;
- do not ship SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL or database credentials;
- a Supabase publishable/anon client is not needed for the demo;
- use one server-side PostgreSQL connection path via DATABASE_URL;
- keep parameterized SQL, transactions, validation and idempotency in FastAPI.

4. Reduce public database exposure even though RLS is disabled
- revoke direct table DML/TRUNCATE/REFERENCES/TRIGGER grants from Supabase anon
  and authenticated roles because the browser does not use PostgREST;
- do not expose the PostgreSQL port publicly;
- configure the FastAPI database user with only the permissions needed by the app;
- keep drishti_readonly SELECT-only if it already exists;
- do not confuse revoked browser grants with RLS: RLS must remain disabled.

5. Demo actor and audit
- keep a small set of synthetic demo profiles/roles for screen presentation;
- send a demo actor ID/role to FastAPI only for audit/display, not as a security
  boundary;
- audit create/update/delete, import, evidence upload/download, entity changes,
  model run, prediction review and export;
- include request ID, demo actor, action, resource, resource ID and timestamp;
- never log secrets, full narratives, uploaded file contents or sensitive fields.

6. Network/demo deployment guardrails
- restrict CORS to localhost and the exact hackathon frontend origin;
- place the deployed API behind HTTPS/API Gateway or an equivalent HTTPS ingress;
- configure conservative request-size and rate limits;
- ensure API error responses never return SQL, stack traces or credentials;
- use only synthetic data in public demonstrations and reset it after the event.

7. Frontend
- keep the demo profile/role switcher only if it helps present role-specific UI;
- label it "Demo view" and do not call it login/authentication;
- remove login/reset/password flows from the required hackathon scope;
- enable FIR/intake writes after the API-only and synthetic-data checks pass.

8. Tests
- all application tables report RLS disabled and FORCE RLS disabled;
- no RLS policy is required by the hackathon implementation;
- anon/authenticated cannot directly mutate tables through PostgREST grants;
- the frontend bundle/source contains no database password, service key or
  direct Supabase table query;
- FastAPI refuses a non-synthetic database in HACKATHON_MODE;
- CORS rejects an unlisted origin;
- normal synthetic FIR create/read/update, audit creation and model-request
  flows work through FastAPI.

Apply the migration safely. Create docs/phase-reports/PHASE_03_REPORT.md with the
table-by-table RLS-disabled verification, grant audit, API-only data-flow proof,
synthetic-data guard test, CORS test and deferred production security list.
~~~

Definition of Done:

- RLS and FORCE RLS are disabled on every DRISHTI application table.
- The browser has no direct Supabase/database data path or embedded secret.
- All application reads/writes go through FastAPI.
- Only a database explicitly marked synthetic can run in hackathon mode.
- Synthetic demo writes work and sensitive actions create audit events.
- Supabase Auth/JWT/RLS production security is clearly listed as deferred.

---

# Prompt 4 - Canonical identity and entity-resolution workflows

Objective: make people/organisations/entities reliable across cases and eliminate name-based graph/case linking.

~~~text
Implement Phase 4: canonical identity, case-party workflows, entity resolution,
merge/split governance, and migration away from name-based linking.

Use the Prompt 1 identity schema and Prompt 3 API-only hackathon access mode.

Backend:
1. CRUD/search for CanonicalPerson, CanonicalOrganisation and CanonicalEntity.
2. CasePartyRole endpoints for accused, victim, complainant, witness, informant,
   guardian and organisation roles.
3. Alias/identifier/contact/address endpoints with sensitivity classification.
4. EntityResolutionCandidate creation using deterministic/fuzzy candidate
   features, but never automatic merge.
5. Review endpoint: accept match, reject, create new, merge, split/unmerge.
6. Store reviewer, reason, source records, confidence, before/after and audit.
7. Add duplicate prevention and idempotency.

Migration:
1. Backfill CanonicalPersonID links for synthetic records using Prompt 1 truth
   metadata, not names.
2. Link EntityGraph to CanonicalEntityID.
3. Replace risk/features/case-network/entity-profile joins that use
   ROW_NUMBER/name matching.
4. Remove name-equality cross-case relationships from application behavior.
5. Keep compatibility views while old tables remain.

UI:
- real People page in each case;
- canonical profile page;
- case-role add/edit/remove;
- search/create person/organisation;
- entity-resolution review inbox;
- side-by-side candidate evidence;
- merge/split history;
- optional role-based field presentation for demo UX only; do not describe it as
  a security boundary while production authorization is deferred.

Graph rule:
- graph nodes represent canonical entities;
- graph relationships require SourceRecord/EvidenceEntityLink or explicit
  synthetic-unverified state;
- no link is considered confirmed only because names/phones are similar.

Tests:
- same name/different person remains separate;
- alias/same person resolves after review;
- merge then unmerge restores links;
- case/graph queries use canonical ID;
- synthetic cross-unit filtering behaves consistently in the demo UI;
- no remaining production code performs name-based identity linking.

Create docs/phase-reports/PHASE_04_REPORT.md with migration counts and proof that
all graph-person nodes are linked or explicitly unverified candidates.
~~~

Definition of Done:

- Stable canonical identities power case and graph relationships.
- Name-based case linking is removed.
- Entity merges are reviewed, audited, and reversible.

---

# Prompt 5 - Digital evidence upload, S3 storage, manual metadata, and evidence UI

Objective: accept already-digital demo files and manually entered evidence
metadata without OCR, transcription, image analysis or automated extraction.

~~~text
Implement Phase 5: simple hackathon digital-evidence intake using Amazon S3 for
file objects and PostgreSQL for structured metadata/provenance.

Do not place file bytes in PostgreSQL. Do not expose AWS credentials to React.
Do not add OCR, transcription, document extraction, image recognition, barcode
scanning, ID scanning or automatic canonical-field creation.

Supported hackathon inputs:
- structured FIR/complaint data remains a form in Prompt 2;
- optional already-digital PDF/document, image, video/CCTV or audio file;
- CSV/JSON/CDR/device/chat/transaction export;
- court/order/chargesheet file;
- external URL/reference where no file is uploaded.

For every file/reference, collect metadata manually:
- CaseID and optional linked CanonicalEntityID;
- evidence type/category;
- title and short description;
- source/source system and synthetic reference number;
- captured/received/uploaded date-time;
- language;
- tags;
- uploader/demo actor;
- confidentiality/demo classification;
- optional notes;
- file name, MIME type, size and SHA-256 generated by the system.

AWS/infrastructure:
- one private development/demo evidence bucket;
- block all public access;
- enable versioning and server-side encryption;
- CORS limited to the exact frontend origin when direct pre-signed upload is used;
- server IAM permission limited to the demo bucket/prefix;
- short-lived pre-signed upload/download URLs;
- lifecycle cleanup suitable for synthetic hackathon data.

Backend:
1. Create an EvidenceItem in draft state from manually entered metadata.
2. Issue a short-lived pre-signed upload URL or perform a server-mediated upload.
3. Complete by validating object existence, allowed size, extension/MIME and hash.
4. Record EvidenceObject, EvidenceVersion and an append-only EvidenceActivityEvent.
5. Use simple states: draft, uploading, available, failed, archived.
6. Support link/unlink to case/entity, metadata correction, new file version,
   download, archive and synthetic-demo reset.
7. Never overwrite version/activity history.
8. Migrate useful legacy CaseEvidence metadata into logical EvidenceItem records.
9. File content must not be parsed or sent to any ML model in this phase.

Frontend:
- replace the existing metadata-only EvidencePage;
- case-context upload/drop zone plus a manual metadata form;
- upload progress/cancel/retry;
- evidence list with type, title, source, date, tags, version, hash and state;
- evidence details/activity timeline;
- preview only for safe browser-supported formats;
- short-lived download action;
- clear message: "File contents are not automatically extracted."

Datagen integration:
- upload the small Prompt 1 already-digital fixture files to the demo S3 bucket;
- update EvidenceObject/version metadata and verify hashes;
- do not generate scanned/OCR-specific fixtures;
- do not commit fixture files.

Hackathon safeguards:
- all metadata access remains React -> FastAPI -> PostgreSQL;
- S3 stays private; use short-expiry exact-object pre-signed URLs;
- allow-list file size and types;
- audit upload/download/version/archive;
- never use real FIRs or real evidence.

Tests:
- successful upload and manual metadata save;
- duplicate hash warning;
- invalid size/type and corrupt/missing object;
- interrupted/retried upload;
- metadata correction;
- version replacement and immutable activity history;
- expired download URL;
- fixture uploader hash verification;
- proof that upload does not create extracted fields or trigger a prediction.

Create docs/phase-reports/PHASE_05_REPORT.md with bucket settings (no secrets),
supported input types, evidence row/object counts, screenshots and test results.
~~~

Definition of Done:

- Already-digital synthetic evidence can be uploaded to private S3.
- Every file has manually entered metadata, a hash, a version and activity history.
- Evidence UI supports upload, metadata editing, linking, versioning and download.
- No OCR/transcription/extraction dependency or automatic prediction is present.

---

# Prompt 6 - OPTIONAL FUTURE: OCR, transcription, and extraction

Status: **Deferred until after the hackathon. Skip this prompt in the current
implementation sequence and continue from Prompt 5 directly to Prompt 7.**

Objective: preserve a future integration point only. The hackathon uses
structured digital forms/imports and manual evidence metadata, so OCR,
speech-to-text, automated document parsing and an extraction-review inbox are
not required.

~~~text
Do not implement Phase 6 for the hackathon.

Keep these items in the future backlog:
- OCR for scanned PDFs/images using Amazon Textract or Catalyst Zia OCR;
- speech-to-text for audio;
- template extraction for FIRs, statements, court files, CDR and transactions;
- confidence/provenance storage;
- human accept/correct/reject review before canonicalization;
- multilingual Kannada/English evaluation;
- invalidation of affected FeatureSnapshots after an accepted correction.

Current hackathon rule:
- enter structured data directly in React forms or validated CSV/JSON imports;
- enter file metadata manually;
- never infer canonical fields or prediction features from uploaded file bytes;
- do not create an extraction queue, extraction UI or extraction cloud cost.

Create no PHASE_06_REPORT.md unless this optional phase is deliberately activated
after the hackathon.
~~~

Definition of Done for the hackathon:

- Prompt 6 remains Deferred.
- No OCR/transcription/extraction service is required to run the demo.
- Uploaded files do not affect canonical data or predictions.

---

# Prompt 7 - Structured digital statements, property metadata, court, and lifecycle inputs

Objective: implement the remaining structured digital forms that the current
schema lacks, with manual entry instead of OCR or automated extraction.

~~~text
Implement Phase 7: contextual forms/APIs for typed statements, property/seizure
metadata, optional manually entered lab-result metadata, court events, bail,
disposition and complete case timelines.

All information is entered digitally through forms or validated imports. Do not
add OCR, speech-to-text or automated parsing. An uploaded file may be linked as a
reference, but its content must not automatically populate these forms.

Statements:
- speaker canonical person + case role;
- statement type, recorded by, date/time/place, language;
- typed statement text and optional document/audio evidence link;
- versions, correction reason, translation, redaction/access classification;
- review/approval state.

Property/seizure:
- Seizure event and memo evidence;
- PropertyItem type, synthetic identifier/serial, description, quantity/unit,
  estimated value, owner, recovered/seized status;
- vehicle/weapon/substance specialized fields;
- package/seal/location fields entered manually where the demo uses them;
- disposal/release/return events.

Optional lab-result metadata:
- do not build a full forensic laboratory workflow for the hackathon;
- if a scenario needs it, provide a small form for test type, lab name,
  requested/result dates, result summary, status and linked digital report;
- all fields are manual and clearly synthetic.

Court/lifecycle:
- CourtEvent, remand, hearing, bail, chargesheet/supplementary document,
  transfer, disposition, closure, reopen;
- derive/display status from events or enforce prerequisites;
- preserve event history;
- create OutcomeObservation only from verified final events.

UI:
- StatementsPage;
- Property/Seizure page;
- optional Lab Result Metadata panel;
- Court/Lifecycle page;
- update TimelinePage to use CaseEvent/CourtEvent instead of only derived
  registration/arrest/chargesheet dates;
- contextual add actions with role permissions.

Tests:
- valid and invalid event transitions;
- evidence/reference linkage;
- version history;
- closed/charge-sheeted prerequisites;
- restricted statement access;
- outcome not available before final event.

Extend datagen golden scenarios and report coverage. Create
docs/phase-reports/PHASE_07_REPORT.md.
~~~

Definition of Done:

- Major hackathon investigative/court inputs are structured, digital and auditable.
- Case status/timeline is event-backed and consistent.
- Verified outcomes can support future labels.
- No OCR/transcription/extraction is required.

---

# Prompt 8 - Digital/CDR/device/media and financial imports

Objective: support validated high-volume structured imports and reviewed graph
links for digital and money evidence through FastAPI.

~~~text
Implement Phase 8: digital/device/CDR/chat/IP/location and financial data imports.

Create template-driven import pipelines for:
- CDR/call events;
- chat/message exports;
- IP/network logs;
- device artifacts;
- GPS/location observations;
- bank transactions;
- account/KYC records;
- wallet/UPI references.

Import workflow:
1. Upload source file as evidence.
2. Select template/schema version.
3. Parse into staging only.
4. Show dry-run counts, mapping, errors, duplicates and rejected rows.
5. Approve commit.
6. Create SourceRecord provenance for every canonical row.
7. Resolve phones/accounts/devices/people through reviewed candidates.
8. Support idempotency, retry, partial errors and rollback/supersession.

Schema/API:
- Device, DeviceArtifact, CommunicationEvent, LocationObservation;
- expand FinancialAccount/FinancialTransaction with source/version/reference,
  currency, normalized channel and reviewed owner/case links where required;
- EvidenceEntityLink/TransactionLink provenance;
- no raw identifiers in logs.

Analytics:
- keep money patterns rule-based with explicit reason codes;
- graph relationships remain candidate/reviewed and evidence-backed;
- no communication/financial link implies guilt;
- add reviewer disposition for alerts.

UI:
- digital import inbox;
- column mapping/dry-run/error download;
- transaction/account views;
- CDR/device timeline and aggregate visualization;
- reviewed entity-link queue;
- money alerts with source/evidence/reason.

Tests:
- template versions;
- malformed/duplicate/partial batch;
- idempotent retry;
- invalid template/unapproved commit state;
- reviewed vs unreviewed graph link;
- structuring/fan-in/layering rule fixtures;
- rollback/supersession.

Update datagen and create docs/phase-reports/PHASE_08_REPORT.md.
~~~

Definition of Done:

- Digital and financial inputs load through staging/review/provenance.
- Graph/money outputs are evidence-backed and reviewable.

---

# Prompt 9 - Jurisdiction boundaries, station geography, maps, and spatial repair

Objective: make the database and map enforce valid state/district/unit/beat/SHO geography.

~~~text
Implement Phase 9: versioned jurisdiction geography and repair/regenerate the
spatial data path.

Database:
- load Karnataka state/district/taluk boundaries from datagen/geo;
- create versioned Unit/beat/SHO boundaries and UnitLocation;
- spatial SRID/type constraints and GiST indexes;
- helper functions/views for state/district/unit containment;
- validity periods and source metadata.

Validation:
- every case/location observation must be checked against assigned jurisdiction;
- allow staged mismatch with DataQualityIssue, but block canonical submit unless
  a permitted override/reassignment is reviewed and audited;
- zero canonical out-of-state/out-of-district records in the new fixture.

Live synthetic repair:
- do not silently move rows;
- identify invalid current rows;
- because data is synthetic, regenerate from Prompt 1 truth where possible;
- otherwise quarantine/supersede with an audit/source record;
- refresh spatial analytics only after validation.

Frontend:
- station/beat/SHO boundary layers;
- intake location picker constrained to assigned jurisdiction;
- mismatch warning/reassign workflow;
- case/hotspot/forecast layers clearly distinguished;
- time slider and data freshness;
- synthetic/demo visual badge.

Tests:
- boundary self-test;
- DB containment function;
- coastal/border cases;
- wrong assigned district;
- valid reassignment;
- map layer and intake interaction.

Create docs/phase-reports/PHASE_09_REPORT.md with before/after spatial counts.
~~~

Definition of Done:

- Boundaries and stations are persisted/versioned.
- Canonical geography has zero containment failures.
- UI and database share the same jurisdiction rules.

---

# Prompt 10 - Feature schemas, snapshots, labels, and prediction governance

Objective: build the safe bridge between verified inputs and any model.

~~~text
Implement Phase 10: governed feature and prediction contracts.

Database/service:
- FeatureDefinition;
- FeatureSchemaVersion;
- FeatureSnapshot;
- TrainingDatasetSnapshot;
- OutcomeLabel;
- PredictionRequest;
- PredictionResult;
- PredictionReview;
- supersession/staleness relationships;
- ModelVersion governance fields from migration 008.

FeatureDefinition must include:
- name/type/description;
- source table/field/event;
- transformation and window;
- observation cutoff behavior;
- sensitivity/protected classification;
- allowed tasks;
- missing/stale policy;
- owner and approval.

Feature builder:
1. Read only validated canonical records that are eligible for the selected task.
2. Enforce observation cutoff and source version.
3. Block post-outcome leakage.
4. Exclude protected/restricted features from all hackathon prediction schemas
   unless a separately reviewed aggregate task explicitly permits them.
5. Store values, source record/version IDs, schema version, quality status and hash.
6. Make snapshot immutable.

Prediction workflow:
- strict model/feature schema compatibility;
- queued/running/completed/failed/stale/superseded/reviewed/rejected states;
- model artifact/image digest;
- explanation and limitations;
- human review/override reason;
- expiry and rollback;
- idempotent request.

Labels:
- only verified outcome events;
- separate observation and label windows;
- time/geographic split metadata;
- exclusions and approval;
- never use current synthetic risk labels as production truth.

Triggers:
- raw upload: no prediction;
- accepted canonical edit: invalidate affected snapshots/results;
- verified aggregate event: update eligible aggregate job;
- retraining remains a separate approved pipeline.

APIs/UI:
- prediction job status;
- feature/data-as-of display;
- explanation/source versions;
- stale/superseded banner;
- reviewer action;
- admin feature/model registry.

Tests:
- reproducibility from snapshot;
- schema mismatch rejection;
- unverified source blocked;
- stale after correction;
- leakage check;
- protected feature check;
- idempotent request;
- review/audit.

Create docs/phase-reports/PHASE_10_REPORT.md.
~~~

Definition of Done:

- Every prediction is tied to an immutable feature snapshot.
- New inputs do not affect a model until explicitly included in an approved schema/model version.
- Labels and observation windows are leakage-safe.

---

# Prompt 11 - Embeddings, similar cases, graph rebuilding, and evidence-backed analytics

Objective: rebuild derived intelligence from verified canonical inputs.

~~~text
Implement Phase 11: rebuild embeddings, similar-case search, graph analytics,
hidden associations, patterns and money links using verified canonical data.

Embeddings:
- embed approved case/document/statement chunks with access metadata;
- use one coherent vector space per ModelVersion;
- store source version/hash;
- re-embed on approved source change;
- filter retrieval by the selected synthetic demo case/unit context;
- evaluate on human-labelled similar/not-similar cases.

Similar cases:
- show why records match and source links;
- no outcome leakage into similarity query text;
- apply the same case/unit demo-context filter before ANN results;
- return confidence/limitations.

Graph:
- nodes = canonical entities;
- edges = reviewed/provenanced relationships;
- no name matching;
- evidence/source records attached;
- candidate vs confirmed distinction;
- rebuild PageRank/betweenness/communities;
- hidden association requires independent evidence kinds and reviewer state.

Patterns/money:
- regenerate from valid cases/transactions;
- version rule/model parameters;
- store source record IDs;
- expose reviewer disposition;
- never state culpability from centrality/association.

Remove or archive invalid derived rows from the old synthetic identity graph.
Do not mix old and new canonical graph spaces.

Tests:
- case/unit-context-filtered retrieval;
- same-model embedding search;
- no name-based links;
- edge provenance;
- graph rebuild idempotency;
- hidden-association proof path;
- evaluation metrics.

Create docs/phase-reports/PHASE_11_REPORT.md with old/new row counts and metrics.
~~~

Definition of Done:

- Similarity and graph outputs use canonical, verified, demo-context-filtered sources.
- Old invalid graph-derived data is isolated/archived.

---

# Prompt 12 - TimesFM, ST-GNN, hotspots, and near-repeat forecasting

Objective: validate aggregate area/time forecasting with strong baselines and valid geography.

~~~text
Implement Phase 12: aggregate forecasting after Prompt 9 and Prompt 10 gates pass.

Tasks:
- beat/unit/district daily or weekly incident-count forecasts;
- hotspots and near-repeat cells;
- no person-level prediction.

Data:
- only canonical valid geography/events;
- observation cutoff;
- source completeness;
- approved weather/holiday/event/area context;
- no post-window information.

Models:
- seasonal naive and moving-average baselines;
- TimesFM 2.5 adapter;
- ST-GNN only where dependencies/data support it;
- existing NumPy/statistical fallback;
- Hawkes/ETAS near-repeat;
- ST-DBSCAN/KDE hotspots.

Evaluation:
- rolling-origin backtests;
- geographic holdouts;
- MAE, RMSE, WAPE/sMAPE;
- interval coverage;
- error by district/unit/head/season;
- comparison against simple baselines;
- abstain/low-confidence on insufficient data.

Persistence:
- FeatureSnapshot and PredictionResult;
- model/version/artifact;
- horizon and data cutoff;
- lower/upper interval;
- backtest metrics;
- contributing source versions;
- stale/superseded handling.

Runtime:
- CPU for light algorithms;
- AWS Batch/SageMaker later for heavier TimesFM/ST-GNN;
- scheduled daily/weekly, not every keystroke.

UI:
- horizon;
- interval/fan chart;
- data freshness;
- baseline comparison;
- backtest metrics;
- map layer and limitations.

Tests:
- time leakage;
- invalid geography exclusion;
- sparse series;
- deterministic fallback;
- batch idempotency;
- metric thresholds.

Create docs/phase-reports/PHASE_12_REPORT.md.
~~~

Definition of Done:

- Forecasts are aggregate, backtested, uncertainty-aware and baseline-compared.
- Invalid geography/person targeting is excluded.

---

# Prompt 13 - TabFM aggregate task and model validation

Objective: replace synthetic individual offender scoring with an approved aggregate/review-support task.

~~~text
Implement Phase 13: redesign TabFM usage.

Do not reuse the current synthetic offender-risk target. Archive/label its
CrimeRiskScore/ModelInference outputs synthetic-demo-only.

Choose and document one approved aggregate task, for example:
- beat/time-window incident-count band;
- station/case-workload band;
- aggregate case-review queue band.

Do not choose a task that automatically scores a person for criminal-justice action.

Implement:
1. Task/target definition and model card.
2. Approved FeatureSchemaVersion using only verified pre-cutoff inputs.
3. TrainingDatasetSnapshot with time/geographic splits.
4. Baselines: prior-period/statistical and XGBoost/HistGradientBoosting.
5. TabFM/TabPFN candidate adapters.
6. Calibration, confidence, abstention and threshold review.
7. Leakage/protected/proxy feature checks.
8. Metrics by time/geography/data completeness.
9. Reviewer workflow and limitations.
10. Register only approved model versions; staged/shadow/retired lifecycle.

Run small/medium/full benchmarks and record:
- 500, 5,000 and full-row runtime;
- CPU/GPU memory;
- latency/throughput;
- cost estimate;
- metric comparison against baselines.

Persist FeatureSnapshot/PredictionResult/Review and update UI labels so no page
presents synthetic individual risk as operational truth.

Tests:
- task schema;
- label independence;
- leakage;
- protected fields;
- baseline comparison;
- deterministic fallback;
- model unavailable;
- stale/superseded.

Create docs/phase-reports/PHASE_13_REPORT.md.
~~~

Definition of Done:

- TabFM is used only for an approved aggregate/review-support task.
- Baselines and held-out evaluation are documented.
- Synthetic individual scoring is not operationally displayed.

---

# Prompt 14 - Catalyst-native app/data deployment with external AWS custom ML

Objective: deploy the entire user-facing DRISHTI application on Zoho Catalyst,
use Catalyst services for every matching application capability, migrate a
curated synthetic serving dataset from AWS, use the granted credits deliberately,
and keep AWS only for justified custom analytics/GPU/model workloads.

~~~text
Implement Phase 14: autonomous Catalyst-native deployment, serving-data
migration and external AWS custom-model integration.

Read roadmap sections 13 and 21-25 plus the completed Phase 10-13 contracts.
Use these current official references and re-open them before executing because
CLI/platform behavior may change:
- https://docs.catalyst.zoho.com/en/getting-started/installing-catalyst-cli/
- https://docs.catalyst.zoho.com/en/cli/v1/login/login-from-cli/
- https://docs.catalyst.zoho.com/en/cli/v1/initialize-resources/initialize-new-project/
- https://docs.catalyst.zoho.com/en/serverless/help/appsail/introduction/
- https://docs.catalyst.zoho.com/en/serverless/help/appsail/custom-runtimes/deploy-from-cli/
- https://docs.catalyst.zoho.com/en/slate/help/deploy-from-cli/
- https://docs.catalyst.zoho.com/en/cloud-scale/help/web-client-hosting/introduction/
- https://docs.catalyst.zoho.com/en/cloud-scale/help/api-gateway/key-concepts/
- https://docs.catalyst.zoho.com/en/job-scheduling/
- https://docs.catalyst.zoho.com/en/pipelines/help/deployments/deploy-to-appsail/
- https://docs.catalyst.zoho.com/en/signals/
- https://docs.catalyst.zoho.com/en/cli/v1/data-store-import-and-export/import-operation/
- https://docs.catalyst.zoho.com/en/sdk/python/v1/cloud-scale/stratus/overview/
- https://docs.catalyst.zoho.com/en/quickml/
- https://docs.catalyst.zoho.com/en/zia-services/help/automl/introduction/
- https://docs.catalyst.zoho.com/en/serverless/help/circuits/introduction/
- https://research.google/blog/introducing-tabfm-a-zero-shot-foundation-model-for-tabular-data/
- https://huggingface.co/google/tabfm-1.0.0-pytorch
- https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference.html
- https://docs.aws.amazon.com/sagemaker/latest/dg/batch-transform.html
- https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-batch-code.html

Non-negotiable deployment boundary:
- React is hosted by Catalyst Slate when enabled for the credited project;
- if Slate is unavailable, use Catalyst Web Client Hosting;
- the primary public FastAPI service is hosted by Catalyst AppSail;
- Catalyst Data Store is the operational relational database used by the deployed
  app and its full-text application search;
- Catalyst Stratus stores uploaded evidence/imports/generated reports;
- Catalyst NoSQL stores selected semi-structured board layouts/preferences and
  ephemeral collaboration state where appropriate;
- Catalyst Cache stores only short-lived cache/idempotency/rate-limit state;
- Catalyst Authentication provides deployed login/session identity;
- custom domain/SSL uses Catalyst Domain Mapping where a domain is available;
- application CI/CD uses Catalyst Pipelines;
- AWS does not host the public React app or primary public FastAPI API;
- AWS RDS retains the complete synthetic historical/feature-engineering corpus
  and serves protected advanced analytics only; submitted operational CRUD uses
  Data Store;
- AWS S3 is limited to retained AWS model artifacts and SageMaker/AWS Batch
  staging copies; submitted evidence/import/report objects use Stratus;
- AWS ECR, SageMaker, AWS Batch, SQS/DLQ and CloudWatch remain external custom
  model/analytics services;
- every third-party use must state the specific Catalyst capability gap that
  justifies it.

A. Autonomous Catalyst CLI login and project binding
The implementation agent performs every CLI/file/deployment action. The user is
needed only for the Zoho browser login/consent page opened by Catalyst CLI.

1. From C:\Users\Prajwal\Desktop\DRISHTI, inspect Node.js/npm and run:
   - npm install -g zcatalyst-cli
   - catalyst --version
2. Check existing authentication with `catalyst whoami`.
3. If not authenticated, run `catalyst login --dc in`. Handle the CLI telemetry
   and data-center prompts automatically. Catalyst opens the Zoho Accounts login
   page; pause and tell the user to complete login only. Do not ask the user to
   copy tokens or run commands.
4. As soon as the CLI reports success, continue automatically:
   - catalyst whoami;
   - catalyst project:list;
   - select the existing India-DC credited project displayed as `DHRISTI`, project
     ID `48361000000030003`;
   - verify the ID after selection and never create a duplicate DRISHTI/DHRISTI project.
5. Initialize/bind Catalyst configuration in infra/catalyst/ so the repository
   root and existing application layout are preserved. Use `catalyst init` and
   `catalyst project:use <project_id_or_name>` as supported by the current CLI.
6. The agent handles all interactive arrow/select/confirmation prompts after
   browser login. Use the CLI first; where a component has no CLI lifecycle,
   continue through the authenticated Catalyst SDK/API or automate the already
   signed-in Catalyst console. Do not delegate project/component selection or
   routine console clicks to the user.
7. Assume an existing credited project is available. If Catalyst reports that no
   project exists and this is the account's first project, record the exact
   platform blocker because Catalyst requires first-project creation in its web
   console; do not silently create an unrelated project or spend credits elsewhere.
8. Verify through Catalyst billing/usage APIs or console metadata, without
   exposing sensitive billing information, the screenshot baseline: plan period
   17 July-17 August 2026, INR 1500 Basic plus INR 300 Free usable amount.
9. Verify generated catalyst.json/.catalystrc and project/data-center IDs without
   printing tokens. Commit safe configuration but gitignore local auth/cache,
   secret files, logs and generated build archives.

B. Catalyst component allocation
Create a submission-compliance matrix in PHASE_14_REPORT.md and implement:

- Serverless Functions: API Gateway proxy/adapters, Data Store/Stratus event
  handlers, notification handlers and lightweight integration logic;
- AppSail custom OCI runtime: the full FastAPI service;
- Slate or Web Client Hosting: React/Vite production build;
- Domain Mapping: frontend/API domain and managed SSL where supplied;
- Data Store: operational relational records and full-text search;
- NoSQL: selected semi-structured layout/preferences/presence data;
- Stratus: evidence/import/report objects, versioning and presigned transfers;
- Cache: short-TTL lookup/dashboard/idempotency/rate-limit data;
- QuickML: the approved-text RAG/knowledge-base path and at least one eligible
  no-code ML pipeline experiment if the credited project supports it;
- SmartBrowz: PDF/image report generation and screenshots;
- Catalyst Authentication: deployed user login/session;
- API Gateway: routing, Catalyst authentication and throttling in front of the
  supported web-client/Function endpoints. Current documented targets do not
  include AppSail, so a Gateway Function facade securely invokes AppSail where
  the FastAPI service is needed;
- Connections: OAuth credentials for a compatible third-party/AWS integration
  when the protected AWS adapter exposes OAuth/OIDC;
- Job Scheduling/Cron: scheduled AppSail, Function or external webhook jobs;
- Signals + Event Functions: Data Store/Stratus/auth events and cross-component
  prediction/import/report notifications;
- Circuits: multi-step prediction/report orchestration with branch/parallel steps
  when available in the selected India project;
- Mail and Push Notifications: non-sensitive synthetic task/report/alert notices;
- Pipelines: lint/test/build/deploy/smoke/rollback;
- Catalyst billing Budget/Report: credit monitoring.

Capability not used:
- OCR, face, object recognition, barcode/ID scanning and voice are not part of
  the digital-input hackathon scope, so do not call Zia media/voice services.

Organizer capability compliance matrix

Create this exact 26-row matrix in PHASE_14_REPORT.md and replace `Planned` with
the deployed component ID/test evidence, `Not used` with the verified absence of
that capability, or `Unavailable` with current India-DC/project evidence. A row
must never be silently omitted.

| # | Capability | Required Catalyst service | DRISHTI disposition |
|---:|---|---|---|
| 1 | Serverless backend logic | Functions | Used for events, adapters and notifications |
| 2 | Docker image deployment | AppSail custom OCI | Used for the FastAPI OCI image |
| 3 | Full managed web application | AppSail | Used for the FastAPI application runtime |
| 4 | React/Vite frontend | Slate or Web Client Hosting | Used |
| 5 | Custom domain and SSL | Domain Mappings | Use when a domain is supplied; otherwise record capability absent |
| 6 | Operational relational data | Data Store | Used for the curated serving layer |
| 7 | Semi-structured data | NoSQL | Used only for documented flexible/ephemeral state |
| 8 | Application object/blob storage | Stratus | Used for evidence, imports and reports |
| 9 | Cache | Cache | Used for bounded TTL state only |
| 10 | Full-text application search | Data Store | Used for case/FIR/person/evidence metadata |
| 11 | Text LLM/RAG/knowledge base | QuickML | Used only when the optional approved-text assistant is enabled |
| 12 | No-code ML pipeline | QuickML | Used for an eligible baseline experiment |
| 13 | Automated tabular training | Zia AutoML | Currently unavailable in India; recheck and capture evidence |
| 14 | OCR/face/image/object/barcode/ID processing | Zia Services | Not used because input is digital/manual and extraction is deferred |
| 15 | Speech/voice/translation models | Zia Services | Not used; voice/transcription is deferred |
| 16 | PDF/image/screenshot/headless-browser output | SmartBrowz | Used for reports and board/disaster exports |
| 17 | Login/signup/session identity | Authentication | Used |
| 18 | API routing/auth/throttling | API Gateway | Used in front of Functions; a protected Function facade invokes AppSail where needed |
| 19 | OAuth token lifecycle | Connections | Use for the protected external integration when OAuth/OIDC-compatible; otherwise record the signed-service-auth gap |
| 20 | Scheduled jobs/cron | Job Scheduling | Used |
| 21 | Data/upload/auth event reactions | Signals + Event Functions | Used |
| 22 | Cross-component event routing | Signals | Used |
| 23 | Branch/parallel workflow | Circuits | Currently unavailable in India; recheck and use Functions + Job Scheduling fallback |
| 24 | Transactional email | Mail | Used for data-minimized synthetic notices |
| 25 | Web/mobile push | Push Notifications | Used for data-minimized synthetic notices |
| 26 | CI/CD | Pipelines | Used for test/build/deploy/smoke/rollback |

Availability handling:
- inspect the credited project after login rather than assuming availability;
- QuickML RAG is preferred for RAG because it is available in the India DC;
- official Catalyst documentation currently states Zia AutoML is unavailable in
  the India DC. Attempt/verify the feature gate and record evidence; do not fake
  usage. If unavailable, use a QuickML eligible baseline or justify the custom
  AWS TabFM/TimesFM workload;
- current official Catalyst documentation states Circuits is unavailable in the
  India DC. Re-check at execution time; if unchanged, use Functions + Job
  Scheduling/AppSail and record the documented regional limitation instead of
  pretending the Circuits capability was deployed;
- a service may be omitted only if its matching capability is genuinely absent
  or unavailable, with the reason captured in the compliance matrix.

Required pipeline and workflow inventory

Do not implement every item below as a Catalyst Pipelines object. Catalyst
Pipelines owns CI/CD. Data/event workflows use Functions, AppSail, Data Store,
Stratus, Signals/Event Functions and Job Scheduling; QuickML owns eligible
no-code ML/RAG; AWS Batch/SageMaker owns justified custom model computation.
Current official documentation lists Circuits as unavailable in the India DC, so
use idempotent Functions + Job Scheduling unless this changes before execution.

1. `catalyst-ci-cd`
   Owner: Catalyst Pipelines.
   Trigger: repository change or approved manual release.
   Flow: lint -> type/unit/integration tests -> secret/SAST/dependency/container
   scans -> acquire deployment lock -> Data Store/Stratus pre-deploy export and
   additive-schema compatibility validation -> frontend build -> AppSail OCI
   build -> optional immutable AWS GPU-worker ECR build/test -> Catalyst development
   deploy -> smoke tests -> approved immutable-artifact production promotion ->
   Slate/AppSail rollback or Data Store forward-recovery on failure -> release lock
   and stop temporary GPU resources.
2. `bootstrap-catalyst-serving-data`
   Owner: Catalyst CLI, Data Store import and Stratus.
   Trigger: initial deployment or deliberate serving-layer rebuild.
   Flow: read-only AWS export -> validate synthetic/golden subset -> hash/count ->
   Data Store upsert by ExternalID -> S3-to-Stratus fixture copy -> relationship/
   object reconciliation -> cutover report. This is not continuous two-way sync.
3. `structured-intake-and-import`
   Owner: AppSail/Functions + Data Store + Stratus.
   Trigger: FIR/case draft save/submission, supervisor approval, or approved
   CSV/JSON import.
   Flow: draft/staging -> schema/size/type/duplicate validation -> quality issues/
   partial-error review -> supervisor/import approval -> canonicalization only
   after approval -> authoritative Data Store write -> audit/Signal. Draft save and
   submission must never create a canonical CaseVersion or PredictionRequest.
4. `digital-evidence-ingestion`
   Owner: Stratus + Data Store + Signals/Event Functions + an isolated AppSail
   malware-scanner job/container.
   Trigger: already-digital file upload.
   Flow: private upload -> quarantine -> MIME/size/hash/version validation ->
   isolated malware scan -> available/rejected state -> manual metadata -> case
   link -> audit. The security scan must not perform OCR, transcription, semantic
   media analysis or automatic canonical-field extraction.
5. `identity-resolution-and-graph-refresh`
   Owner: AppSail/Job Scheduling + protected AWS analytics adapter when required.
   Trigger: validated person/party/import change or approved batch run.
   Flow: candidate generation -> review queue -> canonical identity decision ->
   graph rebuild/version -> safe Cache invalidation -> Data Store activity result.
6. `feature-snapshot-and-staleness`
   Owner: Data Store event -> Event Function/AppSail.
   Trigger: committed approved canonical-version or reviewed-metadata change.
   Flow: feature eligibility/leakage checks -> immutable FeatureSnapshot -> mark
   only affected previous predictions stale/superseded -> coalesced/idempotent
   prediction request when the task trigger permits it -> audit. Draft/submitted/
   rejected/quarantined source events are ineligible.
7. `custom-prediction-dispatch-and-result`
   Owner: Job Scheduling + AppSail/Function + protected AWS adapter.
   Trigger: approved PredictionRequest.
   Flow: idempotent request -> minimum-required snapshot -> SQS/Batch/SageMaker ->
   output/schema/safety validation -> PredictionResult in Data Store -> Signal ->
   UI review. Include retry, timeout, DLQ and duplicate-result protection.
8. `model-training-evaluation-and-release`
   Owner: QuickML for an eligible no-code baseline; AWS Batch/SageMaker for
   TabFM, TimesFM, ST-GNN or another justified custom workload.
   Trigger: approved offline experiment, dataset/context release or applicable
   retraining request; never a raw upload or single new FIR.
   Flow: versioned dataset/context and split -> leakage/fairness/safety checks ->
   train eligible conventional/ST-GNN candidates where applicable + perform
   zero-shot/in-context TabFM and TimesFM evaluation without updating their
   pretrained weights -> held-out baseline comparison -> cost/latency report ->
   human approval -> ModelVersion/context registration -> canary/rollback metadata.
9. `aggregate-and-spatiotemporal-forecast`
   Owner: Job Scheduling + AWS Batch/SageMaker/custom CPU or GPU job.
   Trigger: scheduled forecast/backfill or approved manual run.
   Flow: time/area snapshot -> task router dispatches separately typed baseline,
   TimesFM, ST-GNN, hotspot and near-repeat jobs -> validate/calibrate each result ->
   fuse only cutoff/schema/geography-compatible layers -> Data Store forecast
   result -> map/dashboard Signal -> stop temporary compute.
10. `approved-knowledge-rag`
    Owner: Catalyst QuickML.
    Trigger: approved SOP/policy knowledge-base release.
    Flow: validate approved text/source/version -> knowledge-base update -> fixed
    citation/refusal evaluation -> enabled RAG endpoint. Uploaded evidence bytes
    and unreviewed case narratives are excluded.
11. `report-generation-and-delivery`
    Owner: Job Scheduling/AppSail + SmartBrowz + Stratus + Signals.
    Trigger: authorized report/export request.
    Flow: immutable Data Store source snapshot -> SmartBrowz PDF/image -> synthetic
    watermark/hash/version -> private Stratus object -> audit -> report.ready.
12. `notification-delivery`
    Owner: Signals/Event Functions + Catalyst Mail/Push.
    Trigger: approved task/report/prediction/alert lifecycle event.
    Flow: data-minimized template -> recipient/role validation -> send -> delivery
    status/audit in Data Store. Never include evidence content or full narratives.
13. `investigation-board-activity-and-export`
    Owner: AppSail + Data Store/NoSQL/Cache + Signals + SmartBrowz/Stratus.
    Trigger: authenticated board mutation, replay or export.
    Flow: optimistic/idempotent mutation -> append-only BoardActivity -> event/
    replay -> reconstructable layout -> locked snapshot -> attributed export.
14. `hazard-feed-ingestion-and-freshness`
    Owner: Job Scheduling + Functions/AppSail + Stratus/Data Store.
    Trigger: synthetic replay cron or approved digital connector.
    Flow: raw versioned Stratus payload -> normalization/unit/geometry/duplicate
    validation -> HydroMetReading/HazardEvent candidate -> freshness heartbeat ->
    stale/failed Signal and DLQ handling.
15. `hazard-forecast-review-and-alert`
    Owner: Functions + Job Scheduling and protected AWS model adapter.
    Trigger: validated readings/time window.
    Flow: immutable snapshot -> baseline/custom model -> output validation ->
    HazardPrediction/RiskZone in Data Store -> human review -> optional approved
    AlertHistory record -> Mail/Push. Never auto-warn or issue an all-clear.
16. `resource-allocation-and-routing`
    Owner: AppSail/Job Scheduling + protected AWS OR-Tools/PostGIS/pgRouting when
    the measured computation requires it.
    Trigger: approved hazard/resource planning request.
    Flow: constraint validation -> greedy/baseline comparison -> proposed
    allocation/route -> hazard-intersection validation -> Data Store proposal ->
    human approval. Never auto-dispatch or claim a guaranteed-safe route.
17. `reconciliation-backup-recovery-and-cleanup`
    Owner: Catalyst Job Scheduling/Functions plus Catalyst/AWS operational APIs.
    Trigger: schedule, release gate or recovery exercise.
    Flow: Data Store/Stratus count-hash-version reconciliation -> backup/export ->
    restore drill -> failed-job replay -> stale temp-object cleanup -> GPU endpoint/
    Batch shutdown -> budget/health evidence.
18. `embeddings-and-similarity-index-refresh`
    Owner: Job Scheduling + protected AWS Batch/AppSail analytics worker and the
    approved vector/index store.
    Trigger: approved source/version/model change or deliberate rebuild.
    Flow: select authorized reviewed text/structured representation -> generate
    one coherent embedding space per ModelVersion -> validate dimensions/digest ->
    build shadow index -> human-labelled retrieval evaluation -> atomic active-index
    switch -> Data Store index/version metadata -> Cache invalidation -> rollback.
    Uploaded raw file bytes and unreviewed text never enter this workflow.

Phase-order rule for workflows 13-16:
- Prompt 14 may create only shared Catalyst/AWS infrastructure, disabled job
  definitions, reserved Data Store/Stratus/NoSQL namespaces and typed adapter
  contracts needed by Investigation Board and Disaster Response.
- Prompt 14 must not claim that workflows 13-16 are functionally implemented,
  enabled or end-to-end tested. Prompt 16 implements/enables workflow 13; Prompt
  17 implements/enables workflows 14-16 and supplies their domain migrations,
  UI, fixtures and acceptance tests.
- If any of those modules already exists before Prompt 14 executes, preserve it
  and deploy only what its completed phase report proves. Otherwise leave the
  scaffold disabled and cost-free.

For every pipeline/workflow define an owner, trigger, typed input/output,
idempotency key, state machine, retry/timeout, DLQ or failed-item path, audit and
lineage fields, metrics/alerts, credit limit, rollback/replay procedure and an
end-to-end synthetic fixture. Record deployed component/job/pipeline identifiers
and test evidence in the phase report without logging tokens or credentials.

C. React deployment to Catalyst
1. Inspect the current Vite/React build and API URL handling.
2. Keep secrets and DATABASE_URL out of VITE_* variables and the browser bundle.
3. Configure one public API base URL pointing to Catalyst API Gateway. Route
   supported requests to Basic/Advanced I/O Functions. When FastAPI logic is
   required, the Function facade invokes the protected AppSail service with
   propagated correlation/identity context and server-side authentication. Do not
   claim AppSail is a native API Gateway target unless current documentation and
   a deployed test prove it; never expose an AWS URL to the browser.
4. Prefer Slate because it supports React builds and deployment previews. If the
   credited project does not have Slate access, initialize Web Client Hosting.
5. The agent runs all supported CLI initialization/link/deployment commands,
   including `catalyst init slate`, `catalyst slate:link`,
   `catalyst deploy slate`, or the equivalent current Web Client commands.
6. Configure SPA fallback/deep links, asset caching, environment-specific API
   URL, exact CORS origin and the Synthetic Hackathon Demo badge.
7. Integrate Catalyst Authentication for login/session handling and map the
   authenticated Catalyst user to the existing synthetic demo role/assignment.
   Disabling PostgreSQL RLS does not remove this application authentication
   requirement. Never trust a role supplied only by the client.
8. Deploy first to Catalyst development, run smoke tests, then deploy/promote to
   the credited production environment when the CLI/account allows it.
9. If production promotion requires an unavoidable payment/console approval,
   keep the working Catalyst development deployment, document the one exact
   remaining platform action and do not move hosting to AWS.

D. FastAPI deployment to Catalyst AppSail
1. Create/repair a lightweight API Dockerfile separate from the GPU worker.
2. Exclude CUDA/TabFM/TimesFM training packages from the AppSail image.
3. Build an OCI-compliant Linux AMD64 image:
   `docker buildx build --platform linux/amd64 --load ...`.
4. Run as a non-root user, bind Uvicorn to 0.0.0.0, use the configured AppSail
   port (default/custom 9000 where appropriate), and provide /health/live and
   /health/ready.
5. Prefer a fully CLI-driven local OCI deployment so no registry-console action
   is required. Use the current equivalent of:
   `catalyst deploy appsail standalone --name drishti-api --source docker://<image> --port 9000`.
   Inspect `catalyst deploy appsail --help` before running and use the exact
   syntax supported by the installed version.
6. If deploying from AWS ECR instead, use Catalyst's supported ECR integration;
   record the immutable image digest and never expose ECR credentials.
7. Configure server-only environment/secrets through the supported AppSail/Catalyst
   configuration mechanism without echoing values or committing them. Include
   only required Catalyst component identifiers, the Stratus bucket name,
   Connections identifier, feature flags and the protected AWS model/analytics
   adapter URL. The deployed application must not require DATABASE_URL for its
   operational CRUD path.
8. Configure memory/disk/min-max instances conservatively for credits, health
   checks, structured redacted logs and scale-to-low/zero behavior where offered.
9. Map an API custom domain to the API Gateway/Function facade if available;
   otherwise use the generated Catalyst API URL. Treat the AppSail URL as a
   server-side service endpoint and restrict direct access as far as the current
   AppSail controls permit.
10. Do not use CORS as service authentication. AppSail HTTP routes accept the
    authenticated Function facade and reject unauthenticated browser CRUD. For an
    explicitly enabled direct WebSocket/SSE channel, allow only the exact Catalyst
    frontend origins and validate the short-lived scoped handshake token.
11. Use the Catalyst Python SDK for Data Store, Stratus, NoSQL, Cache, Job
    Scheduling, Circuits and other supported Catalyst components. Create narrow
    repository/service interfaces so local tests can use in-memory fakes.
12. The Gateway Function derives identity/role from Catalyst Authentication,
    removes client-supplied identity headers and sends AppSail a short-lived signed
    internal context containing user ID, allowed scope, timestamp, nonce and request
    ID. AppSail verifies signature/audience/expiry/replay before handling a request.

E. Catalyst Data Store, Stratus, NoSQL and Cache migration
1. Create a versioned mapping from the AWS PostgreSQL serving schema to Catalyst
   Data Store tables. Cover every submitted screen/API domain, not only Case/FIR:
   - organisation/geography: State, District, Taluk, Unit, station/beat/SHO
     boundaries and approved SourceVersion references;
   - case lifecycle: Case/FIR, CaseVersion, CaseEvent, category/status, assignment,
     task, AlertHistory and reviewed lifecycle/correction records;
   - canonical identity: person, organisation, alias, identifier, contact/address,
     case-party role and reviewed merge/split/resolution history;
   - evidence: metadata, object/version/hash, case/entity link, custody/activity,
     quarantine state, retention and legal-hold metadata;
   - structured domains: statements, property/seizure/vehicle, lab results,
     digital/CDR/device/media imports, financial accounts/transactions and
     court/chargesheet/outcome records;
   - governance: SourceSystem/SourceRecord, Import/IngestionJob, staging/rejection,
     DataQualityIssue/review, AuditEvent, notification/task/report metadata;
   - analytics contract: FeatureDefinition/Schema/Snapshot, PredictionRequest/
     Result/Review, ModelVersion/Inference, embedding/index version and a curated
     UI projection of reviewed graph/similar-case results while the full analytics
     graph/index remains in AWS;
   - only reserved ExternalID/namespace/adapter contracts for Investigation Board
     and Disaster Response at this phase. Do not create or claim their domain
     tables/workflows until Prompts 16-17 (Investigation Board = Prompt 16,
     Disaster Response = Prompt 17), unless an existing completed phase report
     proves those modules are already implemented.
2. Add a stable `ExternalID` or equivalent unique migration key to every imported
   table and make imports idempotent. Preserve referential identifiers, synthetic
   data labels, timestamps and lineage. Never import credentials or real PII.
3. Implement a `CatalystDataStoreRepository` as the deployed default. Keep any
   PostgreSQL repository only as an offline migration/read-only analytics adapter.
   No deployed operational endpoint may require direct RDS access.
4. Export and validate a curated hackathon serving subset from the existing AWS
   database. Include the golden cases plus enough varied synthetic records to
   exercise search, dashboards, predictions, the investigation board and
   disaster response. Start around 1,000-5,000 linked cases unless measured
   Catalyst credit/capacity permits more; do not blindly copy the full performance
   corpus. Current Catalyst documentation limits Data Store development imports
   to 5,000 records per table (and states no equivalent production insertion
   ceiling); re-check the current limit and design the development subset around it.
5. Import the curated relational data with the current supported Data Store CLI,
   SDK or API. Prefer `catalyst ds:import` with upsert semantics where supported.
   Capture import job IDs, row counts, rejected rows, relationship checks and
   source hashes. Never print secrets.
6. Use Catalyst Data Store full-text search for deployed case/FIR/person/evidence
   metadata search. Do not send this search capability to an external service.
7. Create private Stratus buckets/prefixes for digital evidence, import staging,
   generated reports and board/disaster exports. Enable only required versioning,
   retention and lifecycle controls. Use short-expiry exact-object signed access;
   record SHA-256, size, MIME type, object key/version and lineage in Data Store.
   Keep new evidence objects quarantined until size/type/hash and an isolated
   malware scan pass; scanning is a security control and must not extract semantic
   content or trigger predictions.
8. Copy the Prompt 5 synthetic evidence fixtures from S3 into Stratus, verify
   hashes and update deployed references. Stratus is the application object source
   of truth; S3 remains only for temporary SageMaker/AWS Batch input/output copies.
9. Use Catalyst NoSQL only for genuinely semi-structured state such as saved board
   layouts, user UI preferences, temporary collaboration presence and flexible
   feed envelopes. Do not duplicate authoritative Data Store relational records.
10. Use Catalyst Cache only for bounded TTL data such as reference lookups,
    idempotency keys, rate-limit counters and short-lived computed summaries.
    Cache is never the system of record.
11. Define a one-way analytics synchronization boundary: Data Store/Stratus event
    -> Signals/Event Function or scheduled export -> protected AWS adapter ->
    analytics/model store. Write validated AWS results back to Data Store. Avoid
    indefinite bidirectional dual-write.
12. Document an explicit bootstrap/cutover contract:
    - before cutover, copy the selected AWS records/objects into Data Store/Stratus;
    - after cutover, new application input is written to Data Store/Stratus first;
    - send only validated/versioned feature snapshots or analytics projections to
      AWS, keyed by ExternalID and source version;
    - AWS returns model/geospatial results through the adapter as new result records,
      not competing edits to the source input;
    - run scheduled count/hash/version reconciliation and provide a repeatable
      rebuild of the Catalyst serving subset from the retained AWS corpus;
    - never run uncontrolled two-way row replication or last-write-wins conflict
      resolution across Catalyst and AWS.

F. Secure Catalyst-to-AWS custom analytics/model connectivity
1. No browser component may call AWS or AppSail CRUD routes directly. Catalyst
   API Gateway and its authenticated/throttled Function facade remain the public
   HTTP API boundary; the facade invokes AppSail and protected AWS services
   server-side. A direct AppSail WebSocket/SSE connection is allowed only when
   required and protected by a short-lived, audience/board/user-bound token minted
   through the authenticated Gateway path, strict Origin checks and expiry.
2. Keep RDS private. Never open PostgreSQL 5432 to 0.0.0.0/0 and never store a
   DATABASE_URL in React or use it as the AppSail operational-data path.
3. Implement a minimal protected AWS adapter inside the AWS VPC for the external
   capabilities that Catalyst does not replace:
   Catalyst -> HTTPS AWS API Gateway -> Lambda/ECS adapter -> SageMaker/Batch and,
   only where necessary, PostGIS/pgRouting/analytics RDS.
4. Use Catalyst Connections for third-party OAuth/token lifecycle where the
   integration is compatible. Otherwise use short-lived signed service requests
   with timestamp/nonce replay protection. An API key alone is not authentication.
5. Use AWS execution roles inside Lambda/ECS/SageMaker/Batch, least-privilege IAM,
   request-size/rate limits, TLS, timeouts, circuit breaking, retry with jitter,
   idempotency and redacted audit logs.
6. Record a capability-gap justification for every AWS path—for example custom
   TabFM/TimesFM GPU inference, PostGIS/pgRouting or a required model artifact
   workflow. Do not use AWS to replace a matching Catalyst application service.

G. ML/RAG placement and prediction runtime
1. Use QuickML for any enabled text-LLM/RAG/knowledge-base capability and for an
   eligible no-code ML baseline. Use Zia AutoML only if it is actually exposed in
   this India-DC project; otherwise record the verified regional unavailability.
2. Run TabFM/TimesFM/custom GPU models externally because Catalyst does not expose
   their required custom GPU runtime. Use private ECR images and temporary S3
   staging copies only for SageMaker/AWS Batch execution.
3. Prefer AWS Batch for offline forecasts, backfills and evaluation. Scale compute
   to zero. Use SageMaker asynchronous inference only for a measured near-real-time
   requirement, and a real-time endpoint only after a latency/traffic benchmark.
   Do not select SageMaker Serverless for a GPU-only workload.
4. Compare the QuickML/no-code baseline, when eligible, against the custom AWS
   model using the same time-aware or group-aware split and leakage guardrails.
5. Store model/version/feature lineage and validated predictions in Data Store.
   The AWS runtime never writes to the browser and does not become the authoritative
   application database.

Prediction flow:
Catalyst frontend -> Authentication -> API Gateway -> Function facade -> AppSail
where needed -> validate
input and persist FeatureSnapshot/PredictionRequest in Data Store -> Functions +
Job Scheduling (or Circuits only if newly available) -> protected AWS adapter ->
Batch/SageMaker -> validate result ->
PredictionResult in Data Store -> Signals -> Gateway polling or a scoped AppSail
WebSocket/SSE token channel -> UI.

G.1 Mandatory input-to-feature-to-model routing contract

Do not implement a generic rule that sends every new input to every model. Model
routing is determined by an approved task, FeatureSchemaVersion, subject type,
observation cutoff and data-quality state. Implement and document this matrix:

| Input/event | Canonicalization and trigger | Model route | Required behavior |
|---|---|---|---|
| FIR/case draft create, autosave or edit | Draft only | None | Validate and save the draft; do not create a PredictionRequest and do not call AWS |
| FIR/case submitted for review | Submitted, not yet canonical | None | Create review/audit state only; no prediction |
| Supervisor-approved FIR/case with verified crime head, occurrence time, unit/district and geometry | New canonical CaseVersion/CaseEvent and source version | Lightweight near-repeat immediately when eligible; coalesced station-workload and area-forecast requests for the next approved run | Never score the complainant, accused, victim or FIR itself; mark only affected aggregate snapshots/results stale |
| Approved correction/reclassification/transfer | New immutable canonical version | Rebuild only schemas whose source fields changed | Supersede prior snapshots/results; never mutate historical snapshots or duplicate a request for the same idempotency key |
| Approved chargesheet, court outcome, lab result, statement metadata, property/seizure or lifecycle event | Structured reviewed canonical record | Workload/backlog features, graph/similarity refresh or future labelled-outcome dataset according to the approved schema | A later outcome may become a training label only after label-window closure and approval; it is not an immediate label for the FIR |
| Digital evidence upload to Stratus | Quarantined object plus manually entered metadata | None from raw bytes | Hash/type/size/malware validation only; no OCR/extraction and no prediction from upload |
| Reviewed manual evidence metadata/link | Versioned canonical metadata | Only a schema that explicitly lists those reviewed fields; otherwise graph/index metadata refresh only | Raw content is excluded; record exact source object/version and reviewer |
| CSV/JSON FIR or case import | Per-row staging, validation, deduplication and review | Emit the same canonical events as individually approved forms | Reject/hold bad rows; coalesce accepted rows into bounded model jobs rather than one GPU job per row |
| CDR/device/media/financial structured import | Staged typed rows, canonical entities and reviewed links | Graph/community/hidden-association/similarity workflows; a prediction model only when an approved non-person aggregate schema explicitly permits a field | Never treat an unreviewed candidate link as confirmed evidence or as a model feature |
| Weather/holiday/event/area context | Approved SourceVersion with freshness, units, geography and cutoff | TimesFM/ST-GNN/fused aggregate forecast only | Reject stale/post-cutoff context and preserve provenance |
| Approved SOP/policy/reference text | Curated knowledge-base release | Catalyst QuickML RAG | Exclude case narratives, uploaded evidence and unreviewed intelligence |
| Hazard/readiness/resource inputs added by Prompt 17 | Validated hazard/resource snapshot | Hazard forecast and reviewed allocation/routing pipeline | Keep task/schema/model separate from policing TabFM; never auto-dispatch or auto-warn |

For an approved FIR, persist the canonical record first. Publish the source-change
Signal only after the authoritative transaction commits. The event handler must
determine the affected aggregate subjects (for example station, district, crime
head and time window), invalidate/supersede only their prior snapshots, and create
new requests using an idempotency key such as:
`<task>:<subject>:<cutoff>:<feature-schema-version>:<model-version>:<source-version-hash>`.

G.2 Model-specific execution contract

Implement separate typed adapters; never pass one undefined "all input" object to
every model.

1. TabFM station workload band (`station_workload_band`)
   - Input: the approved aggregate workload feature vector from Prompt 13, such
     as recent/prior/trailing case volume, trend, seasonal factor, prior-year
     quarter, chargesheet throughput, backlog ratio, history months and active
     months share. No narrative, raw evidence or person attributes.
   - Context: a versioned historical table of pre-cutoff feature rows plus known
     workload-band labels. Query rows contain current station snapshots without
     labels.
   - Meaning of `fit`: TabFM receives labelled examples as in-context examples;
     it does not update Google's pretrained weights for every FIR. A new FIR
     changes a station aggregate and therefore may change the next inference.
   - Trigger: approved/coalesced aggregate run, not draft save, upload or every
     keystroke. Prefer scheduled/on-demand Batch; use asynchronous inference only
     when an interactive seconds/minutes requirement is measured.
   - Output: band probabilities, selected workload band, confidence, abstention,
     limitations, schema/model/context digest and expiry. Human review remains
     mandatory.
2. Optional TabFM aggregate area-forecast layer (`area_incident_forecast_tabfm`)
   - Keep it as a different task, schema, handler and ModelVersion from the
     workload model. Use only verified area/time aggregates and a closed label
     window. Do not reuse the retired individual offender-risk target.
3. TimesFM
   - Input: a compact, gap-handled unit/district/beat incident-count series with
     frequency, horizon, cutoff and optional approved dynamic covariate versions.
   - Trigger: daily/weekly schedule, approved backfill or forecast request; one
     newly approved FIR updates the series but does not invoke the full model
     directly unless the coalescing window closes.
   - Output: timestamped trajectory and quantiles/intervals with data freshness.
4. ST-GNN
   - Input: time-by-area count tensor, versioned adjacency/geometry graph and
     approved context. Exclude invalid geography and person nodes.
   - Trigger: scheduled/approved batch after sufficient new data or graph version;
     never retrain on every FIR.
   - Output: area/time predictions, MC-dropout or equivalent uncertainty, graph
     version and fallback status.
5. Hawkes/ETAS near-repeat
   - Input: approved event time, valid coordinates, area/head and bounded recent
     event history.
   - Trigger: permitted near-real-time CPU job after FIR approval, plus scheduled
     rebuild. This does not require a GPU endpoint.
   - Output: short-horizon grid-cell intensity with decay/window assumptions; no
     automatic patrol, arrest or enforcement action.
6. KDE/ST-DBSCAN hotspots
   - Input: validated aggregate event points/time windows.
   - Trigger: scheduled/manual CPU analytics job.
   - Output: versioned hotspot cells/clusters with parameters and validation.
7. Forecast fusion
   - Run only after compatible TabFM/TimesFM/ST-GNN/near-repeat outputs share the
     required cutoff, geography and schema contract. Record each contributing
     ModelVersion, weight, confidence and missing-layer fallback. Fusion is a CPU
     validation/combination step, not another raw-input GPU call.
8. Statistical/XGBoost/HistGradientBoosting/QuickML baselines
   - Run on the same split/features/cutoff as the candidate. A baseline may be an
     explicit fallback result, but never silently claim it was TabFM/TimesFM.
9. Embeddings, similar cases and graph analytics
   - Use only authorized reviewed text or structured representations. Keep one
     embedding space per ModelVersion and rebuild a shadow index before switching.
     Graph community/centrality/path logic is deterministic CPU/PostGIS/NetworkX
     analytics; candidate links require reviewer confirmation and are not TabFM
     predictions.
10. QuickML RAG
    - Use only the approved SOP/policy knowledge base with citations/refusal
      tests. It does not answer from raw FIRs/evidence in the hackathon scope.

G.3 Required AWS GPU implementation (do not claim it exists before this passes)

The current repository must be treated as a local/interim implementation until
the following gaps are closed. Inspect and record the pre-change facts:
- `WorkloadRunRequest` currently defaults to `foundation_kind=tabpfn`;
- `/workload/run` currently executes `run_governed` inside the FastAPI process;
- the current TabFM loader casts weights to BF16 but does not explicitly place
  the model and tensors on CUDA;
- no existing SageMaker/AWS Batch adapter may be inferred merely from roadmap text.

Implement:
1. Create a separate `services/gpu-worker` custom inference image; do not put
   CUDA or TabFM/TimesFM weights into the AppSail API image.
2. Pin Python/CUDA/PyTorch/TabFM/TimesFM versions, model weight digest and license.
   Verify that the TabFM non-commercial/non-production weight license is compatible
   with the hackathon and prevent an undocumented production promotion.
3. Push the immutable GPU image to private ECR and store model artifacts in a
   private, encrypted S3 prefix. Use an execution role rather than static keys.
4. For a requested real TabFM run, explicitly select CUDA, move the model and
   tensors to the CUDA device, use BF16 only after a numerical smoke test, call
   `eval()`/inference mode, chunk queries to bounded memory and report measured
   GPU name/memory/latency. If CUDA or the real weights are unavailable, fail the
   `tabfm` job as unavailable; do not silently return TabPFN/in-context output
   labelled as TabFM. A separately named fallback request may run afterward.
5. Implement SageMaker-compatible health/invocation handlers and a versioned
   request schema containing only:
   - request/idempotency/task identifiers;
   - feature-schema/model/context versions and content hashes;
   - observation cutoff, subject type/IDs and source versions;
   - ordered column definitions;
   - labelled context X/y or an approved S3 context-snapshot URI;
   - unlabelled query rows;
   - output schema, timeout and maximum resource limits.
   Never send a complete FIR JSON, narrative, evidence bytes or database secret.
6. Return a signed/versioned result envelope containing request ID, actual backend,
   actual device, model/artifact digest, schema/context digest, predictions,
   probabilities/quantiles/intervals, confidence/abstention, runtime/memory metrics,
   warnings and error code. Reject mismatched row/column/schema counts.
7. Use SageMaker asynchronous inference for small application-triggered jobs that
   can complete in seconds/minutes; use SageMaker Batch Transform or AWS Batch GPU
   for scheduled multi-station/multi-district runs, backfills and evaluation. Use
   a real-time endpoint only after benchmarking. GPU compute must scale/stop when
   idle; SageMaker Serverless is not a GPU substitute.
8. The AWS adapter updates job state through authenticated callbacks/polling:
   `queued -> dispatched -> running -> completed|failed|timed_out|cancelled`.
   AppSail validates the envelope and writes the authoritative PredictionResult
   to Data Store. AWS must not write directly to the browser or edit source FIRs.
9. Load weights once per warm endpoint worker. A Batch/Transform job may reload
   weights at job startup; include cold-start separately from inference latency.
10. Cache only safe model/context artifacts by digest. Do not cache user identity,
    raw evidence or authoritative results. Close/release CUDA memory between
    incompatible large model stages and stop temporary endpoints after testing.

G.4 Retraining, new outcomes and staleness rules

- A new FIR is an inference input event only after approval; it is not automatically
  a training example and never updates TabFM's pretrained weights.
- Only a later reviewed outcome whose label window has closed may enter a new
  TrainingDatasetSnapshot. Training/evaluation/release is an offline approved
  workflow with time/geographic splits, leakage checks, baseline comparison and
  ModelVersion promotion/rollback.
- TabFM normally performs zero-shot in-context inference using the approved
  labelled context supplied with the request. Updating that context is a dataset
  release, not online learning.
- A structured source correction creates a new FeatureSnapshot and marks dependent
  results stale/superseded. Do not overwrite or delete the old reproducible result.
- Unchanged content hashes reuse the existing snapshot/request/result. Retry or
  duplicate Signals must not create duplicate GPU jobs or results.
- The UI must show `draft/reviewed input`, `prediction queued/running/completed`,
  actual backend/device, data-as-of, model/schema version, stale state, limitations
  and reviewer disposition. Never show a fallback model as the requested model.

G.5 Required end-to-end model/input tests

1. Create a synthetic FIR draft and prove zero PredictionRequest/AWS invocation.
2. Submit it for review and again prove zero model invocation.
3. Approve it with valid structured geography/time/head and prove:
   - the canonical Data Store transaction commits first;
   - one source-change Signal is emitted;
   - affected prior aggregate snapshots become stale/superseded;
   - a near-repeat CPU request is created only when its eligibility gate passes;
   - coalesced workload/forecast requests are idempotent.
4. Run one real TabFM job and assert `actual_backend=tabfm`, `device=cuda`, expected
   artifact/schema/context digests and a valid aggregate PredictionResult. Deliberately
   remove CUDA/weights and prove the job fails rather than masquerading as TabFM.
5. Run the same workload snapshot through the approved baseline and compare held-out
   metrics without overwriting the TabFM result.
6. Run one TimesFM scheduled series request, one ST-GNN/fallback request, one
   near-repeat request and one fused forecast; verify compatible cutoffs, source
   versions, intervals and contributing ModelVersions.
7. Upload a synthetic digital evidence file and prove that quarantine/hash/manual
   metadata occur but no OCR/extraction/prediction request is created.
8. Approve permitted manual metadata and prove only explicitly dependent schemas
   are rebuilt.
9. Import a mixed valid/invalid CSV/JSON fixture and prove rejected rows never
   reach a model and accepted rows coalesce into bounded jobs.
10. Test timeout, retry, DLQ, callback signature, duplicate result, schema mismatch,
    stale result, insufficient history, invalid geography and AWS-unavailable
    fallback behavior.

H. Catalyst Job Scheduling, Signals and workflow services
1. Create Job Pools/Jobs/Crons through CLI/SDK/API where supported.
2. React to Data Store inserts, Stratus uploads and auth/project events with
   Signals + Event Functions where supported. Use them for prediction.requested,
   evidence.uploaded, import.completed and report.ready.
3. Schedule Functions, AppSail internal endpoints or protected AWS webhooks for
   aggregate forecasts, health checks, cleanup, exports and backfills.
4. Use one-minute Job Scheduling only where justified; avoid wasteful polling.
5. Configure retry intervals, Data Store idempotency state and a failed-job review
   path. Persist authoritative state before publishing a Signal.
6. If Circuits is available, use it for a real multi-step branch/parallel workflow
   such as validate -> persist -> feature build -> model route -> result validate
   -> notify. If unavailable in the India DC/project, use Functions + Job
   Scheduling and record the feature-gate/region evidence.
7. Configure Mail and Push for non-sensitive synthetic notification workflows and
   store only delivery metadata/status in Data Store.

I. Catalyst Pipelines and autonomous deployment
Create a versioned Pipeline that performs:
1. acquire an environment-scoped deployment lock/concurrency guard and reject a
   second deployment to the same environment;
2. dependency install/cache with lockfile and runtime-version verification;
3. backend lint/type/unit tests;
4. frontend lint/type/unit tests;
5. Data Store/Stratus/NoSQL/Cache integration tests against a safe development
   environment or contract-test fakes followed by a development smoke test;
6. secret/SAST/dependency/license scan, SBOM generation and browser production
   build with a check that no AWS/AppSail/private URL or secret is embedded;
7. build the API Linux AMD64 OCI image, scan it, push/promote it only by immutable
   digest where a registry is used, and record the digest/SBOM;
8. when the GPU worker/model is not yet deployed, or when its code, Dockerfile,
   CUDA/PyTorch lockfiles, model artifact, handler contract or AWS infrastructure
   changed: build and scan the separate NVIDIA-compatible worker, push an immutable
   private ECR digest, run unit/contract tests, execute the required real-GPU
   CUDA/backend/artifact smoke test on temporary compute, deploy/update a SageMaker
   development canary or Batch test job, verify callback/result compatibility,
   and stop the temporary endpoint/job on success or failure. When none changed,
   reuse the registered immutable digest but still run the Prompt 14 end-to-end
   invocation smoke test;
9. before any Data Store/Stratus mutation: verify target project/DC/environment,
   credit/quota and synthetic marker; export the affected serving rows and object
   manifest with hashes/counts; validate that schema changes are additive,
   idempotent and backward-compatible with both current and candidate API versions;
10. deploy the Catalyst development release in a controlled order: additive Data
    Store/Stratus/NoSQL/Cache configuration -> Authentication/Connections and
    server-side secrets -> Functions/internal auth contracts -> AppSail -> API
    Gateway -> Slate/Web Client -> disabled event/job definitions -> enable only
    the workflows implemented in completed phases;
11. run post-deploy health, authentication, API, frontend, serving-data, event/job,
    idempotency and per-model prediction smoke tests; verify no duplicate services,
    schedules, event subscriptions or public AWS routes were created;
12. promote the exact tested immutable frontend/AppSail/Function/AWS-worker
    artifacts to production only through the supported approval gate; do not
    rebuild different artifacts during promotion;
13. on application smoke-test failure, roll Slate/Web Client, Functions and
    AppSail back to the preceding compatible artifact. Do not destructively roll
    back an applied Data Store schema/import; disable new writers/events, restore
    affected serving rows/objects from the verified export when safe, or apply an
    additive forward-recovery migration and reconcile counts/hashes;
14. always release the deployment lock, disable failed/canary event triggers,
    stop temporary GPU endpoints/jobs and record Catalyst/AWS usage even when an
    earlier stage fails.

The agent creates pipeline configuration, project bindings and deploy scripts,
runs the pipeline or equivalent CLI commands, reads logs, fixes failures and
retries. Do not stop after writing YAML or ask the user to perform routine CLI
steps. The only planned pause is the Zoho browser login/consent.

J. Cost/credit controls
- record Catalyst project/environment/component IDs but no secrets;
- verify the credited DHRISTI project and record the screenshot baseline of
  INR 1,500 Basic + INR 300 Free (INR 1,800 total usable) without assuming that
  the entire balance remains available;
- inspect available usage/credit dashboards/APIs without exposing account data;
- create a budget and alerts/checkpoints at approximately 50%, 75% and 90% of the
  available hackathon budget where Catalyst supports them;
- set conservative AppSail memory/disk/instance settings;
- prevent duplicate dev deployments/services;
- keep only the curated linked serving subset in Data Store and lifecycle temporary
  Stratus imports/reports while preserving required demo evidence;
- use NoSQL and Cache only for the bounded responsibilities above;
- add AWS Budgets/CloudWatch alarms and Catalyst usage checks;
- shut down temporary GPU endpoints/jobs after validation;
- provide a post-hackathon cleanup/export runbook that preserves the required
  Catalyst Data Store/Stratus application data and any deliberately retained AWS
  model artifacts while deleting temporary resources.

K. Verification
Test and prove:
- public frontend URL/domain resolves to Catalyst Slate/Web Client Hosting;
- public API URL/domain resolves through Catalyst API Gateway to a Function and,
  for FastAPI routes, from that Function to AppSail;
- no Amplify/CloudFront/ECS/ALB/EC2/Lambda URL hosts the public app;
- React uses Catalyst Authentication, calls only the Catalyst API and contains no
  secret/direct database/AWS URL;
- AppSail health/readiness and Catalyst SDK connectivity work;
- Data Store is the deployed operational record source and full-text search works;
- Stratus upload/download/hash/version/short-lived access works for one digital
  evidence fixture and one report;
- NoSQL and Cache each have one bounded, tested use without becoming a duplicate
  system of record;
- one authenticated synthetic FIR read and one allowed write work end to end;
- one FeatureSnapshot -> AWS Batch/SageMaker prediction -> PredictionResult
  round trip works through Catalyst and persists the result in Data Store;
- draft/save/submit and raw-evidence uploads provably do not trigger a model;
- one approved synthetic FIR triggers only eligible downstream work, including
  idempotent aggregate snapshot staleness/rebuild and the permitted near-repeat
  path, without any person-level score;
- a requested real TabFM smoke test proves `actual_backend=tabfm` and
  `device=cuda`; missing CUDA/weights fail closed instead of silently returning a
  fallback labelled as TabFM;
- TimesFM, ST-GNN/fallback, near-repeat, hotspots/baselines and forecast fusion
  each use their typed inputs/triggers and record actual backend/model/cutoff;
- Signals/Event Function and Job Scheduling trigger/retry/idempotency work;
- Mail/Push and SmartBrowz work for the selected synthetic demo flow;
- QuickML works for the enabled RAG/no-code baseline, or its absence is supported
  by captured feature-gate evidence rather than an unverified claim;
- Catalyst deployment rollback works;
- the CI/CD concurrency lock prevents overlapping same-environment releases;
- a deliberately failed development smoke test restores the preceding compatible
  frontend/API artifacts, and a simulated Data Store migration/import failure
  follows the documented non-destructive forward-recovery/reconciliation path;
- the production promotion uses the exact development-tested immutable digests;
- workflows 13-16 have no enabled schedule/event subscription before Prompts
  17-18 complete, unless an existing completed phase report proves otherwise;
- remaining AWS PostgreSQL RLS/FORCE RLS remain disabled as required;
- direct public AppSail CRUD access is blocked/restricted where supported and
  documented Gateway authentication/throttling cannot be bypassed for application
  routes; any direct WebSocket/SSE exception passes its short-lived-token tests;
- RDS remains private and no 0.0.0.0/0 ingress or direct AppSail CRUD was added;
- every capability has a matching Catalyst service, an explicit not-used state,
  or a documented availability/custom-runtime exception;
- Catalyst and AWS costs/resources are recorded and temporary GPU resources stop.

Create docs/phase-reports/PHASE_14_REPORT.md with:
- Catalyst project/DC/environment and component names/IDs (no tokens);
- the single browser-login pause and proof the agent completed all later steps;
- Slate/Web Client and AppSail URLs/custom domains;
- CLI/version/commands executed with secrets redacted;
- Pipeline and Job Scheduling configuration;
- deployment lock/environment gates, SBOMs, immutable AppSail/Function/frontend
  artifact identities and configuration;
- pre-deploy Data Store/Stratus export hashes/counts plus additive migration,
  compatibility and forward-recovery evidence;
- AWS GPU-worker ECR digest, CUDA canary/Batch test and guaranteed cleanup state
  when model code changed;
- explicit disabled-scaffold/component state for Prompt 16-17 workflows, with no
  premature schedule/event charges;
- organizer capability-to-Catalyst-service compliance matrix with deployed
  component IDs/URLs, test evidence and explicit not-used/unavailable reasons;
- Data Store import mapping, source hashes, row/object counts and rejected rows;
- Stratus/NoSQL/Cache responsibility and retention summary;
- AWS custom-capability gap justifications and adapter security proof;
- input-to-model routing matrix and proof that draft/raw-file events do not invoke ML;
- actual TabFM GPU/container/artifact/device evidence and explicit fallback test;
- per-model request/response schemas, trigger mode, runtime/cost and end-to-end
  TabFM/TimesFM/ST-GNN/near-repeat/fusion smoke-test evidence;
- end-to-end prediction smoke test;
- credited-plan baseline, Catalyst/AWS cost snapshot and shutdown state;
- rollback and post-hackathon cleanup instructions.
~~~

Definition of Done:

- The public React application is deployed on Catalyst Slate/Web Client Hosting.
- The FastAPI service is deployed on Catalyst AppSail and public HTTP API access
  reaches it through the authenticated API Gateway/Function facade.
- Catalyst CLI completed initialization/configuration/deployment with the user
  interacting only with the Zoho browser login/consent page.
- Catalyst Data Store is the authoritative operational database and full-text
  search provider for the deployed application.
- Catalyst Stratus is the authoritative deployed application object store;
  NoSQL and Cache are used only for their documented bounded responsibilities.
- Catalyst Authentication, API Gateway, Functions/AppSail, Signals/Event
  Functions, SmartBrowz, Pipelines and Job Scheduling are configured and tested
  for the capabilities DRISHTI actually exposes.
- Catalyst Pipelines enforces a deployment lock, immutable-artifact promotion,
  additive serving-data changes, application rollback and non-destructive Data
  Store/Stratus forward recovery; later Prompt 16-17 workflows remain disabled
  scaffolds until their own phases complete.
- QuickML is used for enabled RAG/eligible no-code ML; Zia AutoML/Circuits regional
  availability is verified and honestly documented.
- AWS is retained as the complete historical/analytics database and custom
  GPU/geospatial/model plane, but does not replace Catalyst's submitted
  operational application/data services or host the public app.
- One synthetic prediction completes end to end from Catalyst through AWS and back.
- The synthetic FIR/input routing tests prove that only approved structured data
  reaches the correct typed model; raw evidence and drafts never invoke ML.
- A real TabFM run proves CUDA execution and exact backend/artifact identity;
  fallback models are explicit and cannot be mislabelled as TabFM.
- No browser secret, direct database access, open RDS ingress or ambiguous
  bidirectional source-of-truth exists.
- Temporary GPU resources are stopped and Catalyst/AWS usage is documented.

---

# Prompt 15 - Demo admin/governance, notifications, reports, and optional RAG

Objective: finish the hackathon-facing administration, observability, reporting
and optional knowledge assistant without adding OCR or voice extraction.

~~~text
Implement Phase 15: the hackathon Admin/governance console and remaining demo
capabilities.

Admin:
- Catalyst Authentication user/session mapping to synthetic demo roles; no
  Supabase Auth mapping is required;
- units/stations/demo assignments;
- boundaries, source systems and import templates;
- source reconciliation status and rejected/partial import repair;
- audit search/export;
- retention, archival, evidence expiry and legal-hold policy configuration for
  synthetic demonstration records, without destructive automatic deletion;
- feature schemas/model registry, approval/retirement/rollback and owners;
- prediction/job health, drift/quality signals and periodic independent-review due state;
- ingestion/import/data-quality and evidence quarantine/security-scan queues, but
  no OCR/transcription/semantic extraction queue;
- AWS/Catalyst usage, budgets and feature flags;
- saved dashboard/report filters and role-appropriate configurable report templates;
- visible HACKATHON_MODE, DEMO_DATA_ONLY and RLS-disabled status indicators.

Notifications/work:
- optional case/evidence/review task assignments;
- notification preferences, escalation SLA/due state and delivery history;
- in-app/email/push only for non-sensitive synthetic summaries;
- no evidence content, full narrative or identifiers in notification bodies.

Reports:
- PDF/report generation from structured database fields;
- server-side export authorization and role/case/unit scope checks;
- source/version citations;
- prominent "Synthetic Hackathon Demo" watermark;
- reproducible report snapshot and audit event;
- no OCR or parsing of uploaded files.

Voice:
- voice input and speech-to-text are deferred with Prompt 6;
- do not include microphone/transcription as a required hackathon feature.

Optional RAG/chat:
- use only approved SOP/policy text and manually entered/approved structured text;
- do not ingest uploaded file bytes through OCR;
- filter by selected synthetic demo case/unit context;
- cite source/version;
- enforce the same Catalyst identity, demo role, case/unit scope and source access
  checks as ordinary APIs before retrieval;
- refuse when no supporting source is available;
- do not invent case facts;
- evaluate with a small fixed synthetic question/citation set;
- retain only data-minimized prompt/response/audit metadata with an explicit
  synthetic retention setting; never log secrets or unrestricted evidence text;
- make the feature optional so the demo works without it.

Catalyst services:
- run this module inside the Prompt 14 Catalyst deployment;
- read/write operational metadata through Catalyst Data Store and use its
  full-text search for audit/case/report metadata search;
- store generated report objects in private Stratus and store their hashes,
  versions, source snapshot and lineage in Data Store;
- use SmartBrowz for PDF/screenshot report generation instead of maintaining a
  competing headless browser service;
- use Catalyst Mail and Push only for non-sensitive synthetic notifications;
- use Signals for report.ready/prediction.reviewed/notification events after the
  authoritative Data Store write commits;
- use Catalyst Cache only for short-lived dashboard/lookup caches;
- use Catalyst QuickML RAG for the optional approved-text knowledge assistant
  when that capability is enabled. If the project does not expose it, retain a
  graceful disabled state and capture feature-gate evidence; do not replace it
  with a third-party RAG service for the submission;
- do not use Zia OCR, voice extraction or image analysis in hackathon scope;
- retain AWS RDS for the complete historical/analytics dataset and use AWS only
  for justified custom model/advanced analytics calls. Data Store and Stratus
  remain the deployed application's curated operational sources of truth.

Tests:
- admin health/status values;
- Catalyst identity/role mapping and API authorization matrix;
- RLS-disabled status check;
- audit search;
- retention/legal-hold non-destructive behavior;
- notification preference/escalation/delivery status;
- model drift/review-due and rollback views;
- synthetic report watermark/audit;
- Data Store report metadata and Stratus object/hash/expiry checks;
- notification data minimization;
- optional RAG citations/refusal and graceful disabled state;
- SmartBrowz report or documented AppSail fallback;
- Signals/Mail/Push data minimization when enabled;
- proof that no voice/OCR/extraction dependency is needed.

Create docs/phase-reports/PHASE_15_REPORT.md.
~~~

Definition of Done:

- Admin placeholder is replaced with useful demo controls and health views.
- Retention/legal hold, notification preferences/escalations, model lifecycle/
  drift review and source reconciliation have working synthetic demo paths.
- Reports and notifications work with synthetic structured data and are audited.
- SmartBrowz, Stratus, Signals, Mail/Push and Data Store are used for their
  matching enabled report/notification capabilities.
- RAG is optional, uses approved text only, and uses QuickML when enabled.
- Voice, OCR and extraction remain deferred.

---

# Prompt 16 - Palantir-style Investigation Board on Catalyst with AWS analytics

Objective: add a shared, object-backed analytical canvas where an investigator
can assemble live DRISHTI objects, explore their relationships, separate source
evidence from human hypotheses, annotate reasoning, replay changes, and export a
fully attributable synthetic demonstration board.

~~~text
Implement Phase 16: the DRISHTI Investigation Board.

Read first:
- C:\Users\Prajwal\Desktop\06_INVESTIGATION_BOARD.md completely;
- POLICE FILES/01_UX_UI_ARCHITECTURE.md;
- POLICE FILES/03_DATA_VISUALIZATION.md;
- POLICE FILES/04_NETWORK_GRAPH_ANALYSIS.md;
- docs/phase-reports for completed identity, evidence, import and graph work;
- the Palantir Gotham G-Cloud 14 service document linked at the top of prompt2.md,
  especially its Workspace, Browser, Dossier, Graph, Canvas, Selection, History,
  Table, Search Around and Timeline interaction descriptions.

Use Palantir only as a behavioral reference: shared object-centric analysis,
cross-application object transfer, canvas helpers, history and source-linked
exports. Do not copy Palantir names, branding, screenshots, icons, layouts,
proprietary text or visual assets. Render everything with DRISHTI's Calm
Authority design system.

Current architecture and scope:
- React is deployed through Catalyst Slate/Web Client Hosting;
- FastAPI/board APIs are deployed through Catalyst AppSail behind API Gateway;
- Catalyst Authentication provides the demo session/user identity;
- Catalyst Data Store is the board's operational relational source of truth;
- Catalyst NoSQL stores flexible canvas layout/preferences/ephemeral presence;
- Catalyst Stratus stores existing digital evidence objects and generated exports;
- AWS RDS retains the full historical graph/analytics corpus and may perform
  advanced graph/geospatial computation through the protected AWS adapter;
- React calls Catalyst APIs only; the browser never queries RDS or AWS directly;
- RLS and FORCE RLS remain disabled on remaining AWS PostgreSQL tables;
- no Supabase client, Supabase Realtime or Supabase Auth dependency;
- only synthetic data and synthetic demo actors;
- OCR, transcription and automatic file-content extraction remain deferred.

Application authorization while PostgreSQL RLS is disabled:
- map Catalyst Authentication identities to synthetic IO, Analyst, Supervisor
  and policymaker/demo-lead roles;
- IOs can own/edit assigned-case boards, Analysts can use explicitly shared
  boards, and Supervisors can share, lock, branch and promote within demo scope;
- policymakers/demo-leads have no board access because boards model sensitive
  investigative material, even though all hackathon data is synthetic;
- enforce `investigation_board`, `board_share` and `board_promote` permissions in
  AppSail/Functions for every read, mutation, collaboration and export route;
- warn/block sharing beyond the referenced case/unit scope and require a fresh
  authenticated confirmation for lock, promotion and export actions.

A. Preflight and Catalyst data design
1. Inspect Prompt 14's Data Store schema/import map. Create versioned Catalyst
   table/schema configuration and repeatable CLI/SDK provisioning; do not add a
   new PostgreSQL operational migration for the submitted board.
2. Add Data Store tables without recreating existing case, identity, graph or
   evidence tables:
   - InvestigationBoard;
   - BoardNode;
   - BoardEdge;
   - BoardAnnotation;
   - BoardCollaborator;
   - BoardActivity.
3. InvestigationBoard fields:
   BoardID, Title, Description, OwnerDemoActorID/OwnerEmployeeID as supported by
   the current schema, optional CaseMasterID, Status active|archived|locked,
   Visibility private|shared|unit for demo presentation, IsLocked, Version,
   CreatedAt and UpdatedAt.
4. BoardNode Data Store fields:
   BoardNodeID, BoardID, NodeKind, RefTable, RefID, optional CanonicalEntityID,
   Label, PosX, PosY, Width, Height, StyleJSON, SnapshotJSON,
   SourceVersion/SourceHash where available, CreatedBy and CreatedAt.
5. BoardEdge fields:
   BoardEdgeID, BoardID, SourceNodeID, TargetNodeID,
   EdgeClass evidence|hypothesis, Label, RelationshipType, Directed,
   Confidence, Rationale, optional EvidenceCaseID/SourceRecordID, Style jsonb,
   CreatedBy and CreatedAt.
6. BoardAnnotation supports sticky, text, frame and freehand kinds with content,
   geometry/style JSON, author and timestamps. Use Catalyst-compatible types and
   validate/size-limit serialized JSON at the API boundary.
7. BoardCollaborator stores owner/editor/viewer demo collaboration state. It is
   useful for the UI but is not a production security boundary in hackathon mode.
8. BoardActivity is append-only and stores BoardActivityID, BoardID, demo actor,
   action, target type/ID, before/after or compact DiffJSON, request ID and
   CreatedAt. Block normal UPDATE/DELETE through Data Store permissions and every
   application repository/API path.
9. Create supported Data Store indexes/search columns for BoardID references,
   (RefTable, RefID), CanonicalEntityID, activity ordering and owner/status.
10. Store flexible layout snapshots, user view preferences and ephemeral presence
    in a NoSQL collection keyed by BoardID/user/session. Data Store board/node/
    edge/activity records remain authoritative; NoSQL must be reconstructable.
11. Keep RLS and FORCE RLS disabled on any optional AWS analytics mirror. Do not
    create RLS policies. Catalyst Authentication/API authorization remains active.

B. Object and provenance contract
1. A board node is a reference to a canonical DRISHTI object, not a detached copy.
2. Whitelist supported RefTable/object types server-side; never interpolate an
   arbitrary client-supplied table name into SQL.
3. Support at minimum:
   case/FIR, canonical person, accused, victim, complainant, organisation, other
   case party, vehicle/property, phone/device, account/transaction,
   location/hotspot/map extract, statement, digital import, evidence metadata,
   document/image reference, graph entity, prediction/result and cited chat answer.
   Add `news_event` only when the governed OSINT module exists; render it as
   unverified open-source material with source/version, never as corroborated fact.
4. Prompt 17 later adds hazard event, risk zone, resource, shelter and allocation.
5. Store both:
   - a live object reference that opens the authoritative DRISHTI detail page;
   - a pin-time Snapshot with source/version/hash so the board remains explainable
     if the live object changes.
6. Show live-vs-snapshot differences and broken/superseded references explicitly.
7. Never copy uploaded file bytes into board JSON and never parse them automatically.
8. Preserve the strict edge distinction:
   - evidence edge = imported from verified graph/source data, solid, read-only;
   - hypothesis edge = drawn by a demo investigator, dashed, editable, requires
     a rationale before it can be promoted.
9. Promoting a hypothesis creates a review proposal/AlertHistory item. It must
   never silently create a confirmed NetworkEdge or factual assertion.

C. FastAPI service and transactional API
Implement typed endpoints equivalent to:
- POST /boards;
- GET /boards;
- GET /boards/{board_id};
- PATCH /boards/{board_id};
- POST /boards/{board_id}/archive;
- POST /boards/{board_id}/lock;
- POST /boards/{board_id}/branch;
- POST/PATCH/DELETE /boards/{board_id}/nodes[/node_id];
- POST/PATCH/DELETE /boards/{board_id}/edges[/edge_id];
- POST/PATCH/DELETE /boards/{board_id}/annotations[/annotation_id];
- GET/POST/DELETE /boards/{board_id}/collaborators;
- POST /boards/{board_id}/import/subgraph;
- POST /boards/{board_id}/search-around;
- POST /boards/{board_id}/promote-edge/{edge_id};
- GET /boards/{board_id}/activity?after_id=...;
- GET /boards/{board_id}/table;
- GET /boards/{board_id}/timeline;
- GET /boards/references/{ref_table}/{ref_id};
- POST /boards/{board_id}/export;
- GET /boards/{board_id}/export/{export_id}.

For every mutating request:
- validate the synthetic database/hackathon write guard;
- validate the Catalyst Authentication session and server-side demo role;
- use an idempotency key;
- validate object references and board state;
- use optimistic concurrency through board Version/If-Match;
- use a supported Data Store atomic operation when available. If cross-table
  transactions are not supported, use an idempotent pending/committed mutation
  record with Function/Job compensation and replay so BoardActivity cannot claim
  an uncommitted board change; use a Circuit only if it becomes available in IN;
- return the new BoardActivityID and board Version;
- reject edits to locked boards;
- never expose SQL, database identifiers beyond the approved object contract,
  credentials, raw evidence content or unrestricted snapshots.

D. DRISHTI board experience
Create the top-level Crime Intelligence destination Investigation Board with:
- My Boards: blank, from-case and from-network-selection templates;
- Canvas: the main analytical workspace;
- Timeline: replay/scrub construction history;
- Evidence Trail: source inventory and export preview.

Use a four-region analysis workspace inspired by the referenced behavior:
- left object palette/search/filter panel;
- center React Flow canvas;
- right Selection Inspector showing the selected object's properties, source,
  linked records and open-in-source action;
- collapsible bottom helper drawer for Table, History, Timeline and statistics.

Required canvas interactions:
- drag/drop or Send to Board from another DRISHTI surface;
- pan, zoom, minimap, fit selection and focus mode;
- lasso/multi-select, move, align, distribute and group/frame;
- create/edit sticky notes and annotations;
- connect nodes with a hypothesis edge and mandatory rationale;
- filter/search objects and edges without deleting them;
- evidence/hypothesis visibility toggles;
- on-demand force, radial or hierarchical tidy layout while preserving manual
  positions outside the selected set;
- selected-object details without leaving the board;
- Search Around with hop/type/time filters and preview-before-add;
- Table helper with sortable/exportable node and edge inventory;
- History helper with actor/action/diff;
- Timeline/time scrubber that dims out-of-window objects rather than deleting them;
- undo/redo for the current client session, with every committed result audited;
- keyboard accessibility and useful empty/loading/error/conflict states;
- the documented `F` shortcut and a visible control enter/exit projector focus
  mode without trapping keyboard or screen-reader users.

Visual contract:
- use custom node renderers per object kind: person nodes reuse the profile header,
  case nodes show case number/status, map extracts show a static map thumbnail,
  evidence/document/image nodes expose metadata/provenance but never raw bytes,
  and cited-chat nodes show approved sources;
- node colour encodes entity/object type consistently with the graph module;
- imported graph-node size may encode centrality with a visible legend;
- a reviewed person-of-interest flag may use the existing labelled halo treatment;
  never infer that state from board proximity or a hypothesis edge;
- evidence edges are solid; hypothesis edges are dashed;
- selected and suggested objects use separate outlines/ghost states;
- confidence is shown as text/tooltip, never colour alone;
- avoid a hairball: start with a small selection and expand on demand.

E. Cross-application interoperability
Add Send to Board to:
- case/FIR detail;
- People and canonical entity profiles;
- Network Analysis node, selected cluster and selected path;
- Map/Hotspots selected feature or bounded map extract;
- digital/financial import records and reviewed links;
- prediction/result cards with their FeatureSnapshot reference;
- cited Ask DRISHTI response when that module is enabled;
- governed OSINT/news events when that future module is enabled, preserving the
  visible unverified-source label.

The action opens a board picker, then creates object references through FastAPI.
Do not serialize whole records in the URL or frontend state.

F. Search Around and subgraph import
1. Reuse the completed canonical graph service through the protected AWS
   analytics adapter; never reintroduce name matching.
2. Default to one hop, allow at most three hops, and require maxNeighbors/maxNodes.
3. Rank neighbors using reviewed edge weight/relevance and show a preview count.
4. Import verified relationships as read-only evidence edges with provenance.
5. Mark candidate/unverified relationships visibly and never call them facts.
6. Cache only safe query results in Catalyst Cache and invalidate when graph source
   versions change.
7. Benchmark a two-hop capped import and document node/edge counts and latency;
   target approximately two seconds on the fixed golden fixture and record the
   measured environment rather than hiding a miss.

G. Catalyst-hosted real-time collaboration
1. Do not use Supabase Realtime.
2. Test FastAPI WebSockets on the deployed AppSail custom runtime. If the selected
   AppSail/DC/runtime does not preserve the required connection behavior, use
   Server-Sent Events or short Data Store activity polling as the fallback.
   Do not deploy an AWS ALB/ECS service solely for board collaboration.
   Any direct AppSail WebSocket/SSE handshake must present a short-lived token
   minted through the authenticated API Gateway/Function path and bound to the
   Catalyst user, BoardID, allowed action, audience and exact frontend Origin.
3. Broadcast only after the authoritative Data Store mutation commits. Events
   contain BoardID,
   BoardActivityID, board Version, mutation kind, target and demo actor; never
   broadcast full sensitive snapshots unnecessarily.
4. Reconnect using after_activity_id and replay BoardActivity so no committed
   change is lost.
5. Presence cursors/selections are ephemeral, rate-limited/throttled and stored in
   NoSQL/Cache with short TTL rather than Data Store activity history.
6. Use Catalyst Signals/Event Functions for backend board.activity notifications
   after the Data Store commit. Signals is not assumed to be a browser WebSocket
   transport; Data Store BoardActivity replay/polling remains the correctness path.
7. Resolve concurrent moves with optimistic versions/last committed position and
   show a non-destructive conflict notice for semantic edits.

H. Optional grounded board assist
Implement only after Prompt 11 and the optional Prompt 15 RAG contract exist:
- Explain this board: cited summary of the selected node/edge set;
- What am I missing?: propose related nodes/links from verified graph/similar-case
  results.

Requirements:
- feature-flagged and gracefully absent;
- suggestions are ghost nodes/edges until accepted;
- acceptance creates a hypothesis, never a confirmed fact;
- every suggestion includes source record IDs, model/version and limitations;
- no uploaded file bytes are sent for OCR/extraction;
- no automatic person-level guilt/risk judgement.

I. Locking, branching and export
1. Lock freezes nodes, edges, annotations, title and layout for filing/demo review.
2. Locking requires owner/Supervisor permission. Editing a locked board requires
   an authorized owner/Supervisor to branch a new board linked to its parent; the
   locked version is never modified.
3. Export through Job Scheduling/Functions (or Circuits only if newly available)
   and SmartBrowz to private Stratus with
   short-lived
   download URLs.
4. PDF export includes:
   canvas image, title/version/time, synthetic watermark, node inventory,
   evidence edges and sources, hypothesis edges with rationale/author,
   source-version trail and activity summary/digest.
5. Also support JSON export/import of the DRISHTI board schema for backup, but
   validate all references and never accept arbitrary SQL/table names.

J. Datagen and tests
Add deterministic golden fixtures for:
- a case board with case, people, phone, vehicle, account and location nodes;
- imported evidence links;
- two hypothesis links with rationale;
- annotations and frames;
- collaborator/demo actor activity;
- locked board and branched copy;
- changed/superseded source snapshot;
- Prompt 17 later adds a disaster-review board fixture.

Test:
- Data Store schema/index/search/import and AWS RLS-disabled verification;
- NoSQL reconstructability and Cache/presence TTL behavior;
- whitelisted reference hydration and injection rejection;
- IO/Analyst/Supervisor/policymaker allow-deny matrix, out-of-scope share blocking
  and fresh-confirmation checks for lock/promotion/export;
- mutation + BoardActivity atomicity or compensation/replay and append-only behavior;
- evidence edge immutability versus hypothesis editability;
- rationale required before promotion;
- optimistic concurrency/idempotency;
- locked-board rejection and branch success;
- capped Search Around/subgraph import and no name-based links;
- live reference, snapshot and source-difference display;
- two-browser WebSocket synchronization, reconnect/replay and polling fallback;
- Send to Board from every required surface;
- Table/History/Timeline helpers;
- accessible keyboard navigation and responsive projector focus mode;
- reverse reference lookup and custom renderers for person/case/map/evidence/chat;
- private Stratus export, expiry, object hash and synthetic watermark;
- proof that the board frontend/API are deployed through Catalyst;
- proof of Catalyst Authentication/API Gateway enforcement, no direct
  RDS/Supabase/AWS browser access and no OCR dependency.

Create docs/phase-reports/PHASE_16_REPORT.md with Data Store/NoSQL table or
collection counts,
API/routes, screenshots, two-hop benchmark, collaboration test, export sample,
RLS-disabled verification, limitations and exact Prompt 17 prerequisites.
~~~

Definition of Done:

- A user can create a board, pin supported live objects, move/group/style them,
  annotate reasoning and persist the result.
- Evidence and hypothesis edges are visibly and structurally distinct.
- Selection, Search Around, Table, History and Timeline helpers work.
- Send to Board works from cases, entities, graph, map and supported analytics.
- Capped two-hop import is performant and does not produce a hairball.
- Concurrent demo users see committed edits and can recover missed events.
- Locking, branching and private source-linked export work.
- IO/Analyst/Supervisor permissions and policymaker denial are enforced by the
  Catalyst-authenticated API even though PostgreSQL RLS is disabled.
- Every mutation is attributable through append-only BoardActivity.
- The board runs through Catalyst Authentication/API Gateway/Slate/AppSail with
  Data Store, NoSQL, Cache, Signals and Stratus as its application services.
- AWS RDS is retained only for protected graph/advanced analytics, AWS RLS stays
  disabled as requested, and there is no OCR or direct browser-database dependency.

---

# Prompt 17 - Disaster Response forecasting, readiness, allocation, and maps

Objective: add a separate Emergency Response context that converts synthetic or
approved digital hazard feeds into reproducible area-level forecasts, visible
uncertainty, human-approved resource plans and safe evacuation-route proposals.

~~~text
Implement Phase 17: DRISHTI Disaster Response.

Read first:
- C:\Users\Prajwal\Desktop\07_DISASTER_RESPONSE.md completely;
- C:\Users\Prajwal\Desktop\06_INVESTIGATION_BOARD.md integration notes;
- POLICE FILES/01_UX_UI_ARCHITECTURE.md;
- POLICE FILES/02_ADVANCED_TECHNOLOGY.md;
- POLICE FILES/03_DATA_VISUALIZATION.md;
- POLICE FILES/05_GEOSPATIAL_CRIME_ANALYTICS.md;
- Prompt 9, 10, 12, 14 and 16 reports/contracts.

Scope and safety:
- this is a synthetic hackathon decision-support demonstration, not an official
  warning, dispatch or evacuation system;
- predictions operate at area/time-period level and never make person-level
  policing decisions;
- no forecast may auto-publish an alert, auto-dispatch a resource or declare an
  area safe;
- stale/missing feeds and low confidence must escalate visibly to a human;
- all input is digital API/CSV/JSON/manual structured data; no OCR/transcription;
- RLS and FORCE RLS stay disabled on remaining AWS PostgreSQL tables;
- Browser -> Catalyst frontend -> Authentication -> API Gateway -> Function
  facade -> AppSail -> Data Store/Stratus is the application data path. Only protected
  server-side calls may reach AWS custom model/geospatial/analytics workloads.

Application authorization while PostgreSQL RLS is disabled:
- add a synthetic `disaster_coordinator` role mapped through Catalyst
  Authentication and server-side role middleware;
- enforce `disaster_forecast`, `resource_allocation` and `evacuation_plan`
  permissions on every API action;
- a coordinator may review warnings and approve/dispatch allocations only inside
  the assigned synthetic district/unit; ordinary crime roles receive at most the
  explicitly allowed read-only situational view;
- require fresh authenticated confirmation for warning approval, dispatch and
  evacuation-plan approval, and audit every allow/deny decision.

A. Context and navigation
1. Add a workspace switcher at the top of the shell:
   Crime Intelligence | Emergency Response.
2. Keep Investigation Board inside Crime Intelligence, but allow Prompt 17 hazard
   objects to be sent to a board for after-action analysis.
3. Emergency Response destinations:
   - Situation Overview;
   - Live Situation;
   - Forecast & Risk;
   - Resources;
   - Response Plans.
4. Preserve selected context in the URL/router, not only local component state.
5. Use a visually urgent but calm disaster palette and accessible status labels;
   do not reuse criminal-person risk visuals for hazards.

B. Catalyst operational schema and optional AWS geospatial mirror
Inspect Prompt 14's versioned Catalyst schema/import map. Provision the following
operational tables in Catalyst Data Store through repeatable CLI/SDK/configuration.
If the measured spatial/routing workload requires PostGIS/pgRouting, use the next
available AWS migration (prefer services/ml/sql/017_disaster_response.sql only if
017 is unused) to create an idempotent analytics mirror keyed by the same stable
ExternalIDs. The AWS mirror is reconstructable and is not the submitted app's
operational source of truth.

Add:
- HazardType;
- HazardEvent;
- HazardPrediction;
- HazardRiskZone;
- HydroMetReading;
- Resource;
- ReliefShelter;
- ResourceAllocation;
- EvacuationRoute;
- ResponsePlan;
- ResponseTask;
- optional FeedSource/FeedIngestionRun if current SourceSystem/IngestionJob cannot
  represent hazard feeds cleanly.

Required model:
1. HazardType lookup initially supports flood, urban_flood, landslide, drought,
   heatwave, cyclone, forest_fire, dam_breach and lightning.
2. HazardEvent stores type, predicted/watch/warning/active/recovery/closed status,
   severity, district/unit, geometry, onset/peak time, source and description.
3. HazardPrediction stores ModelVersionID, FeatureSnapshot/input snapshot,
   hazard, district/unit, geometry, forecast window, probability, predicted
   severity, expected impact, calibrated confidence, factors and CreatedAt.
4. HazardRiskZone stores static/dynamic polygons, centroid, risk level/score,
   factor JSON, valid period and source/version.
5. HydroMetReading stores station/source/metric/value/unit/geometry/district,
   observed time, received time, quality flag and ingestion/source reference.
   Support rainfall, river_level, reservoir_level, temperature, wind and humidity.
6. Resource stores resource type, quantity/unit, home unit, position, capacity,
   capabilities, status and last-updated time. Support personnel, vehicle, boat,
   ambulance, relief_material, equipment and medical resource categories, linking
   deployable personnel to the existing synthetic Employee/Unit contract.
7. ReliefShelter stores location, capacity, occupancy, facilities and status.
8. ResourceAllocation stores proposed/approved/dispatched/enroute/onsite/released
   lifecycle, assigned resource/quantity, target zone, reason/score, approver/demo
   actor and timestamps.
9. EvacuationRoute stores event, from-zone, shelter, LineString, distance/time,
   road-graph version, hazard-exclusion version, status and notes.
10. ResponsePlan/ResponseTask store hazard-specific SOP checklists, assignment,
    due time and lifecycle.
11. Reuse AlertHistory by adding a nullable HazardEventID and hazard alert types
    through an idempotent migration. Do not create a competing alert system.
12. Reuse ModelVersion, ModelInference, FeatureSnapshot, SourceRecord,
    IngestionJob, WeatherIndicator/external context and audit tables where their
    current contracts fit; do not create competing model, weather or audit stores.
13. Store validated GeoJSON plus canonical CRS/source/version fields in Data Store
    and create supported search/index columns for time/district/status. Add GiST
    indexes only to the optional AWS PostGIS analytics mirror.
14. Keep RLS/FORCE RLS disabled on the optional AWS mirror and add no policies.
    Enforce Catalyst Authentication and server-side demo-role checks at the API.

C. Synthetic disaster datagen
Add a deterministic datagen/disaster.py module and scenario registry entries for:
- coastal cyclone/monsoon flooding in Dakshina Kannada, Udupi and Uttara Kannada;
- Western Ghats landslide conditions in Kodagu and Chikkamagaluru;
- drought/heatwave in north-interior districts;
- reservoir/river-basin flooding for Cauvery, Krishna and Tungabhadra scenarios;
- Bengaluru urban flooding;
- normal/no-event periods, stale feeds, missing sensors, conflicting readings,
  false alarms, low-confidence forecasts and a late corrected observation;
- available/maintenance/deployed resources and shelters at varying occupancy;
- a route blocked by a hazard polygon and an alternate safe route.

Generate only clearly labelled synthetic records. Reuse canonical Karnataka
boundaries and Unit rows so all points/polygons pass spatial containment.
Add minimum-scenario assertions and deterministic seeds.

D. Pluggable digital feed ingestion
1. Define a connector interface that emits normalized HydroMetReading or
   HazardEvent candidates plus source/version/licence metadata.
2. Required hackathon connector: deterministic synthetic replay from JSON/CSV.
3. Implement at least one read-only live connector—prefer official rainfall from
   IMD/KSNDMC/CWC—when a documented endpoint, licence and required credential are
   available. Otherwise complete the same connector contract against an approved,
   versioned recorded sample, mark `External Access Required` in the phase report
   and keep the deterministic replay as the reliable demo path. Other connectors
   may target Karnataka WRD, GSI, Bhuvan/ISRO, NASA FIRMS or FSI only after
   verifying current official access, licensing, rate limits, attribution and
   geographic coverage at implementation time.
4. Never scrape a portal or bypass registration/terms to make the demo work.
5. Store raw approved feed payloads/version manifests in private Stratus and
   normalized records in Data Store; do not log full payloads or credentials.
   Use S3 only for temporary copies required by SageMaker/AWS Batch.
6. Use idempotent source keys, observed-at versus received-at, unit conversion,
   geometry validation, duplicate detection, quality state and retry/DLQ handling.
7. Record feed heartbeat/freshness and expose stale/failed status to the UI.
8. Do not let an unvalidated reading directly produce a canonical forecast/alert.

E. Hazard models and validation
Implement transparent baselines before complex models:
- flood/urban flood: rainfall and river/reservoir thresholds plus a persistence
  or seasonal baseline, drainage/HAND terrain where approved, and optional
  TimesFM trajectory forecast;
- landslide: rule/RTM susceptibility from slope, terrain and antecedent rainfall;
- drought: SPI/rainfall deficit, reservoir trend and approved NDVI context baseline;
- heatwave: temperature threshold/percentile rule;
- cyclone: imported official track/cone buffered through the protected AWS
  PostGIS analytics adapter when the Catalyst-side GeoJSON baseline is insufficient;
- forest fire: approved detection feed plus dryness/temperature baseline; evaluate
  Hawkes/ST-GNN spread only as a versioned candidate after the baseline passes.

For the hackathon:
1. Support all HazardType values and deterministic baseline fixtures.
2. Fully validate only one MVP forecasting path: flood/urban flood is recommended
   when usable time-series data exists; otherwise choose landslide RTM.
3. Run TimesFM through the Prompt 14 AWS Batch/SageMaker batch contract. Do not
   keep a GPU endpoint running when batch inference is sufficient.
4. Run threshold, RTM, SPI and routing/optimization workloads on CPU
   Fargate/AWS Batch unless measurement proves a GPU need.
5. Every forecast uses an immutable input/FeatureSnapshot and stores data-as-of,
   model/rule version, feature schema, factors, quality, confidence and horizon.
6. Compare against persistence/seasonal/threshold baselines using time-based and
   geographic holdouts. Report calibration, MAE/RMSE where appropriate, event
   precision/recall, false-alarm rate and missed-event rate.
7. Never represent an unvalidated probability as certainty. Distinguish observed,
   model-predicted, official-warning and synthetic-scenario layers.
8. A newer reading invalidates/supersedes affected future predictions through the
   existing version/staleness workflow; it never rewrites history.
9. Persist authoritative prediction/model/source metadata and validated outputs in
   Data Store. AWS model jobs receive immutable, minimum-required snapshots and
   return results only through the protected adapter.
10. Implement the documented fusion contract where used: distribute a coarse
    district/time probability over validated terrain/susceptibility geometry,
    retain both layers, expose a layer switcher and show per-cell confidence. Do
    not present a visually detailed fused surface as more certain than its inputs.

F. Forecast pipeline
Implement:
validated readings -> feature/input snapshot -> baseline/model job -> validate
output -> HazardPrediction/HazardRiskZone -> human review -> optional HazardEvent
watch/warning proposal -> approved AlertHistory item -> UI/WebSocket notification.

Every authoritative pipeline state above is recorded in Data Store. Use Signals
and Event Functions for state-change events and Circuits for the multi-step flow
when available; otherwise use idempotent Functions + Job Scheduling and record the
India-DC/project limitation.

Requirements:
- idempotency, retries, timeout, DLQ and audit;
- no prediction job on raw file upload;
- no automatic public notification;
- explicit stale, failed, superseded and rejected states;
- visible explanation/factor list and source trail;
- cost/latency metrics and batch shutdown verification.

G. Resource allocation and evacuation
1. Build Resource and ReliefShelter CRUD/import through structured forms/CSV into
   Catalyst Data Store.
2. Estimate zone impact using hazard geometry, approved synthetic population/
   SocialIndicator/assets context and explicitly versioned assumptions.
3. Start with a transparent weighted-greedy allocator:
   nearest capable available resource under capacity/quantity/coverage limits.
4. Make Google OR-Tools an optional CPU upgrade for multi-constraint assignment
   or vehicle routing. Compare it to the greedy result on fixed fixtures.
5. The optimizer produces a proposed ResourceAllocation with score/reasons;
   a human must approve before dispatched status.
6. Load a versioned OpenStreetMap-derived road graph only from an approved source
   and record its extract date/licence attribution. Build a separate geographic
   road topology (for example with osm2pgrouting); never reuse the entity-intelligence
   graph as a physical road network.
7. Use pgRouting to find paths from resource/unit to risk zone and from risk zone
   to a suitable shelter. Exclude road edges intersecting the active hazard/block
   geometry and surface when no safe route exists. Execute this justified advanced
   geospatial computation through the protected AWS adapter, then validate and
   materialize the selected route GeoJSON/version in Data Store.
8. Track planned -> approved -> dispatched -> enroute -> onsite -> released with
   timestamps and append-only audit/activity.
9. Never auto-dispatch or describe a route as guaranteed safe.

H. Emergency Response UI
Situation Overview:
- active synthetic hazards and alert acknowledgement;
- existing AlertHistory red-zone pulse and data-minimized ambient alert feed;
- data freshness banner;
- readiness KPIs and allocated-versus-required bullet charts;
- open tasks, unavailable resources and low-confidence warnings.

Live Situation:
- deck.gl/PostGIS hazard extent/risk polygons;
- rate-normalized choropleth where a denominator exists, never raw counts disguised
  as comparable risk;
- sensor/readings layer;
- resource, shelter and route layers;
- district -> taluk/unit -> point drill-down;
- time scrubber for observed and forecast windows, including the selected 72-hour
  planning horizon when supported by the model;
- clear observed/predicted/synthetic legend.

Forecast & Risk:
- hazard/horizon/model/data-as-of selectors;
- confidence-hatched risk surface;
- TimesFM fan chart where used;
- accessible risk gauge plus factor bars/RTM explanation;
- model/source/version Evidence Trail;
- compare baseline versus selected model;
- stale/superseded/low-confidence states.

Resources:
- inventory/readiness table and map;
- allocation planner with requirement/capacity constraints;
- resource-to-zone Sankey or accessible table fallback for allocation flow;
- side-by-side proposed routes/resources and reason scores;
- explicit approve/dispatch lifecycle controls;
- shelter capacity/occupancy.

Response Plans:
- per-hazard SOP template;
- checklist/task assignment;
- due/overdue/complete states;
- event timeline and after-action export.

I. Alerts, collaboration and Investigation Board integration
1. Reuse AlertHistory and the existing FastAPI WebSocket/polling event channel.
2. Threshold/model output creates a reviewable proposal; a demo coordinator
   explicitly confirms watch/warning creation.
3. Critical UI treatment must still show confidence, freshness and synthetic label.
4. Add Send to Board for HazardEvent, HazardPrediction, HazardRiskZone, Resource,
   ReliefShelter, ResourceAllocation and EvacuationRoute.
5. Board hazard nodes remain live references with pin-time snapshots. Allocation
   reasoning added by users remains a hypothesis/annotation, not source evidence.

J. Catalyst deployment and AWS external workloads
Catalyst application layer:
- Slate/Web Client Hosting serves the Emergency Response React routes;
- Catalyst Authentication secures sessions and API Gateway fronts Function APIs;
  the Function facade invokes AppSail hazard/resource/plan services server-side;
- Data Store is authoritative for normalized readings, hazards, forecasts, risk
  zones, resources, shelters, allocations, routes, plans, tasks and alert metadata;
- Stratus is authoritative for raw approved feed snapshots and generated reports;
- NoSQL stores only selected flexible feed envelopes/map/UI preferences and Cache
  stores only bounded short-TTL lookup/map results;
- Catalyst Job Scheduling is the primary scheduler for synthetic feed replay,
  freshness checks, aggregate forecasts and cleanup. Target an AppSail internal
  endpoint or a protected AWS webhook;
- Signals + Event Functions publish feed.stale, forecast.completed,
  alert.review_required and allocation.approved after Data Store commits;
- Circuits orchestrates the multi-step forecast/review workflow when exposed in
  the project; otherwise Functions + Job Scheduling is the documented fallback;
- SmartBrowz generates after-action PDF/map screenshots into Stratus;
- Catalyst Mail/Push sends non-sensitive synthetic warning/task summaries;
- Catalyst Pipelines deploy and verify the new frontend/AppSail code.

AWS external layer:
- RDS PostgreSQL/PostGIS/pgRouting: retained full analytics corpus and
  reconstructable geospatial/routing computation mirror, never submitted-app CRUD;
- S3: temporary SageMaker/AWS Batch inputs/outputs and model artifacts only;
- protected API Gateway + Lambda/ECS adapter when private-VPC access is needed;
- SQS + DLQ for ingestion/forecast/allocation jobs where asynchronous work exists;
- AWS Batch/SageMaker Batch for TimesFM or large backfills;
- CPU AWS Batch for heavy OR-Tools/routing backfills only when AppSail limits or
  measurements justify it;
- ECR for pinned AWS worker images and optional AppSail source image;
- Secrets Manager/SSM and AWS roles inside AWS; no static keys in code/frontend;
- CloudWatch dashboards/alarms for AWS freshness, failures, latency and cost;
- budgets and automatic shutdown for temporary compute.

Do not deploy the primary FastAPI API, React application or routine scheduler on
ECS/ALB, Amplify/CloudFront or EventBridge. EventBridge is allowed only for an
AWS-internal model workflow that Catalyst Job Scheduling cannot trigger safely.

Do not introduce DynamoDB or another database. Catalyst Data Store/Stratus remain
authoritative for the submitted operational feature, while AWS RDS remains the
retained full historical/analytics database.

K. Tests and failure exercises
Test:
- Data Store schema/index/search plus optional AWS PostGIS mirror reconciliation
  and RLS-disabled verification;
- Stratus raw-feed/report object hash, version, expiry and access checks;
- Catalyst Authentication/API Gateway role/rate-limit checks;
- disaster_coordinator/crime-role district/action allow-deny matrix and fresh
  confirmation for warning/dispatch/evacuation approval;
- Signals/Event Function, Job Scheduling and Circuits-or-fallback replay tests;
- datagen scenario coverage and spatial containment;
- connector idempotency, duplicate/unit conversion, retry/DLQ and stale feed;
- live-connector smoke test or recorded-sample contract test plus explicit
  External Access Required evidence;
- invalid/late/conflicting reading handling;
- feature snapshot reproducibility and leakage checks;
- selected MVP model versus baseline and calibration/error metrics;
- low-confidence/stale feed cannot produce an automatic all-clear;
- alert proposal requires human confirmation;
- allocation capacity/capability constraints and human approval;
- no resource can be double-allocated beyond quantity;
- safe-route exclusion around a hazard polygon and explicit no-route result;
- lifecycle transitions and audit history;
- map layers, time scrubber, confidence hatching and freshness states;
- red-zone pulse/ambient alert, rate choropleth, allocation Sankey/table and fused
  coarse/fine layer confidence tests;
- Send to Board and board snapshot/provenance;
- WebSocket reconnect/polling fallback;
- Catalyst Slate/AppSail/Data Store/Stratus deployment and Job Scheduling trigger;
- no real data, no OCR, no auto-dispatch, no direct RDS browser access;
- AWS batch/endpoint resources stop after tests.

L. Delivery sequence
1. Schema + synthetic datagen + lookup APIs.
2. Synthetic feed replay + freshness/quality UI.
3. Threshold breach -> reviewable HazardEvent/AlertHistory flow.
4. One validated flood or landslide forecast path with baseline comparison.
5. Forecast/risk map and Evidence Trail.
6. Resource/shelter inventory and weighted-greedy allocation proposal.
7. Versioned road graph + hazard-avoiding evacuation route.
8. Response plan/tasks and alert lifecycle.
9. Investigation Board integration.
10. Catalyst deployment plus AWS external-workload monitoring, credit/cost limits
    and end-to-end demo exercise.

Create docs/phase-reports/PHASE_17_REPORT.md with Catalyst table/object/row counts
and optional AWS mirror reconciliation,
scenario coverage, connector/source decisions, model baseline comparison,
allocation and routing evidence, screenshots, Catalyst components/credit usage,
AWS external resources/cost/shutdown state,
RLS-disabled verification, safety limitations and post-hackathon requirements.
~~~

Definition of Done:

- Emergency Response is a separate navigable context with all five destinations.
- Synthetic hazard readings/events/resources cover the required Karnataka scenarios.
- At least one approved live-feed connector passes end to end when official access
  is available; otherwise its recorded-sample contract test and exact external
  access/licensing blocker are documented without weakening the synthetic demo.
- One hazard forecast path beats or clearly compares against a transparent baseline
  and renders with confidence, freshness and source/model evidence.
- A threshold/forecast can create a human-reviewed synthetic AlertHistory warning.
- All HazardType values have deterministic baselines/fixtures and the selected MVP
  path has held-out validation.
- The allocator proposes a feasible resource plan and requires human approval.
- A disaster_coordinator can approve and track a resource through planned ->
  dispatched -> enroute -> onsite -> released within the assigned demo district.
- Evacuation routing avoids the fixture hazard polygon or reports no safe route.
- Hazard/resource/route objects can be sent to the Investigation Board.
- Stale/low-confidence inputs never silently create an all-clear or auto-dispatch.
- The feature is deployed through Catalyst Authentication/API Gateway/Slate/
  AppSail/Data Store/Stratus/Signals/Job Scheduling and matching enabled services.
- AWS RDS is retained for the full analytics/geospatial corpus and AWS compute/S3
  is used only for justified model/routing work; AWS RLS stays disabled and there
  is no Supabase, OCR or direct browser-database dependency.

---

# Prompt 18 - Final hackathon testing, CI/CD, recovery, and demo release

> **SUPERSEDED (2026-07-20).** This old Prompt 18 is replaced by the Prompt 18-26
> sequence in `prompt3.md`. The final live release phase is now `prompt3.md`
> Prompt 25 and the independent audit is Prompt 26; the NEW `PHASE_18_REPORT.md`
> is the truth-reconciliation/baseline-repair report, not this final-release step.
> Retained below as historical evidence — do not run this first.

Objective: perform the final verification of the complete synthetic hackathon build
after Investigation Board and Disaster Response are complete, then release the demo.

~~~text
Implement Phase 18: final hackathon verification, CI/CD, backup/recovery and demo
release. Run only after Prompts 16-17 are Complete and include the Investigation
Board and Disaster Response in the same final suite/report.

Test separation:
- unit;
- API;
- disposable repository/adapter integration plus Catalyst development smoke tests;
- frontend component;
- browser end-to-end;
- datagen golden scenarios;
- model reproducibility/evaluation;
- hackathon configuration and RLS-disabled checks;
- load/performance;
- infrastructure;
- backup/recovery.

Required end-to-end journeys:
1. Open Catalyst frontend URL -> Catalyst Authentication -> API Gateway ->
   Function/AppSail health/API succeeds.
2. Select demo profile -> create FIR draft -> validate -> approve -> open case.
3. Add/review a canonical person/party.
4. Upload an already-digital file to Stratus -> enter/edit Data Store metadata ->
   link to case.
5. Add typed statement/property/digital/financial/court data.
6. Entity-resolution candidate -> review -> graph update.
7. Data Store FeatureSnapshot -> AppSail/Function/Job Scheduling -> AWS
   Batch/SageMaker ->
   Data Store result -> review.
8. Correct validated structured input -> old result stale/superseded -> rerun.
9. Generate a watermarked synthetic report and audit event.
10. Restore from backup and roll back a model version.
11. Run the complete demo without OCR, transcription or extraction services.
12. Create/share/edit/lock/branch/export an Investigation Board; replay a missed
    activity and verify evidence versus hypothesis provenance.
13. Replay a synthetic hazard feed -> generate a forecast -> human-review an
    alert -> propose/approve an allocation -> produce a hazard-avoiding route.
14. Exercise notification preferences/escalation, SmartBrowz report delivery and
    the QuickML RAG citation/refusal path when the optional assistant is enabled.

Hackathon safeguards:
- secret/container/IaC/dependency/SAST scans;
- verify RLS and FORCE RLS are disabled on every remaining AWS PostgreSQL table;
- verify anon/authenticated have no direct table DML path used by the browser;
- verify React contains no database/service credentials or direct RDS query;
- verify the FastAPI synthetic-database startup guard;
- verify React is served by Catalyst Slate/Web Client Hosting;
- verify the public API is protected/routed by Catalyst API Gateway and FastAPI is
  served by Catalyst AppSail through the Function facade;
- verify direct AppSail CRUD routes cannot bypass Gateway auth/throttling and any
  direct WebSocket/SSE connection requires a short-lived scoped token and Origin;
- verify Catalyst Authentication session/role mapping and server-side role checks;
- run an allow/deny API authorization matrix for every demo role/resource/action,
  including board sharing/export and disaster allocation/dispatch;
- verify no AWS service hosts the public frontend/primary API;
- exact Catalyst-origin CORS and rate-limit behavior;
- Catalyst Data Store CRUD/full-text/search/lineage tests;
- private Stratus signed-URL/object hash/version/lifecycle tests;
- evidence quarantine, safe fixture malware-scan pass/reject and no-extraction tests;
- NoSQL schema/responsibility and Cache TTL/eviction tests;
- Signals/Event Functions, Job Scheduling and available Circuits retry tests;
- no PII/secrets/file contents in logs;
- audit verification;
- public demo data-reset procedure.

Data:
- all Prompt 1 validation gates adjusted for structured digital/manual-metadata input;
- curated Data Store serving-subset row counts and AWS source reconciliation;
- zero canonical spatial failures;
- stable identity;
- category lifecycle consistency;
- evidence hash/version/activity completeness;
- source/version lineage;
- explicit proof that all records/files are synthetic.

Models:
- approved aggregate/investigation-support tasks only;
- no synthetic individual risk presented as operational;
- reproducible FeatureSnapshots;
- baseline comparison;
- quality/latency/cost monitoring;
- safe fallback when AWS/SageMaker is unavailable;
- rollback tested;
- no model reads raw uploaded file bytes.

CI/CD:
- Catalyst Pipelines build/lint/test/scan/Data Store-import/deploy stages;
- disposable test -> Catalyst development -> Catalyst demo/production environment;
- Slate/Web Client and AppSail deployment/version rollback;
- backup/export before Data Store or Stratus change and documented rollback;
- AppSail API image and AWS worker ECR digest pinning;
- Catalyst URL/domain post-deploy smoke tests;
- automatic block on failure;
- verification that hackathon mode cannot point at a non-synthetic database;
- verification that the user was required only for Catalyst browser login/consent.

Operations:
- Catalyst Authentication/API Gateway/Functions/AppSail/Data Store/Stratus/
  Signals/Pipeline/Job Scheduling health plus AWS model health runbook;
- Catalyst credit/usage checks and AWS GPU/endpoint shutdown alarms;
- backup retention and restore drill;
- queue/DLQ replay where used;
- endpoint/model rollback;
- evidence object/version recovery test;
- retention/legal-hold protection and source-reconciliation recovery tests;
- one-command or documented post-event shutdown/reset.

Run the full suite and produce:
- docs/phase-reports/PHASE_18_REPORT.md;
- HACKATHON_DEMO_CHECKLIST.md;
- HACKATHON_DEMO_RUNBOOK.md;
- DISASTER_RECOVERY_RUNBOOK.md;
- MODEL_RELEASE_CHECKLIST.md;
- final architecture/deployment diagram;
- Catalyst CLI login/deploy/rollback runbook;
- Catalyst component and AWS external-service inventory;
- organizer capability-to-required-Catalyst-service evidence matrix;
- POST_HACKATHON_BACKLOG.md containing an explicit production-security and future
  implementation list.

POST_HACKATHON_BACKLOG.md must classify every item as Deferred, Platform
Unavailable, External Access Required or Optional Future, with owner/dependency/
acceptance criteria. It must include at minimum:
- production PostgreSQL RLS/policies, full authorization/privacy review, secret
  rotation, penetration testing and incident-response exercise;
- OCR, transcription, translation, document extraction and Zia media/voice pilots;
- Zia AutoML and Circuits re-evaluation if India-DC availability changes;
- multilingual Kannada/English UI with reviewed translation;
- offline-first encrypted field capture and an authorized mobile evidence client;
- approved RMS/CCTNS/court/lab and live disaster-agency connectors with contracts,
  licensing, reconciliation and outage fallbacks;
- enforceable retention/deletion/privacy-request/legal-hold workflows for real data;
- differential redaction/access views for victims, witnesses, juveniles and
  sensitive cases;
- governed RAG knowledge expiry/evaluation and model-drift/independent review;
- full named/restorable Investigation Board snapshot versions;
- multi-tenancy only after a real requirement and formal isolation design.

Declare only "hackathon-demo ready." Never declare production-ready while AWS
RLS, complete production authorization policy and production privacy controls are
deferred.
If anything fails, leave the phase Pending and provide the exact remediation.
~~~

Definition of Done:

- All critical hackathon user journeys and failure paths pass.
- RLS-disabled/API-only/synthetic-data guards are verified.
- Recovery, model rollback and data lineage are exercised.
- CI/CD blocks a demo release on failed checks.
- Frontend and primary API are proven to be hosted by Zoho Catalyst.
- Catalyst Authentication, API Gateway, Data Store, Stratus, NoSQL/Cache bounded
  uses and event/job services pass their relevant tests.
- Catalyst CLI automation requires only the user's Zoho browser login/consent.
- AWS RDS is retained for the full historical/analytics corpus and AWS compute is
  used only for justified custom model/geospatial/advanced-analytics work.
- The submitted application uses Catalyst Data Store/Stratus as its curated
  operational serving layer and has no ambiguous bidirectional source of truth.
- OCR/transcription/extraction are not runtime dependencies.
- Production limitations and future work are explicit.
- Every deferred/unavailable/external-access/future item is present in
  POST_HACKATHON_BACKLOG.md with no silent omission.
- Investigation Board and Disaster Response journeys from Prompts 16-17 are included in the Phase 18 suite/report.

---
## Prompt 14-18 completeness audit

Requirements coverage was re-audited against the organizer's 26 Catalyst
capabilities, DRISHTI_REMAINING_FEATURES_AND_AWS_ROADMAP.md,
C:\Users\Prajwal\Desktop\06_INVESTIGATION_BOARD.md and
C:\Users\Prajwal\Desktop\07_DISASTER_RESPONSE.md.

Covered in Prompts 14-18:
- all 26 organizer capability rows have an explicit Used, Not used, Unavailable or
  conditional disposition and required report evidence;
- autonomous Catalyst CLI login/project binding, deployment, CI/CD, rollback,
  credit controls and the Catalyst/AWS integration boundary;
- curated Data Store/Stratus serving-layer bootstrap, one-way analytics sync,
  reconciliation/rebuild and new-input-to-prediction flow;
- the complete 18-item application/data/model/event/operations pipeline inventory;
- Catalyst-authenticated administration, source reconciliation, retention/legal
  hold demo controls, notification preferences/escalation, reports and QuickML RAG;
- full hackathon security, authorization, recovery, cost, model and browser tests;
- Investigation Board object/provenance contract, roles, canvas helpers,
  collaboration, promotion, locking/branching, reverse references and exports;
- Disaster Response roles, multi-hazard data/baselines, feed connectors,
  forecasting/fusion, maps, alerts, allocation, routing, plans and board integration.

Intentional exceptions—not silent omissions:
- PostgreSQL RLS/FORCE RLS policies are intentionally deferred/disabled for the
  hackathon; Catalyst Authentication and server-side action authorization remain
  required;
- OCR, transcription, automatic document/media extraction, image recognition,
  barcode/ID scanning, voice and automatic translation are deferred;
- current official documentation lists Zia AutoML and Circuits as unavailable in
  the India DC; execution must recheck and record evidence/fallbacks;
- a custom domain is conditional on the user supplying/controlling a domain;
- live government/agency feeds are conditional on official access/licensing;
  connector contracts and recorded synthetic replay are still required;
- multilingual, offline/mobile, production external-system connectors, real-data
  privacy/deletion/redaction, full board snapshot versions and multi-tenancy are
  explicitly recorded in POST_HACKATHON_BACKLOG.md rather than silently omitted.

This audit confirms requirements coverage in the prompt library, not completed
implementation. Prompts 14-18 remain Pending until their code, deployment, tests,
phase reports and Definitions of Done are actually verified.

---

## Rules for moving between prompts

Before starting Prompt N+1, verify:

- Prompt N is marked Complete in the status table.
- docs/phase-reports/PHASE_N_REPORT.md exists, except Prompt 6 because it is
  intentionally Deferred.
- Catalyst Data Store/NoSQL/Stratus schema/import changes are applied to the
  correct development environment; any justified AWS analytics migration is
  applied only to the correct AWS RDS development/staging environment.
- no tests are failing.
- no new secret is committed.
- RLS and FORCE RLS remain disabled on every remaining AWS PostgreSQL table.
- the frontend has no direct RDS/database query path.
- no legacy Supabase client or credential is required by pending-phase runtime code.
- HACKATHON_MODE can run only against the explicitly marked synthetic database.
- no uploaded file content or unvalidated manual metadata is reaching features.
- no individual synthetic risk output is being presented as operational.
- from Prompt 14 onward, the public frontend is Catalyst Slate/Web Client Hosting
  and the primary public API is Catalyst AppSail;
- from Prompt 14 onward, Catalyst Authentication/API Gateway protect the public
  application, Data Store is the curated operational relational serving layer,
  Stratus is the application object store, and NoSQL/Cache are used only for their
  documented bounded responsibilities;
- AWS RDS is retained for the full historical/analytics corpus, but no deployed
  operational CRUD endpoint depends on direct RDS access;
- every third-party implementation of an organizer-listed capability is removed
  or has a verified Catalyst availability/custom-runtime gap documented in the
  current phase compliance matrix;
- no Amplify/CloudFront/ECS/ALB/EC2/Lambda URL hosts the public DRISHTI app;
- Catalyst CLI configuration/deployment is reproducible and requires the user
  only for Zoho browser login/consent;
- Catalyst credits/usage and AWS external costs are checked and temporary model
  compute is shut down.

Prompt 6 is the only sequencing exception: after Prompt 5 is Complete, leave
Prompt 6 as Deferred and continue directly to Prompt 7.

Prompt 18 (in THIS file) was originally the final release phase. **Superseded
(2026-07-20):** `prompt3.md` redefines Prompt 18 as truth reconciliation + scope
freeze + baseline repair, and moves the final live release to `prompt3.md` Prompt
25 (with an independent audit in Prompt 26). The new `PHASE_18_REPORT.md` documents
that reconciliation; the Investigation Board and Disaster Response live journeys are
verified in `prompt3.md` Prompts 23-25.

If a phase is partially complete, rerun the same prompt with:

~~~text
Continue the current DRISHTI phase from its existing implementation and phase
report. Do not restart or replace completed work. Re-audit the Definition of
Done, implement only the missing/failed items, rerun the affected tests, update
the same phase report, and mark Complete only when every gate passes.
~~~

## Recommended first command/session

> **STATUS UPDATE (2026-07-20, reconciled in Prompt 18).** Prompts 1-17 in this
> file are **implemented locally** and regression-tested. The authoritative
> continuation is now **`prompt3.md`** — paste its Global Execution Contract and
> its **Prompt 18** first, then proceed through Prompts 18-26 in order. The **old
> Prompt 18 below is superseded** by `prompt3.md`'s Prompt 18-26; do not run it
> first. This file is retained as historical evidence.
>
> Cloud-acceptance caveat: Prompts 14, 16 and 17 are locally implemented, but
> their **live Catalyst/AWS acceptance is continued in `prompt3.md`** (Prompts
> 21-25), not proven here. Do not read "implemented locally" as "deployed".

Start at:

~~~powershell
Set-Location "C:\Users\Prajwal\Desktop\DRISHTI"
kiro-cli chat
~~~

Then paste (current continuation):

1. The Global Execution Contract from `prompt3.md`
2. `prompt3.md` Prompt 18 (truth reconciliation, scope freeze, baseline repair)

Historical note: Prompts 1-8 were recorded Complete (Prompt 6 intentionally
Deferred); Prompts 9-17 were then implemented locally and proceed in numerical
order. The line "Prompt 18 is the final release gate" refers to the OLD Prompt 18
in this file and is superseded — the final live release phase is now
`prompt3.md` Prompt 25, with an independent audit in Prompt 26.


---

## Addendum — Prompt 26 final status correction (2026-07-24)

> Appended by the independent Prompt 26 audit. This older spec (`prompt2.md`) is
> **superseded** by `prompt3new.md` Prompts 18–26 for all post-Prompt-17 work. The
> authoritative, evidence-backed final status lives in:
> `docs/phase-reports/PHASE_26_REPORT.md`, `FINAL_IMPLEMENTATION_AUDIT.md`,
> `SUBMISSION_EVIDENCE_INDEX.md`, and `artifacts/phase-26/FINAL_AUDIT_MANIFEST.json`.

**Audited state (do not read older status lines above as current):**

- Prompts 18–24 (prompt3new): **Complete** with live/offline evidence.
- Prompt 25: **Pending** — all local/security/AWS-model/load/recovery suites green +
  local gate 16/16; blocked only at the live edge by **RB-2** (live `/api/ask` 502).
- Prompt 26: **Audit complete; submission CONDITIONAL** — 44 PASS, 5 PASS(offline),
  1 accepted auth deviation, 2 FAIL across the 52 Definition-of-Done requirements.

**Accepted demo deviation (owner decision):** real Catalyst IAM login is intentionally
replaced by the offline synthetic role-card picker + gateway demo-auth for the submission
(RB-1/RB-4). It is reversible and the real IAM + six-role server-side authorization logic
is proven. This does not weaken any non-auth honesty gate.

**Architecture stands as stated in this file's override note:** Catalyst hosts the public
app + operational serving/object data; AWS is bounded to the justified custom-ML plane +
the synthetic analytics corpus (server-to-server only); the browser never reaches AWS/RDS
or a database directly. Re-verified this pass: route boundary 336/0, AWS SageMaker
endpoints = 0, six-role enum parity across frontend/gateway/backend.

**This remains a synthetic hackathon demonstration on Zoho Catalyst — never production.**
