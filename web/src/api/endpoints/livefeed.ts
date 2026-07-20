import { apiClient } from "@/api/client";

/* Prompt 20 Part E — Live Command Center committed-FIR flow (services/ml/app/livefeed).
   A committed FIR refreshes aggregate projections idempotently; it never rescores
   a person or auto-dispatches staff. Locally polled; Catalyst Signal in Prompt 23. */

export interface ProjectionState {
  last_processed_ts?: string | null;
  last_success_ts?: string | null;
  last_failure_ts?: string | null;
  processed_count: number;
  freshness_seconds?: number | null;
}
export interface FreshnessResponse {
  transport: string;
  event_type: string;
  processed_count: number;
  duplicate_suppressed: number;
  projections: Record<string, ProjectionState>;
  recent: Array<{
    case_id: number; district_id?: number | null; status: string;
    source_ts?: string | null; processed_ts: string; signal_published: boolean;
  }>;
  guarantees: { person_rescored: boolean; auto_dispatch: boolean };
}
export interface ProjectResponse {
  district_id: number;
  as_of?: string | null;
  district_statistic: { before: number; after: number; delta: number };
  supervisor_workload: { before: number; after: number; delta: number; note?: string };
  hotspot_near_repeat: { prior_similar_in_window: number; near_repeat_eligible_after: boolean; window_days: number };
  guarantees: { person_rescored: boolean; auto_dispatch: boolean };
  note: string;
}

export const livefeedApi = {
  freshness: (s?: AbortSignal) => apiClient.get<FreshnessResponse>("/livefeed/freshness", undefined, s),
  project: (body: { district_id: number; crime_head_id?: number; station_id?: number }, s?: AbortSignal) =>
    apiClient.post<ProjectResponse>("/livefeed/project", body, undefined, s),
};
