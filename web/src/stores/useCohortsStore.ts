import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { TimePreset } from "@/stores/useTimeStore";

/* ============================================================================
   Saved lenses / cohorts (doc 01 §8.4). A lens is a named, reusable scope —
   here, a saved time window — that can be re-applied across destinations. This
   is the shell-level persistence for the feature; richer filter cohorts land
   with the Cases / Analytics explorers. Real client state, no fabrication.
   ========================================================================== */

export interface Cohort {
  id: string;
  name: string;
  preset: TimePreset;
  start: string;
  end: string;
  createdAt: number;
}

interface CohortsState {
  cohorts: Cohort[];
  save: (c: Omit<Cohort, "id" | "createdAt">) => void;
  remove: (id: string) => void;
}

export const useCohortsStore = create<CohortsState>()(
  persist(
    (set) => ({
      cohorts: [],
      save: (c) =>
        set((s) => ({
          cohorts: [
            { ...c, id: `co_${Date.now().toString(36)}`, createdAt: Date.now() },
            ...s.cohorts,
          ].slice(0, 20),
        })),
      remove: (id) => set((s) => ({ cohorts: s.cohorts.filter((c) => c.id !== id) })),
    }),
    { name: "drishti.cohorts" },
  ),
);
