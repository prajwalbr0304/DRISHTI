import type { CaseDetailResponse } from "@/api/types";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

/* Arrests sub-page (doc 01 §4.2). */
export function ArrestsPage({ detail }: { detail: CaseDetailResponse }) {
  const items = detail.arrests;
  if (!items.length) {
    return <p className="py-8 text-center text-13 text-content-dim">No arrests recorded for this case.</p>;
  }
  return (
    <div className="space-y-1.5">
      {items.map((a) => (
        <div key={a.id} className="flex items-center gap-3 rounded-control border border-hairline bg-surface px-4 py-2.5">
          <Badge variant="accent" className="shrink-0">
            {a.type === 1 ? "Arrest" : a.type === 2 ? "Surrender" : "Event"}
          </Badge>
          <span className="min-w-0 flex-1 text-13 text-content">
            Accused #{a.accused_id ?? "—"}
          </span>
          <span className="tnum shrink-0 text-12 text-content-dim">
            {a.date ? formatDate(a.date) : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
