import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/api/contracts";
import { api } from "@/api";
import { cn, formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Widget } from "@/components/widget/Widget";
import { EmptyState } from "@/components/common/EmptyState";
import { GitCompareArrows } from "lucide-react";

/* Similar Cases sub-page (doc 01 §4.2, doc 03 §2.11): ranked by embedding
   similarity with similarity bars + outcomes. Phase 11: a demo case/unit
   CONTEXT filter is applied before the ANN search, and each hit shows WHY it
   matched (shared context/MO — never outcome). */
export function SimilarPage({ caseId }: { caseId: number }) {
  const navigate = useNavigate();
  const [scope, setScope] = useState<"district" | "all">("district");
  const q = useQuery({
    queryKey: ["cases", "similar", caseId, scope],
    queryFn: ({ signal }) => api.cases.similar(caseId, { k: 10, scope }, signal),
  });

  // 409 = corpus not embedded yet — an honest, actionable state.
  if (q.error instanceof ApiError && q.error.status === 409) {
    return (
      <EmptyState
        icon={GitCompareArrows}
        title="Similarity corpus not built"
        description="The case-embedding corpus is empty. Run the embed job (python -m app.batch embed-cases) to enable modus-operandi search."
      />
    );
  }

  const results = q.data?.results ?? [];

  return (
    <Widget
      title="Similar cases"
      contextChip={q.data ? `top ${results.length}` : undefined}
      provenance={q.data?.result}
      loading={q.isLoading}
      error={q.error}
      empty={!q.isLoading && !q.error && results.length === 0}
      emptyLabel="No comparable cases found."
      onRefresh={() => q.refetch()}
      info={
        <p className="text-content-dim">
          Nearest neighbours by case embedding (pgvector, cosine) in one model-version space,
          filtered to the selected demo context first. {q.data?.limitations}
        </p>
      }
    >
      {/* demo case/unit CONTEXT filter (applied before the ANN search) */}
      <div className="mb-2 flex items-center gap-1.5 text-12">
        <span className="text-content-dim">Context:</span>
        {(["district", "all"] as const).map((s) => (
          <button key={s} type="button" onClick={() => setScope(s)}
            className={cn("rounded-full border px-2.5 py-0.5 capitalize transition-colors",
              scope === s ? "border-primary bg-primary/10 text-content" : "border-hairline text-content-dim hover:text-content")}>
            {s === "district" ? "This district" : "All districts"}
          </button>
        ))}
      </div>

      {q.data && results.length > 0 && (
        <div className="space-y-1">
          {results.map((c) => (
            <button
              key={c.case_id}
              type="button"
              onClick={() => navigate(`/cases/${c.case_id}`)}
              className="flex w-full items-center gap-3 rounded-control px-2 py-2 text-left transition-colors hover:bg-surface-2"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-13 font-medium text-content">
                  {c.crime_no ?? `Case ${c.case_id}`}
                </span>
                <span className="block truncate text-12 text-content-dim">
                  {[c.crime_group, c.crime_subhead, c.district].filter(Boolean).join(" · ")}
                </span>
                {c.why_match && c.why_match.length > 0 && (
                  <span className="mt-0.5 flex flex-wrap gap-1">
                    {c.why_match.map((w) => (
                      <Badge key={w} variant="low" className="text-[11px]">{w}</Badge>
                    ))}
                  </span>
                )}
              </span>
              {c.disposition && (
                <Badge variant="neutral" className="shrink-0">
                  {c.disposition}
                </Badge>
              )}
              <span className="flex w-32 shrink-0 items-center gap-2">
                <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <span
                    className="absolute inset-y-0 left-0 rounded-full bg-primary"
                    style={{ width: `${Math.round(c.similarity * 100)}%` }}
                  />
                </span>
                <span className="tnum w-9 text-right text-12 font-medium text-primary">
                  {formatPercent(c.similarity, 0)}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </Widget>
  );
}
