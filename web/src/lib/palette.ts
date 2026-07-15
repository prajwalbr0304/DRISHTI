import { hashString } from "@/lib/utils";

/* ============================================================================
   The colour system, defined ONCE (doc 03 §5–6).

   Rules encoded here:
   - Exactly one 12-hue categorical palette, assigned deterministically so a
     given category is the SAME colour everywhere in the product.
   - Semantic severity hues are reserved and must never be used decoratively.
   - Sequential + diverging ramps are colour-blind-aware; no rainbow ramp exists.
   - Nothing here encodes meaning by colour alone — callers must also supply an
     icon/label/pattern (see chart-theme.ts `SERIES_DASH`).
   ========================================================================== */

/** The fixed 12-hue category palette (mirrors the --cat-* CSS variables). */
export const CATEGORY_PALETTE = [
  "#6366f1", // 1 indigo
  "#14b8a6", // 2 teal
  "#f97316", // 3 orange
  "#8b5cf6", // 4 violet
  "#ec4899", // 5 pink
  "#06b6d4", // 6 cyan
  "#84cc16", // 7 lime
  "#f43f5e", // 8 rose
  "#a855f7", // 9 purple
  "#0ea5e9", // 10 sky
  "#d946ef", // 11 fuchsia
  "#64748b", // 12 slate
] as const;

export type CategoryColor = (typeof CATEGORY_PALETTE)[number];

/** Reserved semantic severity colours (mirror --sev-* variables). */
export const SEVERITY = {
  critical: "#ef4444",
  high: "#f59e0b",
  medium: "#eab308",
  low: "#22c55e",
} as const;

export type Severity = keyof typeof SEVERITY;

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

/** Colours reserved for meaning; guard against decorative reuse. */
const RESERVED = new Set<string>(Object.values(SEVERITY).map((c) => c.toLowerCase()));

/**
 * Stable category -> colour assignment. The same key always maps to the same
 * hue, product-wide. An explicit registry pins known crime heads to specific
 * indices; anything else hashes deterministically into the palette.
 */
const CATEGORY_REGISTRY: Record<string, number> = {
  // Crime-head anchors (indices into CATEGORY_PALETTE, 0-based)
  theft: 0,
  burglary: 1,
  robbery: 2,
  assault: 3,
  "cyber-crime": 4,
  fraud: 5,
  narcotics: 6,
  homicide: 7,
  "missing-person": 8,
  "vehicle-theft": 9,
  extortion: 10,
  other: 11,
};

const dynamicAssignments = new Map<string, number>();
let nextDynamic = 0;

/** Get the fixed colour for a category key (case/space-insensitive). */
export function categoryColor(key: string): string {
  const norm = key.trim().toLowerCase().replace(/\s+/g, "-");
  if (norm in CATEGORY_REGISTRY) return CATEGORY_PALETTE[CATEGORY_REGISTRY[norm]];
  if (dynamicAssignments.has(norm))
    return CATEGORY_PALETTE[dynamicAssignments.get(norm)!];
  // Deterministic fall-back: hash into palette, avoiding thrash across reloads.
  const idx = hashString(norm) % CATEGORY_PALETTE.length;
  dynamicAssignments.set(norm, idx);
  nextDynamic++;
  return CATEGORY_PALETTE[idx];
}

/** Colour by ordinal position (e.g. bar/line series index). Wraps at 12. */
export function seriesColor(index: number): string {
  return CATEGORY_PALETTE[((index % 12) + 12) % 12];
}

export function severityColor(sev: Severity): string {
  return SEVERITY[sev];
}

/** Dev-time guard: refuse to use a reserved severity hue as a category colour. */
export function assertNotReserved(hex: string) {
  if (import.meta.env.DEV && RESERVED.has(hex.toLowerCase())) {
    // eslint-disable-next-line no-console
    console.error(
      `[palette] "${hex}" is a reserved severity colour and must not be used decoratively.`,
    );
  }
}

/* ---------------------------------------------------------------------------
   Sequential + diverging ramps (choropleths, heat, KDE, risk gradients).
   Colour-blind-aware, single-hue / two-hue — deliberately NOT a rainbow.
   ------------------------------------------------------------------------- */

/** Single-hue blue sequential (low -> high). Safe for all CVD types. */
export const SEQUENTIAL_BLUE = [
  "#0b1a3a",
  "#12376b",
  "#1d5aa6",
  "#2f7fd1",
  "#5aa2e8",
  "#9cc7f5",
] as const;

/** Warm sequential for intensity/heat (low -> high). */
export const SEQUENTIAL_HEAT = [
  "#1a1035",
  "#5b1667",
  "#a32167",
  "#dd513a",
  "#f4941e",
  "#f6d746",
] as const;

/** Diverging ramp for signed change (decrease <-> increase), CVD-safe teal/brown. */
export const DIVERGING = [
  "#8c510a",
  "#d8b365",
  "#f6e8c3",
  "#c7eae5",
  "#5ab4ac",
  "#01665e",
] as const;

/** Sample a ramp at t in [0,1] (nearest stop; deterministic, no interpolation). */
export function sampleRamp(ramp: readonly string[], t: number): string {
  const clamped = Math.min(1, Math.max(0, t));
  const idx = Math.round(clamped * (ramp.length - 1));
  return ramp[idx];
}
