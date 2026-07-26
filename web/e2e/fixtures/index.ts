/* ============================================================================
   Deterministic response fixtures for the LOCAL Playwright E2E target.

   These mirror the SERVER CONTRACTS (services/ml/app domain schemas, surfaced in
   web/src/api/types.ts). They are the authoritative shapes the UI renders — the
   browser never executes model-authored code, so every fixture is plain,
   inert JSON. Keep them minimal but realistic (field names must match the
   Pydantic/TypeScript contracts exactly).

   Fixtures are intentionally decoupled from src/ (no `@/` imports): the E2E
   layer treats the API surface as an external contract, not an internal type.
   ========================================================================== */

/** Provenance envelope embedded as `result` in every AI/analytics response. */
const aiResult = (answer: string, confidence = 0.82) => ({
  answer,
  confidence,
  source_record_ids: ["CaseMaster:12", "CaseMaster:13"],
  reasoning_summary: "grounded",
  model_version: "drishti-nlsql@1.0.0",
});

/* ------------------------------- global shell ---------------------------- */

/** GET /health — ProfileMenu service dot. */
export const health = {
  status: "ok",
  app: "drishti-ml",
  version: "1.0.0",
  database: true,
  extensions: { vector: true, postgis: true },
  detail: "synthetic",
};

/** GET /intake/status — SyntheticBadge label + submit gate. */
export const intakeStatus = {
  hackathon_mode: true,
  demo_data_only: true,
  synthetic_db: true,
  writes_localhost_only: true,
  submit_enabled: true,
  submit_disabled_reason: null,
  environment_label: "Synthetic Hackathon Demo",
};

/** GET /geo/alerts — NotificationsBell (real geo alerts back the bell). */
export const geoAlerts = {
  result: aiResult("1 active alert in scope."),
  count: 1,
  alerts: [
    {
      alert_id: 5001,
      alert_type: "hotspot_surge",
      severity: "medium",
      title: "Chain-snatching uptick — Jayanagar",
      message: "Rolling 7-day count above the seasonal band.",
      district_id: 1,
      district_name: "Bengaluru City",
      crime_head_id: 12,
      lon: 77.5,
      lat: 12.9,
      status: "open",
      payload: null,
      created_at: "2026-07-20T09:15:00Z",
    },
  ],
};

/* --------------------------------- intake -------------------------------- */

/** GET /intake/drafts — inbox (data state). */
export const intakeDrafts = {
  items: [
    {
      intake_draft_id: 9001,
      draft_key: "SYN-DRAFT-0001",
      status: "draft",
      case_kind: "fir_standard",
      case_category_code: "cognizable",
      crime_no: null,
      case_master_id: null,
      party_count: 2,
      validation_ok: null,
      created_by_actor: "io.ramesh",
      submitted_by_actor: null,
      reviewed_by_actor: null,
      revision_no: 1,
      created_at: "2026-07-19T06:00:00Z",
      updated_at: "2026-07-19T06:30:00Z",
      submitted_at: null,
    },
    {
      intake_draft_id: 9002,
      draft_key: "SYN-DRAFT-0002",
      status: "submitted",
      case_kind: "fir_standard",
      case_category_code: "cognizable",
      crime_no: "CR-2050/2026",
      case_master_id: null,
      party_count: 3,
      validation_ok: true,
      created_by_actor: "io.ramesh",
      submitted_by_actor: "io.ramesh",
      reviewed_by_actor: null,
      revision_no: 2,
      created_at: "2026-07-18T05:00:00Z",
      updated_at: "2026-07-18T07:00:00Z",
      submitted_at: "2026-07-18T07:00:00Z",
    },
  ],
  total: 2,
  page: 1,
  page_size: 50,
};

export const intakeDraftsEmpty = { items: [], total: 0, page: 1, page_size: 50 };

