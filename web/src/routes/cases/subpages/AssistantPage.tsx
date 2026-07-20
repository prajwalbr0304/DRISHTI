import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Lightbulb, Search, Send, ShieldCheck } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { InvestigationAnswer, InvestigationItem } from "@/api/endpoints/investigate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Widget } from "@/components/widget/Widget";
import { SendToBoard } from "@/components/board/SendToBoard";

/* Prompt 20 Part D — case-scoped investigation assistant. Bilingual (EN/Kannada)
   case questions are answered by composing the existing summary/similar/identity/
   leads/timeline capabilities. FACTS (evidence-backed) are shown separately from
   HYPOTHESES (suggestions); cited objects can be sent to the Investigation Board.
   Not a second free-form chatbot — free-form data questions use Ask DRISHTI. */

const QUICK: { en: string; label: string }[] = [
  { en: "Have similar cases happened before?", label: "Similar cases?" },
  { en: "What are the next investigative leads?", label: "Next leads" },
  { en: "Who is connected to this case?", label: "Connections" },
  { en: "Show the case timeline", label: "Timeline" },
];

function ItemRow({ it }: { it: InvestigationItem }) {
  return (
    <li className="rounded-control border border-hairline px-2.5 py-2">
      <div className="flex items-start gap-2">
        <span className="min-w-0 flex-1">
          <span className="block text-13 font-medium text-content">{it.label}</span>
          <span className="block text-12 text-content-dim">{it.detail}</span>
          <span className="mt-1 flex flex-wrap gap-1">
            {it.source_ids.slice(0, 6).map((s) => (
              <span key={s} className="rounded bg-surface-2 px-1 text-[11px] text-content-dim">{s}</span>
            ))}
          </span>
        </span>
        {it.confidence != null && (
          <Badge variant="neutral" className="shrink-0">{Math.round(it.confidence * 100)}%</Badge>
        )}
      </div>
    </li>
  );
}

export function AssistantPage({ caseId }: { caseId: number }) {
  const [text, setText] = useState("");
  const ask = useMutation<InvestigationAnswer, unknown, string>({
    mutationFn: (q: string) => api.investigate.ask(caseId, q),
  });
  const brief = useMutation<InvestigationAnswer, unknown, void>({
    mutationFn: () => api.investigate.brief(caseId),
  });

  const data = ask.data ?? brief.data;
  const pending = ask.isPending || brief.isPending;
  const error = ask.error ?? brief.error;

  return (
    <Widget
      title="Investigation assistant"
      info={
        <p className="text-content-dim">
          Case-scoped assistant. Facts (evidence) are separated from hypotheses (suggestions);
          two people are never called the same on embedding similarity alone. Cited objects can
          be sent to the Investigation Board.
        </p>
      }
    >
      <form
        className="mb-3 flex flex-wrap items-center gap-2"
        onSubmit={(e) => { e.preventDefault(); if (text.trim()) ask.mutate(text.trim()); }}
      >
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask about this case (English or ಕನ್ನಡ)…"
          className="h-8 min-w-[16rem] flex-1 text-13"
          aria-label="case question"
        />
        <Button type="submit" size="sm" disabled={!text.trim() || pending}>
          <Search className="size-3.5" /> Ask
        </Button>
        <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => brief.mutate()}>
          Full brief
        </Button>
      </form>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {QUICK.map((qq) => (
          <button key={qq.label} type="button" disabled={pending}
            onClick={() => { setText(qq.en); ask.mutate(qq.en); }}
            className="rounded-full border border-hairline px-2.5 py-0.5 text-12 text-content-dim transition-colors hover:text-content disabled:opacity-50">
            {qq.label}
          </button>
        ))}
      </div>

      {pending && <p className="text-12 text-content-dim">Composing from case evidence…</p>}
      {error ? <p className="text-12 text-severity-high">{errorMessage(error)}</p> : null}

      {data && !pending && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-12">
            <Badge variant="primary">{data.intent.replace(/_/g, " ")}</Badge>
            <Badge variant="neutral">{data.language === "kn" ? "ಕನ್ನಡ" : "English"}</Badge>
            <Badge variant="neutral">{data.citations.length} citations</Badge>
            <span className="text-content-dim">{data.planner_source}</span>
          </div>
          <p className="text-13 text-content">{data.answer}</p>

          {/* FACTS */}
          <div>
            <div className="mb-1 flex items-center gap-1.5 text-12 font-semibold text-content">
              <CheckCircle2 className="size-3.5 text-severity-low" /> Facts &amp; evidence
            </div>
            {data.facts.length ? (
              <ul className="space-y-1">{data.facts.map((f, i) => <ItemRow key={i} it={f} />)}</ul>
            ) : <p className="text-12 text-content-dim">No evidence-backed items for this question.</p>}
          </div>

          {/* HYPOTHESES */}
          <div>
            <div className="mb-1 flex items-center gap-1.5 text-12 font-semibold text-content">
              <Lightbulb className="size-3.5 text-severity-medium" /> Hypotheses &amp; suggestions
            </div>
            {data.hypotheses.length ? (
              <ul className="space-y-1">{data.hypotheses.map((h, i) => <ItemRow key={i} it={h} />)}</ul>
            ) : <p className="text-12 text-content-dim">No suggestions for this question.</p>}
          </div>

          {/* citable objects -> Board */}
          {data.citable_objects.length > 0 && (
            <div className="rounded-control border border-hairline p-2.5">
              <div className="mb-1.5 text-12 font-medium text-content">Send cited objects to a board</div>
              <div className="flex flex-wrap gap-1.5">
                {data.citable_objects.slice(0, 12).map((o) => (
                  <SendToBoard
                    key={`${o.ref_table}:${o.ref_id}`}
                    variant="ghost" size="sm"
                    label={o.label}
                    target={{ refTable: o.ref_table, refId: o.ref_id, nodeKind: o.kind, label: o.label }}
                  />
                ))}
              </div>
            </div>
          )}

          <ul className="space-y-0.5">
            {data.limitations.map((l) => (
              <li key={l} className="flex items-start gap-1 text-11 text-content-dim">
                <ShieldCheck className="mt-0.5 size-3 shrink-0" /> {l}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Widget>
  );
}
