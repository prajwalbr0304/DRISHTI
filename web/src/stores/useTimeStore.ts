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

/* The operational dataset is HISTORICAL (synthetic). The machine clock can sit
   months past the last record, so anchoring "now" to the real clock makes every
   window land after the data ends -> "No data for the current scope". We anchor
   "now" to the latest data date instead. This fallback is refreshed at runtime
   from GET /geo/coverage (see useDataAnchor), so it also adapts if data changes. */
export const DATA_AS_OF_FALLBACK = "2025-12-31";

function rangeForPreset(preset: TimePreset, anchorISO: string): { start: string; end: string } {
  const parsed = new Date(`${anchorISO}T12:00:00`);
  const anchor = isNaN(parsed.getTime()) ? new Date() : parsed;
  const days = PRESETS.find((p) => p.id === preset)?.days ?? 30;
  const start = new Date(anchor.getTime() - days * 86400000);
  return { start: toISODate(start), end: toISODate(anchor) };
}

interface TimeState {
  preset: TimePreset;
  anchor: string; // "now" for the presets = latest data date (ISO yyyy-mm-dd)
  start: string; // ISO date (yyyy-mm-dd)
  end: string;
  playhead: number; // 0..1 within [start, end]
  playing: boolean;

  setPreset: (p: TimePreset) => void;
  setCustomRange: (start: string, end: string) => void;
  setAnchor: (anchorISO: string) => void;
  setPlayhead: (v: number) => void;
  togglePlay: () => void;
  setPlaying: (v: boolean) => void;
}

// Default to 12 months: crime trends need several points to read as a trend (and
// for the rolling-mean anomaly band to detect the "emerging" signal); a 30-day
// window over monthly buckets is a single dot. Users can still narrow via presets.
const initial = rangeForPreset("12m", DATA_AS_OF_FALLBACK);

export const useTimeStore = create<TimeState>()(
  persist(
    (set) => ({
      preset: "12m",
      anchor: DATA_AS_OF_FALLBACK,
      start: initial.start,
      end: initial.end,
      playhead: 1,
      playing: false,

      setPreset: (preset) =>
        set((s) => {
          if (preset === "custom") return { preset };
          return { preset, ...rangeForPreset(preset, s.anchor), playhead: 1, playing: false };
        }),
      setCustomRange: (start, end) => set({ preset: "custom", start, end }),
      // Re-anchor "now" to the latest data date and recompute the active preset
      // window (custom ranges are left untouched).
      setAnchor: (anchor) =>
        set((s) => (s.preset === "custom" ? { anchor } : { anchor, ...rangeForPreset(s.preset, anchor) })),
      setPlayhead: (playhead) => set({ playhead: Math.min(1, Math.max(0, playhead)) }),
      togglePlay: () => set((s) => ({ playing: !s.playing })),
      setPlaying: (playing) => set({ playing }),
    }),
    {
      name: "drishti.time",
      version: 2,
      partialize: (s) => ({ preset: s.preset, anchor: s.anchor, start: s.start, end: s.end }),
      // v1 persisted clock-anchored (future, empty) ranges. Recompute from the
      // preset against the data anchor so upgrades don't keep a stale window.
      migrate: (persisted, version) => {
        const p = (persisted ?? {}) as Partial<TimeState>;
        const preset = (p.preset ?? "12m") as TimePreset;
        const anchor = p.anchor ?? DATA_AS_OF_FALLBACK;
        if (preset === "custom" && p.start && p.end) return { ...p, anchor } as TimeState;
        return { ...p, preset, anchor, ...rangeForPreset(preset, anchor) } as TimeState;
      },
    },
  ),
);

/** The date the playhead currently points at, for display. */
export function playheadDate(start: string, end: string, playhead: number): Date {
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  return new Date(s + (e - s) * playhead);
}
