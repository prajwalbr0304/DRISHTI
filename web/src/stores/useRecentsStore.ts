import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ObjectRef } from "@/api/types";

/* ============================================================================
   Recently-opened objects. This is the user's OWN activity (things they peeked
   at), recorded client-side — not fabricated server data. Powers the
   Investigator "Recent activity" widget (resume where you left off).
   ========================================================================== */

export interface RecentItem extends ObjectRef {
  at: number; // epoch ms
}

const CAP = 15;

interface RecentsState {
  items: RecentItem[];
  record: (ref: ObjectRef) => void;
  clear: () => void;
}

function sameRef(a: ObjectRef, b: ObjectRef) {
  return a.kind === b.kind && String(a.id) === String(b.id);
}

export const useRecentsStore = create<RecentsState>()(
  persist(
    (set) => ({
      items: [],
      record: (ref) =>
        set((s) => {
          const without = s.items.filter((it) => !sameRef(it, ref));
          return { items: [{ ...ref, at: Date.now() }, ...without].slice(0, CAP) };
        }),
      clear: () => set({ items: [] }),
    }),
    { name: "drishti.recents" },
  ),
);
