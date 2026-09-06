import type { AiResult } from "@/api/contracts";

/* ============================================================================
   Domain models — 1:1 with the Wave-B Pydantic schemas
   (services/ml/app/<domain>/schemas.py). Field names match the JSON exactly.
   ========================================================================== */

/* --------------------------------- Cases ---------------------------------- */
export interface SimilarCase {
  case_id: number;
  crime_no?: string | null;
  crime_group?: string | null;
  crime_subhead?: string | null;
  gravity?: string | null;
  district?: string | null;
  status?: string | null;
  disposition?: string | null;
  accused_count: number;
  arrest_count: number;
  registered_date?: string | null;
  similarity: number;
  distance: number;
  why_match?: string[];
  source_links?: string[];
}
export interface SimilarResponse {
  result: AiResult;
  query_case_id: number;
  model_name: string;
  model_version_id: number;
  corpus_size: number;
  scope?: string;
  scope_district_id?: number | null;
  limitations?: string;
  results: SimilarCase[];
}

export interface SummaryClaim {
  text: string;
  citations: string[];
}
export interface TimelineEvent {
  date: string;
  label: string;
  citations: string[];
}
export interface SummaryResponse {
  result: AiResult;
  case_id: number;
  crime_no?: string | null;
  summary_id?: number | null;
  summary_text: string;
  sentences: SummaryClaim[];
  timeline: TimelineEvent[];
  claim_count: number;
  cited_claim_count: number;
  fully_cited: boolean;
  confidence: number;
}

export interface Lead {
  recommendation_id?: number | null;
  rank: number;
  kind: string;
  step: string;
  score: number;
  evidence: string[];
  why: string;
}
export interface LeadsResponse {
  result: AiResult;
  case_id: number;
  crime_no?: string | null;
  io_employee_id?: number | null;
  leads: Lead[];
}

/* ---------------------------------- Geo ----------------------------------- */
export interface HotspotFeature {
  hotspot_id: number;
  name?: string | null;
  district_id?: number | null;
  district_name?: string | null;
  crime_head_id?: number | null;
  crime_group?: string | null;
  intensity?: number | null;
  case_count?: number | null;
  centroid_lon?: number | null;
  centroid_lat?: number | null;
  geometry?: Record<string, unknown> | null;
  period_start?: string | null;
  period_end?: string | null;
}
export interface HotspotResponse {
  result: AiResult;
  count: number;
  hotspots: HotspotFeature[];
}

export interface TrendPoint {
  period: string;
  count: number;
  rolling_mean?: number | null;
  rolling_upper?: number | null;
  rolling_lower?: number | null;
  is_anomaly: boolean;
}
export interface TrendDecomposition {
  periods: string[];
  trend: (number | null)[];
  seasonal: (number | null)[];
  residual: (number | null)[];
}
export interface TrendResponse {
  result: AiResult;
  scope: Record<string, unknown>;
  total: number;
  latest_period?: string | null;
  mom_delta?: number | null;
  mom_pct?: number | null;
  yoy_delta?: number | null;
  yoy_pct?: number | null;
  series: TrendPoint[];
  decomposition?: TrendDecomposition | null;
}

/** Severity strings the backend emits on alerts. */
export type AlertSeverity = "info" | "low" | "medium" | "high" | "critical";
export interface AlertFeature {
  alert_id: number;
  alert_type: string;
  severity: AlertSeverity;
  title: string;
  message?: string | null;
  district_id?: number | null;
  district_name?: string | null;
  crime_head_id?: number | null;
  lon?: number | null;
  lat?: number | null;
  status: string;
  payload?: Record<string, unknown> | null;
  created_at?: string | null;
}
export interface AlertResponse {
  result: AiResult;
  count: number;
  alerts: AlertFeature[];
}

/* --------------------------------- Graph ---------------------------------- */
export interface GraphNode {
  entity_id: number;
  entity_type: string;
  label?: string | null;
  ref_table?: string | null;
  distance?: number | null;
  community?: number | null;
  pagerank?: number | null;
  betweenness?: number | null;
  attributes?: Record<string, unknown> | null;
}
export interface GraphEdge {
  edge_id: number;
  source: number;
  target: number;
  relationship_type: string;
  weight: number;
  confidence?: number | null;
}
export interface SubgraphResponse {
  result: AiResult;
  focal_entity?: number | null;
  max_hops?: number | null;
  top_n?: number | null;
  node_count: number;
  edge_count: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}
