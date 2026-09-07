import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { ScopeType } from "@/config/roles";

/* ============================================================================
   Hooks for the cards that are NOT operational crime measures: the platform
   tier (seats, imports, model registry, UI overrides), the station approval
   inbox, and the financial-intelligence counters.

   WHY THIS FILE EXISTS. Every one of these cards was declared in the KPI
   registry and bound to nothing, so it rendered the resolver's fallback: a
   "pending — no data binding" note written for whoever maintains the registry
   rather than for the officer reading the board. Four of the platform board's
   nine cards were that note. The endpoints existed the whole time.

   WHY THE HOOKS ARE GATED BY SCOPE. `useKpiValues` runs on EVERY board, and
   hooks cannot be called conditionally — so without a gate an SHO opening their
   station board would issue requests to /admin/models, /admin/ui-visibility,
   /org/seats and /imports/batches. Several of those answer 403 to a non-admin
   seat, which is correct behaviour that would surface as error cards on a board
   that never asked for them. `enabled` keeps the hook call unconditional and the
   REQUEST conditional, which is the distinction that matters.

   `retry: false` throughout: a 403 here is a decision, not a transient failure,
   and retrying it three times only delays the card settling.
   ========================================================================== */

const SLOW = { staleTime: 10 * 60_000, retry: false } as const;

/** Provisioned, active seats across the force. `page_size: 1` because only the
 *  server-side total is read — the seat DIRECTORY widget fetches its own page. */
export function useSeatCount(enabled: boolean) {
  return useQuery({
    queryKey: ["org", "seats", "count"],
    queryFn: ({ signal }) => api.org.seats({ page_size: 1, active_only: true }, signal),
    enabled,
    ...SLOW,
  });
}

/** Structured imports staged and awaiting commit or rollback.
 *
 *  `status: "staged"` is the whole point of the card: a committed or rolled-back
 *  batch is finished work, and counting it would turn a queue depth into a running
 *  total that only ever grows. */
export function useStagedImports(enabled: boolean) {
  return useQuery({
    queryKey: ["imports", "batches", "staged", "count"],
    queryFn: ({ signal }) =>
      api.imports.listBatches({ status: "staged", page_size: 1 }, signal),
    enabled,
    ...SLOW,
  });
}

/** Registered model versions, including retired ones. */
export function useModelRegistry(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "models", "count"],
    queryFn: ({ signal }) => api.admin.models(signal),
    enabled,
    ...SLOW,
  });
}

/** Per-role UI visibility overrides currently diverging from the registry
 *  defaults, across EVERY role.
 *
 *  Deliberately unfiltered by role, unlike `useUiVisibility`, which asks for the
 *  overrides that apply to the caller. The admin card answers a different question
 *  — "how far has this deployment drifted from the shipped defaults" — and asking
 *  it per-role would answer "how far has MY board drifted", which is nearly always
 *  zero and says nothing about the deployment. */
export function useUiOverrideCount(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "ui-visibility", "all"],
    queryFn: ({ signal }) => api.adminConsole.uiVisibility({}, signal),
    enabled,
    ...SLOW,
  });
}

/** Submitted FIR drafts awaiting approval, return or rejection.
 *
 *  Scoped server-side to the caller's station, so there is no district in the key:
 *  the same URL is one SHO's inbox and, to a platform seat, the force's. */
export function useReviewQueue(enabled: boolean) {
  return useQuery({
    queryKey: ["intake", "drafts", "submitted", "count"],
    queryFn: ({ signal }) =>
      api.intake.listDrafts({ status: "submitted", page_size: 1 }, signal),
    enabled,
    ...SLOW,
  });
}

/** Flagged transactions, with the per-reason split.
 *
 *  ONE request serves two cards. The response carries `total` and a `by_reason`
 *  histogram, so "flagged transactions" and "circular flows" are two readings of
 *  the same payload rather than two queries — and they cannot disagree, which they
 *  could if the circular count were fetched separately with its own reason filter. */
export function useFlaggedFinance(enabled: boolean) {
  return useQuery({
    queryKey: ["money", "flagged", "summary"],
    queryFn: ({ signal }) => api.money.flagged({ page_size: 1 }, signal),
    enabled,
    ...SLOW,
  });
}

/** Entity-resolution graph statistics (link counts, merge history, pending
 *  candidates). Aggregate counters only — no persons, no identifiers. */
export function useIdentityStats(enabled: boolean) {
  return useQuery({
    queryKey: ["identity", "stats"],
    queryFn: ({ signal }) => api.identity.stats(signal),
    enabled,
    ...SLOW,
  });
}

/** The three `enabled` flags the resolver needs, derived from one scope.
 *
 *  Kept here beside the hooks rather than inlined at the call site so that adding a
 *  card cannot silently widen which boards issue admin requests: the decision is in
 *  one readable place.
 *
 *  `financial` is true at wing scope for EVERY wing, not just the two the cards are
 *  restricted to. The wing-code restriction is applied by `kpiApplies`, which needs
 *  the code resolved from /org/wings — and gating the fetch on a value that arrives
 *  one render later would leave a Traffic wing board holding a permanently loading
 *  card. One extra aggregate read on a wing board is the cheaper mistake. */
export function kpiSources(scope: ScopeType) {
  return {
    /** Platform-tier counters: seats, imports, models, UI overrides. */
    platform: scope === "platform",
    /** The station approval inbox. */
    review: scope === "station" || scope === "platform",
    /** Money-trail and identity-resolution counters. */
    financial: scope === "wing" || scope === "platform",
  };
}
