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
