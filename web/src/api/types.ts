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
}
export interface SimilarResponse {
  result: AiResult;
  query_case_id: number;
  model_name: string;
  model_version_id: number;
  corpus_size: number;
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
  nodes: GraphNode[];
  edges: GraphEdge[];
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
  scatter: ScatterSeries[];
  narrative: NarrativeCard;
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
export interface ForecastRunResponse {
  result: AiResult;
  head_id?: number | null;
  horizon_days: number;
  prediction_start?: string | null;
  prediction_end?: string | null;
  layers: LayerRun[];
  alerts_written: number;
  fused: FusedDistrict[];
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

export interface CaseCore {
  case_id: number;
  crime_no?: string | null;
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

/* ------------------------- Map: raw incident points (15f) ----------------- */
export interface PointFeature {
  case_id: number;
  lon: number;
  lat: number;
  crime_head_id?: number | null;
  crime_group?: string | null;
  date?: string | null;
  hour?: number | null;
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
}
export interface CaseLinksResponse {
  source_case_id: number;
  source_lon?: number | null;
  source_lat?: number | null;
  source_crime_no?: string | null;
  count: number;
  links: CaseLinkNode[];
}
