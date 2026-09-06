import { apiClient } from "@/api/client";

/* ============================================================================
   Aggregate court outcomes.

   Backs the conviction-rate card, which shipped in an honest `pending` state
   because the underlying data was reachable only per case — and the seats that
   need the metric (state and wing command) are precisely the ones that must not
   read case rows. This endpoint answers it as counts, so they can.
   ========================================================================== */

export interface DispositionCount {
  disposition_type: string;
  label: string;
  count: number;
  share_of_disposed: number | null;
}

export interface OutcomesOverview {
  scope: {
    district_ids: number[] | null;
    unit_id: number | null;
    crime_head_ids: number[] | null;
  };

  /** Convictions / (convictions + acquittals), as a 0..1 fraction.
   *
   *  null — not zero — when nothing reached a verdict: "no verdicts yet" is a
   *  different statement from "a 0% conviction rate". */
  conviction_rate: number | null;
  conviction_rate_denominator: string;
  convicted: number;
  acquitted: number;
  verdicts: number;

  /** Cases reaching a verdict as a share of all finally-disposed cases. A high
   *  conviction rate on few prosecutions is a different picture from the same
   *  rate on many, so both are reported. */
  prosecution_rate: number | null;
  prosecution_rate_denominator: string;
  total_disposed: number;
  breakdown: DispositionCount[];

  as_of: string | null;
  data_age_days: number | null;
  stale: boolean;
  empty: boolean;
  window_days: number | null;
  limitations: string[];
  dataset: string;
}

export const outcomesApi = {
  /** Conviction rate + disposal mix, confined server-side to the caller's seat. */
  overview: (params: { window_days?: number } = {}, s?: AbortSignal) =>
    apiClient.get<OutcomesOverview>("/outcomes/overview", { ...params }, s),
};