export interface PathResponse {
  result: AiResult;
  found: boolean;
  method?: string | null;
  hops?: number | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
}
export interface CommunitiesResponse {
  result: AiResult;
  num_communities: number;
  modularity?: number | null;
  known_gangs: number;
  precision: number;
  recall: number;
  f1: number;
  rediscovered_gangs: number;
  candidate_new_groups: number;
}
export interface PersonOfInterest {
  entity_id: number;
  label?: string | null;
  entity_type: string;
  pagerank: number;
  betweenness: number;
  community?: number | null;
}
export interface CentralityResponse {
  result: AiResult;
  computed: boolean;
  persons_of_interest: PersonOfInterest[];
}
export interface HiddenAssociationCard {
  association_id: number;
  entity_a: number;
  entity_b: number;
  label_a?: string | null;
  label_b?: string | null;
  independent_links: number;
  link_kinds: string[];
  proof_record_ids: string[];
  shared_intermediaries: number[];
  shared_case_count: number;
  score: number;
  review_status?: string;
  independent_evidence_kinds?: string[];
}
export interface HiddenFeedResponse {
  result: AiResult;
  total: number;
  page: number;
  page_size: number;
  items: HiddenAssociationCard[];
}
export interface ProofPathResponse {
  result: AiResult;
  entity_a: number;
  entity_b: number;
  link_kinds: string[];
  review_status?: string;
  independent_evidence_kinds?: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/* --- Phase 11: canonical-space isolation, rebuild, reviewer disposition --- */
export interface GraphArchiveTableStatus {
  total: number;
  archived: number;
  live: number;
  legacy_still_live: number;
}
export interface GraphArchiveStatus {
  result: AiResult;
  clean: boolean;
  tables: Record<string, GraphArchiveTableStatus>;
}
export interface GraphRebuildResult {
  result: AiResult;
  canonical_nodes: number;
  canonical_edges: number;
  confirmed_edges: number;
  communities?: number | null;
  modularity?: number | null;
  nodes_scored?: number | null;
  hidden_candidates?: number | null;
  archived: Record<string, number>;
}
export interface GraphReviewResult {
  result: AiResult;
  id: number;
  kind: string;
  review_status: string;
  found: boolean;
}

/* -------------------------------- Analytics ------------------------------- */
export interface CorrelationCell {
  crime_category: string;
  indicator: string;
  r?: number | null;
  p_value?: number | null;
  n: number;
  strength?: string | null;
  direction?: string | null;
  /** Least-squares line through this cell's district points. Carried per CELL,
   *  so a grid showing one chart per indicator draws every fit from one call.
   *  Null whenever `r` is null (suppressed / too few districts to fit). */
  fit_slope?: number | null;
  fit_intercept?: number | null;
}
export interface ScatterPoint {
  district_id: number;
  district_name: string;
  x: number;
  y: number;
  crime_count: number;
  population: number;
}
export interface ScatterSeries {
  crime_category: string;
  indicator: string;
  r?: number | null;
  fit_slope?: number | null;
  fit_intercept?: number | null;
  points: ScatterPoint[];
}
export interface NarrativeCard {
  headline: string;
  detail: string;
  disclaimer: string;
  indicator?: string | null;
  crime_category?: string | null;
  r?: number | null;
  threshold_value?: number | null;
  pct_difference?: number | null;
}
/** One district's averaged indicators + its per-100k crime rates: the raw panel
 *  the Pearson matrix is computed from.
 *
 *  Aggregate-only — a row is a district, never a person. A cell suppressed for
 *  k-anonymity is ABSENT from `rates`/`counts`, never reported as a zero, so a
 *  consumer must treat "missing" as "withheld" rather than "none". */
export interface DistrictPanelRow {
  district_id: number;
  district_name: string;
  population: number;
  /** indicator key -> mean over the period */
  indicators: Record<string, number>;
  /** crime category -> rate per 100k */
  rates: Record<string, number>;
  /** crime category -> raw case count */
  counts: Record<string, number>;
}
export interface SocioEconomicResponse {
  result: AiResult;
  period_start?: string | null;
  period_end?: string | null;
  indicators: string[];
  crime_categories: string[];
  districts_analysed: number;
  k_threshold: number;
  suppressed_cells: number;
  focus_indicator: string;
  correlation_matrix: CorrelationCell[];
  /** Scatter for the FOCUS indicator only. Views that render several indicators
   *  at once should build their series from `districts` instead. */
  scatter: ScatterSeries[];
  narrative: NarrativeCard;
  districts: DistrictPanelRow[];
}

/** Crime-pattern detections (doc 01 §4.6). pattern_type ∈ pattern_type_enum. */
export type PatternType =
  | "serial"
  | "spree"
  | "modus_operandi"
  | "temporal"
  | "spatial"
  | "network"
  | "repeat_offender";
export interface PatternLinkedCase {
  case_id: number;
  relevance?: number | null;
  crime_no?: string | null;
  registered_date?: string | null;
  crime_group?: string | null;
  status?: string | null;
  district?: string | null;
}
export interface CrimePatternCard {
  pattern_id: number;
  pattern_type: PatternType | string;
  name: string;
  description?: string | null;
  crime_head_id?: number | null;
  crime_group?: string | null;
  model_version_id?: number | null;
  model_version?: string | null;
  confidence?: number | null;
  attributes: Record<string, unknown>;
  detected_at?: string | null;
  is_active: boolean;
  linked_case_count: number;
  cases: PatternLinkedCase[];
}
export interface CrimePatternsResponse {
  result: AiResult;
  total: number;
  pattern_types: string[];
  by_type: Record<string, number>;
  items: CrimePatternCard[];
}

/* ------------------- Ask DRISHTI: chat history (15h) ---------------------- */
/** Speech-to-text metadata for a voice query (VoiceTranscript). */
export interface VoiceInfo {
  transcript_text?: string | null;
  language?: string | null;
  confidence?: number | null;
  is_low_confidence: boolean;
  raw_audio_ref?: string | null;
}
/** One stored chat turn. Assistant turns carry the grounded answer anatomy. */
export interface ChatMessageOut {
  message_id: number;
  sender: "user" | "assistant" | string;
  content?: string | null;
  language?: string | null; // en | kn
  generated_sql?: string | null;
  cited_record_ids: (number | string)[];
  confidence?: number | null;
  model_version?: string | null;
  created_at?: string | null;
  voice?: VoiceInfo | null;
}
export interface ChatSessionSummary {
  session_id: number;
  title?: string | null;
  role?: string | null;
  language?: string | null;
  user_display_name?: string | null;
  created_at?: string | null;
  last_activity?: string | null;
  message_count: number;
  user_message_count: number;
  assistant_message_count: number;
  first_question?: string | null;
  has_voice: boolean;
}
export interface ChatSessionsResponse {
  count: number;
  sessions: ChatSessionSummary[];
}
export interface ChatSessionDetail {
  session_id: number;
  title?: string | null;
  role?: string | null;
  language?: string | null;
  user_display_name?: string | null;
  created_at?: string | null;
  messages: ChatMessageOut[];
}

/* --- Prompt 19: typed, server-validated visualization spec for an answer ---
   The server decides the chart kind and hands back column indices into the same
   `columns` / `rows_preview` the answer already carries. The client renders it
   deterministically (never evaluates model-authored code) and always keeps the
   accessible table fallback (accessible_table.row_ref === "rows_preview"). */
export type VizKind =
  | "table"
  | "number"
  | "bar"
  | "line"
  | "choropleth"
  | "heatmap"
  | "timeline"
  | "network"
  | "sankey"
  | "link";
export interface VizDimension {
  field: string;
  label: string;
  /** column index into `columns` / `rows_preview`. */
  index: number;
  role: string;
}
export interface VizMeasure {
  field: string;
  label: string;
  /** column index into `columns` / `rows_preview`. */
  index: number;
  unit: string;
}
export interface VizAccessibleTable {
  columns: string[];
  /** "rows_preview" => render from the message's own columns + rows_preview. */
  row_ref: string;
}
export interface VizSpec {
  kind: VizKind;
  title: string;
  dimensions: VizDimension[];
  measures: VizMeasure[];
  time_field: string | null;
  geo_field: string | null;
  source_ids: string[];
  /** ISO timestamp the data is "as of". */
  as_of: string;
  dataset: string; // "synthetic"
  suppressed: number;
  confidence: number; // 0..1
  scope_role: string;
  row_total: number;
  language: string; // "en" | "kn"
  accessible_table: VizAccessibleTable;
}

/** Live NL->SQL answer (Phase 2). Scoped server-side by role. */
export interface AskResponse {
  result: AiResult;
  session_id: number;
  reply: string;
  language: string;
  sql?: string | null;
  cited_record_ids: string[];
  confidence: number;
  needs_clarification: boolean;
  blocked: boolean;
  model_version?: string | null;
  row_count: number;
  columns: string[];
  rows_preview: unknown[][];
  /* Prompt 19: which planner produced the answer + degraded-fallback flag, and
     the typed visualization spec (null for a text-only answer). */
  planner_source: string; // e.g. "catalyst-quickml-llm" | "openai-compatible" | "deterministic-fallback" | "deterministic-briefing"
  planner_primary: string; // configured primary planner for the live contract
  planner_degraded: boolean; // true when it fell back from the primary due to an outage
  visualization: VizSpec | null;
}

/** Prompt 19: server-declared chat capabilities (GET /chat/capabilities). */
export interface CapabilitiesSemanticPlanner {
  primary: string;
  provider: string;
  quickml_llm_configured: boolean;
  fallback: string;
}
export interface CapabilitiesVoice {
  voice_query_enabled: boolean;
  /** Browser speech in the current deployment; never presented as Bedrock audio. */
  provider: string;
  /** Current turn transport, e.g. "browser-continuous-turns". Absent on older APIs. */
  mode?: string;
  /** Older deployments advertise the equivalent through `browser_fallback`. */
  continuous_mode_available?: boolean;
  unscored_auto_send_available?: boolean;
  /** True when the server-side Nova audio relay is enabled. */
  server_audio_streaming?: boolean;
  sonic_available?: boolean;
  sonic_model?: string;
  sonic_languages?: string[];
  sonic_voices?: Record<string, string>;
  zia_voice_available: boolean;
  zia_translation_available: boolean;
  browser_fallback: boolean;
  bilingual_text: boolean;
  low_confidence_threshold: number;
  evidence_extraction_enabled: boolean;
  platform_limitation: string | null;
  evidence: string | null;
}
export interface CapabilitiesScope {
  query_voice_enabled: boolean;
  evidence_extraction_enabled: boolean;
}
export interface Capabilities {
  semantic_planner: CapabilitiesSemanticPlanner;
  voice: CapabilitiesVoice;
  languages: string[];
  visualization_kinds: string[];
  scope: CapabilitiesScope;
}

/* ---------------------------------- Risk ---------------------------------- */
export interface RiskFactor {
  feature: string;
  label: string;
  value: number;
  contribution: number;
  direction: string;
}
export interface RiskResponse {
  result: AiResult;
  entity_id: number;
  accused_master_id?: number | null;
  offender_name?: string | null;
  district_id?: number | null;
  risk_band: string;
  risk_level: string;
  risk_score: number;
  class_probabilities: Record<string, number>;
  factors: RiskFactor[];
  model_version: string;
  scored_at?: string | null;
  rescored: boolean;
}
export interface CalibrationResponse {
  result: AiResult;
  n_train: number;
  n_test: number;
  foundation: Record<string, unknown>;
  baseline: Record<string, unknown>;
  agreement: number;
}

/* ---------------------------------- Money --------------------------------- */
export interface TraceNode {
  account_id: number;
  label?: string | null;
  account_type?: string | null;
  bank?: string | null;
  is_flagged: boolean;
  owner_entity_id?: number | null;
  hop: number;
}
export interface TraceEdge {
  source_account: number;
  target_account: number;
  amount: number;
  txn_count: number;
  is_flagged: boolean;
  flag_reasons: string[];
  transaction_ids: number[];
  hop: number;
}
export interface TraceResponse {
  result: AiResult;
  start_account: number;
  max_hops: number;
  node_count: number;
  edge_count: number;
  total_traced_amount: number;
  cycle_guarded: boolean;
  nodes: TraceNode[];
  edges: TraceEdge[];
}
export interface UnifiedNode {
  id: string;
  kind: "account" | "entity" | string;
  label?: string | null;
  account_id?: number | null;
  entity_id?: number | null;
  account_type?: string | null;
  bank?: string | null;
  is_flagged?: boolean | null;
  entity_type?: string | null;
  attributes?: Record<string, unknown> | null;
}
export interface UnifiedEdge {
  id: string;
  source: string;
  target: string;
  kind: "transaction" | "owns" | string;
  amount?: number | null;
  txn_count?: number | null;
  is_flagged?: boolean | null;
  flag_reason?: string | null;
}
export interface UnifiedResponse {
  result: AiResult;
  seed_kind: "entity" | "account" | string;
  seed_id: number;
  node_count: number;
  edge_count: number;
  nodes: UnifiedNode[];
  edges: UnifiedEdge[];
}
export interface FlaggedTxn {
  transaction_id: number;
  source_account: number;
  destination_account: number;
  amount: number;
  txn_timestamp?: string | null;
  channel?: string | null;
  flag_reason?: string | null;
  evidence_case_id?: number | null;
}
export interface FlaggedFeedResponse {
  result: AiResult;
  total: number;
  page: number;
  page_size: number;
  by_reason: Record<string, number>;
  items: FlaggedTxn[];
}
export interface PatternMetric {
  detected: number;
  ground_truth: number;
  true_positive: number;
  precision: number;
  recall: number;
  f1: number;
}
export interface DetectionResponse {
  result: AiResult;
  transactions_scanned: number;
  transactions_flagged: number;
  by_pattern: Record<string, number>;
  alerts_written: number;
  structuring_hubs: number;
  layering_chains: number;
  circular_flows: number;
  validation: Record<string, PatternMetric>;
  model_version_id: number;
}

/* -------------------------------- Forecast -------------------------------- */
export interface LayerRun {
  layer: string;
  model?: string | null;
  model_version_id?: number | null;
  written: number;
}
export interface FusedDistrict {
  district_id: number;
  district?: string | null;
  fused_count: number;
  confidence: number;
  risk_class?: string | null;
  contributing_models: string[];
  near_term_spike: boolean;
}
export interface GovernedPersistence {
  model_version_id?: number | null;
  feature_schema_version_id?: number | null;
  snapshots_new: number;
  snapshots_reused: number;
  requests_new: number;
  results_new: number;
  superseded_prior: number;
  skipped: number;
  backtest_referenced: boolean;
  error?: string | null;
}
export interface ForecastRunResponse {
  result: AiResult;
  head_id?: number | null;
  horizon_days: number;
  prediction_start?: string | null;
  prediction_end?: string | null;
  layers: LayerRun[];
  alerts_written: number;
  fused: FusedDistrict[];
  governed?: GovernedPersistence | null;
}
export interface LayerInfo {
  layer: string;
  model_name: string;
  model_version_id: number;
  predictions: number;
  horizon_days?: number | null;
}
export interface LayersResponse {
  result: AiResult;
  layers: LayerInfo[];
}
export interface LayerPrediction {
  layer: string;
  model_name?: string | null;
  predicted_count?: number | null;
  probability?: number | null;
  confidence?: number | null;
  prediction_start?: string | null;
  prediction_end?: string | null;
  features: Record<string, unknown>;
}
export interface DistrictForecastResponse {
  result: AiResult;
  district_id: number;
  district?: string | null;
  head_id?: number | null;
  layers: LayerPrediction[];
}
export interface MapCell {
  prediction_id: number;
  district_id?: number | null;
  lat?: number | null;
  lon?: number | null;
  predicted_count?: number | null;
  confidence?: number | null;
  risk_class?: string | null;
}
export interface ForecastMapResponse {
  result: AiResult;
  layer: string;
  head_id?: number | null;
  count: number;
  cells: MapCell[];
}
export interface NearRepeatCell {
  lat: number;
  lon: number;
  intensity: number;
  confidence: number;
  contributing_events: number;
}
export interface NearRepeatTriggerResponse {
  result: AiResult;
  event: Record<string, unknown>;
  district_id?: number | null;
  head_id?: number | null;
  recent_events: number;
  affected_cells: NearRepeatCell[];
}
export interface ValidationResponse {
  result: AiResult;
  cutoff: string;
  horizon_months: number;
  area_fraction: number;
  overall?: Record<string, unknown> | null;
  per_crime_head: Record<string, unknown>;
}

/* --- Phase 12: rolling-origin backtest + data freshness + governed persistence --- */
export interface ForecastMetric {
  name?: string | null;
  family?: string | null;
  mae?: number | null;
  rmse?: number | null;
  wape?: number | null;
  smape?: number | null;
  coverage_80?: number | null;
  coverage_50?: number | null;
  n?: number | null;
}
export interface BacktestResponse {
  result: AiResult;
  scope: Record<string, unknown>;
  n_series: number;
  origins: string[];
  scored_points: number;
  cells_considered: number;
  abstained_cells: number;
  abstention_rate: number;
  model: ForecastMetric;
  baselines: Record<string, ForecastMetric>;
  skill_vs_baselines: Record<string, Record<string, number>>;
  beats_all_baselines?: boolean | null;
  error_by_district: Record<string, unknown>[];
  error_by_season: Record<string, ForecastMetric | null>;
  error_by_head: Record<string, Record<string, unknown>>;
  geo_holdout: Record<string, unknown>;
  persisted_backtest_id?: number | null;
}
export interface FreshnessResponse {
  result: AiResult;
  as_of: Record<string, string | null>;
  case_data_stale_days?: number | null;
  approved_sources: Record<string, unknown>[];
  valid_geography: Record<string, unknown>;
}

/* -------------------------------- Explain --------------------------------- */
export interface FactorBar {
  feature: string;
  label: string;
  value?: number | null;
  contribution: number;
  direction: string;
}
export interface GaugeBars {
  score: number;
  level: string;
  band?: string | null;
  class_probabilities: Record<string, number>;
  factors: FactorBar[];
}
export interface ModelInfo {
  model_version_id: number;
  model_name: string;
  version: string;
  model_type?: string | null;
  framework?: string | null;
  status?: string | null;
  hyperparameters: Record<string, unknown>;
  metrics: Record<string, unknown>;
  trained_at?: string | null;
  deployed_at?: string | null;
}
export interface InferenceAudit {
  inference_id: number;
  matched_by: string;
  input_snapshot: Record<string, unknown>;
  output: Record<string, unknown>;
  confidence?: number | null;
  latency_ms?: number | null;
  inferred_at?: string | null;
}
export interface ExplainResponse {
  result: AiResult;
  table: string;
  record_id: string;
  subject: Record<string, unknown>;
  model?: ModelInfo | null;
  inference?: InferenceAudit | null;
  gauge_bars?: GaugeBars | null;
  source_record_ids: string[];
  reproducible: boolean;
  reproducibility_note: string;
}
export interface ModelCard {
  model_version_id: number;
  model_name: string;
  version: string;
  model_type?: string | null;
  framework?: string | null;
  status?: string | null;
  calibration: Record<string, unknown>;
  inferences: number;
  mean_confidence?: number | null;
  first_inference?: string | null;
  last_inference?: string | null;
}
export interface ModelsResponse {
  result: AiResult;
  count: number;
  models: ModelCard[];
}
export interface DriftPoint {
  period: string;
  count: number;
  mean_confidence?: number | null;
}
export interface ModelDetailResponse {
  result: AiResult;
  model: ModelCard;
  calibration: Record<string, unknown>;
  drift: DriftPoint[];
  drift_flag: string;
  notes: string;
}
export interface ContractRoute {
  path: string;
  methods: string;
  response_model?: string | null;
  conforms: boolean;
  via: string;
}
export interface ContractAuditResponse {
  result: AiResult;
  total: number;
  conforming: number;
  non_conforming: number;
  routes: ContractRoute[];
}

/* ------------------------- Shell UI reference types ----------------------- */
/** Object kinds the shell can peek at without navigating. */
export type EntityKind =
  | "person"
  | "case"
  | "vehicle"
  | "phone"
  | "account"
  | "location"
  | "organisation"
  | "association"
  | "model"
  | "alert";

/** A lightweight reference the peek rail can resolve to a real record. */
export interface ObjectRef {
  kind: EntityKind;
  id: number | string;
  label: string;
  sublabel?: string;
}

/* ------------------------- Cases: Explorer + Case file (15c) -------------- */
export interface CaseListItem {
  case_id: number;
  crime_no?: string | null;
  internal_crime_no?: string | null;
  case_no?: string | null;
  registered_date?: string | null;
  status_id?: number | null;
  status?: string | null;
  crime_group?: string | null;
  crime_subhead?: string | null;
  gravity?: string | null;
  district_id?: number | null;
  district?: string | null;
  station_id?: number | null;
  station?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  brief_facts?: string | null;
  record_origin: string;
  is_synthetic: boolean;
  reference_mapping_kind?: string | null;
  location_label?: string | null;
  location_precision?: string | null;
  not_exact_incident_scene: boolean;
  location_uncertainty_radius_m?: number | null;
  location_attribution?: string | null;
  victim_count: number;
  accused_count: number;
  has_arrest: boolean;
  has_chargesheet: boolean;
}
export interface CaseListResponse {
  items: CaseListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface FilterOption {
  id: number;
  name?: string | null;
}
export interface FilterOptionsResponse {
  districts: FilterOption[];
  stations: FilterOption[];
  crime_heads: FilterOption[];
  sub_heads: FilterOption[];
  statuses: FilterOption[];
  gravities: FilterOption[];
}

/** Per-stage caseload counts for the Command Center "My caseload" pipeline.
 *  Each case sits in exactly one stage, so `stages` counts sum to `total`. */
export interface CaseloadStage {
  key: string;
  label: string;
  count: number;
}
export interface CaseloadStatusBreakdown {
  status: string;
  stage: string;
  count: number;
}
export interface CaseloadResponse {
  stages: CaseloadStage[];
  by_status: CaseloadStatusBreakdown[];
  total: number;
  open_total: number;
  disposed_total: number;
}

export interface CaseCore {
  case_id: number;
  crime_no?: string | null;
  internal_crime_no?: string | null;
  registered_date?: string | null;
  incident_from?: string | null;
  incident_to?: string | null;
  brief_facts?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  station_id?: number | null;
  io_employee_id?: number | null;
  major_head_id?: number | null;
  minor_head_id?: number | null;
  crime_group?: string | null;
  crime_subhead?: string | null;
  gravity?: string | null;
  status?: string | null;
  district_id?: number | null;
  district?: string | null;
  station?: string | null;
  io_name?: string | null;
  record_origin: string;
  is_synthetic: boolean;
  reference_mapping_kind?: string | null;
  location_label?: string | null;
  location_precision?: string | null;
  not_exact_incident_scene: boolean;
  location_uncertainty_radius_m?: number | null;
  location_attribution?: string | null;
}
export interface CasePerson {
  id: number;
  name?: string | null;
  age?: number | null;
  person_id?: string | null;
}
export interface CaseSectionRow {
  act?: string | null;
  section?: string | null;
  description?: string | null;
  act_name?: string | null;
}
export interface CaseArrest {
  id: number;
  accused_id?: number | null;
  date?: string | null;
  io_id?: number | null;
  type?: number | null;
}
export interface CaseChargesheet {
  id: number;
  date?: string | null;
  cstype?: string | null;
}
export interface CaseTimelineEntry {
  date: string;
  type: "registered" | "incident" | "arrest" | "chargesheet" | string;
  label: string;
  detail?: string | null;
}
export interface CaseCurrentVersion {
  case_version_id: number;
  version_no: number;
  status_code: string;
  record_origin: string;
  is_synthetic: boolean;
  read_only: boolean;
  excluded_from_derived_analytics: boolean;
  source_cutoff?: string | null;
  official_references: Record<string, unknown>;
  reference_mapping: Record<string, unknown>;
  location: Record<string, unknown>;
  change_reason?: string | null;
}
export interface CaseSourceSummary {
  source_record_id: number;
  external_ref?: string | null;
  record_kind?: string | null;
  source_system_code?: string | null;
  source_system_name?: string | null;
  public_source_id?: string | null;
  title?: string | null;
  publisher?: string | null;
  published_date?: string | null;
  source_url?: string | null;
  authenticity?: string | null;
  presentation_use?: string | null;
  rights_and_handling?: string | null;
  last_checked?: string | null;
}
export interface CaseNotice {
  code: "PENDING_TRIAL" | "ALLEGATION_NOT_FINDING" | "PUBLIC_SOURCE_REFERENCE" | string;
  severity: "warning" | "info" | string;
  title: string;
  message: string;
}
export interface CaseDetailResponse {
  core: CaseCore;
  sections: CaseSectionRow[];
  section_labels: string[];
  victims: CasePerson[];
  accused: CasePerson[];
  complainants: CasePerson[];
  arrests: CaseArrest[];
  chargesheets: CaseChargesheet[];
  timeline: CaseTimelineEntry[];
  current_version?: CaseCurrentVersion | null;
  sources?: CaseSourceSummary[];
  notices?: CaseNotice[];
}

export interface CaseNetworkNode {
  id: string;
  kind: "case" | "accused" | string;
  label?: string | null;
  sub?: string | null;
  root: boolean;
  case_id?: number | null;
}
export interface CaseNetworkEdge {
  source: string;
  target: string;
  type: string;
  label?: string | null;
}
export interface CaseNetworkResponse {
  case_id: number;
  crime_no?: string | null;
  node_count: number;
  edge_count: number;
  linked_case_count: number;
  nodes: CaseNetworkNode[];
  edges: CaseNetworkEdge[];
}

export interface EvidenceItem {
  evidence_id: number;
  evidence_type: string;
  title: string;
  description?: string | null;
  reference?: string | null;
  created_by_role?: string | null;
  created_at?: string | null;
}
export interface EvidenceListResponse {
  available: boolean;
  items: EvidenceItem[];
}
export interface EvidenceCreateRequest {
  evidence_type: string;
  title: string;
  description?: string | null;
  reference?: string | null;
}
export interface EvidenceCreateResponse {
  evidence: EvidenceItem;
}

/* ------------------- People & Entities: Explorer + Profile (15d) ---------- */
export interface EntityListItem {
  entity_id: number;
  entity_type: string;
  label: string;
  ref_table?: string | null;
  ref_id?: string | null;
  pagerank?: number | null;
  community?: number | null;
  district_id?: number | null;
  district?: string | null;
  /** Canonical person this graph node resolves to, when it has one. Null for
   *  non-person nodes and for legacy rows with no canonical link. The face
   *  gallery is keyed on this, not on entity_id. */
  canonical_person_id?: number | null;
}
export interface EntityListResponse {
  items: EntityListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface EntityLinkedCase {
  case_id: number;
  crime_no?: string | null;
  registered_date?: string | null;
  crime_group?: string | null;
  status?: string | null;
  role: string;
}
export interface EntityGang {
  gang_id: number;
  gang_name?: string | null;
}
export interface EntityDetailResponse {
  entity_id: number;
  entity_type: string;
  label: string;
  ref_table?: string | null;
  ref_id?: string | null;
  accused_master_id?: number | null;
  canonical_entity_id?: number | null;
  /** Canonical person behind this node, when it has one — the key the face
   *  gallery and canonical profile are addressed by. */
  canonical_person_id?: number | null;
  attributes: Record<string, unknown>;
  longitude?: number | null;
  latitude?: number | null;
  created_at?: string | null;
  pagerank?: number | null;
  betweenness?: number | null;
  community?: number | null;
  district_id?: number | null;
  district?: string | null;
  cases: EntityLinkedCase[];
  gangs: EntityGang[];
}

/* ------------------- Network Analysis: communities (15e) ------------------ */
export interface CommunityListItem {
  community: number;
  size: number;
  gang_members: number;
}
export interface CommunityListResponse {
  communities: CommunityListItem[];
}
export interface CommunitySubgraphResponse {
  community: number;
  node_count: number;
  edge_count: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/* Path Finder: ready-made connected entity pairs (a shares a neighbour `via` with b). */
export interface PathSuggestionEndpoint {
  entity_id: number;
  label?: string | null;
  entity_type?: string | null;
}
export interface PathSuggestion {
  a: PathSuggestionEndpoint;
  b: PathSuggestionEndpoint;
  via: PathSuggestionEndpoint;
}
export interface PathSuggestionsResponse {
  suggestions: PathSuggestion[];
}

/* ------------------------- Map: raw incident points (15f) ----------------- */
export interface PointFeature {
  case_id: number;
  lon: number;
  lat: number;
  crime_head_id?: number | null;
  crime_group?: string | null;
  date?: string | null;
  hour?: number | null;
  crime_no?: string | null;
  location_label?: string | null;
  location_precision?: string | null;
  not_exact_incident_scene: boolean;
  uncertainty_radius_m?: number | null;
  location_attribution?: string | null;
  excluded_from_derived_analytics: boolean;
}
export interface PointsResponse {
  count: number;
  capped: boolean;
  points: PointFeature[];
}

/* ------------------------- Map: police stations (15f) --------------------- */
export interface StationFeature {
  station_id: number;
  name?: string | null;
  district?: string | null;
  lon: number;
  lat: number;
  case_count: number;
  top_crime?: string | null;
}
export interface StationsResponse {
  count: number;
  stations: StationFeature[];
}

/* ------------------------- Map: linked cases (arc view, 15f) -------------- */
export interface CaseLinkNode {
  case_id: number;
  lon: number;
  lat: number;
  crime_no?: string | null;
  crime_group?: string | null;
  via?: string | null;
  record_origin: string;
  is_synthetic: boolean;
  reference_mapping_kind?: string | null;
  location_label?: string | null;
  location_precision?: string | null;
  not_exact_incident_scene: boolean;
  uncertainty_radius_m?: number | null;
  location_attribution?: string | null;
}
export interface CaseLinksResponse {
  source_case_id: number;
  source_lon?: number | null;
  source_lat?: number | null;
  source_crime_no?: string | null;
  source_record_origin: string;
  source_is_synthetic: boolean;
  source_reference_mapping_kind?: string | null;
  source_location_label?: string | null;
  source_location_precision?: string | null;
  source_not_exact_incident_scene: boolean;
  source_uncertainty_radius_m?: number | null;
  source_location_attribution?: string | null;
  count: number;
  links: CaseLinkNode[];
}

/* --- Phase 9: jurisdiction freshness / containment scan / reassignment.
   1:1 with services/ml/app/geo/schemas.py. The UI and DB share one source of
   truth: DB-backed boundaries + these containment/repair endpoints. --- */
export interface JurisdictionBoundaryFreshness {
  count: number;
  version?: number | null;
  as_of?: string | null;
  source?: string | null;
}
export interface JurisdictionFreshness {
  boundaries: Record<string, JurisdictionBoundaryFreshness>;
  unit_locations: number;
  last_scan?: Record<string, unknown> | null;
  open_jurisdiction_issues: number;
  environment_label: string;
}
export interface ContainmentScanResult {
  run_id: number;
  run_key: string;
  scope: string;
  checked: number;
  out_of_state: number;
  out_of_district: number;
  issues_raised: number;
}
export interface ContainmentIssue {
  data_quality_issue_id: number;
  issue_type: string;
  severity: string;
  status: string;
  case_master_id?: number | null;
  crime_no?: string | null;
  assigned_district_id?: number | null;
  assigned_district_name?: string | null;
  resolved_district_id?: number | null;
  resolved_district_name?: string | null;
  detail: Record<string, unknown>;
  created_at?: string | null;
}
export interface ContainmentIssuesResponse {
  total: number;
  page: number;
  page_size: number;
  status: string;
  items: ContainmentIssue[];
}
export interface JurisdictionReassignRequest {
  case_master_id: number;
  to_district_id?: number | null;
  action?: "reassign" | "override" | "quarantine";
  reason: string;
  data_quality_issue_id?: number | null;
  actor?: string | null;
}
export interface JurisdictionReassignResult {
  jurisdiction_reassignment_id: number;
  case_master_id: number;
  action: string;
  from_district_id?: number | null;
  to_district_id?: number | null;
  new_case_version_id: number;
  issues_resolved: number;
  source_record_id?: number | null;
}

/* ============================================================================
   Intake (Phase 2) — 1:1 with services/ml/app/intake/schemas.py.
   Structured FIR/case intake: drafts, validation, canonical parties, workflow.
   ========================================================================== */

/* --- draft payload (wizard steps) --- */
export interface IntakeSourceInfo {
  source_system_code?: string | null;
  source_method?: string | null;
  external_source_id?: string | null;
  originating_unit_id?: number | null;
  receiving_unit_id?: number | null;
}
export interface IntakeRegistration {
  crime_no?: string | null;
  registration_date?: string | null; // YYYY-MM-DD
  registration_time?: string | null; // HH:MM
  registering_officer_id?: number | null;
  station_id?: number | null;
  district_id?: number | null;
  assigned_io_id?: number | null;
  sensitivity?: string | null;
  classification?: string | null;
}
export interface IntakeIncidentInfo {
  incident_from?: string | null;
  incident_to?: string | null;
  info_received_at?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  address?: string | null;
  landmark?: string | null;
  beat?: string | null;
  occurrence_description?: string | null;
  /** Phase 9: supervisory reason that lets an out-of-assigned-district incident
   *  be submitted (recorded + audited). Empty -> the mismatch blocks submit. */
  jurisdiction_override_reason?: string | null;
}
export interface IntakeActSection {
  act_code: string;
  section_code: string;
}
export interface IntakeClassification {
  major_head_id?: number | null;
  minor_head_id?: number | null;
  gravity_id?: number | null;
  acts_sections: IntakeActSection[];
  category_specific: Record<string, unknown>;
}
export interface IntakeNarrative {
  brief_facts?: string | null;
  language?: string | null;
  source_notes?: string | null;
  reviewer_notes?: string | null;
  restricted: boolean;
}
export interface IntakeDraftPayload {
  source: IntakeSourceInfo;
  registration: IntakeRegistration;
  incident: IntakeIncidentInfo;
  classification: IntakeClassification;
  narrative: IntakeNarrative;
}

/* --- parties --- */
export type IntakePartyRole =
  | "complainant" | "victim" | "accused" | "witness"
  | "informant" | "guardian" | "organisation" | "unknown";
export interface IntakePartyInput {
  role_type: IntakePartyRole | string;
  party_nature: "person" | "organisation" | "unknown" | string;
  canonical_person_id?: number | null;
  canonical_organisation_id?: number | null;
  is_unknown: boolean;
  display_name?: string | null;
  attributes: Record<string, unknown>;
  sequence_no?: number | null;
}
export interface IntakePartyOut extends IntakePartyInput {
  intake_draft_party_id: number;
}

/* --- validation / duplicates / jurisdiction --- */
export interface IntakeValidationIssue {
  field: string;
  code: string;
  message: string;
  severity: "error" | "warning" | string;
}
export interface IntakeJurisdictionInfo {
  has_point: boolean;
  latitude?: number | null;
  longitude?: number | null;
  in_state?: boolean | null;
  in_assigned_district?: boolean | null;
  resolved_district_id?: number | null;
  resolved_district_name?: string | null;
  nearest_unit_id?: number | null;
  nearest_unit_name?: string | null;
  note?: string | null;
}
export interface IntakeDuplicateCandidate {
  kind: "case" | "draft" | "source" | string;
  id: number;
  crime_no?: string | null;
  external_ref?: string | null;
  reason: string;
  match_score: number;
  detail?: string | null;
}
export interface IntakeValidationResponse {
  ok: boolean;
  can_submit: boolean;
  errors: IntakeValidationIssue[];
  warnings: IntakeValidationIssue[];
  jurisdiction: IntakeJurisdictionInfo;
  duplicate_candidates: IntakeDuplicateCandidate[];
  validated_at?: string | null;
}
export interface IntakeDuplicateCheckResponse {
  external_source_id?: string | null;
  candidates: IntakeDuplicateCandidate[];
}

/* --- draft read models --- */
export interface IntakeDraftActivity {
  intake_draft_activity_id: number;
  event_type: string;
  actor?: string | null;
  detail: Record<string, unknown>;
  created_at?: string | null;
}
export interface IntakeDraftResponse {
  intake_draft_id: number;
  draft_key: string;
  status: string;
  case_kind: string;
  case_category_code: string;
  source_system_id?: number | null;
  source_record_id?: number | null;
  ingestion_job_id?: number | null;
  case_master_id?: number | null;
  crime_no?: string | null;
  revision_no: number;
  created_by_actor?: string | null;
  submitted_by_actor?: string | null;
  reviewed_by_actor?: string | null;
  review_note?: string | null;
  return_reason?: string | null;
  payload: IntakeDraftPayload;
  parties: IntakePartyOut[];
  validation?: IntakeValidationResponse | null;
  created_at?: string | null;
  updated_at?: string | null;
  submitted_at?: string | null;
  reviewed_at?: string | null;
}
export interface IntakeDraftListItem {
  intake_draft_id: number;
  draft_key: string;
  status: string;
  case_kind: string;
  case_category_code: string;
  crime_no?: string | null;
  case_master_id?: number | null;
  party_count: number;
  validation_ok?: boolean | null;
  created_by_actor?: string | null;
  submitted_by_actor?: string | null;
  reviewed_by_actor?: string | null;
  revision_no: number;
  created_at?: string | null;
  updated_at?: string | null;
  submitted_at?: string | null;
}
export interface IntakeDraftListResponse {
  items: IntakeDraftListItem[];
  total: number;
  page: number;
  page_size: number;
}

/* --- submit / review / events --- */
export interface IntakeApprovalResult {
  draft: IntakeDraftResponse;
  case_master_id: number;
  case_version_id: number;
  case_event_id: number;
  crime_no: string;
  case_party_role_ids: number[];
  canonical_person_ids: number[];
}
export interface IntakeCaseEventResponse {
  case_master_id: number;
  case_event_id: number;
  from_status?: string | null;
  to_status: string;
  is_terminal: boolean;
  legacy_status?: string | null;
}

/* --- lookups + workflow metadata --- */
export interface IntakeOptionItem {
  id: number;
  name?: string | null;
  parent_id?: number | null;
  extra?: string | null;
}
export interface IntakeActOption {
  act_code: string;
  short_name?: string | null;
  description?: string | null;
}
export interface IntakeSectionOption {
  section_code: string;
  act_code: string;
  description?: string | null;
}
export interface IntakePartyRoleOption {
  value: string;
  label: string;
}
export interface IntakeTransitionMeta {
  event_type: string;
  from_status?: string | null;
  to_status?: string | null;
  requires_prior_event?: string | null;
  is_terminal: boolean;
  description?: string | null;
}
export interface IntakeCaseKindMeta {
  kind: string;
  category: string;
  label: string;
  allow_accused: boolean;
  allow_arrest: boolean;
  allow_chargesheet: boolean;
  allow_court: boolean;
  initial_event: string;
  initial_status: string;
  description: string;
  allowed_party_roles: string[];
}
export interface IntakeStatusMeta {
  code: string;
  label: string;
  legacy_name?: string | null;
}
export interface IntakeWorkflowMetaResponse {
  kinds: IntakeCaseKindMeta[];
  statuses: IntakeStatusMeta[];
  party_roles: IntakePartyRoleOption[];
  transitions_by_category: Record<string, IntakeTransitionMeta[]>;
  event_labels: Record<string, string>;
}
export interface IntakeLookupsResponse {
  categories: IntakeOptionItem[];
  gravities: IntakeOptionItem[];
  districts: IntakeOptionItem[];
  units: IntakeOptionItem[];
  crime_heads: IntakeOptionItem[];
  crime_subheads: IntakeOptionItem[];
  statuses: IntakeOptionItem[];
  officers: IntakeOptionItem[];
  courts: IntakeOptionItem[];
  acts: IntakeActOption[];
  sections: IntakeSectionOption[];
  party_roles: IntakePartyRoleOption[];
}
export interface IntakeStatusResponse {
  hackathon_mode: boolean;
  demo_data_only: boolean;
  synthetic_db: boolean;
  writes_localhost_only: boolean;
  submit_enabled: boolean;
  submit_disabled_reason?: string | null;
  environment_label: string;
}

/* --- request bodies --- */
export interface IntakeCreateDraftRequest {
  case_kind: string;
  case_category_code?: string | null;
  idempotency_key?: string | null;
  created_by_actor?: string | null;
  payload: IntakeDraftPayload;
  parties: IntakePartyInput[];
}
export interface IntakeUpdateDraftRequest {
  case_kind?: string | null;
  case_category_code?: string | null;
  payload?: IntakeDraftPayload | null;
  actor?: string | null;
  expected_revision_no?: number | null;
  autosave?: boolean;
}

/* --- data-quality review queue --- */
export interface IntakeDataQualityIssue {
  data_quality_issue_id: number;
  issue_type: string;
  severity: string;
  status: string;
  source_record_id?: number | null;
  ingestion_job_id?: number | null;
  case_master_id?: number | null;
  evidence_item_id?: number | null;
  detail: Record<string, unknown>;
  resolved_by_actor?: string | null;
  created_at?: string | null;
  resolved_at?: string | null;
}
export interface IntakeDataQualityListResponse {
  items: IntakeDataQualityIssue[];
  total: number;
  by_severity: Record<string, number>;
  page: number;
  page_size: number;
}

/* --- canonical case parties (CasePartyRole resolved through canonical identity) --- */
export interface IntakeCaseParty {
  case_party_role_id: number;
  role_type: string;
  is_unknown: boolean;
  party_label?: string | null;
  sequence_no?: number | null;
  canonical_person_id?: number | null;
  person_ref?: string | null;
  person_label?: string | null;
  canonical_organisation_id?: number | null;
  org_ref?: string | null;
  org_name?: string | null;
  legacy_ref_table?: string | null;
  legacy_ref_id?: number | null;
}
export interface IntakeCasePartyListResponse {
  case_master_id: number;
  count: number;
  parties: IntakeCaseParty[];
}

/* ===========================================================================
   Phase 4 — canonical identity + entity resolution (services/ml/app/identity)
   =========================================================================== */

export interface IdentityPersonSummary {
  canonical_person_id: number;
  public_ref: string;
  display_label: string | null;
  is_unknown: boolean;
  primary_gender_id: number | null;
  approx_birth_year: number | null;
  is_juvenile: boolean;
  resolution_status: string;
  merged_into: number | null;
  case_count: number | null;
  alias_count: number | null;
}

export interface IdentityPersonSearchResponse {
  items: IdentityPersonSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface IdentityAlias { person_alias_id: number; alias_name: string; alias_type: string }
export interface IdentityIdentifier {
  person_identifier_id: number; identifier_type: string; identifier_value: string; sensitivity: string;
}
export interface IdentityContact {
  person_contact_id: number; contact_type: string; contact_value: string; sensitivity: string;
}
export interface IdentityAddress {
  person_address_id: number; district_id: number | null; address_text: string | null;
  latitude: number | null; longitude: number | null; sensitivity: string;
}
export interface IdentityCaseRole {
  case_party_role_id: number; case_master_id: number; crime_no: string | null;
  role_type: string; is_unknown: boolean; party_label: string | null; sequence_no: number | null;
}
export interface IdentityMergeHistory {
  entity_merge_history_id: number; action: string;
  winner_canonical_person_id: number | null; loser_canonical_person_id: number | null;
  reason: string | null; actor: string | null; created_at: string | null;
}
export interface IdentityPersonDetail extends IdentityPersonSummary {
  attributes: Record<string, unknown>;
  canonical_entity_id: number | null;
  aliases: IdentityAlias[];
  identifiers: IdentityIdentifier[];
  contacts: IdentityContact[];
  addresses: IdentityAddress[];
  case_roles: IdentityCaseRole[];
  merge_history: IdentityMergeHistory[];
}

export interface IdentityOrgSummary {
  canonical_organisation_id: number; public_ref: string; name: string; org_type: string | null;
}
export interface IdentityOrgSearchResponse {
  items: IdentityOrgSummary[]; total: number; page: number; page_size: number;
}

export interface IdentityCandidatePersonRef {
  canonical_person_id: number; public_ref: string; display_label: string | null;
  case_count: number | null; alias_count: number | null;
}
export interface IdentityCandidate {
  entity_resolution_candidate_id: number;
  person_a: IdentityCandidatePersonRef;
  person_b: IdentityCandidatePersonRef;
  method: string;
  score: number | null;
  match_features: Record<string, unknown>;
  status: string;
  reviewed_by_actor: string | null;
  reviewed_at: string | null;
  created_at: string | null;
}
export interface IdentityCandidateListResponse {
  items: IdentityCandidate[]; total: number; page: number; page_size: number;
}
export interface IdentityGenerateResponse { created: number; candidates: IdentityCandidate[] }

export interface IdentityMergeResult {
  action: string;
  winner_canonical_person_id: number;
  loser_canonical_person_id: number;
  moved_references: Record<string, number>;
  entity_merge_history_id: number | null;
  reversible: boolean;
}

export interface IdentityReviewResult {
  entity_resolution_candidate_id: number;
  status: string;
  merge: IdentityMergeResult | null;
}

export interface IdentityPartyMutation {
  case_party_role_id: number; case_master_id: number;
  canonical_person_id: number | null; canonical_organisation_id: number | null;
  role_type: string; is_unknown: boolean;
}

export type IdentityLinkStats = Record<string, number>;

/* ===========================================================================
   Phase 5 — digital evidence platform (services/ml/app/evidence/schemas.py).
   Files live in a PRIVATE S3 bucket; only MANUAL metadata lives in PostgreSQL.
   `Ev`-prefixed to avoid clashing with the legacy CaseEvidence types above.
   =========================================================================== */

export interface EvStatus {
  hackathon_mode: boolean;
  demo_data_only: boolean;
  synthetic_db: boolean;
  writes_localhost_only: boolean;
  s3_configured: boolean;
  upload_enabled: boolean;
  max_bytes: number;
  allowed_extensions: string[];
  allowed_mime_types: string[];
  presign_expiry_seconds: number;
  extraction_disabled_note: string;
  environment_label: string;
}

export interface EvLabelledValue { value: string; label: string }
export interface EvLookups {
  evidence_types: EvLabelledValue[];
  categories: EvLabelledValue[];
  confidentialities: EvLabelledValue[];
  languages: EvLabelledValue[];
  link_types: EvLabelledValue[];
  source_systems: EvLabelledValue[];
}

export interface EvObject {
  evidence_object_id: number;
  version_no: number;
  is_current: boolean;
  file_name?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  sha256: string;
  storage_status: string;
  storage_key?: string | null;
  created_at?: string | null;
}
export interface EvVersion {
  evidence_version_id: number;
  version_no: number;
  evidence_object_id?: number | null;
  change_reason?: string | null;
  created_by_actor?: string | null;
  created_at?: string | null;
}
export interface EvActivity {
  evidence_activity_event_id: number;
  event_type: string;
  actor?: string | null;
  detail: Record<string, unknown>;
  created_at?: string | null;
}
export interface EvCaseLink {
  evidence_case_link_id: number;
  case_master_id: number;
  crime_no?: string | null;
  link_type: string;
  created_at?: string | null;
  record_origin: string;
  is_synthetic: boolean;
  reference_mapping_kind?: string | null;
}
export interface EvEntityLink {
  evidence_entity_link_id: number;
  canonical_entity_id: number;
  entity_ref?: string | null;
  entity_label?: string | null;
  link_type: string;
  review_status: string;
  confidence?: number | null;
}
export interface EvItem {
  evidence_item_id: number;
  case_master_id?: number | null;
  crime_no?: string | null;
  source_system_id?: number | null;
  evidence_type: string;
  category?: string | null;
  title: string;
  description?: string | null;
  synthetic_reference?: string | null;
  language?: string | null;
  tags: string[];
  uploader_actor?: string | null;
  confidentiality: string;
  state: string; // draft | uploading | available | failed | archived
  is_synthetic: boolean;
  is_read_only: boolean;
  manual_metadata: Record<string, unknown>;
  captured_at?: string | null;
  received_at?: string | null;
  uploaded_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  current_object?: EvObject | null;
  objects: EvObject[];
  versions: EvVersion[];
  case_links: EvCaseLink[];
  entity_links: EvEntityLink[];
  activity: EvActivity[];
  is_previewable: boolean;
}
export interface EvListItem {
  evidence_item_id: number;
  case_master_id?: number | null;
  evidence_type: string;
  category?: string | null;
  title: string;
  synthetic_reference?: string | null;
  source_label?: string | null;
  state: string;
  is_synthetic: boolean;
  is_read_only: boolean;
  language?: string | null;
  tags: string[];
  version_no?: number | null;
  sha256?: string | null;
  file_name?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  captured_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}
export interface EvListResponse {
  items: EvListItem[];
  total: number;
  page: number;
  page_size: number;
  by_state: Record<string, number>;
}

export interface EvCreateRequest {
  case_id?: number | null;
  canonical_entity_id?: number | null;
  evidence_type: string;
  category?: string | null;
  title: string;
  description?: string | null;
  source_system_code?: string | null;
  synthetic_reference?: string | null;
  captured_at?: string | null;
  received_at?: string | null;
  language?: string;
  tags?: string[];
  confidentiality?: string;
  uploader_actor?: string | null;
  notes?: string | null;
  external_reference_url?: string | null;
  metadata_only?: boolean;
  idempotency_key?: string | null;
}
export interface EvCreateResponse { item: EvItem; duplicate_warning?: string | null }

export interface EvMetadataUpdate {
  evidence_type?: string | null;
  category?: string | null;
  title?: string | null;
  description?: string | null;
  synthetic_reference?: string | null;
  captured_at?: string | null;
  received_at?: string | null;
  language?: string | null;
  tags?: string[] | null;
  confidentiality?: string | null;
  notes?: string | null;
  change_reason?: string | null;
  actor?: string | null;
}

export interface EvUploadUrlRequest {
  file_name: string;
  mime_type: string;
  size_bytes: number;
  sha256?: string | null;
  change_reason?: string | null;
  actor?: string | null;
}
export interface EvUploadUrlResponse {
  evidence_item_id: number;
  version_no: number;
  storage_key: string;
  upload_url: string;
  method: string;
  headers: Record<string, string>;
  expires_in: number;
  expires_at: string;
  max_bytes: number;
}
export interface EvCompleteRequest {
  storage_key: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  sha256?: string | null;
  version_no?: number | null;
  change_reason?: string | null;
  actor?: string | null;
}
export interface EvCompleteResponse {
  item: EvItem;
  evidence_object_id: number;
  version_no: number;
  sha256: string;
  size_bytes: number;
  duplicate_warning?: string | null;
  duplicate_of_item_ids: number[];
}
export interface EvDownloadUrlResponse {
  evidence_item_id: number;
  evidence_object_id: number;
  version_no: number;
  file_name?: string | null;
  mime_type?: string | null;
  url: string;
  expires_in: number;
  expires_at: string;
}
export interface EvLinkRequest {
  case_id?: number | null;
  canonical_entity_id?: number | null;
  link_type?: string;
  actor?: string | null;
}
export interface EvArchiveRequest { reason?: string | null; actor?: string | null }
export interface EvMigrateResponse {
  scanned: number;
  migrated: number;
  skipped_existing: number;
  item_ids: number[];
}
export interface EvResetResponse {
  case_master_id: number;
  items_deleted: number;
  objects_deleted_in_storage: number;
  ok: boolean;
}

/* ===========================================================================
   Phase 7 — casework (services/ml/app/casework/schemas.py). Statements,
   property/seizure, lab results, court/bail/disposition/outcome, event-backed
   lifecycle + timeline. `Cw`-prefixed. Manual entry only; files linked by id.
   =========================================================================== */

export interface CwLabelledValue { value: string; label: string }
export interface CwOptionItem { id: number; name?: string | null }
export interface CwLookups {
  statement_types: CwLabelledValue[];
  property_item_types: CwLabelledValue[];
  property_statuses: CwLabelledValue[];
  court_event_types: CwLabelledValue[];
  bail_statuses: CwLabelledValue[];
  disposition_types: CwLabelledValue[];
  lab_test_types: CwLabelledValue[];
  lab_statuses: CwLabelledValue[];
  access_classifications: CwLabelledValue[];
  courts: CwOptionItem[];
}

/* --- statements --- */
export interface CwStatementVersion {
  statement_version_id: number;
  version_no: number;
  statement_text?: string | null;
  correction_reason?: string | null;
  translation?: string | null;
  redacted: boolean;
  created_by_actor?: string | null;
  created_at?: string | null;
}
export interface CwStatement {
  statement_id: number;
  case_master_id: number;
  statement_type: string;
  canonical_person_id?: number | null;
  speaker_ref?: string | null;
  speaker_label?: string | null;
  case_party_role_id?: number | null;
  recorded_by_actor?: string | null;
  recorded_at?: string | null;
  place?: string | null;
  language?: string | null;
  access_classification: string;
  state: string;
  evidence_item_id?: number | null;
  current_text?: string | null;
  current_version_no?: number | null;
  is_restricted: boolean;
  access_limited: boolean;
  versions: CwStatementVersion[];
  created_at?: string | null;
}
export interface CwStatementListResponse {
  case_master_id: number;
  count: number;
  items: CwStatement[];
}
export interface CwStatementCreate {
  statement_type: string;
  canonical_person_id?: number | null;
  case_party_role_id?: number | null;
  recorded_by_actor?: string | null;
  recorded_at?: string | null;
  place?: string | null;
  language?: string;
  access_classification?: string;
  evidence_item_id?: number | null;
  statement_text: string;
  actor?: string | null;
}
export interface CwStatementCorrection {
  statement_text?: string | null;
  correction_reason: string;
  translation?: string | null;
  redact?: boolean;
  actor?: string | null;
}

/* --- property / seizure --- */
export interface CwPropertyItemInput {
  item_type: string;
  synthetic_identifier?: string | null;
  description?: string | null;
  quantity?: number | null;
  unit?: string | null;
  estimated_value?: number | null;
  owner_canonical_person_id?: number | null;
  status?: string;
  vehicle_fields?: Record<string, unknown>;
  weapon_fields?: Record<string, unknown>;
}
export interface CwPropertyItem extends CwPropertyItemInput {
  property_item_id: number;
  seizure_id?: number | null;
  case_master_id: number;
  owner_label?: string | null;
  status: string;
  created_at?: string | null;
}
export interface CwSeizure {
  seizure_id: number;
  case_master_id: number;
  seizure_type: string;
  seized_at?: string | null;
  place?: string | null;
  memo_evidence_item_id?: number | null;
  actor?: string | null;
  created_at?: string | null;
  items: CwPropertyItem[];
}
export interface CwSeizureListResponse {
  case_master_id: number;
  seizures: CwSeizure[];
  unlinked_items: CwPropertyItem[];
  count: number;
}
export interface CwSeizureCreate {
  seizure_type?: string;
  seized_at?: string | null;
  place?: string | null;
  memo_evidence_item_id?: number | null;
  actor?: string | null;
  items?: CwPropertyItemInput[];
}

/* --- lab results --- */
export interface CwLabResult {
  lab_result_id: number;
  case_master_id: number;
  property_item_id?: number | null;
  seizure_id?: number | null;
  test_type: string;
  lab_name?: string | null;
  synthetic_reference?: string | null;
  requested_at?: string | null;
  result_at?: string | null;
  result_summary?: string | null;
  status: string;
  report_evidence_item_id?: number | null;
  access_classification: string;
  access_limited: boolean;
  created_by_actor?: string | null;
  created_at?: string | null;
}
export interface CwLabResultListResponse {
  case_master_id: number;
  count: number;
  items: CwLabResult[];
}
export interface CwLabResultInput {
  test_type: string;
  lab_name?: string | null;
  synthetic_reference?: string | null;
  requested_at?: string | null;
  result_at?: string | null;
  result_summary?: string | null;
  status?: string;
  report_evidence_item_id?: number | null;
  property_item_id?: number | null;
  seizure_id?: number | null;
  access_classification?: string;
  actor?: string | null;
}

/* --- court / bail / disposition / outcome / lifecycle --- */
export interface CwCourtEvent {
  court_event_id: number;
  case_master_id: number;
  court_id?: number | null;
  court_name?: string | null;
  court_reference_kind?: string | null;
  event_type: string;
  scheduled_at?: string | null;
  occurred_at?: string | null;
  outcome?: string | null;
  detail: Record<string, unknown>;
  created_at?: string | null;
}
export interface CwBail {
  bail_event_id: number;
  case_master_id: number;
  canonical_person_id?: number | null;
  person_label?: string | null;
  bail_type?: string | null;
  status: string;
  decided_at?: string | null;
  court_id?: number | null;
  detail: Record<string, unknown>;
  created_at?: string | null;
}
export interface CwDisposition {
  case_disposition_id: number;
  case_master_id: number;
  disposition_type: string;
  disposition_date?: string | null;
  court_event_id?: number | null;
  is_final: boolean;
  detail: Record<string, unknown>;
  created_at?: string | null;
}
export interface CwOutcome {
  outcome_observation_id: number;
  case_master_id: number;
  observation_type: string;
  observed_at?: string | null;
  observation_window_start?: string | null;
  observation_window_end?: string | null;
  verified: boolean;
  source_event_id?: number | null;
  detail: Record<string, unknown>;
  created_at?: string | null;
}
export interface CwTransitionMeta {
  event_type: string;
  label: string;
  from_status?: string | null;
  to_status?: string | null;
  requires_prior_event?: string | null;
  is_terminal: boolean;
  description?: string | null;
}
export interface CwCourtLifecycleView {
  case_master_id: number;
  category?: string | null;
  current_status?: string | null;
  current_status_label?: string | null;
  legacy_status?: string | null;
  has_case_version: boolean;
  read_only: boolean;
  read_only_reason?: string | null;
  prior_event_types: string[];
  allowed_transitions: CwTransitionMeta[];
  court_events: CwCourtEvent[];
  bail_events: CwBail[];
  dispositions: CwDisposition[];
  outcomes: CwOutcome[];
  has_final_disposition: boolean;
  can_record_outcome: boolean;
}
export interface CwCourtEventInput {
  event_type: string;
  court_id?: number | null;
  scheduled_at?: string | null;
  occurred_at?: string | null;
  outcome?: string | null;
  evidence_item_id?: number | null;
  detail?: Record<string, unknown>;
  actor?: string | null;
}
export interface CwBailInput {
  canonical_person_id?: number | null;
  bail_type?: string | null;
  status?: string;
  decided_at?: string | null;
  court_id?: number | null;
  detail?: Record<string, unknown>;
  actor?: string | null;
}
export interface CwDispositionInput {
  disposition_type: string;
  disposition_date?: string | null;
  court_event_id?: number | null;
  is_final?: boolean | null;
  detail?: Record<string, unknown>;
  actor?: string | null;
}
export interface CwOutcomeInput {
  observation_type?: string;
  observed_at?: string | null;
  observation_window_start?: string | null;
  observation_window_end?: string | null;
  detail?: Record<string, unknown>;
  actor?: string | null;
}
export interface CwLifecycleEventResult {
  case_master_id: number;
  case_event_id: number;
  from_status?: string | null;
  to_status: string;
  is_terminal: boolean;
  legacy_status?: string | null;
  bootstrapped_version: boolean;
}

/* --- timeline --- */
export interface CwTimelineEntry {
  date?: string | null;
  kind: string;
  type: string;
  label: string;
  detail?: string | null;
  ref_id?: number | null;
}
export interface CwTimelineResponse {
  case_master_id: number;
  count: number;
  event_backed: boolean;
  entries: CwTimelineEntry[];
}

/* ------------------- Phase 8: digital + financial imports ----------------- */
/* 1:1 with services/ml/app/imports/schemas.py. `Imp*` prefix. */

export interface ImpTemplateVersion {
  import_template_version_id: number;
  version: string;
  status: string;
  target_table?: string | null;
  fields: Array<Record<string, unknown>>;
  required_columns: string[];
  dedupe_keys: string[];
  notes?: string | null;
}
export interface ImpTemplate {
  import_template_id: number;
  code: string;
  name: string;
  domain: string;
  target_table: string;
  description?: string | null;
  versions: ImpTemplateVersion[];
}
export interface ImpTemplateListResponse {
  count: number;
  templates: ImpTemplate[];
}

export interface ImpStagingRow {
  import_staging_row_id?: number | null;
  row_number?: number | null;
  status: string;
  reject_reason?: string | null;
  mapped: Record<string, unknown>;
  canonical_target_table?: string | null;
  canonical_target_id?: number | null;
}
export interface ImpBatch {
  import_batch_id: number;
  ingestion_job_id?: number | null;
  import_template_version_id: number;
  template_code?: string | null;
  template_version?: string | null;
  domain: string;
  target_table?: string | null;
  case_master_id?: number | null;
  evidence_item_id?: number | null;
  source_file_name?: string | null;
  source_format: string;
  status: string;
  dry_run: boolean;
  totals: Record<string, number>;
  error_summary: Record<string, number>;
  mapping: Record<string, unknown>;
  superseded_by_import_batch_id?: number | null;
  created_by_actor?: string | null;
  approved_by_actor?: string | null;
  committed_at?: string | null;
  created_at?: string | null;
  sample_rows: ImpStagingRow[];
}
export interface ImpBatchListItem {
  import_batch_id: number;
  domain: string;
  template_code?: string | null;
  status: string;
  dry_run: boolean;
  case_master_id?: number | null;
  totals: Record<string, number>;
  created_by_actor?: string | null;
  created_at?: string | null;
}
export interface ImpBatchListResponse {
  items: ImpBatchListItem[];
  total: number;
  page: number;
  page_size: number;
}
export interface ImpStagingRowListResponse {
  import_batch_id: number;
  total: number;
  page: number;
  page_size: number;
  status_filter?: string | null;
  items: ImpStagingRow[];
}
export interface ImpCommitResult {
  import_batch_id: number;
  status: string;
  target_table?: string | null;
  committed: number;
  rejected: number;
  duplicate: number;
  source_records_created: number;
  canonical_rows_created: number;
  candidate_entity_links: number;
  idempotent_replay: boolean;
}
export interface ImpRollbackResult {
  import_batch_id: number;
  status: string;
  canonical_rows_deleted: number;
  source_records_retracted: number;
}

export interface ImpEntityLinkItem {
  evidence_entity_link_id: number;
  evidence_item_id?: number | null;
  evidence_title?: string | null;
  canonical_entity_id: number;
  entity_kind?: string | null;
  entity_label?: string | null;
  entity_ref?: string | null;
  link_type: string;
  confidence?: number | null;
  review_status: string;
  reviewed_by_actor?: string | null;
  reviewed_at?: string | null;
  source_record_id?: number | null;
  import_batch_id?: number | null;
  case_master_id?: number | null;
}
export interface ImpEntityLinkQueueResponse {
  total: number;
  page: number;
  page_size: number;
  review_status?: string | null;
  items: ImpEntityLinkItem[];
}

export interface ImpAccount {
  account_id: number;
  account_no?: string | null;
  account_type?: string | null;
  holder_name?: string | null;
  bank?: string | null;
  ifsc?: string | null;
  currency?: string | null;
  is_flagged: boolean;
  owner_canonical_person_id?: number | null;
  owner_review_status?: string | null;
  import_batch_id?: number | null;
}
export interface ImpAccountListResponse {
  total: number;
  page: number;
  page_size: number;
  items: ImpAccount[];
}
export interface ImpTransaction {
  transaction_id: number;
  source_account_id: number;
  destination_account_id: number;
  amount: number;
  currency?: string | null;
  txn_timestamp?: string | null;
  channel?: string | null;
  normalized_channel?: string | null;
  is_flagged: boolean;
  flag_reason?: string | null;
  review_status?: string | null;
  evidence_case_id?: number | null;
  import_batch_id?: number | null;
  synthetic_reference?: string | null;
}
export interface ImpTransactionListResponse {
  total: number;
  page: number;
  page_size: number;
  items: ImpTransaction[];
}

export interface ImpCommEvent {
  communication_event_id: number;
  comm_type: string;
  occurred_at?: string | null;
  duration_sec?: number | null;
  endpoint_a?: string | null;
  endpoint_b?: string | null;
  review_status?: string | null;
  case_master_id?: number | null;
  import_batch_id?: number | null;
}
export interface ImpCdrTimelineResponse {
  scope: string;
  scope_id: number;
  total: number;
  by_type: Record<string, number>;
  by_day: Record<string, number>;
  top_endpoints: Array<{ endpoint: string; count: number }>;
  events: ImpCommEvent[];
}
export interface ImpDeviceArtifact {
  device_artifact_id: number;
  artifact_type: string;
  synthetic_reference?: string | null;
  import_batch_id?: number | null;
}
export interface ImpDevice {
  device_id: number;
  device_type?: string | null;
  synthetic_identifier?: string | null;
  label?: string | null;
  case_master_id?: number | null;
  import_batch_id?: number | null;
  artifacts: ImpDeviceArtifact[];
}
export interface ImpDeviceListResponse {
  scope: string;
  scope_id: number;
  count: number;
  devices: ImpDevice[];
}

export interface ImpMoneyScanResponse {
  result: AiResult;
  transactions_scanned: number;
  alerts_written: number;
  by_type: Record<string, number>;
  by_reason_code: Record<string, number>;
  model_version_id: number;
}
export interface ImpMoneyAlert {
  money_alert_id: number;
  alert_type: string;
  reason_code: string;
  severity: string;
  title?: string | null;
  message?: string | null;
  account_id?: number | null;
  case_master_id?: number | null;
  evidence_item_id?: number | null;
  transaction_ids: number[];
  source_record_ids: number[];
  status: string;
  latest_disposition?: string | null;
  created_at?: string | null;
}
export interface ImpMoneyAlertListResponse {
  total: number;
  page: number;
  page_size: number;
  by_status: Record<string, number>;
  items: ImpMoneyAlert[];
}

/* ===================================================================== */
/* Phase 10 — governed feature & prediction contracts                     */
/* 1:1 with services/ml/app/governance/schemas.py. Predictions are        */
/* aggregate decision-support only; every result ties to an immutable     */
/* feature snapshot; protected attributes never enter a prediction schema.*/
/* ===================================================================== */
export interface GovFeatureDefinition {
  feature_definition_id: number;
  name: string;
  value_type: string;
  description?: string | null;
  source_table?: string | null;
  source_field?: string | null;
  source_event?: string | null;
  transformation?: string | null;
  window_spec?: string | null;
  observation_cutoff_behavior: string;
  sensitivity: string;
  allowed_tasks: string[];
  missing_policy: string;
  stale_policy: string;
  owner?: string | null;
  approval_status: string;
}
export interface GovFeatureDefinitionListResponse {
  total: number;
  items: GovFeatureDefinition[];
}
export interface GovFeatureSchemaVersion {
  feature_schema_version_id: number;
  schema_name: string;
  version: string;
  feature_definition_ids: number[];
  task?: string | null;
  status: string;
  approved_by_actor?: string | null;
  approved_at?: string | null;
  created_at?: string | null;
  features: GovFeatureDefinition[];
  has_protected_feature: boolean;
}
export interface GovFeatureSchemaListResponse {
  total: number;
  items: GovFeatureSchemaVersion[];
}
export interface GovFeatureSnapshot {
  feature_snapshot_id: number;
  feature_schema_version_id?: number | null;
  subject_kind: string;
  subject_ref_id: string;
  observation_cutoff?: string | null;
  values: Record<string, unknown>;
  source_versions: Record<string, unknown>;
  quality_status: string;
  content_hash: string;
  is_immutable: boolean;
  superseded_by_feature_snapshot_id?: number | null;
  stale_reason?: string | null;
  superseded_at?: string | null;
  built_by_actor?: string | null;
  created_at?: string | null;
}
export interface GovFeatureSnapshotListResponse {
  total: number;
  page: number;
  page_size: number;
  items: GovFeatureSnapshot[];
}
export interface GovBuildSnapshotResult extends GovFeatureSnapshot {
  unknown_features: string[];
  reused: boolean;
}
export interface GovInvalidateResult {
  subject_kind: string;
  subject_ref_id: string;
  snapshots_marked_stale: number;
  results_marked_stale: number;
  requests_marked_stale: number;
}
export interface GovModelVersion {
  model_version_id: number;
  model_name: string;
  model_type?: string | null;
  version: string;
  framework?: string | null;
  artifact_uri?: string | null;
  artifact_digest?: string | null;
  image_digest?: string | null;
  feature_schema_version_id?: number | null;
  training_dataset_snapshot_id?: number | null;
  approval_status?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  environment?: string | null;
  evaluation_report: Record<string, unknown>;
  status?: string | null;
  is_rollback_target: boolean;
  rollback_to_model_version_id?: number | null;
}
export interface GovModelVersionListResponse {
  total: number;
  items: GovModelVersion[];
}
export interface GovPredictionReview {
  prediction_review_id: number;
  reviewer_actor?: string | null;
  decision: string;
  override_reason?: string | null;
  reviewed_at?: string | null;
}
export interface GovPredictionResult {
  prediction_result_id: number;
  model_version_id?: number | null;
  feature_snapshot_id?: number | null;
  output: Record<string, unknown>;
  explanation: Record<string, unknown>;
  limitations?: string | null;
  confidence?: number | null;
  lower_interval?: number | null;
  upper_interval?: number | null;
  expires_at?: string | null;
  is_stale: boolean;
  stale_reason?: string | null;
  superseded_by_result_id?: number | null;
  created_at?: string | null;
}
export interface GovPredictionRequest {
  prediction_request_id: number;
  model_version_id?: number | null;
  model_version_label?: string | null;
  feature_snapshot_id?: number | null;
  request_kind: string;
  idempotency_key?: string | null;
  status: string;
  requested_by_actor?: string | null;
  created_at?: string | null;
}
export interface GovPredictionRequestListResponse {
  total: number;
  page: number;
  page_size: number;
  items: GovPredictionRequest[];
}
export interface GovPredictionDetail {
  request: GovPredictionRequest;
  result?: GovPredictionResult | null;
  reviews: GovPredictionReview[];
  feature_snapshot?: GovFeatureSnapshot | null;
  model_version?: GovModelVersion | null;
  is_current: boolean;
  answer?: AiResult | null;
}
export interface GovOutcomeLabel {
  outcome_label_id: number;
  case_master_id?: number | null;
  subject_kind: string;
  subject_ref_id?: string | null;
  label_name: string;
  label_value?: string | null;
  outcome_observation_id?: number | null;
  observation_cutoff?: string | null;
  label_window_start?: string | null;
  label_window_end?: string | null;
  split_tag?: string | null;
}
export interface GovOutcomeLabelListResponse {
  total: number;
  page: number;
  page_size: number;
  leakage_safe: boolean;
  splits: Record<string, number>;
  items: GovOutcomeLabel[];
}

/* ==========================================================================
   Facial recognition (services/ml/app/face) — 1:N search of a probe photo
   against the canonical person gallery.

   A score is an investigative LEAD requiring human confirmation, never an
   identification: `matched` means "cleared the model threshold, worth a look".
   Confirming a hit records a reviewable entity-resolution candidate; it never
   merges identities. Probe bytes are never persisted server-side.
   ========================================================================== */

export interface FaceEngineInfo {
  name?: string | null;
  version?: string | null;
  family?: string | null;
  dim?: number | null;
  /** False = the backend compares IMAGES, not identities. The UI must say so. */
  biometric: boolean;
  recommended_threshold?: number | null;
  strong_threshold?: number | null;
  note?: string | null;
  providers: string[];
  pack?: string | null;
}
export interface FaceModelsInfo {
  pack: string;
  present: boolean;
  detector?: string | null;
  recogniser?: string | null;
  approx_download_mb?: number | null;
  /** Exact command an operator must run when the weights are absent. */
  install_command?: string | null;
  directory?: string | null;
}
export interface FaceGalleryInfo {
  model_version_id?: number | null;
  model_name?: string | null;
  face_count: number;
  person_count: number;
  /** Gallery built by a different encoder — the two vector spaces don't compare. */
  model_mismatch: boolean;
}
export interface FaceStatusResponse {
  enabled: boolean;
  available: boolean;
  /** Engine present AND a non-empty, model-matched gallery to search. */
  search_ready: boolean;
  engine: FaceEngineInfo;
  models?: FaceModelsInfo | null;
  gallery: FaceGalleryInfo;
  probes: Record<string, number>;
  onnxruntime: Record<string, unknown>;
  max_image_bytes: number;
  recommended_long_edge: number;
  default_top_k: number;
  max_top_k: number;
  max_gallery_per_person: number;
  unavailable_reason?: string | null;
  warnings: string[];
}

export type FaceCaptureMode = "upload" | "camera";
export type FaceOrigin =
  | "intake_fir" | "standalone" | "case_file" | "person_page" | "enrolment";
export type FaceBand = "strong" | "probable" | "weak";
export type FaceDecision = "confirmed" | "rejected" | "no_match" | "new_person";

export interface FaceSearchRequest {
  /** Raw or data-URL base64. Downscale in the browser first (see status). */
  image_base64: string;
  top_k?: number;
  min_similarity?: number;
  capture_mode?: FaceCaptureMode;
  origin?: FaceOrigin;
  intake_draft_key?: string | null;
  case_id?: number | null;
  actor?: string | null;
}
export interface FaceRecentCase {
  case_id?: number | null;
  crime_no?: string | null;
  registered_date?: string | null;
  role_type?: string | null;
  crime_group?: string | null;
  district?: string | null;
  status?: string | null;
}
export interface FacePersonRecord {
  canonical_person_id: number;
  public_ref: string;
  display_label?: string | null;
  is_unknown: boolean;
  primary_gender_id?: number | null;
  approx_birth_year?: number | null;
  is_juvenile: boolean;
  resolution_status: string;
  canonical_entity_id?: number | null;
  aliases: string[];
  case_count: number;
  role_types: string[];
  districts: string[];
  recent_cases: FaceRecentCase[];
  first_seen?: string | null;
  last_seen?: string | null;
}
export interface FaceMatch {
  rank: number;
  canonical_person_id: number;
  similarity: number;
  distance?: number | null;
  band: FaceBand;
  above_threshold: boolean;
  gallery_hits: number;
  gallery_quality?: number | null;
  image_label?: string | null;
  person_face_embedding_id?: number | null;
  evidence_item_id?: number | null;
  person: FacePersonRecord;
}
export interface FaceProbeInfo {
  probe_ref: string;
  faces_detected: number;
  /** Detector box in SOURCE image pixels — drives the on-screen face bracket. */
  bounding_box: { x?: number; y?: number; w?: number; h?: number };
  /** 5 landmarks [x, y] in source pixels (eyes, nose, mouth corners). */
  landmarks: number[][];
  detector_score?: number | null;
  quality?: number | null;
  image_width?: number | null;
  image_height?: number | null;
  image_sha256?: string | null;
  capture_mode: FaceCaptureMode;
}
export interface FaceSearchResponse {
  probe: FaceProbeInfo;
  matches: FaceMatch[];
  best_match?: FaceMatch | null;
  matched: boolean;
  threshold: number;
  model_name: string;
  model_version_id: number;
  biometric: boolean;
  gallery_face_count: number;
  gallery_person_count: number;
  latency_ms: number;
  disclaimer: string;
  warnings: string[];
}

export interface FaceEnrolRequest {
  image_base64: string;
  canonical_person_id: number;
  image_label?: string | null;
  evidence_item_id?: number | null;
  make_primary?: boolean;
  capture_mode?: FaceCaptureMode;
  actor?: string | null;
}
export interface FaceRecord {
  person_face_embedding_id: number;
  model_version_id: number;
  model_name?: string | null;
  image_sha256: string;
  image_label?: string | null;
  bounding_box: Record<string, unknown>;
  detector_score?: number | null;
  quality_score?: number | null;
  is_primary: boolean;
  enrolment_source: string;
  enrolled_by_actor?: string | null;
  evidence_item_id?: number | null;
  is_archived: boolean;
  created_at?: string | null;
  sensitivity: string;
}
export interface FaceEnrolResponse {
  created: boolean;
  face: FaceRecord;
  canonical_person_id: number;
  gallery_face_count: number;
  detector_score?: number | null;
  quality?: number | null;
  warnings: string[];
}
export interface FaceListResponse {
  canonical_person_id: number;
  faces: FaceRecord[];
  model_name?: string | null;
  biometric: boolean;
}
export interface FaceDeleteResponse {
  archived: boolean;
  person_face_embedding_id: number;
  canonical_person_id?: number | null;
  gallery_face_count: number;
}

export interface FaceDecisionRequest {
  decision: FaceDecision;
  canonical_person_id?: number | null;
  /** Add the probe photo to that person's gallery (deliberate, off by default). */
  enrol_probe?: boolean;
  /** Identity already on the draft/case — a mismatch raises a review candidate. */
  existing_canonical_person_id?: number | null;
  note?: string | null;
  actor?: string | null;
}
export interface FaceDecisionResponse {
  probe_ref: string;
  decision: FaceDecision;
  canonical_person_id?: number | null;
  enrolled_face_id?: number | null;
  entity_resolution_candidate_id?: number | null;
  message: string;
  warnings: string[];
}

export interface FaceProbeTrailItem {
  probe_ref: string;
  actor?: string | null;
  actor_role?: string | null;
  origin?: string | null;
  capture_mode?: string | null;
  faces_detected: number;
  match_count: number;
  top_similarity?: number | null;
  top_canonical_person_id?: number | null;
  top_display_label?: string | null;
  top_public_ref?: string | null;
  decision: string;
  created_at?: string | null;
  latency_ms?: number | null;
  model_name?: string | null;
}
export interface FaceProbeTrailResponse {
  items: FaceProbeTrailItem[];
  total: number;
}
