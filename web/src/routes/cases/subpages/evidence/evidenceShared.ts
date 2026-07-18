import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { BadgeProps } from "@/components/ui/badge";

/* Shared helpers/hooks for the case Evidence sub-page (Phase 5). */

export const EV_STATE_LABEL: Record<string, string> = {
  draft: "Draft",
  uploading: "Uploading",
  available: "Available",
  failed: "Failed",
  archived: "Archived",
};

export function stateBadgeVariant(state: string): BadgeProps["variant"] {
  switch (state) {
    case "available":
      return "low"; // greenish "healthy"
    case "uploading":
      return "primary";
    case "failed":
      return "critical";
    case "archived":
      return "outline";
    default:
      return "neutral"; // draft
  }
}

export function prettyType(t?: string | null): string {
  if (!t) return "—";
  return t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function shortHash(sha?: string | null): string {
  if (!sha) return "—";
  return sha.length > 14 ? `${sha.slice(0, 10)}…${sha.slice(-4)}` : sha;
}

/** Activity verbs -> human labels for the timeline. */
export const ACTIVITY_LABEL: Record<string, string> = {
  created: "Created",
  upload_url_issued: "Upload link issued",
  uploaded: "File uploaded",
  version_added: "New version added",
  metadata_updated: "Metadata corrected",
  linked: "Linked",
  unlinked: "Unlinked",
  download: "Download link issued",
  archived: "Archived",
  restored: "Restored",
  failed: "Upload failed",
  access_attempt: "Access attempt",
  custody_transfer: "Custody transfer",
};

export const evidenceKeys = {
  status: ["evidence", "status"] as const,
  lookups: ["evidence", "lookups"] as const,
  list: (caseId: number, filters: Record<string, unknown>) =>
    ["evidence", "list", caseId, filters] as const,
  item: (id: number) => ["evidence", "item", id] as const,
};

/** Cached S3/hackathon status (drives the upload affordance + allow-list). */
export function useEvidenceStatus() {
  return useQuery({
    queryKey: evidenceKeys.status,
    queryFn: ({ signal }) => api.evidence.status(signal),
    staleTime: 60_000,
  });
}

/** Cached lookups for the metadata form. */
export function useEvidenceLookups() {
  return useQuery({
    queryKey: evidenceKeys.lookups,
    queryFn: ({ signal }) => api.evidence.lookups(signal),
    staleTime: 5 * 60_000,
  });
}
