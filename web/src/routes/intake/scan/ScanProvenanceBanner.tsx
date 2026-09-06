import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ScanLine } from "lucide-react";
import { api } from "@/api";
import { Badge } from "@/components/ui/badge";
import { formatPercent } from "@/routes/intake/scan/scanQueries";
import type { IntakeDraftResponse } from "@/api/types";

/* ============================================================================
   Shown at the top of a draft that was prefilled from a scan.

   Its job is accountability: anyone opening the draft — including the approving
   supervisor — must be able to see at a glance that a machine read these values,
   how many were corrected, and how many were flagged as unclear. Without this the
   scanned lane and the typed lane would look identical at the approval gate,
   which is exactly where the difference matters most.
   ========================================================================== */

/** A draft is scan-prefilled when its source system says so. */
export function isScanPrefilled(draft?: IntakeDraftResponse | null): boolean {
  return draft?.payload?.source?.source_system_code === "FIR_SCAN_OCR";
}

export function ScanProvenanceBanner({ draft }: { draft?: IntakeDraftResponse | null }) {
  const draftKey = draft?.draft_key;
  const enabled = isScanPrefilled(draft) && !!draftKey;

  // The scan is found via the queue rather than a reverse lookup endpoint, which
  // keeps the API surface smaller for a purely informational banner.
  const q = useQuery({
    queryKey: ["intake", "scan", "for-draft", draftKey],
    queryFn: async ({ signal }) => {
      const queue = await api.intake.scanQueue({ status: "applied", page_size: 100 }, signal);
      const match = queue.items.find((i) => i.draft_key === draftKey);
      if (!match) return null;
      return api.intake.scanProvenance(match.scan_key, signal);
    },
    enabled,
    staleTime: 5 * 60_000,
  });

  if (!enabled) return null;

  const prov = q.data;
  const edited = prov?.fields.filter((f) => f.was_edited).length ?? 0;
  const flagged = prov?.fields.filter((f) => f.requires_review && !f.was_edited).length ?? 0;
  const total = prov?.fields.length ?? 0;

  return (
    <div className="mb-3 rounded-card border border-primary/30 bg-primary/5 p-3">
      <div className="flex flex-wrap items-start gap-2">
        <ScanLine className="mt-0.5 size-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="text-13 text-content">
            This draft was filled in by reading a scanned form. Every value is your
            responsibility to confirm before submitting.
          </p>
          {total > 0 && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <Badge variant="neutral" className="tnum">
                {total} field{total === 1 ? "" : "s"} from the scan
              </Badge>
              {edited > 0 && (
                <Badge variant="primary" className="tnum">{edited} corrected</Badge>
              )}
              {flagged > 0 && (
                <Badge variant="medium" className="tnum">
                  <AlertTriangle className="size-3" /> {flagged} still unconfirmed
                </Badge>
              )}
              {prov?.ocr_confidence != null && (
                <Badge variant="neutral" className="tnum">
                  Recogniser {formatPercent(prov.ocr_confidence)}
                </Badge>
              )}
            </div>
          )}
          {prov?.sha256 && (
            <p className="mt-1.5 break-all text-11 text-content-dim">
              Source page {prov.file_name} · SHA-256 {prov.sha256.slice(0, 16)}…
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
