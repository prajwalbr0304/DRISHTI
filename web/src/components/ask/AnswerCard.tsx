import { useState } from "react";
import {
  Check,
  ChevronDown,
  Copy,
  Database,
  HelpCircle,
  ShieldAlert,
  Sparkles,
  Square,
  TriangleAlert,
  Volume2,
} from "lucide-react";
import type { AskMessage } from "@/stores/useAskStore";
import { usePeekStore } from "@/stores/usePeekStore";
import { parseSourceRecord } from "@/lib/provenance";
import { cn, confidenceBand, formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { AnswerVisualization } from "@/components/ask/AnswerVisualization";

/* ============================================================================
   Assistant turn (doc 01 §4.7). A grounded answer shows all four parts:
     1. the natural-language reply (in the asked language),
     2. inline numbered citations to the exact records used (kind-aware peek),
     3. a collapsible, read-only "SQL executed" block (proof it's grounded),
     4. a confidence chip.
   Plus honest non-answer states: thinking, a clarifying question, a scope/guard
   refusal (no fabricated data), and request errors.
   ========================================================================== */

export interface AnswerCardTts {
  supported: boolean;
  isSpeaking: boolean;
  onSpeak: (message: AskMessage) => void;
  onStop: () => void;
}

export function AnswerCard({ message, tts }: { message: AskMessage; tts?: AnswerCardTts }) {
  if (message.thinking) return <ThinkingBubble />;

  const cites = message.citedRecordIds ?? [];
  const tone = message.blocked ? "blocked" : message.error ? "error" : "normal";
  const canSpeak = !!tts?.supported && !message.error && message.text.trim().length > 0;

  return (
    <div
      className={cn(
        "max-w-[92%] space-y-3 rounded-card rounded-tl-sm border bg-surface p-3.5 shadow-card",
        tone === "blocked" && "border-severity-high/50 bg-severity-high/5",
        tone === "error" && "border-hairline",
        tone === "normal" && "border-hairline",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-12 font-semibold text-content-dim">
          <Sparkles className="size-3.5 text-primary" /> DRISHTI
        </span>
        {message.blocked && (
          <Badge variant="high"><ShieldAlert className="size-3" /> access blocked</Badge>
        )}
        {message.needsClarification && !message.blocked && (
          <Badge variant="neutral"><HelpCircle className="size-3" /> needs detail</Badge>
        )}
        {message.error && <Badge variant="high"><TriangleAlert className="size-3" /> error</Badge>}
        {message.plannerDegraded && !message.error && (
          <SimpleTooltip label="The primary semantic planner was unavailable; a deterministic fallback answered this.">
            <Badge variant="neutral">offline fallback</Badge>
          </SimpleTooltip>
        )}
        {message.confidence != null && !message.blocked && !message.error && !message.needsClarification && (
          <ConfidenceChip value={message.confidence} />
        )}
        {canSpeak && (
          <SimpleTooltip label={tts!.isSpeaking ? "Stop" : "Listen (read aloud)"}>
            <button
              type="button"
              onClick={() => (tts!.isSpeaking ? tts!.onStop() : tts!.onSpeak(message))}
              aria-label={tts!.isSpeaking ? "Stop reading" : "Read answer aloud"}
              className={cn(
                "grid size-6 shrink-0 place-items-center rounded-control transition-colors",
                message.confidence != null && !message.blocked ? "" : "ml-auto",
                tts!.isSpeaking
                  ? "bg-primary/15 text-primary"
                  : "text-content-dim hover:bg-surface-2 hover:text-content",
              )}
            >
              {tts!.isSpeaking ? <Square className="size-3.5" /> : <Volume2 className="size-4" />}
            </button>
          </SimpleTooltip>
        )}
      </div>

      {/* 1. reply + 2. inline numbered citations */}
      <p lang={message.language} className="whitespace-pre-wrap text-14 leading-relaxed text-content">
        {message.text}
        {cites.length > 0 && <InlineCitations ids={cites} />}
      </p>

      {cites.length > 0 && <SourcesRow ids={cites} />}

      {/* typed visualization (or the results table when no spec is present) */}
      <AnswerVisualization message={message} />

      {/* 3. collapsible read-only SQL */}
      {message.generatedSql && <SqlBlock sql={message.generatedSql} />}

      {/* provenance footer */}
      {message.modelVersion && !message.error && (
        <div className="flex items-center gap-2 border-t border-hairline pt-2 text-12 text-content-dim">
          <span>{message.blocked ? "refused server-side" : "grounded answer"}</span>
          <code className="ml-auto rounded bg-surface-2 px-1.5 py-0.5">{message.modelVersion}</code>
        </div>
      )}
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div className="max-w-[92%] rounded-card rounded-tl-sm border border-hairline bg-surface p-3.5 shadow-card">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-12 font-semibold text-content-dim">
          <Sparkles className="size-3.5 text-primary" /> DRISHTI
        </span>
      </div>
      <div className="mt-2 flex items-center gap-1" aria-label="Thinking">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-1.5 animate-pulse rounded-full bg-content-dim"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
        <span className="ml-1.5 text-12 text-content-dim">translating to read-only SQL…</span>
      </div>
    </div>
  );
}

/* ------------------------------ citations --------------------------------- */
/** Normalise a cited id to the "Table:id" contract, then resolve to a peekable ref. */
function normalize(raw: number | string): string {
  if (typeof raw === "number") return `CaseMaster:${raw}`;
  if (/^\d+$/.test(raw)) return `CaseMaster:${raw}`;
  return raw;
}
function aggregated(raw: string): string | null {
  const m = raw.match(/^(.+?)\(aggregated\)$/);
  return m ? m[1] : null;
}

function InlineCitations({ ids }: { ids: (number | string)[] }) {
  const push = usePeekStore((s) => s.push);
  return (
    <span className="ml-1 inline-flex flex-wrap gap-0.5 align-baseline">
      {ids.map((raw, i) => {
        const parsed = parseSourceRecord(normalize(raw));
        return (
          <button
            key={`${raw}-${i}`}
            type="button"
            disabled={!parsed.ref}
            onClick={() => parsed.ref && push(parsed.ref)}
            title={parsed.ref ? `Open ${parsed.ref.label}` : String(raw)}
            className="inline-flex h-4 min-w-4 items-center justify-center rounded bg-primary/15 px-1 align-super text-[10px] font-semibold text-primary transition-colors hover:bg-primary/25 disabled:opacity-60"
          >
            {i + 1}
          </button>
        );
      })}
    </span>
  );
}

function SourcesRow({ ids }: { ids: (number | string)[] }) {
  const push = usePeekStore((s) => s.push);
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-12 text-content-dim">
      <span className="font-medium">Sources:</span>
      {ids.map((raw, i) => {
        const agg = typeof raw === "string" ? aggregated(raw) : null;
        if (agg) {
          return (
            <span key={`${raw}-${i}`} className="inline-flex items-center gap-1 rounded-control border border-hairline bg-surface-2/60 px-1.5 py-0.5">
              {agg} · aggregated
            </span>
          );
        }
        const parsed = parseSourceRecord(normalize(raw));
        return (
          <button
            key={`${raw}-${i}`}
            type="button"
            disabled={!parsed.ref}
            onClick={() => parsed.ref && push(parsed.ref)}
            className="inline-flex items-center gap-1 rounded-control border border-hairline bg-surface-2/60 px-1.5 py-0.5 tnum transition-colors hover:bg-surface-2 disabled:opacity-60"
          >
            <span className="text-[10px] font-semibold text-primary">{i + 1}</span>
            {parsed.ref?.label ?? String(raw)}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------- SQL block -------------------------------- */
function SqlBlock({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <div className="overflow-hidden rounded-control border border-hairline">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 bg-surface-2/50 px-2.5 py-1.5 text-12 text-content-dim transition-colors hover:text-content"
      >
        <Database className="size-3.5" />
        <span className="font-medium text-content">SQL executed</span>
        <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px]">read-only · whitelisted SELECT</span>
        <ChevronDown className={cn("ml-auto size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="relative border-t border-hairline bg-surface">
          <button
            type="button"
            onClick={copy}
            className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-control border border-hairline bg-surface-2 px-1.5 py-0.5 text-[11px] text-content-dim transition-colors hover:text-content"
          >
            {copied ? <Check className="size-3 text-accent" /> : <Copy className="size-3" />}
            {copied ? "Copied" : "Copy"}
          </button>
          <pre className="overflow-x-auto px-3 py-2.5 text-12 leading-relaxed text-content">
            <code className="tnum whitespace-pre-wrap break-words font-mono">{sql}</code>
          </pre>
        </div>
      )}
    </div>
  );
}

/* ----------------------------- confidence --------------------------------- */
function ConfidenceChip({ value }: { value: number }) {
  const band = confidenceBand(value);
  return (
    <span
      className={cn(
        "ml-auto inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-12 font-medium",
        band === "high"
          ? "border-transparent bg-accent/15 text-accent"
          : band === "medium"
            ? "border-hairline bg-surface-2 text-content"
            : "border-hairline bg-surface-2 text-content-dim",
      )}
      title={`Model confidence: ${band}`}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          band === "high" ? "bg-accent" : band === "medium" ? "bg-primary" : "bg-content-dim",
        )}
      />
      <span className="tnum">{formatPercent(value, 0)}</span> confidence
    </span>
  );
}
