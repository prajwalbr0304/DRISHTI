import { ArrowDownRight, ArrowUpRight, ShieldCheck } from "lucide-react";
import type { SocioEconomicResponse } from "@/api/types";
import { cn } from "@/lib/utils";

/* ============================================================================
   Socio-economic read-out (doc 03 §2.10). Plain-language narrative + the
   strongest correlations, with the mandatory "correlational, not causal"
   disclaimer and the k-anonymity suppression count surfaced (honesty rules,
   doc 03 §1/§7). A policymaker's home turf.
   ========================================================================== */

export function SocioNarrativeCard({
  data,
  /** Hide the top-5 ranked list when a correlation chart already carries it
   *  (the Command Center panel), so the same numbers aren't shown twice. */
  compact = false,
}: {
  data: SocioEconomicResponse;
  compact?: boolean;
}) {
  const top = compact
    ? []
    : [...data.correlation_matrix]
        .filter((c) => c.r != null)
        .sort((a, b) => Math.abs(b.r ?? 0) - Math.abs(a.r ?? 0))
        .slice(0, 5);

  return (
    <div className="space-y-3">
      {/* Narrative */}
      <div>
        <p className="text-14 font-medium text-content">{data.narrative.headline}</p>
        <p className="mt-1 text-13 text-content-dim">{data.narrative.detail}</p>
      </div>

      {/* Strongest correlations */}
      {top.length > 0 && (
        <div className="space-y-1.5">
          {top.map((c) => {
            const r = c.r ?? 0;
            const pos = r >= 0;
            const Icon = pos ? ArrowUpRight : ArrowDownRight;
            return (
              <div
                key={`${c.crime_category}-${c.indicator}`}
                className="flex items-center gap-3 rounded-control bg-surface-2/50 px-2.5 py-1.5"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-13 text-content">
                    {c.indicator} <span className="text-content-dim">↔</span> {c.crime_category}
                  </div>
                  {c.strength && <div className="text-12 capitalize text-content-dim">{c.strength}</div>}
                </div>
                <span className="relative h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-surface-2">
                  <span
                    className="absolute inset-y-0 left-0 rounded-full bg-primary"
                    style={{ width: `${Math.min(100, Math.abs(r) * 100)}%` }}
                  />
                </span>
                <span
                  className={cn(
                    "tnum inline-flex w-14 shrink-0 items-center justify-end gap-0.5 text-13 font-medium",
                    pos ? "text-content" : "text-content-dim",
                  )}
                >
                  <Icon className="size-3.5" />
                  {pos ? "+" : ""}
                  {r.toFixed(2)}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Honesty footer */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-hairline pt-2 text-12 text-content-dim">
        <span className="tnum">{data.districts_analysed} districts</span>
        <span className="inline-flex items-center gap-1">
          <ShieldCheck className="size-3.5" />
          <span className="tnum">{data.suppressed_cells}</span> cells suppressed (k≥{data.k_threshold})
        </span>
      </div>
      <p className="text-12 italic text-content-dim">{data.narrative.disclaimer}</p>
    </div>
  );
}
