import { apiClient } from "@/api/client";

/* Prompt 20 Part C — supervisor station/officer operational performance
   (services/ml/app/performance). Supervisory view; scope confined server-side.
   Distinct from the ML workload-band prediction (api.workload). */

export interface AgeBucket {
  bucket: string;
  count: number;
}
export interface StationRow {
  unit_id: number;
  unit_name?: string | null;
  district_name?: string | null;
  total: number;
  open_cases: number;
  new_cases: number;
  overdue: number;
}
export interface PerformanceOverview {
  scope: { unit_id?: number | null; district_id?: number | null };
  as_of?: string | null;
  data_age_days?: number | null;
  stale: boolean;
  empty: boolean;
  window_days: number;
  totals: {
    total_cases?: number;
    active_workload?: number;
    new_cases_in_window?: number;
    overdue_reviews?: number;
    overdue_threshold_days?: number;
    stations_in_scope?: number;
    officers_in_scope?: number;
    disposed_or_closed?: number;
  };
  ageing: AgeBucket[];
  chargesheet: {
    filed_in_window?: number;
    new_cases_in_window?: number;
    throughput_ratio?: number | null;
    throughput_ratio_denominator?: string;
    median_days_to_chargesheet?: number | null;
    avg_days_to_chargesheet?: number | null;
  };
  officers: {
    officers_with_open_cases?: number;
    median_open_per_officer?: number;
    p90_open_per_officer?: number;
    max_open_per_officer?: number;
    heavy_load_officers?: number;
    heavy_load_threshold?: number;
    note?: string;
  };
  workload_balance: {
    stations_compared?: number;
    stations_in_scope?: number;
    median_open?: number;
    max_open?: number;
    total_open_across_stations?: number;
    imbalance_ratio_max_over_median?: number | null;
    note?: string;
  };
  stations: StationRow[];
  limitations: string[];
  dataset: string;
}

export const performanceApi = {
  overview: (params: { unit_id?: number; district_id?: number; window_days?: number } = {}, s?: AbortSignal) =>
    apiClient.get<PerformanceOverview>("/performance/overview", params, s),
};
