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

/** One district in the league table.
 *
 *  The denominators travel with the count on purpose: `open_cases` on its own
 *  invites a ranking, and `stations` / `officers` / `new_cases` are what make it
 *  readable as workload instead. */
export interface DistrictRow {
  district_id: number;
  district_name?: string | null;
  total_cases: number;
  open_cases: number;
  new_cases: number;
  overdue: number;
  stations: number;
  officers: number;
  chargesheets_filed: number;
  /** Filings over new cases in the same window. null — never 0 — when the window
   *  held no new cases, since a district that registered nothing has no rate. */
  chargesheet_rate?: number | null;
  open_per_station?: number | null;
}

export interface DistrictPerformance {
  scope: { district_ids?: number[] | null };
  as_of?: string | null;
  data_age_days?: number | null;
  stale: boolean;
  empty: boolean;
  window_days: number;
  districts: DistrictRow[];
  totals: {
    districts_compared?: number;
    total_cases?: number;
    open_cases?: number;
    new_cases?: number;
    overdue?: number;
    median_open_per_district?: number | null;
  };
  limitations: string[];
  dataset: string;
}

export const performanceApi = {
  overview: (params: { unit_id?: number; district_id?: number; window_days?: number } = {}, s?: AbortSignal) =>
    apiClient.get<PerformanceOverview>("/performance/overview", params, s),

  /** Districts in the caller's scope, side by side — the range and wing league
   *  table. Confined server-side, so a DIG gets the districts of their range and
   *  an unposted seat gets none. */
  districts: (params: { district_id?: number; window_days?: number } = {}, s?: AbortSignal) =>
    apiClient.get<DistrictPerformance>("/performance/districts", params, s),
};


/* ============================================================================
   Rollup-backed dashboard summary (/dashboard/summary).

   The count KPIs served from the mv_case_daily materialized view rather than the
   base tables. /performance/overview costs seven sequential aggregates over
   CaseMaster JOIN Unit JOIN CaseStatusMaster; unfiltered, each is a full scan.

   NOT a drop-in replacement: the rollup carries no officer or chargesheet linkage,
   so officer load and chargesheet throughput stay on /performance/overview.

   A 503 here is a REFUSAL, not a fault. The view's definition embeds the
   fail-closed analytics-eligibility predicate, so it goes stale when a CaseVersion
   changes; if its recorded policy attestation is no longer current the server
   declines rather than serving figures computed under a superseded policy.
   ========================================================================== */

export interface DashboardSummary {
  scope: {
    district_ids?: number[] | null;
    unit_id?: number | null;
    crime_head_ids?: number[] | null;
  };
  /** Always "mv_case_daily". Named so a caller comparing this against
   *  /performance/overview can see the two read different sources. */
  source: string;
  as_of?: string | null;
  data_age_days?: number | null;
  stale: boolean;
  empty: boolean;
  window_days: number;
  window_start?: string | null;
  /** Warnings about the DATA, distinct from the standing `limitations`. Populated
   *  when the window opens inside a sparse tail, which makes the window figure
   *  unrepresentative while leaving the totals sound. */
  data_notes: string[];
  totals: {
    total_cases?: number;
    open_cases?: number;
    closed_cases?: number;
    new_cases_in_window?: number;
    overdue_open?: number;
    overdue_threshold_days?: number;
    heinous_cases?: number;
    units_in_scope?: number;
    districts_in_scope?: number;
  };
  ageing: AgeBucket[];
  /** Refresh time and policy attestation of the rollup these figures came from. */
  rollup: {
    registered?: boolean;
    refreshed_at?: string | null;
    policy_version?: string | null;
    policy_sha256?: string | null;
    rollup_rows?: number | null;
    refresh_seconds?: number | null;
    refreshed_by?: string | null;
  };
  limitations: string[];
  dataset: string;
}

export const dashboardApi = {
  /** Count KPIs and open-case ageing for the caller's scope, from the rollup. */
  summary: (params: { district_id?: number; window_days?: number } = {},
            s?: AbortSignal) =>
    apiClient.get<DashboardSummary>("/dashboard/summary", params, s),
};
