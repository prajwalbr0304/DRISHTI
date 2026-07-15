import { useEffect, useState } from "react";
import { CATEGORY_PALETTE, seriesColor } from "@/lib/palette";

/* ============================================================================
   Shared chart theme + enforced house rules (doc 03 §5–6).

   The rules are not guidelines here — they are executable guards:
     • no pie/donut with more than 4 slices
     • no 3D
     • no dual Y axes
     • no rainbow ramps (only the sanctioned sequential/diverging ramps)
     • never colour-alone: every series also carries a dash/shape/label channel

   Every chart in the product should pull axis/grid/tooltip styling from
   `useChartTheme()` and its series colours from the palette, so the whole
   product reads as one instrument.
   ========================================================================== */

/** Dash patterns so line/area series stay distinct without relying on colour. */
export const SERIES_DASH = [
  "0",
  "6 3",
  "2 3",
  "8 3 2 3",
  "10 4",
  "1 3",
] as const;

/** Point shapes so scatter/legend series are distinguishable without colour. */
export const SERIES_SHAPE = [
  "circle",
  "square",
  "triangle",
  "diamond",
  "cross",
  "star",
] as const;

export type ResolvedChartTheme = {
  text: string;
  textDim: string;
  grid: string;
  axis: string;
  surface: string;
  surface2: string;
  tooltipBg: string;
  tooltipBorder: string;
  primary: string;
  accent: string;
  categorical: string[];
  fontFamily: string;
  fontSize: number;
};

function readVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function resolveTheme(): ResolvedChartTheme {
  return {
    text: readVar("--text", "#e8ecf6"),
    textDim: readVar("--text-dim", "#94a0bd"),
    grid: readVar("--border", "#28324d"),
    axis: readVar("--border", "#28324d"),
    surface: readVar("--surface", "#141b2e"),
    surface2: readVar("--surface-2", "#1d2740"),
    tooltipBg: readVar("--surface-2", "#1d2740"),
    tooltipBorder: readVar("--border", "#28324d"),
    primary: readVar("--primary", "#3b82f6"),
    accent: readVar("--accent", "#12b981"),
    categorical: [...CATEGORY_PALETTE],
    fontFamily: "Inter, 'Noto Sans Kannada', system-ui, sans-serif",
    fontSize: 12,
  };
}

/**
 * Resolve theme tokens to concrete colours for chart libraries (Recharts/visx),
 * re-reading whenever the <html> theme class flips (Ops <-> Desk).
 */
export function useChartTheme(): ResolvedChartTheme {
  const [theme, setTheme] = useState<ResolvedChartTheme>(() => resolveTheme());

  useEffect(() => {
    const update = () => setTheme(resolveTheme());
    update();
    const obs = new MutationObserver(update);
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => obs.disconnect();
  }, []);

  return theme;
}

/** Common Recharts axis props for a consistent, quiet look. */
export function axisProps(theme: ResolvedChartTheme) {
  return {
    stroke: theme.axis,
    tick: { fill: theme.textDim, fontSize: theme.fontSize },
    tickLine: false,
    axisLine: { stroke: theme.axis },
  } as const;
}

export function gridProps(theme: ResolvedChartTheme) {
  return {
    stroke: theme.grid,
    strokeDasharray: "2 4",
    vertical: false,
  } as const;
}

export function tooltipStyle(theme: ResolvedChartTheme) {
  return {
    contentStyle: {
      background: theme.tooltipBg,
      border: `1px solid ${theme.tooltipBorder}`,
      borderRadius: 10,
      color: theme.text,
      fontSize: 12,
      fontFamily: theme.fontFamily,
      boxShadow: "0 8px 28px -8px rgb(0 0 0 / 0.45)",
    },
    labelStyle: { color: theme.textDim, marginBottom: 4 },
    itemStyle: { color: theme.text },
    cursor: { fill: theme.surface2, opacity: 0.5 },
  } as const;
}

/* ---------------------------------------------------------------------------
   Executable guardrails — call these from chart components.
   ------------------------------------------------------------------------- */

export const MAX_PIE_SLICES = 4;

/** True when a pie/donut is permissible (<= 4 slices). */
export function pieIsPermitted(sliceCount: number): boolean {
  return sliceCount <= MAX_PIE_SLICES;
}

/**
 * Reduce arbitrary categories to a pie-safe set: top (MAX-1) + "Other".
 * Use this instead of ever rendering a >4-slice pie.
 */
export function toPieSafe<T extends { value: number; name: string }>(
  data: T[],
): { name: string; value: number }[] {
  if (data.length <= MAX_PIE_SLICES) return data.map((d) => ({ name: d.name, value: d.value }));
  const sorted = [...data].sort((a, b) => b.value - a.value);
  const top = sorted.slice(0, MAX_PIE_SLICES - 1).map((d) => ({ name: d.name, value: d.value }));
  const rest = sorted.slice(MAX_PIE_SLICES - 1).reduce((s, d) => s + d.value, 0);
  return [...top, { name: "Other", value: rest }];
}

type ChartSpec = {
  kind: "line" | "area" | "bar" | "pie" | "scatter" | "heatmap" | "choropleth";
  slices?: number;
  yAxes?: number;
  threeD?: boolean;
  usesRainbow?: boolean;
  /** must be true: every series carries a non-colour channel (dash/shape/label). */
  redundantEncoding?: boolean;
};

/** Validate a chart spec against house rules. Returns violations (empty = ok). */
export function validateChart(spec: ChartSpec): string[] {
  const errors: string[] = [];
  if (spec.threeD) errors.push("3D charts are not allowed.");
  if ((spec.yAxes ?? 1) > 1) errors.push("Dual/second Y axes are not allowed.");
  if (spec.usesRainbow) errors.push("Rainbow ramps are not allowed; use a sanctioned ramp.");
  if (spec.kind === "pie" && (spec.slices ?? 0) > MAX_PIE_SLICES)
    errors.push(`Pie/donut limited to ${MAX_PIE_SLICES} slices (got ${spec.slices}).`);
  if (spec.redundantEncoding === false)
    errors.push("Series must not rely on colour alone (add dash/shape/label).");
  return errors;
}

/** Dev-time assertion; logs loudly but never crashes the app. */
export function assertChart(spec: ChartSpec) {
  if (!import.meta.env.DEV) return;
  const errors = validateChart(spec);
  if (errors.length) {
    // eslint-disable-next-line no-console
    console.error("[chart-theme] chart violates house rules:\n - " + errors.join("\n - "));
  }
}

export { seriesColor, CATEGORY_PALETTE };
