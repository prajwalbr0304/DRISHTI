import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";

/* Shared react-query hooks for the scanned-FIR lane. Capability and the printable
   template are both server-owned contracts, so they are fetched rather than
   duplicated in the client. */

export function useScanCapability() {
  return useQuery({
    queryKey: ["intake", "scan", "capability"],
    queryFn: ({ signal }) => api.intake.scanCapability(signal),
    staleTime: 5 * 60_000,
  });
}

export function useScanTemplate() {
  return useQuery({
    queryKey: ["intake", "scan", "template"],
    queryFn: ({ signal }) => api.intake.scanTemplate(signal),
    staleTime: 30 * 60_000,
  });
}

export function useScanQueue(params: { status?: string; review_state?: string; page?: number } = {}) {
  return useQuery({
    queryKey: ["intake", "scan", "queue", params],
    queryFn: ({ signal }) => api.intake.scanQueue(params, signal),
  });
}

/** Confidence -> UI band. Mirrors the server's auto-fill threshold so the badge
    and the server's decision to pre-fill can never disagree. */
export type ConfidenceBand = "high" | "medium" | "low";

export function confidenceBand(confidence: number, autoFillThreshold: number): ConfidenceBand {
  if (confidence >= Math.max(autoFillThreshold, 0.85)) return "high";
  if (confidence >= autoFillThreshold) return "medium";
  return "low";
}

export function formatPercent(value?: number | null): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

/** Human label for a dotted payload path or a party pseudo-path. */
export function fieldLabel(path: string): string {
  if (path.startsWith("__")) {
    const body = path.slice(2).replace(/_/g, " ");
    return body.charAt(0).toUpperCase() + body.slice(1);
  }
  const key = path.includes(".") ? path.split(".").slice(1).join(".") : path;
  const words = key.replace(/_id$/, "").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
