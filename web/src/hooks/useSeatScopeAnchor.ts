import { useEffect } from "react";
import { useMyScope } from "@/hooks/useMyScope";
import { useScopeStore } from "@/stores/useScopeStore";

/* ============================================================================
   Anchor the global district scope to the seat's own region.

   The district counterpart of useDataAnchor. The top-bar selector starts on "All
   districts", which is the right opening scope for a state seat and the wrong one
   for a district seat — an SHO should not have to re-pick their own station's
   district on every fresh session just to see their own numbers. So the seat's
   posting, resolved SERVER-SIDE (see useMyScope), seeds the selector once.

   Two guarantees, both enforced in useScopeStore.seedFromSeat:
     an explicit user choice is never overwritten (that is what `chosen` is for,
     including an explicit "All districts", which looks identical to the initial
     state by district id alone);
     and re-applying is harmless, so this can run on every route.

   Because the seed re-applies while the user has not chosen, switching seats
   moves the scope with them — SHO view opens on their district, DGP view returns
   to state-wide — without anyone touching the selector.

   Like useDataAnchor this MUST be mounted somewhere that renders on every route
   (AppShell), not inside the selector: the scope drives every widget, including
   pages where the top bar's dropdown is never opened.
   ========================================================================== */

export function useSeatScopeAnchor() {
  const seat = useMyScope();
  const seedFromSeat = useScopeStore((s) => s.seedFromSeat);

  useEffect(() => {
    // Wait for the real answer. Mid-flight, useMyScope falls back to a
    // role-shaped guess; seeding from that would set the scope, then correct it,
    // and any widget that fetched in between would have queried the wrong scope.
    if (seat.loading) return;
    seedFromSeat(seat.districtId);
  }, [seat.loading, seat.districtId, seedFromSeat]);
}
