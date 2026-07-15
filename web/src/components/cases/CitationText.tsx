import { useState } from "react";
import { FileText } from "lucide-react";
import type { SummaryClaim } from "@/api/types";
import { cn } from "@/lib/utils";
import { parseSourceRecord } from "@/lib/provenance";
import { usePeekStore } from "@/stores/usePeekStore";

/* ============================================================================
   Citation-annotated text (doc 03 §2.12, Perplexity-style). Each claim carries
   inline numbered citations; clicking a number scrolls to and highlights the
   cited source record below; clicking a source opens it in the peek rail.
   ========================================================================== */

export function CitationText({ sentences }: { sentences: SummaryClaim[] }) {
  const push = usePeekStore((s) => s.push);
  const [flash, setFlash] = useState<number | null>(null);

  // Number citations in order of first appearance.
  const order: string[] = [];
  for (const s of sentences) for (const c of s.citations) if (!order.includes(c)) order.push(c);
  const numberOf = new Map(order.map((id, i) => [id, i + 1]));

  function goToSource(n: number) {
    const el = document.getElementById(`case-source-${n}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setFlash(n);
      window.setTimeout(() => setFlash((v) => (v === n ? null : v)), 1600);
    }
  }

  return (
    <div className="space-y-4">
      {/* Prose with inline citations */}
      <div className="space-y-2 text-14 leading-relaxed text-content">
        {sentences.map((s, i) => (
          <p key={i}>
            {s.text}{" "}
            {s.citations.map((c) => {
              const n = numberOf.get(c)!;
              return (
                <button
                  key={c}
                  type="button"
                  onClick={() => goToSource(n)}
                  className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-primary/15 px-1 align-super text-[10px] font-semibold text-primary transition-colors hover:bg-primary/25"
                  title={c}
                >
                  {n}
                </button>
              );
            })}
          </p>
        ))}
      </div>

      {/* Sources */}
      {order.length > 0 && (
        <div className="border-t border-hairline pt-3">
          <div className="mb-2 flex items-center gap-1.5 text-12 font-semibold text-content-dim">
            <FileText className="size-3.5" /> Sources
          </div>
          <ol className="space-y-1">
            {order.map((id, i) => {
              const n = i + 1;
              const parsed = parseSourceRecord(id);
              return (
                <li
                  key={id}
                  id={`case-source-${n}`}
                  className={cn(
                    "flex items-center gap-2 rounded-control px-2 py-1 transition-colors",
                    flash === n && "bg-primary/10 ring-1 ring-primary/40",
                  )}
                >
                  <span className="tnum grid size-4 shrink-0 place-items-center rounded bg-surface-2 text-[10px] font-semibold text-content-dim">
                    {n}
                  </span>
                  <button
                    type="button"
                    disabled={!parsed.ref}
                    onClick={() => parsed.ref && push(parsed.ref)}
                    className={cn(
                      "tnum truncate text-12",
                      parsed.ref
                        ? "cursor-pointer text-content hover:text-primary"
                        : "cursor-default text-content-dim",
                    )}
                    title={parsed.ref ? "Open in peek rail" : id}
                  >
                    {id}
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}
