import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Layout, Layouts } from "react-grid-layout";

/* ============================================================================
   Per-dashboard grid state (AWS-style movable/resizable cards), keyed by a
   stable dashboard id (e.g. the role home). Two independent pieces:

     layouts  where each tile sits. Empty = use the code defaults; once the user
              drags or resizes, their arrangement is persisted and "Reset
              layout" clears it.
     hidden   which tiles the user dismissed. A dense board (the state command
              band is 28 cards) is only usable if a chief can put away the
              measures they don't watch. Dismissal is always REVERSIBLE — the
              grid offers "Show N hidden" whenever anything is hidden, so this
              can never become a one-way trap.

   Client-only, no fabrication: hiding a card changes what is displayed, never
   what was measured.
   ========================================================================== */

interface DashboardState {
  layouts: Record<string, Layouts>;
  hidden: Record<string, string[]>;
  save: (id: string, layouts: Layouts) => void;
  reset: (id: string) => void;
  hideTile: (id: string, key: string) => void;
  showAllTiles: (id: string) => void;
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set) => ({
      layouts: {},
      hidden: {},
      save: (id, layouts) => set((s) => ({ layouts: { ...s.layouts, [id]: layouts } })),
      reset: (id) =>
        set((s) => {
          const next = { ...s.layouts };
          delete next[id];
          return { layouts: next };
        }),
      hideTile: (id, key) =>
        set((s) => {
          const current = s.hidden[id] ?? [];
          if (current.includes(key)) return s;
          return { hidden: { ...s.hidden, [id]: [...current, key] } };
        }),
      showAllTiles: (id) =>
        set((s) => {
          const next = { ...s.hidden };
          delete next[id];
          return { hidden: next };
        }),
    }),
    {
      name: "drishti.dashboards",
      version: 2,
      // v1 persisted `layouts` only; `hidden` simply starts empty for everyone
      // who already has a stored board.
      migrate: (persisted) => ({ hidden: {}, ...(persisted as object) }) as DashboardState,
    },
  ),
);

/** Stable empty array so `useDashboardStore(s => hiddenTiles(s, id))` selectors
 *  don't return a fresh reference every render. */
const NO_HIDDEN: string[] = [];

/** Keys the user has dismissed on a given dashboard. */
export function hiddenTiles(state: DashboardState, id: string): string[] {
  return state.hidden[id] ?? NO_HIDDEN;
}

/* ----------------------------------------------------------------------------
   Additive merge of a saved arrangement onto the current code defaults.

   A saved layout is an all-or-nothing SNAPSHOT: the moment a user drags one
   tile we persist exactly the tiles that existed then. A tile added in code
   afterwards is simply absent from that snapshot, and react-grid-layout
   SYNTHESISES a position for it rather than using the geometry the tile
   declares — so new cards land in arbitrary places for anyone who has ever
   touched their board.

   Merging by tile key fixes that in one place:
     * a key present in the snapshot keeps the USER's x/y/w/h,
     * a key absent from it uses the DECLARED geometry,
     * a key no longer in the code drops out (a removed tile can't linger),
     * min constraints stay code-owned, so a stale snapshot can never pin a
       tile below the minimum size its content needs.

   The defaults are also the source of truth for which breakpoints exist; a
   breakpoint the user never arranged falls through to the declared layout.
   -------------------------------------------------------------------------- */
export function mergeLayouts(saved: Layouts | undefined, defaults: Layouts): Layouts {
  if (!saved) return defaults;
  const merged: Layouts = {};
  for (const breakpoint of Object.keys(defaults)) {
    const declared = defaults[breakpoint];
    const arranged = saved[breakpoint];
    if (!arranged) {
      merged[breakpoint] = declared;
      continue;
    }
    const byKey = new Map<string, Layout>(arranged.map((item) => [item.i, item]));
    merged[breakpoint] = declared.map((item) => {
      const user = byKey.get(item.i);
      if (!user) return item;
      return {
        ...item,
        x: user.x,
        y: user.y,
        w: Math.max(user.w, item.minW ?? 1),
        h: Math.max(user.h, item.minH ?? 1),
      };
    });
  }
  return merged;
}
