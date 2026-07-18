import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, X } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

/* ============================================================================
   Semantic "cases like this MO" bar (doc 01 §4.2). Enter a reference case id;
   pgvector nearest-neighbour search (GET /cases/{id}/similar) returns the
   closest modus-operandi matches with similarity bars. Real, live search.
   ========================================================================== */

export function MoSearchBar() {
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [caseId, setCaseId] = useState<number | null>(null);

  const q = useQuery({
    queryKey: ["cases", "similar", caseId],
    queryFn: ({ signal }) => api.cases.similar(caseId!, { k: 8 }, signal),
    enabled: caseId != null,
  });

  function run() {
    const id = Number(input.trim());
    if (Number.isFinite(id) && id > 0) setCaseId(id);
  }

  return (
    <div className="rounded-card border border-hairline bg-surface p-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
        className="flex items-center gap-2"
      >
        <Sparkles className="size-4 shrink-0 text-primary" />
        <span className="hidden shrink-0 text-13 text-content-dim sm:inline">Cases like this MO</span>
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          inputMode="numeric"
          placeholder="reference case id…"
          className="h-8 max-w-[220px]"
        />
        <Button type="submit" size="sm" disabled={!input.trim()}>
          Find similar
        </Button>
        {caseId != null && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={() => {
              setCaseId(null);
              setInput("");
            }}
            aria-label="Clear"
          >
            <X />
          </Button>
        )}
      </form>

      {caseId != null && (
        <div className="mt-3 border-t border-hairline pt-3">
          {q.isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          )}
          {q.error && <p className="text-12 text-content-dim">{errorMessage(q.error)}</p>}
          {q.data && q.data.results.length === 0 && (
            <p className="text-12 text-content-dim">No comparable cases found.</p>
          )}
          {q.data && q.data.results.length > 0 && (
            <>
              <div className="mb-1.5 text-12 text-content-dim">
                Closest modus-operandi matches to case {caseId} · corpus{" "}
                <span className="tnum">{q.data.corpus_size.toLocaleString("en-IN")}</span>
              </div>
              <div className="space-y-1">
                {q.data.results.map((c) => (
                  <button
                    key={c.case_id}
                    type="button"
                    onClick={() => navigate(`/cases/${c.case_id}`)}
                    className="flex w-full items-center gap-3 rounded-control px-2 py-1.5 text-left transition-colors hover:bg-surface-2"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-13 text-content">
                        {c.crime_no ?? `Case ${c.case_id}`}
                      </span>
                      <span className="block truncate text-12 text-content-dim">
                        {[c.crime_group, c.district].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    {c.disposition && (
                      <Badge variant="neutral" className="shrink-0">
                        {c.disposition}
                      </Badge>
                    )}
                    <span className="flex w-28 shrink-0 items-center gap-2">
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
            </>
          )}
        </div>
      )}
    </div>
  );
}