const emptyDraftPayload = {
  source: {
    source_system_code: null,
    source_method: null,
    external_source_id: null,
    originating_unit_id: null,
    receiving_unit_id: null,
  },
  registration: {
    crime_no: null,
    registration_date: null,
    registration_time: null,
    registering_officer_id: null,
    station_id: null,
    district_id: null,
    assigned_io_id: null,
    sensitivity: null,
    classification: null,
  },
  incident: {
    incident_from: null,
    incident_to: null,
    info_received_at: null,
    latitude: null,
    longitude: null,
    address: null,
    landmark: null,
    beat: null,
    occurrence_description: null,
    jurisdiction_override_reason: null,
  },
  classification: {
    major_head_id: null,
    minor_head_id: null,
    gravity_id: null,
    acts_sections: [],
    category_specific: {},
  },
  narrative: {
    brief_facts: null,
    language: "en",
    source_notes: null,
    reviewer_notes: null,
    restricted: false,
  },
};

/** POST /intake/drafts and GET /intake/drafts/{key} — freshly-created draft. */
export const intakeDraft = {
  intake_draft_id: 9003,
  draft_key: "SYN-DRAFT-NEW1",
  status: "draft",
  case_kind: "fir_standard",
  case_category_code: "cognizable",
  source_system_id: null,
  source_record_id: null,
  ingestion_job_id: null,
  case_master_id: null,
  crime_no: null,
  revision_no: 1,
  created_by_actor: "io.ramesh",
  submitted_by_actor: null,
  reviewed_by_actor: null,
  review_note: null,
  return_reason: null,
  payload: emptyDraftPayload,
  parties: [],
  validation: null,
  created_at: "2026-07-21T06:00:00Z",
  updated_at: "2026-07-21T06:00:00Z",
  submitted_at: null,
  reviewed_at: null,
};

/** GET /intake/lookups — minimal reference options for the wizard. */
export const intakeLookups = {
  categories: [{ id: 1, name: "Cognizable" }],
  gravities: [{ id: 1, name: "High" }],
  districts: [{ id: 1, name: "Bengaluru City" }],
  units: [{ id: 1, name: "Cyber Crime PS" }],
  crime_heads: [{ id: 1, name: "Cyber Crime" }],
  crime_subheads: [{ id: 1, name: "Online Fraud", parent_id: 1 }],
  statuses: [{ id: 1, name: "Registered" }],
  officers: [{ id: 1, name: "Demo IO" }],
  courts: [{ id: 1, name: "CMM Court" }],
  acts: [{ act_code: "IPC", short_name: "IPC", description: "Indian Penal Code" }],
  sections: [{ section_code: "420", act_code: "IPC", description: "Cheating" }],
  party_roles: [{ value: "complainant", label: "Complainant" }],
};

/** GET /intake/workflow — kinds/statuses/transitions metadata. */
export const intakeWorkflow = {
  kinds: [
    {
      kind: "fir_standard",
      category: "cognizable",
      label: "FIR (standard)",
      allow_accused: true,
      allow_arrest: true,
      allow_chargesheet: true,
      allow_court: true,
      initial_event: "register",
      initial_status: "registered",
      description: "Standard cognizable FIR.",
      allowed_party_roles: ["complainant", "victim", "accused", "witness"],
    },
  ],
  statuses: [{ code: "registered", label: "Registered", legacy_name: null }],
  party_roles: [
    { value: "complainant", label: "Complainant" },
    { value: "victim", label: "Victim" },
    { value: "accused", label: "Accused" },
  ],
  transitions_by_category: { cognizable: [] },
  event_labels: { register: "Registered" },
};

/* ---------------------------------- cases -------------------------------- */

/** GET /cases/filters — filter rail reference values. */
export const caseFilters = {
  districts: [{ id: 1, name: "Bengaluru City" }],
  stations: [{ id: 1, name: "Cyber Crime PS" }],
  crime_heads: [{ id: 1, name: "Cyber Crime" }],
  sub_heads: [{ id: 1, name: "Online Fraud" }],
  statuses: [{ id: 1, name: "Under Investigation" }],
  gravities: [{ id: 1, name: "High" }],
};

