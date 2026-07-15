import type { CaseDetailResponse } from "@/api/types";
import { Badge } from "@/components/ui/badge";

/* Acts & Sections sub-page (doc 01 §4.2): ordered list from case detail. */
export function SectionsPage({ detail }: { detail: CaseDetailResponse }) {
  const items = detail.sections;
  if (!items.length) {
    return <p className="py-8 text-center text-13 text-content-dim">No act/section charges recorded.</p>;
  }
  return (
    <div className="space-y-1.5">
      {items.map((s, i) => (
        <div
          key={`${s.act}-${s.section}-${i}`}
          className="flex items-center gap-3 rounded-control border border-hairline bg-surface px-4 py-2.5"
        >
          <Badge variant="primary" className="tnum shrink-0">
            {s.act} {s.section}
          </Badge>
          <span className="min-w-0 flex-1 truncate text-13 text-content">
            {s.description ?? s.act_name ?? "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
