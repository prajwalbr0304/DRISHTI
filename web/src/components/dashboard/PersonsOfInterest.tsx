import { Target } from "lucide-react";
import type { PersonOfInterest } from "@/api/types";
import { cn } from "@/lib/utils";

/* ============================================================================
   Network-of-interest shortcut (doc 01 §4.1 analyst). Ranks persons by graph
   centrality; the importance bar encodes PageRank and the halo marks the top
   "kingpin" node (doc 03 §4 encoding contract). Each row peeks the entity.
   ========================================================================== */

export function PersonsOfInterest({
  people,
  onSelect,
}: {
  people: PersonOfInterest[];
  onSelect: (p: PersonOfInterest) => void;
}) {
  const peak = Math.max(1e-9, ...people.map((p) => p.pagerank ?? 0));

  return (
    <div className="space-y-0.5">
      {people.map((p, i) => {
        const pct = ((p.pagerank ?? 0) / peak) * 100;
        const top = i === 0;
        return (
          <button
            key={p.entity_id}
            type="button"
            onClick={() => onSelect(p)}
            className="flex w-full items-center gap-3 rounded-control px-2 py-1.5 text-left transition-colors hover:bg-surface-2"
          >
            <span className="tnum grid size-6 shrink-0 place-items-center rounded-control bg-surface-2 text-12 font-semibold text-content-dim">
              {i + 1}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5">
                {top && <Target className="size-3.5 shrink-0 text-primary" aria-label="Highest centrality" />}
                <span className="truncate text-13 font-medium text-content">
                  {p.label ?? `Entity ${p.entity_id}`}
                </span>
              </span>
              <span className="mt-1 flex items-center gap-2">
                <span className="relative h-1 w-24 overflow-hidden rounded-full bg-surface-2">
                  <span
                    className={cn("absolute inset-y-0 left-0 rounded-full", top ? "bg-primary" : "bg-primary/60")}
                    style={{ width: `${pct}%` }}
                  />
                </span>
                <span className="text-12 capitalize text-content-dim">{p.entity_type}</span>
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
