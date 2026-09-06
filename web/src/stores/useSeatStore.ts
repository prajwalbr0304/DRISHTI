import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ScopeType, UserRole } from "@/config/roles";

/* ============================================================================
   The seat the user is operating as.

   There are ~11,825 provisioned seats, so a role alone no longer identifies one.
   A role says WHICH BOARD to render; the seat says WHOSE jurisdiction — an SP of
   Mysuru and an SP of Belagavi share a role and see different districts.

   IMPORTANT: this is a VIEW selection, not authentication. The username is sent as
   X-Demo-Actor and the server resolves that seat's scope from its own `users`
   record. Picking a seat here cannot grant its jurisdiction; the server derives it
   independently and refuses anything outside it. The API Gateway strips the header
   entirely in the deployed path and re-derives the seat from the Catalyst session.
   ========================================================================== */

export interface SelectedSeat {
  username: string;
  displayName: string | null;
  role: UserRole;
  scopeType: ScopeType;
  /** Rank-facing label, e.g. "DIG / Range Command". */
  scopeLabel: string;
  /** Where the seat is posted, e.g. "Jayanagar PS-1, Bengaluru City". */
  postingLabel: string | null;
  rankLabel: string | null;
}

interface SeatState {
  seat: SelectedSeat | null;
  setSeat: (seat: SelectedSeat) => void;
  clearSeat: () => void;
}

export const useSeatStore = create<SeatState>()(
  persist(
    (set) => ({
      seat: null,
      setSeat: (seat) => set({ seat }),
      clearSeat: () => set({ seat: null }),
    }),
    {
      name: "drishti.seat",
      version: 1,
      partialize: (s) => ({ seat: s.seat }),
    },
  ),
);

/** The actor to send as X-Demo-Actor, or null to fall back to the role's seeded
 *  demo seat. Display/audit only — never authentication. */
export function selectedActor(): string | null {
  return useSeatStore.getState().seat?.username ?? null;
}
