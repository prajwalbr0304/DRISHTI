import { DEFAULT_ROLE, demoActorFor } from "@/config/roles";
import { useAuthOptional } from "@/auth";
import { useRoleOptional } from "@/providers/RoleProvider";
import { useSeatStore } from "@/stores/useSeatStore";

/* ============================================================================
   The identity of the seat the workspace is currently operating as, as a react-
   query cache key.

   WHY THIS IS NEEDED. A growing number of endpoints answer differently for two
   seats that share a ROLE, because the server derives scope from the seat record
   behind X-Demo-Actor rather than from X-Role. /org/my-scope and /cases/filters are
   the clearest cases: an SP of Bagalkot and an SP of Mysuru are both
   `district_command`, and each is entitled to exactly one — different — district.

   Keying those queries by role alone silently served the first seat's answer to the
   second. Opening SP Ganesh Gowda after SP Anand showed Anand's district in the
   region selector, under Gowda's name, with every widget on the page scoped to it.
   A cache key is the whole fix: the request already carried the right header.

   PRECEDENCE MIRRORS THE ACTOR HEADER exactly — see `setActorGetter` in
   providers/RoleProvider. It has to: if this key were coarser than the header, two
   different actors would share a cache entry, which is the bug. If it were finer,
   queries would refetch for no reason.
   ========================================================================== */

export function useSeatKey(): string {
  /* Both contexts read OPTIONALLY. This is a leaf helper consumed by broadly-shared
     hooks (useDistricts, useMyScope, useFilterOptions), so demanding a provider here
     would make a component test that renders one widget fail on a provider it has no
     reason to mount — and the fallback is well defined anyway: it matches the API
     client's own default actor, `demo.${DEFAULT_ROLE}`. */
  const role = useRoleOptional()?.role ?? DEFAULT_ROLE;
  const auth = useAuthOptional();
  // Subscribed, not read once: picking a seat must invalidate the keys that
  // depend on it, and `selectedActor()` is a non-reactive getter for the client.
  const username = useSeatStore((s) => s.seat?.username ?? null);
  return username || auth?.user?.email || demoActorFor(role);
}
