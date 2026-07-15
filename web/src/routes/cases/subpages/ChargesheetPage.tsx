import type { CaseDetailResponse } from "@/api/types";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

const CSTYPE: Record<string, string> = {
  A: "Chargesheet filed",
  B: "Closed as false case",
  C: "Closed as undetected",
};

/* Chargesheet sub-page (doc 01 §4.2). */
export function ChargesheetPage({ detail }: { detail: CaseDetailResponse }) {
  const items = detail.chargesheets;
  if (!items.length) {
    return <p className="py-8 text-center text-13 text-content-dim">No chargesheets filed on this case.</p>;
  }
  return (
    <div className="space-y-2">
      {items.map((c) => (
        <div key={c.id} className="flex items-center gap-3 rounded-card border border-hairline bg-surface px-4 py-3">
          <Badge variant={c.cstype === "A" ? "primary" : c.cstype === "B" ? "high" : "neutral"} className="shrink-0">
            {c.cstype ?? "—"}
          </Badge>
          <span className="min-w-0 flex-1 text-13 text-content">
            {CSTYPE[c.cstype ?? ""] ?? "Chargesheet"}
          </span>
          <span className="tnum shrink-0 text-12 text-content-dim">
            {c.date ? formatDate(c.date) : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
