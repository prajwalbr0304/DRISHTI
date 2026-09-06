import { apiClient } from "@/api/client";

/* ============================================================================
   CCTV monitoring API client — the live watch wall.

   The pipeline this mirrors, and why the calls are shaped this way:

     video analytics  -> proposeAlert   (status 'proposed', never actionable)
     analyst          -> confirmAlert   (confirm=true, else the server returns 428)
                      or dismissAlert   (with a reason from a closed list)
     system           -> dispatch proposal (nearest responder, ranked + explained)
     analyst          -> transitionDispatch('dispatched', confirm=true, else 428)

   Confirming an alert and dispatching a unit are two SEPARATE confirmations on
   purpose. `confirmAlert` says "this detection is real"; it may return a dispatch
   PROPOSAL, but nothing is sent until `transitionDispatch` is called with its own
   confirmation. Reads are open to any authenticated role; writes are role-gated
   and district-scoped server-side.
   ========================================================================== */

/** What this deployment can actually do. Rendered verbatim in the UI so a viewer
    is never left assuming real frame inference is running when it is not. */
export interface CctvCapability {
  cctv_enabled: boolean;
  detector_kind: "synthetic_replay" | "external_analytics";
  detector_label: string;
  detector_selector: string;
  runs_frame_inference_in_service: boolean;
  external_ingest_enabled: boolean;
  analysis_window_seconds: number;
  low_confidence_threshold: number;
  min_alert_confidence: number;
  detection_types: string[];
  auto_dispatch: boolean;
  requires_human_confirmation: boolean;
  note: string;
}

export type CameraStatus = "online" | "degraded" | "offline" | "maintenance";
export type StreamKind = "hls" | "mp4_loop" | "image_snapshot" | "none";
export type AlertStatus = "proposed" | "confirmed" | "dismissed" | "dispatched" | "resolved";
export type DispatchStatus =
  | "proposed" | "dispatched" | "acknowledged" | "enroute" | "onsite" | "closed" | "cancelled";

export interface CctvCamera {
  camera_id: number;
  code: string;
  name: string;
  location_label?: string | null;
  lon: number;
  lat: number;
  bearing_degrees?: number | null;
  fov_degrees?: number | null;
  district_id?: number | null;
  unit_id?: number | null;
  stream_kind: StreamKind;
  stream_url?: string | null;
  poster_url?: string | null;
  status: CameraStatus;
  analytics_enabled: boolean;
  detector_profile?: string | null;
  last_heartbeat_at?: string | null;
  last_analysed_at?: string | null;
  notes?: string | null;
  version: number;
  created_at?: string | null;
  updated_at?: string | null;
  /** Rolled up server-side so the map can colour a marker without N+1 reads. */
  open_alert_count: number;
  top_open_severity?: string | null;
}

export interface CctvResponder {
  patrol_unit_id: number;
  code: string;
  name: string;
  kind: "station" | "patrol_vehicle" | "traffic_patrol" | "control_room";
  unit_id?: number | null;
  district_id?: number | null;
  lon: number;
  lat: number;
  status: "available" | "engaged" | "offline";
  contact_label?: string | null;
  capabilities: string[];
  version: number;
}

/** Normalised to the frame ([0,1]) so the overlay is resolution-independent. */
export interface CctvBox {
  x: number;
  y: number;
  w: number;
  h: number;
  label?: string | null;
  score?: number | null;
}

export interface CctvDetection {
  cctv_detection_id: number;
  camera_id: number;
  camera_name?: string | null;
  detection_type: string;
  detection_label?: string | null;
  confidence: number;
  severity: string;
  object_count?: number | null;
  boxes: CctvBox[];
  attributes: Record<string, unknown>;
  /** Provenance: a synthetic-replay detection must never read as a model inference. */
  detector_kind: string;
  detector_label: string;
  frame_object_key?: string | null;
  clip_object_key?: string | null;
  detected_at?: string | null;
  received_at?: string | null;
  window_seconds?: number | null;
  quality_flag: string;
  district_id?: number | null;
  lon?: number | null;
  lat?: number | null;
}

