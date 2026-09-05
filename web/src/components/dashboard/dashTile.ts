import { createContext, useContext } from "react";

/* ============================================================================
   What a tile knows about the board it sits on.

   DashboardGrid wraps every tile in this, so a card can offer "remove" without
   the board passing an onRemove down to all 28 of them, and without any card
   needing to know its own key or which dashboard it belongs to.

   Outside a grid the context is null and the affordance is simply absent — a
   KpiCard rendered on its own (or in a test) has nothing to be removed from.
   ========================================================================== */

export interface DashTileHandle {
  /** This tile's stable key, for labelling the control. */
  key: string;
  /** Dismiss this tile. Reversible: the grid exposes "Show N hidden". */
  remove: () => void;
}

export const DashTileContext = createContext<DashTileHandle | null>(null);

export function useDashTile(): DashTileHandle | null {
  return useContext(DashTileContext);
}
