import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AskLang } from "@/stores/useAskStore";

/* ============================================================================
   Saved Queries (doc 01 §4.7) — reusable natural-language prompts. Persisted
   client-side (the DB SavedQuery table + server persistence arrive with the
   Phase-2 engine). Real user data, no fabrication.
   ========================================================================== */

export interface SavedQuery {
  id: string;
  text: string;
  language: AskLang | string;
  createdAt: number;
}

interface SavedQueriesState {
  queries: SavedQuery[];
  save: (text: string, language: AskLang | string) => void;
  remove: (id: string) => void;
  has: (text: string) => boolean;
}

export const useSavedQueriesStore = create<SavedQueriesState>()(
  persist(
    (set, get) => ({
      queries: [],
      save: (text, language) => {
        const trimmed = text.trim();
        if (!trimmed || get().has(trimmed)) return;
        set((s) => ({
          queries: [
            { id: `sq_${Date.now().toString(36)}`, text: trimmed, language, createdAt: Date.now() },
            ...s.queries,
          ].slice(0, 50),
        }));
      },
      remove: (id) => set((s) => ({ queries: s.queries.filter((q) => q.id !== id) })),
      has: (text) => get().queries.some((q) => q.text === text.trim()),
    }),
    { name: "drishti.savedqueries" },
  ),
);
