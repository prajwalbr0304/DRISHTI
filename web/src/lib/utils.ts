import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind-aware className combiner (shadcn convention). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/* ---------------------------------------------------------------------------
   Formatting — all numbers render with tabular figures (pair with `.tnum`).
   ------------------------------------------------------------------------- */

const numberFmt = new Intl.NumberFormat("en-IN");

/** Locale-grouped integer/decimal, e.g. 12,34,567 (en-IN grouping). */
export function formatNumber(value: number, opts?: Intl.NumberFormatOptions) {
  if (opts) return new Intl.NumberFormat("en-IN", opts).format(value);
  return numberFmt.format(value);
}

/** Compact counts for KPIs: 1.2K, 3.4M. */
export function formatCompact(value: number) {
  return new Intl.NumberFormat("en-IN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

/** 0..1 -> "72%". */
export function formatPercent(value: number, fractionDigits = 0) {
  return new Intl.NumberFormat("en-IN", {
    style: "percent",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

const dateFmt = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});
const dateTimeFmt = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatDate(d: Date | string | number) {
  return dateFmt.format(new Date(d));
}
export function formatDateTime(d: Date | string | number) {
  return dateTimeFmt.format(new Date(d));
}

/** ISO date (yyyy-mm-dd) for API params. */
export function toISODate(d: Date) {
  return d.toISOString().slice(0, 10);
}

/** Human relative time, e.g. "3h ago", "just now". */
export function timeAgo(d: Date | string | number) {
  const then = new Date(d).getTime();
  const secs = Math.round((Date.now() - then) / 1000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const table: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, secsIn] of table) {
    if (Math.abs(secs) >= secsIn) return rtf.format(-Math.round(secs / secsIn), unit);
  }
  return "just now";
}

/** Clamp helper. */
export function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n));
}

/** Deterministic small hash for stable colour/id assignment. */
export function hashString(input: string) {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Confidence 0..1 -> qualitative band used across Evidence Trails. */
export function confidenceBand(c: number): "high" | "medium" | "low" {
  if (c >= 0.75) return "high";
  if (c >= 0.5) return "medium";
  return "low";
}