/** GET /cases — filterable index (data state). */
export const caseList = {
  items: [
    {
      case_id: 1001,
      crime_no: "CR-1001/2026",
      case_no: "1001",
      registered_date: "2026-03-04",
      status_id: 1,
      status: "Under Investigation",
      crime_group: "Cyber Crime",
      crime_subhead: "Online Fraud",
      gravity: "high",
      district_id: 1,
      district: "Bengaluru City",
      station_id: 1,
      station: "Cyber Crime PS",
      latitude: null,
      longitude: null,
      brief_facts: "Synthetic cyber-fraud FIR for E2E.",
      victim_count: 1,
      accused_count: 1,
      has_arrest: false,
      has_chargesheet: false,
    },
    {
      case_id: 1002,
      crime_no: "CR-1002/2026",
      case_no: "1002",
      registered_date: "2026-03-06",
      status_id: 1,
      status: "Chargesheeted",
      crime_group: "Property Crime",
      crime_subhead: "House Break-in",
      gravity: "medium",
      district_id: 1,
      district: "Bengaluru City",
      station_id: 2,
      station: "Jayanagar PS",
      latitude: null,
      longitude: null,
      brief_facts: "Synthetic property FIR for E2E.",
      victim_count: 2,
      accused_count: 2,
      has_arrest: true,
      has_chargesheet: true,
    },
  ],
  total: 2,
  page: 1,
  page_size: 25,
};

export const caseListEmpty = { items: [], total: 0, page: 1, page_size: 25 };

/** GET /cases/{id}/detail — full case (overview + people + timeline). */
export const caseDetail = {
  core: {
    case_id: 1001,
    crime_no: "CR-1001/2026",
    registered_date: "2026-03-04",
    incident_from: "2026-03-01",
    incident_to: "2026-03-02",
    brief_facts: "Synthetic cyber-fraud FIR used for the deterministic E2E journey.",
    latitude: null,
    longitude: null,
    station_id: 1,
    io_employee_id: 1,
    major_head_id: 1,
    minor_head_id: 1,
    crime_group: "Cyber Crime",
    crime_subhead: "Online Fraud",
    gravity: "high",
    status: "Under Investigation",
    district_id: 1,
    district: "Bengaluru City",
    station: "Cyber Crime PS",
    io_name: "Demo IO",
  },
  sections: [{ act: "IPC", section: "420", description: "Cheating", act_name: "Indian Penal Code" }],
  section_labels: ["IPC 420", "IT Act 66C", "IPC 468"],
  victims: [{ id: 1, name: "Victim One", age: 34, person_id: "P-1" }],
  accused: [{ id: 2, name: "Accused One", age: 29, person_id: "P-2" }],
  complainants: [{ id: 3, name: "Complainant One", age: 40, person_id: "P-3" }],
  arrests: [],
  chargesheets: [],
  timeline: [{ date: "2026-03-04", type: "registered", label: "FIR registered", detail: null }],
};

/* -------------------------------- evidence ------------------------------- */

/** GET /evidence/status — S3 + hackathon flags (drives the upload affordance). */
export const evidenceStatus = {
  hackathon_mode: true,
  demo_data_only: true,
  synthetic_db: true,
  writes_localhost_only: true,
  s3_configured: false,
  upload_enabled: false,
  max_bytes: 52428800,
  allowed_extensions: ["pdf", "jpg", "csv"],
  allowed_mime_types: ["application/pdf", "image/jpeg", "text/csv"],
  presign_expiry_seconds: 900,
  extraction_disabled_note: "File contents are not automatically extracted.",
  environment_label: "Synthetic Hackathon Demo",
};

/** GET /evidence/lookups — form reference values. */
export const evidenceLookups = {
  evidence_types: [{ value: "image", label: "Image" }],
  categories: [{ value: "scene_photo", label: "Scene photo" }],
  confidentialities: [{ value: "standard", label: "Standard" }],
  languages: [{ value: "en", label: "English" }],
  link_types: [{ value: "primary", label: "Primary" }],
  source_systems: [{ value: "FIR_FORM", label: "FIR form" }],
};

/** GET /evidence/items — case evidence list (data state). */
export const evidenceList = {
  items: [
    {
      evidence_item_id: 7,
      case_master_id: 1001,
      evidence_type: "image",
      category: "scene_photo",
      title: "Scene photo near gate",
      synthetic_reference: "SYN-EV-7",
      source_label: "FIR_FORM",
      state: "available",
      language: "en",
      tags: ["synthetic"],
      version_no: 1,
      sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
      file_name: "photo.jpg",
      mime_type: "image/jpeg",
      size_bytes: 1024,
      captured_at: null,
      created_at: "2026-03-05T10:00:00Z",
      updated_at: null,
    },
  ],
  total: 1,
  page: 1,
  page_size: 200,
  by_state: { available: 1 },
};

