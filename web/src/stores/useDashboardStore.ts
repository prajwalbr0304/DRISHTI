import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Layouts } from "react-grid-layout";

/* ============================================================================
   Per-dashboard grid layouts (AWS-style movable/resizable cards). Keyed by a
   stable dashboard id (e.g. the role home). Empty = use the code defaults; once
   the user drags/resizes, their arrangement is persisted here and "Reset layout"
   clears it. Client-only, no fabrication.
   ========================================================================== */

interface DashboardState {
  layouts: Record<string, Layouts>;
  save: (id: string, layouts: Layouts) => void;
  reset: (id: string) => void;
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set) => ({
      layouts: {},
      save: (id, layouts) => set((s) => ({ layouts: { ...s.layouts, [id]: layouts } })),
      reset: (id) =>
        set((s) => {
          const next = { ...s.layouts };
          delete next[id];
          return { layouts: next };
        }),
    }),
    { name: "drishti.dashboards" },
  ),
);