export interface CctvAlert {
  cctv_alert_id: number;
  cctv_detection_id: number;
  camera_id: number;
  camera_code?: string | null;
  camera_name?: string | null;
  stream_kind?: StreamKind | null;
  stream_url?: string | null;
  poster_url?: string | null;
  alert_type: string;
  alert_label?: string | null;
  severity: string;
  title: string;
  message?: string | null;
  confidence: number;
  status: AlertStatus;
  reviewed_by_actor?: string | null;
  reviewed_at?: string | null;
  review_note?: string | null;
  dismiss_reason?: string | null;
  district_id?: number | null;
  lon?: number | null;
  lat?: number | null;
  location_label?: string | null;
  nearest_unit_id?: number | null;
  detector_kind?: string | null;
  detector_label?: string | null;
  quality_flag?: string | null;
  object_count?: number | null;
  synthetic: boolean;
  version: number;
  created_at?: string | null;
  updated_at?: string | null;
  age_seconds?: number | null;
  dispatch_count: number;
  active_dispatch_status?: DispatchStatus | null;
}

export interface CctvDispatch {
  cctv_dispatch_id: number;
  cctv_alert_id: number;
  patrol_unit_id?: number | null;
  unit_id?: number | null;
  unit_name: string;
  unit_kind?: string | null;
  distance_km: number;
  eta_minutes?: number | null;
  score?: number | null;
  /** Explainability payload: distance, geometry source, ETA assumption, rule. */
  reason: {
    distance_km?: number;
    eta_minutes?: number;
    geometry_source?: string;
    eta_assumptions_version?: string;
    avg_speed_kmh?: number;
    search_radius_km?: number;
    responder_status?: string;
    responder_kind?: string;
    rule?: string;
    [key: string]: unknown;
  };
  status: DispatchStatus;
  proposed_by_actor?: string | null;
  approved_by_actor?: string | null;
  district_id?: number | null;
  proposed_at?: string | null;
  dispatched_at?: string | null;
  acknowledged_at?: string | null;
  enroute_at?: string | null;
  onsite_at?: string | null;
  closed_at?: string | null;
  notes?: string | null;
  version: number;
}

export interface CctvResponderCandidate {
  unit_id?: number | null;
  patrol_unit_id?: number | null;
  unit_name?: string | null;
  unit_kind?: string | null;
  code?: string | null;
  status?: string | null;
  distance_km: number;
  eta_minutes?: number | null;
  score?: number | null;
  lon?: number | null;
  lat?: number | null;
  geometry_source?: string;
}

export interface CctvDispatchProposal {
  cctv_alert_id: number;
  dispatch: CctvDispatch | null;
  alternatives: CctvResponderCandidate[];
  /** 'postgis_knn' (canonical station geometry) or 'datastore_haversine'. */
  geometry_source: string;
  considered: number;
  max_distance_km: number;
  eta_assumptions_version: string;
  /** Set when the PostGIS path was unavailable and the fallback was used. */
  fallback_reason?: string | null;
  /** Set when no responder was in range — never rounded up to a distant one. */
  detail?: string | null;
}

export interface CctvActivityEntry {
  cctv_activity_id: number;
  subject_type: string;
  subject_id: string;
  actor: string;
  action: string;
  diff: Record<string, unknown>;
  created_at?: string | null;
}

export interface CctvAlertDetail {
  alert: CctvAlert;
  detection: CctvDetection | null;
  camera: CctvCamera | null;
  dispatches: CctvDispatch[];
  activity: CctvActivityEntry[];
  nearby_cameras: CctvCamera[];
}

export interface CctvCameraHealth {
  total: number;
  online: number;
  degraded: number;
  offline: number;
  maintenance: number;
  analytics_enabled: number;
}

export interface CctvOverview {
  cameras: CctvCameraHealth;
  pending_review: number;
  confirmed_awaiting_dispatch: number;
  dispatched_active: number;
  dismissed_today: number;
  low_confidence_pending: number;
  alerts_last_hour: number;
  by_type: Record<string, number>;
  capability: CctvCapability;
  district_id?: number | null;
}

export interface CctvAnalyticsRun {
  cameras_analysed: number;
  detections_created: number;
  detections_suppressed: number;
  alerts_proposed: number;
  below_alert_threshold: number;
  detector_kind: string;
  detector_label: string;
  alerts: CctvAlert[];
  note: string;
}

export interface CctvDetectionType {
  code: string;
  label: string;
  default_severity: string;
}

export interface CctvMutationResult {
  ok: boolean;
  id?: number | null;
  kind?: string;
  status?: string | null;
  version?: number | null;
  idempotent_replay?: boolean;
  /** Present on confirmAlert: the nearest-responder proposal, NOT a dispatch. */
  dispatch_proposal?: CctvDispatchProposal;
}

export type CctvDismissReason =
  | "false_positive" | "duplicate" | "already_handled" | "not_actionable"
  | "poor_visibility" | "other";

const q = (params: Record<string, unknown>) => {
  const out: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) out[k] = v as never;
  return out;
};

