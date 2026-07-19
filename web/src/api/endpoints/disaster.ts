import { apiClient } from "@/api/client";
import type { AiResult } from "@/api/contracts";

/* ============================================================================
   Emergency Response (Prompt 17) API client. Reads are open to any
   authenticated role (crime roles read-only); writes require the synthetic
   disaster_coordinator and are scoped to the assigned district. Warning
   approval / dispatch / evacuation-plan approval require confirm=true.

   The coordinator's assigned district is carried as a header so the server-side
   scope check applies (display/scoping only — never authentication).
   ========================================================================== */

export interface HazardType {
  hazard_type_id: number;
  code: string;
  name: string;
  category?: string | null;
  default_lead_time_hours?: number | null;
  active: boolean;
}

export interface HazardEvent {
  hazard_event_id: number;
  hazard_code: string;
  status: string;
  severity: string;
  district_id?: number | null;
  unit_id?: number | null;
  geojson: Record<string, unknown>;
  centroid?: [number, number] | null;
  onset_at?: string | null;
  predicted_peak_at?: string | null;
  source?: string | null;
  source_version?: string | null;
  description?: string | null;
  version: number;
  created_at?: string | null;
}

export interface HazardRiskZone {
  hazard_risk_zone_id: number;
  hazard_code: string;
  zone_kind: string;
  name?: string | null;
  district_id?: number | null;
  geojson: Record<string, unknown>;
  centroid?: [number, number] | null;
  risk_level: string;
  score?: number | null;
  factors: Record<string, unknown>;
  is_active: boolean;
}

export interface HazardPrediction {
  hazard_prediction_id: number;
  hazard_code: string;
  hazard_event_id?: number | null;
  model_version_label?: string | null;
  feature_snapshot_id?: string | null;
  district_id?: number | null;
  geojson: Record<string, unknown>;
  forecast_start?: string | null;
  forecast_end?: string | null;
  horizon_hours?: number | null;
  data_as_of?: string | null;
  probability?: number | null;
  predicted_severity?: string | null;
  expected_impact: Record<string, unknown>;
  confidence?: number | null;
  factors: Record<string, unknown>;
  baseline_comparison: Record<string, unknown>;
  quality_state: string;
  superseded_by_id?: number | null;
  created_at?: string | null;
}

export interface FeedFreshness {
  feed_code: string;
  provider?: string | null;
  connector_kind: string;
  external_access_required: boolean;
  freshness_sla_minutes?: number | null;
  last_observed_at?: string | null;
  last_run_at?: string | null;
  age_minutes?: number | null;
  status: string;
  licence?: string | null;
  attribution?: string | null;
}

export interface HydroMetReading {
  hydromet_reading_id: number;
  station_code: string;
  source_agency?: string | null;
  metric_type: string;
  value?: number | null;
  unit?: string | null;
  lon?: number | null;
  lat?: number | null;
  district_id?: number | null;
  observed_at?: string | null;
  received_at?: string | null;
  quality_flag: string;
}

export interface Resource {
  resource_id: number;
  resource_type: string;
  name: string;
  quantity: number;
  unit?: string | null;
  home_unit_id?: number | null;
  lon?: number | null;
  lat?: number | null;
  district_id?: number | null;
  capacity?: number | null;
  capabilities: string[];
  status: string;
  version: number;
}

export interface Shelter {
  relief_shelter_id: number;
  name: string;
  lon?: number | null;
  lat?: number | null;
  district_id?: number | null;
  capacity: number;
  current_occupancy: number;
  facilities: string[];
  status: string;
  version: number;
}

export interface Allocation {
  resource_allocation_id?: number | null;
  hazard_event_id?: number | null;
  resource_id?: number | null;
  resource_name?: string | null;
  resource_type?: string | null;
  target_zone_id?: number | null;
  quantity_allocated: number;
  status: string;
  score?: number | null;
  reason: Record<string, unknown>;
  district_id?: number | null;
  proposed_at?: string | null;
  approved_at?: string | null;
  dispatched_at?: string | null;
  enroute_at?: string | null;
  onsite_at?: string | null;
  released_at?: string | null;
}

export interface EvacRoute {
  evacuation_route_id?: number | null;
  hazard_event_id?: number | null;
  from_zone_id?: number | null;
  to_shelter_id?: number | null;
  geojson: Record<string, unknown>;
  distance_km?: number | null;
  est_minutes?: number | null;
  road_graph_version?: string | null;
  hazard_exclusion_version?: string | null;
  status: string;
  notes?: string | null;
}

export interface DisasterAlert {
  alert_id: number;
  alert_type: string;
  severity: string;
  title: string;
  message?: string | null;
  hazard_event_id?: number | null;
  district_id?: number | null;
  status: string;
  confidence?: number | null;
  freshness?: string | null;
  synthetic: boolean;
  acknowledged_by?: string | null;
  created_at?: string | null;
}

export interface ResponseTask {
  response_task_id: number;
  response_plan_id: number;
  title: string;
  sequence: number;
  assigned_to_actor?: string | null;
  status: string;
  due_at?: string | null;
  completed_at?: string | null;
}

export interface ResponsePlan {
  response_plan_id: number;
  hazard_event_id?: number | null;
  hazard_code: string;
  title: string;
  template_code?: string | null;
  status: string;
  district_id?: number | null;
  tasks: ResponseTask[];
}

