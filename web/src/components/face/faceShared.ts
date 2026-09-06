import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { FaceBand, FaceMatch, FacePersonRecord } from "@/api/types";

/** Engine + gallery state. Cached briefly: it changes when someone enrols a
 *  photo, and a stale "nothing enrolled" would wrongly disable the scanner. */
export function useFaceStatus(enabled = true) {
  return useQuery({
    queryKey: ["face", "status"],
    queryFn: ({ signal }) => api.face.status(signal),
    enabled,
    staleTime: 30_000,
    retry: 1,
  });
}

export function usePersonFaces(cpid?: number | null) {
  return useQuery({
    queryKey: ["face", "person", cpid],
    queryFn: ({ signal }) => api.face.personFaces(cpid as number, signal),
    enabled: typeof cpid === "number" && cpid > 0,
  });
}

/** Honour the OS "reduce motion" setting: the scan graphics are decorative
 *  progress feedback, so they must be droppable without losing information. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

export interface BandMeta {
  label: string;
  /** What the officer should actually do about it. */
  guidance: string;
  badge: "low" | "medium" | "high" | "neutral" | "primary";
  bar: string;
  text: string;
}

/* Bands are always rendered with an icon + words. A bare cosine number means
   nothing to the person reading it, and colour alone is not an accessible
   signal for "this might be your suspect". */
export const BAND_META: Record<FaceBand, BandMeta> = {
  strong: {
    label: "Strong match",
    guidance: "Very likely the same person. Verify against the record before acting.",
    badge: "low",
    bar: "bg-severity-low",
    text: "text-severity-low",
  },
  probable: {
    label: "Possible match",
    guidance: "Worth checking. Confirm with other identifiers before linking.",
    badge: "medium",
    bar: "bg-severity-medium",
    text: "text-severity-medium",
  },
  weak: {
    label: "Not a match",
    guidance: "Below the match threshold — treat this person as not on record.",
    badge: "neutral",
    bar: "bg-content-dim/50",
    text: "text-content-dim",
  },
};

export function bandMeta(band: FaceBand | string | undefined): BandMeta {
  return BAND_META[(band as FaceBand) ?? "weak"] ?? BAND_META.weak;
}

const GENDERS: Record<number, string> = { 1: "Male", 2: "Female", 3: "Trans / other" };

export function genderLabel(id?: number | null): string | null {
  return id ? GENDERS[id] ?? null : null;
}

export function personName(p?: FacePersonRecord | null): string {
  if (!p) return "—";
  if (p.is_unknown) return "Unknown / unidentified";
  return p.display_label?.trim() || p.public_ref;
}

/** Approximate age from ApproxBirthYear — labelled "approx." wherever shown,
 *  because the underlying field is itself an approximation. */
export function approxAge(year?: number | null): number | null {
  if (!year) return null;
  const age = new Date().getFullYear() - year;
  return age > 0 && age < 130 ? age : null;
}

export function similarityPct(v?: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

/** One-line summary of why a hit is worth attention. */
export function matchSummary(m: FaceMatch): string {
  const parts: string[] = [];
  if (m.person.case_count > 0) {
    parts.push(`${m.person.case_count} case${m.person.case_count === 1 ? "" : "s"} on record`);
  }
  if (m.person.role_types.length) {
    parts.push(m.person.role_types.map((r) => r.replace(/_/g, " ")).join(", "));
  }
  if (m.person.districts.length) parts.push(m.person.districts.slice(0, 2).join(", "));
  return parts.join(" · ") || "No case involvement recorded";
}

/** Progress stages the scanner narrates. Each one corresponds to real work, so
 *  the readout stays honest instead of being decorative theatre. */
export const SCAN_STAGES = [
  { key: "acquire", label: "Acquiring frame" },
  { key: "prepare", label: "Normalising image" },
  { key: "detect", label: "Detecting face" },
  { key: "encode", label: "Extracting descriptor" },
  { key: "search", label: "Searching person records" },
  { key: "rank", label: "Ranking candidates" },
] as const;

export type ScanStageKey = (typeof SCAN_STAGES)[number]["key"];
