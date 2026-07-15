import { FileText, GitBranch, Info } from "lucide-react";
import type { AiResult } from "@/api/contracts";
import { cn, confidenceBand, formatPercent } from "@/lib/utils";
import { parseSourceRecords } from "@/lib/provenance";
import { usePeekStore } from "@/stores/usePeekStore";

/* ============================================================================
   Evidence Trail — the panel the provenance strip expands. Bound exactly to the
   AiResult contract: { confidence, source_record_ids, reasoning_summary,
   model_version }. Every source record is a peekable reference.
   ========================================================================== */

const BAND_LABEL: Record<ReturnType<typeof confidenceBand>, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export function EvidenceTrail({ result }: { result: AiResult }) {
  const push = usePeekStore((s) => s.push);
  const records = parseSourceRecords(result.source_record_ids ?? []);
  const band = confidenceBand(result.confidence);

  return (
    <div className="space-y-3 text-13">
      {/* Confidence — bar + numeric + label (never colour-alone) */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className="text-12 font-medium text-content-dim">{BAND_LABEL[band]}</span>
          <span className="tnum font-semibold text-content">{formatPercent(result.confidence, 0)}</span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
          role="meter"
          aria-valuenow={Math.round(result.confidence * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Confidence"
        >
          <div
            className={cn(
              "h-full rounded-full",
              band === "low" ? "bg-content-dim" : "bg-primary",
            )}
            style={{ width: `${Math.round(result.confidence * 100)}%` }}
          />
        </div>
      </div>

      {/* Reasoning */}
      {result.reasoning_summary && (
        <div className="flex gap-2">
          <Info className="mt-0.5 size-3.5 shrink-0 text-content-dim" />
          <p className="leading-relaxed text-content">{result.reasoning_summary}</p>
        </div>
      )}

      {/* Model version */}
      <div className="flex items-center gap-2">
        <GitBranch className="size-3.5 shrink-0 text-content-dim" />
        <span className="text-content-dim">Model</span>
        <code className="tnum rounded bg-surface-2 px-1.5 py-0.5 text-12 text-content">
          {result.model_version || "—"}
        </code>
      </div>

      {/* Source records — provenance, each peekable */}
      <div>
        <div className="mb-1.5 flex items-center gap-2 text-12 font-medium text-content-dim">
          <FileText className="size-3.5" />
          Source records
          <span className="tnum">({records.length})</span>
        </div>
        {records.length === 0 ? (
          <p className="text-12 text-content-dim">No source records cited.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {records.map((r) => {
              const clickable = Boolean(r.ref);
              return (
                <li key={r.raw}>
                  <button
                    type="button"
                    disabled={!clickable}
                    onClick={() => r.ref && push(r.ref)}
                    className={cn(
                      "tnum rounded-control border border-hairline bg-surface-2 px-2 py-1 text-12 transition-colors",
                      clickable
                        ? "cursor-pointer text-content hover:border-primary/60 hover:text-primary"
                        : "cursor-default text-content-dim",
                    )}
                    title={clickable ? "Open in peek rail" : r.raw}
                  >
                    {r.raw}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
