import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSeatKey } from "@/hooks/useSeatKey";

/* ============================================================================
   Drop the previous seat's cached answers when the seat changes.

   WHY. Almost every endpoint in this service is confined server-side to the
   caller's seat: `geo_scope` narrows /geo/trends, /geo/hotspots, /geo/alerts,
   /cases/caseload, /outcomes/overview, /dashboard/summary, /performance/districts
   and /casework/hearings/next, and /cases/filters and /org/my-scope answer purely
   from the seat record. The response therefore depends on a header that no query
   key mentioned.

   Most keys carried the district instead, which is a PROXY for the seat and not the
   same thing. It breaks in two directions:

     two seats in the SAME district — an SHO and their IO, or two SHOs of
     neighbouring stations — share a district but are confined to different units,
     so they collided on one cache entry;

     and a seat switch that lands on the same district id changed nothing about the
     key at all, so nothing refetched.

   WHY CLEARING, NOT KEYING. The specific queries whose correctness matters within a
   session are keyed by seat explicitly (useMyScope, useDistricts, useFilterOptions),
   which is race-free because the key changes atomically with the seat. This is the
   net underneath that: a seat switch is closer to a user switch than to a filter
   change, so treating every cached answer as belonging to the previous seat is both
   correct and complete — including for endpoints nobody remembered to audit.

   The cost is refetching a handful of genuinely seat-independent lookups (crime
   heads, statuses, boundaries) on a switch, which is a rare and deliberate action.
   Showing one officer another officer's jurisdiction is not a trade worth making to
   avoid that.

   Mounted in AppShell so it runs on every route, beside the other two anchors.
   ========================================================================== */

export function useSeatCacheReset() {
  const seatKey = useSeatKey();
  const queryClient = useQueryClient();
  const previous = useRef(seatKey);

  useEffect(() => {
    if (previous.current === seatKey) return;
    previous.current = seatKey;
    /* removeQueries, not invalidateQueries: invalidation marks entries stale but
       KEEPS serving them while the refetch is in flight, which is the one behaviour
       that must not happen here — the stale data is another seat's jurisdiction and
       would be on screen under the new seat's name. Removing forces every mounted
       query into its loading state instead. */
    queryClient.removeQueries();
  }, [seatKey, queryClient]);
}