export interface SituationOverview {
  generated_at: string;
  active_hazards: number;
  open_alerts: number;
  low_confidence_warnings: number;
  readiness: Record<string, number>;
  unavailable_resources: number;
  open_tasks: number;
  feed_freshness: FeedFreshness[];
  stale_feeds: number;
  hazards: HazardEvent[];
}

export interface ForecastRunResponse {
  result: AiResult;
  prediction: HazardPrediction;
  baseline_comparison: Record<string, unknown>;
  escalation?: string | null;
  event_proposal_id?: number | null;
}

export interface MutationResult {
  ok: boolean;
  id?: number | null;
  kind?: string;
  status?: string | null;
  version?: number | null;
  idempotent_replay?: boolean;
}

export interface AllocationProposal {
  hazard_event_id: number;
  optimizer: string;
  proposals: Allocation[];
  unmet: Record<string, number>;
  reasons: string[];
  comparison: Record<string, unknown>;
}

const q = (params: Record<string, unknown>) => {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) out[k] = v as never;
  return out;
};

export const disasterApi = {
  hazardTypes: (signal?: AbortSignal) =>
    apiClient.get<{ hazard_types: HazardType[] }>("/disaster/hazard-types", undefined, signal),
  overview: (districtId?: number, signal?: AbortSignal) =>
    apiClient.get<SituationOverview>("/disaster/overview", q({ district_id: districtId }), signal),
  events: (params: { status?: string; district_id?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ events: HazardEvent[] }>("/disaster/events", q(params), signal),
  zones: (params: { hazard_code?: string; district_id?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ zones: HazardRiskZone[] }>("/disaster/zones", q(params), signal),
  predictions: (params: { hazard_code?: string; district_id?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ predictions: HazardPrediction[] }>("/disaster/predictions", q(params), signal),
  readings: (params: { district_id?: number; metric?: string } = {}, signal?: AbortSignal) =>
    apiClient.get<{ readings: HydroMetReading[] }>("/disaster/readings", q(params), signal),
  feedFreshness: (signal?: AbortSignal) =>
    apiClient.get<{ feeds: FeedFreshness[] }>("/disaster/feeds/freshness", undefined, signal),
  resources: (params: { district_id?: number; status?: string } = {}, signal?: AbortSignal) =>
    apiClient.get<{ resources: Resource[] }>("/disaster/resources", q(params), signal),
  shelters: (params: { district_id?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ shelters: Shelter[] }>("/disaster/shelters", q(params), signal),
  allocations: (params: { event_id?: number; district_id?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ allocations: Allocation[] }>("/disaster/allocations", q(params), signal),
  routes: (params: { event_id?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ routes: EvacRoute[] }>("/disaster/routes", q(params), signal),
  alerts: (params: { district_id?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ alerts: DisasterAlert[] }>("/disaster/alerts", q(params), signal),
  plans: (params: { district_id?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ plans: ResponsePlan[] }>("/disaster/plans", q(params), signal),
  plan: (planId: number, signal?: AbortSignal) =>
    apiClient.get<ResponsePlan>(`/disaster/plans/${planId}`, undefined, signal),
  validate: (hazardCode = "flood", signal?: AbortSignal) =>
    apiClient.get<Record<string, unknown>>("/disaster/forecast/validate",
      { hazard_code: hazardCode }, signal),

  // writes (coordinator)
  seed: () => apiClient.post<{ seeded: Record<string, unknown> }>("/disaster/demo/seed"),
  ingestFeed: (feedCode: string, readings?: unknown[]) =>
    apiClient.post<Record<string, unknown>>(`/disaster/feeds/${feedCode}/ingest`,
      readings ? { readings } : undefined),
  runForecast: (body: { hazard_code: string; district_id: number; horizon_hours?: number;
                        data_as_of?: string; create_event_proposal?: boolean }) =>
    apiClient.post<ForecastRunResponse>("/disaster/forecast/run", body),
  transitionEvent: (eventId: number, status: string) =>
    apiClient.post<MutationResult>(`/disaster/events/${eventId}/transition`, undefined, { status }),
  proposeAlert: (body: { hazard_event_id: number; alert_type: string; severity?: string;
                        title: string; message?: string }) =>
    apiClient.post<MutationResult>("/disaster/alerts/propose", body),
  approveAlert: (alertId: number) =>
    apiClient.post<MutationResult>(`/disaster/alerts/${alertId}/approve`, undefined, { confirm: true }),
  proposeAllocation: (body: { hazard_event_id: number; required: Record<string, number>;
                             max_distance_km?: number; optimizer?: string }) =>
    apiClient.post<AllocationProposal>("/disaster/allocations/propose", body),
  transitionAllocation: (allocId: number, status: string, confirm = true) =>
    apiClient.request<MutationResult>(`/disaster/allocations/${allocId}/transition`,
      { method: "POST", params: { status }, body: { confirm } }),
  proposeRoute: (body: { hazard_event_id: number; from_zone_id?: number; to_shelter_id?: number }) =>
    apiClient.post<EvacRoute>("/disaster/routes/propose", body),
  selectRoute: (routeId: number) =>
    apiClient.post<MutationResult>(`/disaster/routes/${routeId}/select`, undefined, { confirm: true }),
  createPlan: (body: { hazard_code: string; hazard_event_id?: number; title: string; district_id?: number }) =>
    apiClient.post<ResponsePlan>("/disaster/plans", body),
  patchTask: (taskId: number, body: { status?: string; assigned_to_actor?: string; due_at?: string }) =>
    apiClient.request<MutationResult>(`/disaster/tasks/${taskId}`, { method: "PATCH", body }),
};
