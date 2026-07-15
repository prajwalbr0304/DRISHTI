import { create } from "zustand";
import { persist } from "zustand/middleware";
import { toISODate } from "@/lib/utils";

/* ============================================================================
   Global time scrubber. A single window (start..end) scopes every time-aware
   widget in the product, plus a normalised playhead (0..1) for animating
   through the window. Presets snap the window; "custom" preserves the range.
   ========================================================================== */

export type TimePreset = "24h" | "7d" | "30d" | "90d" | "12m" | "custom";

export const PRESETS: { id: TimePreset; label: string; days: number }[] = [
  { id: "24h", label: "24h", days: 1 },
  { id: "7d", label: "7 days", days: 7 },
  { id: "30d", label: "30 days", days: 30 },
  { id: "90d", label: "90 days", days: 90 },
  { id: "12m", label: "12 months", days: 365 },
];

function rangeForPreset(preset: TimePreset): { start: string; end: string } {
  const end = new Date();
  const days = PRESETS.find((p) => p.id === preset)?.days ?? 30;
  const start = new Date(end.getTime() - days * 86400000);
  return { start: toISODate(start), end: toISODate(end) };
}

interface TimeState {
  preset: TimePreset;
  start: string; // ISO date (yyyy-mm-dd)
  end: string;
  playhead: number; // 0..1 within [start, end]
  playing: boolean;

  setPreset: (p: TimePreset) => void;
  setCustomRange: (start: string, end: string) => void;
  setPlayhead: (v: number) => void;
  togglePlay: () => void;
  setPlaying: (v: boolean) => void;
}

const initial = rangeForPreset("30d");

export const useTimeStore = create<TimeState>()(
  persist(
    (set) => ({
      preset: "30d",
      start: initial.start,
      end: initial.end,
      playhead: 1,
      playing: false,

      setPreset: (preset) => {
        if (preset === "custom") return set({ preset });
        const r = rangeForPreset(preset);
        set({ preset, start: r.start, end: r.end, playhead: 1, playing: false });
      },
      setCustomRange: (start, end) => set({ preset: "custom", start, end }),
      setPlayhead: (playhead) => set({ playhead: Math.min(1, Math.max(0, playhead)) }),
      togglePlay: () => set((s) => ({ playing: !s.playing })),
      setPlaying: (playing) => set({ playing }),
    }),
    {
      name: "drishti.time",
      partialize: (s) => ({ preset: s.preset, start: s.start, end: s.end }),
    },
  ),
);

/** The date the playhead currently points at, for display. */
export function playheadDate(start: string, end: string, playhead: number): Date {
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  return new Date(s + (e - s) * playhead);
}
