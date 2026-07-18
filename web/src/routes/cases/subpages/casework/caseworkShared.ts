import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { BadgeProps } from "@/components/ui/badge";
import { useRole } from "@/providers/RoleProvider";

/* Shared helpers/hooks for the Phase 7 casework sub-pages. */

/** Roles that may add/manage casework records (server-enforced too). */
export function useCanWriteCasework(): boolean {
  const { role } = useRole();
  return role === "investigator" || role === "supervisor" || role === "super_admin";
}

/** Roles that may see restricted statement/lab text (server redacts otherwise). */
export function useCanSeeRestricted(): boolean {
  const { role } = useRole();
  return role === "investigator" || role === "supervisor" || role === "super_admin";
}

export function pretty(v?: string | null): string {
  if (!v) return "—";
  return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function dispositionBadge(t: string): BadgeProps["variant"] {
  if (t === "convicted") return "critical";
  if (t === "acquitted") return "low";
  if (t.startsWith("closed") || t === "withdrawn") return "outline";
  return "neutral";
}

export function statusBadge(status?: string | null): BadgeProps["variant"] {
  switch (status) {
    case "convicted":
    case "false_c_report":
      return "critical";
    case "acquitted":
    case "missing_recovered":
      return "low";
    case "chargesheeted":
    case "pending_trial":
      return "primary";
    default:
      return "neutral";
  }
}

export const caseworkKeys = {
  lookups: ["casework", "lookups"] as const,
  timeline: (cid: number) => ["casework", "timeline", cid] as const,
  statements: (cid: number) => ["casework", "statements", cid] as const,
  seizures: (cid: number) => ["casework", "seizures", cid] as const,
  labs: (cid: number) => ["casework", "labs", cid] as const,
  court: (cid: number) => ["casework", "court", cid] as const,
};

export function useCaseworkLookups() {
  return useQuery({
    queryKey: caseworkKeys.lookups,
    queryFn: ({ signal }) => api.casework.lookups(signal),
    staleTime: 5 * 60_000,
  });
}

/** datetime-local value -> ISO (or undefined). */
export function toISO(v: string): string | undefined {
  return v ? new Date(v).toISOString() : undefined;
}
