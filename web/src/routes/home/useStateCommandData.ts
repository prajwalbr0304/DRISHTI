import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import { useScopeStore } from "@/stores/useScopeStore";

/* ============================================================================
   Extra Command Center hooks for the DGP / State Command board.

   Kept alongside useDashboardData rather than inside it: these back the state
   command KPI band only, and several are expensive enough to want their own
   staleTime. The generic dashboard hooks stay untouched so the IGP, SP,
   supervisor and analyst boards are unaffected.

   AGGREGATE ONLY. Every read below returns counts, ratios or queue depths — no
   case rows, no parties, no coordinates. That is a hard constraint of the seat
   (doc 01 §4.1 + §7), not an accident of what happened to be available.

   DISTRICT SCOPE, same three-way honesty as useDashboardData:
     server-side  /performance/overview takes district_id and confines it to the
                  caller's scope server-side, so the district joins the key.
     not at all   the backtest, the contract audit, the data-quality and
                  jurisdiction queues, patterns, communities and the
                  notification queues have no district dimension. They stay
                  state-wide and the cards say so via STATE_WIDE_NOTE.
   ========================================================================== */

/** Slow-moving reads: a route audit and a queue depth are not per-render data. */
const SLOW = { staleTime: 10 * 60_000, retry: false } as const;

/** Aggregate station/officer accountability — workload, ageing, chargesheet
 *  throughput, overdue reviews, load balance. The window must key the cache:
 *  the same scope over a different window is a different answer. */
export function useStatePerformance(windowDays = 90) {
  const districtId = useScopeStore((s) => s.districtId);
  return useQuery({
    queryKey: ["performance", "overview", districtId ?? null, null, windowDays],
    queryFn: ({ signal }) =>
      api.performance.overview(
        { district_id: districtId ?? undefined, window_days: windowDays },
        signal,
      ),
  });
}

/** Response-contract audit: how many routes actually declare + honour a response
 *  model. The board's own "are these numbers contract-checked" metric. */
export function useContractAudit() {
  return useQuery({
    queryKey: ["explain", "contract"],
    queryFn: ({ signal }) => api.explain.contract(signal),
    ...SLOW,
  });
}

/** Staging data-quality queue. Deliberately UNFILTERED: the service computes
 *  `total` against the status filter but `by_severity` always across the whole
 *  table, so filtering here would print a total and a severity split that
 *  disagree. One row is fetched because only the aggregates are used. */
export function useDataQualitySummary() {
  return useQuery({
    queryKey: ["intake", "quality", "summary"],
    queryFn: ({ signal }) => api.intake.qualityIssues({ page_size: 1 }, signal),
    ...SLOW,
  });
}

/** Boundary versions + the open containment-issue count. Shares the Live Map's
 *  cache entry — same key, same request. */
export function useJurisdictionFreshness() {
  return useQuery({
    queryKey: ["geo", "jurisdiction", "freshness"],
    queryFn: ({ signal }) => api.geo.jurisdictionFreshness(signal),
    ...SLOW,
  });
}

/** Communities ranked by size, with a known-gang cross-reference. `limit` is a
 *  hard cap on the rows returned, so the card must say "largest N". */
export const COMMUNITY_LIMIT = 200;
export function useCommunities() {
  return useQuery({
    queryKey: ["graph", "communities", "list", COMMUNITY_LIMIT],
    queryFn: ({ signal }) => api.graph.communitiesList(COMMUNITY_LIMIT, signal),
    ...SLOW,
  });
}

/** Open work tasks. `total` is a server-side COUNT honouring the status filter,
 *  and /notifications/tasks is not actor-scoped, so this is the whole open
 *  queue rather than only the tasks assigned to this seat. */
export function useOpenTasks() {
  return useQuery({
    queryKey: ["notifications", "tasks", "open"],
    queryFn: ({ signal }) => api.notifications.tasks({ status: "open", limit: 1 }, signal),
    refetchInterval: 120_000,
  });
}


/** Aggregate court outcomes — conviction rate and the disposal mix.
 *
 *  The conviction-rate card was `pending` until this existed. The blocker was not
 *  the data: CaseDisposition has carried convicted / acquitted / B-report /
 *  C-report with an IsFinal flag all along. It was that computing a rate meant
 *  reading case rows, which is exactly what this aggregate-only seat must not do.
 *  /outcomes/overview answers it as counts instead.
 *
 *  Confined server-side to the caller's seat, so the district joins the key. */
export function useOutcomes(windowDays?: number) {
  const districtId = useScopeStore((s) => s.districtId);
  return useQuery({
    queryKey: ["outcomes", "overview", districtId ?? null, windowDays ?? null],
    queryFn: ({ signal }) =>
      api.outcomes.overview(
        windowDays ? { window_days: windowDays } : {},
        signal,
      ),
    ...SLOW,
  });
}


/** Soonest scheduled hearings for the seat, for the "Next court date" card.
 *
 *  Scoped SERVER-side from the seat's posting, so there is no district in the query
 *  key: the same URL returns a station's seven hearings to an SHO and the state's
 *  10,322 to a DGP. Kept out of the client-side-narrowed group for that reason. */
export function useNextHearings(limit = 10) {
  return useQuery({
    queryKey: ["casework", "hearings", "next", limit],
    queryFn: ({ signal }) => api.casework.nextHearings({ limit }, signal),
    ...SLOW,
  });
}


/** Count KPIs from the mv_case_daily rollup, with the live path as a fallback.
 *
 *  The rollup answers the same questions as /performance/overview in one query over
 *  a much smaller table, which is what makes a board affordable for ~11,800 seats
 *  rather than ten demo logins.
 *
 *  It can legitimately DECLINE (503) when its policy attestation is not current —
 *  the view embeds the fail-closed eligibility predicate, so it goes stale when a
 *  CaseVersion changes. `retry: false` because a refusal is a decision, not a
 *  transient error, and retrying it just delays the fallback.
 *
 *  Callers should treat `undefined` as "use the live figure", not as "no data":
 *  `useKpiValues` already holds the live /performance response for the cards the
 *  rollup cannot answer, so the fallback costs nothing extra. */
export function useDashboardRollup(windowDays = 90) {
  const districtId = useScopeStore((s) => s.districtId);
  return useQuery({
    queryKey: ["dashboard", "summary", districtId ?? null, windowDays],
    queryFn: ({ signal }) =>
      api.dashboard.summary(
        { district_id: districtId ?? undefined, window_days: windowDays }, signal),
    ...SLOW,
    retry: false,
  });
}
