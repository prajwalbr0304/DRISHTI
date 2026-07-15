import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Sparkles, Zap } from "lucide-react";
import { api } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Widget } from "@/components/widget/Widget";
import { usePeekStore } from "@/stores/usePeekStore";
import { parseSourceRecord } from "@/lib/provenance";

/* Leads sub-page (doc 01 §4.2): ranked investigative next-steps with evidence
   behind each. Decision support, not orders. */
export function LeadsPage({ caseId }: { caseId: number }) {
  const push = usePeekStore((s) => s.push);
  const [trigger, setTrigger] = useState(0);

  const q = useQuery({
    queryKey: ["cases", "leads", caseId, trigger],
    queryFn: ({ signal }) => api.cases.leads(caseId, signal),
    enabled: trigger > 0,
    staleTime: Infinity,
  });

  const leads = q.data?.leads ?? [];

  return (
    <Widget
      title="Investigative leads"
      provenance={q.data?.result}
      loading={q.isLoading}
      error={q.error}
      onRefresh={trigger > 0 ? () => setTrigger((v) => v + 1) : undefined}
      info={
        <p className="text-content-dim">
          Ranked next steps — each carries the evidence record IDs behind it. Decision support
          only; suggestions, not orders. Generated via POST /cases/{"{id}"}/leads.
        </p>
      }
    >
      {trigger === 0 && (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <Sparkles className="size-5 text-primary" />
          <p className="max-w-sm text-13 text-content-dim">
            Generate ranked investigative leads for this case. The backend writes OfficerRecommendation
            rows and returns the evidence behind each.
          </p>
          <Button variant="primary" onClick={() => setTrigger(1)}>
            <RefreshCw /> Generate leads
          </Button>
        </div>
      )}

      {trigger > 0 && !q.isLoading && leads.length === 0 && !q.error && (
        <p className="py-8 text-center text-13 text-content-dim">No investigative leads generated.</p>
      )}

      {leads.length > 0 && (
        <div className="space-y-2">
          {leads.map((l) => (
            <div key={l.rank} className="rounded-card border border-hairline bg-surface p-3">
              <div className="flex items-start gap-2">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold text-white">
                  {l.rank}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-13 font-medium text-content">{l.step}</span>
                    <Badge variant="neutral" className="shrink-0 capitalize">{l.kind}</Badge>
                    <span className="tnum ml-auto text-12 text-content-dim">
                      score {Math.round(l.score * 100)}%
                    </span>
                  </div>
                  <p className="mt-1 text-12 text-content-dim">{l.why}</p>
                  {l.evidence.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {l.evidence.map((e) => {
                        const p = parseSourceRecord(e);
                        return (
                          <button
                            key={e}
                            type="button"
                            disabled={!p.ref}
                            onClick={() => p.ref && push(p.ref)}
                            className="tnum rounded-control border border-hairline bg-surface-2 px-1.5 py-0.5 text-12 text-content-dim transition-colors hover:border-primary/60 hover:text-primary disabled:cursor-default disabled:hover:border-hairline disabled:hover:text-content-dim"
                          >
                            {e}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Widget>
  );
}
