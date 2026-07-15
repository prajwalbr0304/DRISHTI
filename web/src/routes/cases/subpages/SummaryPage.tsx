import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Sparkles } from "lucide-react";
import { api } from "@/api";
import { Button } from "@/components/ui/button";
import { Widget } from "@/components/widget/Widget";
import { CitationText } from "@/components/cases/CitationText";

/* AI Summary sub-page (doc 01 §4.2, doc 03 §2.12): LLM summary + timeline,
   every claim cited to a record ID. Inline numbered citations scroll to the
   cited source. Provenance strip bound to result. */
export function SummaryPage({ caseId }: { caseId: number }) {
  const [trigger, setTrigger] = useState(0);
  const q = useQuery({
    queryKey: ["cases", "summary", caseId, trigger],
    queryFn: ({ signal }) => api.cases.summary(caseId, signal),
    enabled: trigger > 0,
    staleTime: Infinity,
  });

  const hasResult = trigger > 0 && !q.isLoading && !q.error && q.data;

  return (
    <Widget
      title="AI Summary"
      provenance={q.data?.result}
      loading={q.isLoading}
      error={q.error}
      onRefresh={trigger > 0 ? () => setTrigger((v) => v + 1) : undefined}
      info={
        <p className="text-content-dim">
          Ontology-Augmented Generation: a case brief built strictly from linked records. Every
          claim carries an inline numbered citation — click a number to scroll to the source.
        </p>
      }
    >
      {!hasResult && trigger === 0 && (
        <div className="flex flex-col items-center justify-center gap-3 py-8 text-center">
          <Sparkles className="size-5 text-primary" />
          <p className="max-w-sm text-13 text-content-dim">
            Generate a fully-cited AI summary of this case. This calls the backend service, writes a
            reproducible AISummary row, and returns inline-cited claims.
          </p>
          <Button variant="primary" onClick={() => setTrigger(1)}>
            <RefreshCw /> Generate summary
          </Button>
        </div>
      )}

      {hasResult && q.data && (
        <div className="space-y-4">
          {/* Citation-annotated sentences */}
          <CitationText sentences={q.data.sentences} />

          {/* Timeline */}
          {q.data.timeline.length > 0 && (
            <div className="border-t border-hairline pt-3">
              <div className="mb-2 text-12 font-semibold uppercase tracking-wide text-content-dim">
                Derived timeline
              </div>
              <ol className="space-y-1.5">
                {q.data.timeline.map((t, i) => (
                  <li key={i} className="flex items-start gap-3 rounded-control px-2 py-1">
                    <span className="tnum shrink-0 text-12 text-content-dim">{t.date}</span>
                    <span className="text-13 text-content">{t.label}</span>
                    {t.citations.length > 0 && (
                      <span className="ml-auto shrink-0 text-12 text-content-dim tnum">
                        [{t.citations.join(", ")}]
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Stats */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-hairline pt-2 text-12 text-content-dim">
            <span className="tnum">{q.data.claim_count} claims</span>
            <span className="tnum">{q.data.cited_claim_count} cited</span>
            <span>{q.data.fully_cited ? "✓ Fully cited" : "⚠ Partially cited"}</span>
            <span className="tnum">conf. {Math.round(q.data.confidence * 100)}%</span>
          </div>
        </div>
      )}
    </Widget>
  );
}