export const evidenceListEmpty = { items: [], total: 0, page: 1, page_size: 200, by_state: {} };

/* ---------------------------------- ask ---------------------------------- */

/** GET /chat/sessions — empty (welcome state, no replayable examples). */
export const chatSessionsEmpty = { count: 0, sessions: [] };

/** GET /chat/capabilities — declared planner/voice/viz capabilities. */
export const chatCapabilities = {
  semantic_planner: {
    primary: "catalyst-quickml-llm",
    provider: "catalyst-quickml",
    quickml_llm_configured: true,
    fallback: "deterministic-fallback",
  },
  voice: {
    voice_query_enabled: true,
    provider: "browser-web-speech",
    zia_voice_available: false,
    zia_translation_available: false,
    browser_fallback: true,
    bilingual_text: true,
    low_confidence_threshold: 0.6,
    evidence_extraction_enabled: false,
    platform_limitation: null,
    evidence: null,
  },
  languages: ["en", "kn"],
  visualization_kinds: ["table", "number", "bar", "line", "choropleth", "timeline"],
  scope: { query_voice_enabled: true, evidence_extraction_enabled: false },
};

/** POST /chat/ask — grounded, cited answer with a typed `number` visualization
 *  and its accessible-table fallback (row_ref → rows_preview). */
export const askGrounded = {
  result: aiResult("There are 42 cyber-crime FIRs in Bengaluru City this year."),
  session_id: 1,
  reply: "There are 42 cyber-crime FIRs in Bengaluru City this year.",
  language: "en",
  sql: 'SELECT COUNT(*) AS case_count FROM "CaseMaster" WHERE crime_group = \'Cyber Crime\'',
  cited_record_ids: ["CaseMaster:12", "CaseMaster:13"],
  confidence: 0.82,
  needs_clarification: false,
  blocked: false,
  model_version: "drishti-nlsql@1.0.0",
  row_count: 1,
  columns: ["case_count"],
  rows_preview: [[42]],
  planner_source: "catalyst-quickml-llm",
  planner_primary: "catalyst-quickml-llm",
  planner_degraded: false,
  visualization: {
    kind: "number",
    title: "Total FIRs",
    dimensions: [],
    measures: [{ field: "case_count", label: "FIRs", index: 0, unit: "cases" }],
    time_field: null,
    geo_field: null,
    source_ids: ["CaseMaster(aggregated)"],
    as_of: "2026-07-21T00:00:00Z",
    dataset: "synthetic",
    suppressed: 0,
    confidence: 0.82,
    scope_role: "crime_analyst",
    row_total: 1,
    language: "en",
    accessible_table: { columns: ["case_count"], row_ref: "rows_preview" },
  },
};

/* ---------------------------- investigation board ------------------------ */

const boardSummary = {
  board_id: 1,
  title: "Operation Nightingale",
  description: "Synthetic investigation board for the E2E journey.",
  owner_actor: "demo.investigating_officer",
  case_master_id: null,
  status: "active",
  visibility: "private",
  is_locked: false,
  version: 1,
  parent_board_id: null,
  node_count: 0,
  edge_count: 0,
  my_role: "owner",
  created_at: "2026-07-15T06:00:00Z",
  updated_at: "2026-07-20T06:00:00Z",
};

/** GET /boards — board list (data state). */
export const boardList = { count: 1, items: [boardSummary] };
export const boardListEmpty = { count: 0, items: [] };

/** GET /boards/{id} — full board (empty canvas → "Empty board" overlay). */
export const boardDetail = {
  board: boardSummary,
  nodes: [],
  edges: [],
  annotations: [],
  collaborators: [],
  latest_activity_id: 0,
};

/** GET /boards/meta/object-kinds — palette metadata. */
export const boardObjectKinds = { node_kinds: ["case", "entity"], ref_tables: ["CaseMaster", "EntityGraph"] };