export const cctvApi = {
  // --- reads ---------------------------------------------------------------
  capability: (signal?: AbortSignal) =>
    apiClient.get<CctvCapability>("/cctv/capability", undefined, signal),
  detectionTypes: (signal?: AbortSignal) =>
    apiClient.get<{ detection_types: CctvDetectionType[]; dismiss_reasons: string[] }>(
      "/cctv/detection-types", undefined, signal),
  overview: (districtId?: number, signal?: AbortSignal) =>
    apiClient.get<CctvOverview>("/cctv/overview", q({ district_id: districtId }), signal),
  cameras: (params: { district_id?: number; status?: string; with_alerts_only?: boolean } = {},
            signal?: AbortSignal) =>
    apiClient.get<{ cameras: CctvCamera[] }>("/cctv/cameras", q(params), signal),
  camera: (cameraId: number, signal?: AbortSignal) =>
    apiClient.get<CctvCamera>(`/cctv/cameras/${cameraId}`, undefined, signal),
  responders: (params: { district_id?: number; status?: string } = {}, signal?: AbortSignal) =>
    apiClient.get<{ responders: CctvResponder[] }>("/cctv/responders", q(params), signal),
  nearestResponders: (params: { lon: number; lat: number; district_id?: number;
                                max_distance_km?: number; limit?: number },
                      signal?: AbortSignal) =>
    apiClient.get<{ candidates: CctvResponderCandidate[]; geometry_source: string;
                    considered: number; max_distance_km: number;
                    eta_assumptions_version: string; fallback_reason?: string | null }>(
      "/cctv/responders/nearest", q(params), signal),
  detections: (params: { camera_id?: number; detection_type?: string; district_id?: number;
                         limit?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ detections: CctvDetection[] }>("/cctv/detections", q(params), signal),
  alerts: (params: { status?: AlertStatus; district_id?: number; camera_id?: number;
                     detection_type?: string; min_confidence?: number; limit?: number } = {},
           signal?: AbortSignal) =>
    apiClient.get<{ alerts: CctvAlert[] }>("/cctv/alerts", q(params), signal),
  alert: (alertId: number, signal?: AbortSignal) =>
    apiClient.get<CctvAlertDetail>(`/cctv/alerts/${alertId}`, undefined, signal),
  dispatches: (params: { alert_id?: number; status?: DispatchStatus; district_id?: number;
                         limit?: number } = {}, signal?: AbortSignal) =>
    apiClient.get<{ dispatches: CctvDispatch[] }>("/cctv/dispatch", q(params), signal),
  activity: (limit = 100, signal?: AbortSignal) =>
    apiClient.get<{ activity: CctvActivityEntry[] }>("/cctv/activity", q({ limit }), signal),

  // --- writes --------------------------------------------------------------
  seed: () => apiClient.post<{ seeded: Record<string, number> }>("/cctv/demo/seed"),
  runAnalytics: (body: { camera_ids?: number[]; district_id?: number } = {}) =>
    apiClient.post<CctvAnalyticsRun>("/cctv/analytics/run", body),

  /** Human confirmation that the detection is real. The server requires the fresh
      confirmation and returns 428 without it, so `confirm` is always sent true. */
  confirmAlert: (alertId: number, body: { note?: string; propose_dispatch?: boolean;
                                          max_distance_km?: number } = {}) =>
    apiClient.post<CctvMutationResult>(
      `/cctv/alerts/${alertId}/confirm`,
      { confirm: true, propose_dispatch: body.propose_dispatch ?? true, ...body },
      { confirm: true }),

  /** Dismissal is the SAFE direction (it sends nobody), so it needs no fresh
      confirmation — but it does need a reason, which is the detector's only
      honest precision signal. */
  dismissAlert: (alertId: number, reason: CctvDismissReason, note?: string) =>
    apiClient.post<CctvMutationResult>(`/cctv/alerts/${alertId}/dismiss`, { reason, note }),

  proposeDispatch: (alertId: number, body: { max_distance_km?: number;
                                             patrol_unit_id?: number } = {}) =>
    apiClient.post<CctvDispatchProposal>(`/cctv/alerts/${alertId}/dispatch/propose`, body),

  /** `dispatched` is the consequential transition and carries its own fresh
      confirmation; the later status updates are just bookkeeping. */
  transitionDispatch: (dispatchId: number, status: DispatchStatus,
                       opts: { expectedVersion?: number; notes?: string } = {}) =>
    apiClient.request<CctvMutationResult>(`/cctv/dispatch/${dispatchId}/transition`, {
      method: "POST",
      params: { status },
      body: { confirm: true, expected_version: opts.expectedVersion, notes: opts.notes },
    }),
};