/** GET /boards/{id}/activity — collaboration poll (no new activity). */
export const boardActivity = {
  board_id: 1,
  after_id: 0,
  latest_activity_id: 0,
  count: 0,
  items: [],
};

/** POST|GET /boards/{id}/presence — ephemeral roster. */
export const boardPresence = { board_id: 1, count: 0, actors: [] };

/* ----------------------------- emergency (ER) ---------------------------- */

const feedFresh = {
  feed_code: "open_meteo_live",
  provider: "Open-Meteo",
  connector_kind: "http",
  external_access_required: true,
  freshness_sla_minutes: 60,
  last_observed_at: "2026-07-21T05:00:00Z",
  last_run_at: "2026-07-21T05:05:00Z",
  age_minutes: 240,
  status: "stale",
  licence: "CC BY 4.0",
  attribution: "Open-Meteo",
};

/** GET /disaster/overview — situation KPIs (data state, incl. a stale feed). */
export const disasterOverview = {
  generated_at: "2026-07-21T09:00:00Z",
  active_hazards: 2,
  open_alerts: 1,
  low_confidence_warnings: 1,
  readiness: { available_resources: 6 },
  unavailable_resources: 1,
  open_tasks: 3,
  feed_freshness: [feedFresh],
  stale_feeds: 1,
  hazards: [
    {
      hazard_event_id: 1,
      hazard_code: "flood",
      status: "active",
      severity: "high",
      district_id: 1,
      unit_id: null,
      geojson: {},
      centroid: [77.6, 12.97],
      onset_at: "2026-07-21T02:00:00Z",
      predicted_peak_at: "2026-07-21T12:00:00Z",
      source: "synthetic",
      source_version: "v1",
      description: "Synthetic urban flood scenario.",
      version: 1,
      created_at: "2026-07-21T02:00:00Z",
    },
  ],
};

/** GET /disaster/overview — empty state (nothing seeded). */
export const disasterOverviewEmpty = {
  generated_at: "2026-07-21T09:00:00Z",
  active_hazards: 0,
  open_alerts: 0,
  low_confidence_warnings: 0,
  readiness: { available_resources: 0 },
  unavailable_resources: 0,
  open_tasks: 0,
  feed_freshness: [],
  stale_feeds: 0,
  hazards: [],
};

/** GET /disaster/alerts — review/acknowledge queue. */
export const disasterAlerts = {
  alerts: [
    {
      alert_id: 1,
      alert_type: "hazard",
      severity: "high",
      title: "Flood warning — Bengaluru Urban",
      message: "Rising water levels near the low-lying wards.",
      hazard_event_id: 1,
      district_id: 1,
      status: "proposed",
      confidence: 0.72,
      freshness: "fresh",
      synthetic: true,
      acknowledged_by: null,
      created_at: "2026-07-21T06:00:00Z",
    },
  ],
};

export const disasterHazardTypes = {
  hazard_types: [
    {
      hazard_type_id: 1,
      code: "flood",
      name: "Flood",
      category: "hydromet",
      default_lead_time_hours: 12,
      active: true,
    },
  ],
};

/* ------------------------------ kitchen sink ----------------------------- */

/** Permissive default for any endpoint a journey touches incidentally. It
 *  carries every common envelope key (empty), so pages render honest empty
 *  states instead of throwing. Journeys assert against explicit fixtures. */
export const kitchenSink = {
  result: aiResult("", 0),
  items: [],
  results: [],
  sessions: [],
  nodes: [],
  edges: [],
  alerts: [],
  hazards: [],
  events: [],
  zones: [],
  predictions: [],
  readings: [],
  feeds: [],
  resources: [],
  shelters: [],
  allocations: [],
  routes: [],
  plans: [],
  communities: [],
  suggestions: [],
  stations: [],
  points: [],
  hotspots: [],
  models: [],
  count: 0,
  total: 0,
  page: 1,
  page_size: 50,
  by_state: {},
  by_status: {},
  by_type: {},
  by_reason: {},
  readiness: {},
  feed_freshness: [],
  stale_feeds: 0,
  series: [],
};
