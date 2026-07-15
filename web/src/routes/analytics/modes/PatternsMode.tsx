import { useState } from "react";
import {
  ChevronDown,
  Clock,
  Fingerprint,
  MapPin,
  Repeat,
  Share2,
  Sparkles,
  UserRoundCheck,
  Zap,
} from "lucide-react";
import type { CrimePatternCard, PatternType } from "@/api/types";
import { useUIStore } from "@/stores/useUIStore";
import { usePeekStore } from "@/stores/usePeekStore";
import { cn, formatNumber, formatPercent } from "@/lib/utils";
import { Widget } from "@/components/widget/Widget";
import { Badge } from "@/components/ui/badge";
import { NativeSelect } from "@/components/ui/native-select";
import { useFilterOptions, usePatterns } from "@/routes/analytics/useAnalyticsData";

/* Crime Patterns (doc 01 §4.6): CrimePattern detections — serial, MO-match,
   spatial, temporal, network — as pattern cards, each expanding to the linked
   cases that evidence it (CrimePatternCase). Individual-case turf, so this
   sub-page is gated out for policymakers upstream. */

const TYPE_META: Record<string, { label: string; icon: React.ElementType }> = {
  serial: { label: "Serial", icon: Repeat },
  spree: { label: "Spree", icon: Zap },
  modus_operandi: { label: "Modus operandi", icon: Fingerprint },
  temporal: { label: "Temporal", icon: Clock },
  spatial: { label: "Spatial", icon: MapPin },
  network: { label: "Network", icon: Share2 },
  repeat_offender: { label: "Repeat offender", icon: UserRoundCheck },
};

function typeMeta(t: string) {
  return TYPE_META[t] ?? { label: t, icon: Fingerprint };
}

export function PatternsMode() {
  const filters = useFilterOptions();
  const [patternType, setPatternType] = useState<PatternType | "">("");
  const [headId, setHeadId] = useState<string>("");

  const q = usePatterns({
    pattern_type: patternType || undefined,
    crime_head_id: headId ? Number(headId) : undefined,
  });
  const data = q.data;
  const items = data?.items ?? [];
  const empty = !q.isLoading && !q.error && items.length === 0;

  return (
    <div className="space-y-4">
      {/* Type filter pills + head selector */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1">
          <TypePill active={!patternType} label="All types" onClick={() => setPatternType("")} />
          {Object.entries(data?.by_type ?? {}).map(([t, n]) => (
            <TypePill
              key={t}
              active={patternType === t}
              label={`${typeMeta(t).label} (${n})`}
              icon={typeMeta(t).icon}
              onClick={() => setPatternType(t as PatternType)}
            />
          ))}
        </div>
        <NativeSelect
          value={headId}
          onChange={setHeadId}
          options={(filters.data?.crime_heads ?? []).map((h) => ({ value: String(h.id), label: h.name ?? `Head ${h.id}` }))}
          placeholder="All crime heads"
          aria-label="Crime head"
          className="w-52"
        />
      </div>

      <Widget
        title="Detected crime patterns"
        contextChip={data ? `${data.total} active` : undefined}
        provenance={data?.result}
        loading={q.isLoading}
        error={q.error}
        empty={empty}
        emptyLabel="No active patterns for this scope."
        onRefresh={() => q.refetch()}
        info={
          <p className="text-content-dim">
            Patterns detected across cases (serial, modus-operandi, temporal, spatial, network).
            Each card opens the FIRs that evidence it. Decision support — a lead to verify, not a verdict.
          </p>
        }
        flush
      >
        <div className="space-y-2 px-3 py-2">
          {items.map((p) => (
            <PatternRow key={p.pattern_id} pattern={p} />
          ))}
        </div>
      </Widget>
    </div>
  );
}

function TypePill({
  active,
  label,
  icon: Icon,
  onClick,
}: {
  active: boolean;
  label: string;
  icon?: React.ElementType;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-control px-2.5 py-1.5 text-12 font-medium transition-colors",
        active ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
      )}
    >
      {Icon && <Icon className="size-3.5" />}
      {label}
    </button>
  );
}

function PatternRow({ pattern: p }: { pattern: CrimePatternCard }) {
  const [open, setOpen] = useState(false);
  const askAbout = useUIStore((s) => s.askAbout);
  const push = usePeekStore((s) => s.push);
  const meta = typeMeta(p.pattern_type);
  const Icon = meta.icon;
  const conf = p.confidence ?? 0;
  const hidden = Math.max(0, p.linked_case_count - p.cases.length);

  return (
    <div className="rounded-card border border-hairline bg-surface-2/40">
      <div className="flex items-start gap-3 p-3">
        <div className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-control bg-surface-2 text-content-dim">
          <Icon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-14 font-semibold text-content">{p.name}</span>
            <Badge variant="neutral">{meta.label}</Badge>
            {p.crime_group && <Badge variant="neutral">{p.crime_group}</Badge>}
          </div>
          {p.description && <p className="mt-1 text-13 text-content-dim">{p.description}</p>}

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-12 text-content-dim">
            <span className="inline-flex items-center gap-1.5">
              confidence
              <span className="relative inline-block h-1.5 w-16 overflow-hidden rounded-full bg-surface-2 align-middle">
                <span className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: `${Math.min(100, conf * 100)}%` }} />
              </span>
              <span className="tnum font-medium text-content">{formatPercent(conf, 0)}</span>
            </span>
            <span className="tnum">{formatNumber(p.linked_case_count)} linked case(s)</span>
            {p.model_version && <code className="rounded bg-surface-2 px-1.5 py-0.5">{p.model_version}</code>}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            title="Explain this pattern in Ask DRISHTI"
            onClick={() =>
              askAbout(
                `Explain the "${p.name}" ${meta.label.toLowerCase()} crime pattern — what links its ` +
                  `${p.linked_case_count} cases, and what should an investigator check next?`,
              )
            }
            className="grid size-7 place-items-center rounded-control text-content-dim transition-colors hover:bg-surface-2 hover:text-content"
          >
            <Sparkles className="size-4" />
          </button>
          {p.cases.length > 0 && (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              className="grid size-7 place-items-center rounded-control text-content-dim transition-colors hover:bg-surface-2 hover:text-content"
            >
              <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
            </button>
          )}
        </div>
      </div>

      {open && p.cases.length > 0 && (
        <div className="border-t border-hairline">
          <ul className="divide-y divide-hairline">
            {p.cases.map((c) => (
              <li key={c.case_id}>
                <button
                  type="button"
                  onClick={() =>
                    push({
                      kind: "case",
                      id: c.case_id,
                      label: c.crime_no ?? `Case ${c.case_id}`,
                      sublabel: [c.crime_group, c.district].filter(Boolean).join(" · ") || undefined,
                    })
                  }
                  className="flex w-full items-center gap-3 px-4 py-2 text-left transition-colors hover:bg-surface-2/60"
                >
                  <span className="min-w-0 flex-1">
                    <span className="tnum block truncate text-13 font-medium text-content">
                      {c.crime_no ?? `Case ${c.case_id}`}
                    </span>
                    <span className="block truncate text-12 text-content-dim">
                      {[c.crime_group, c.district, c.status].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  {c.registered_date && (
                    <span className="tnum shrink-0 text-12 text-content-dim">{c.registered_date}</span>
                  )}
                  {c.relevance != null && (
                    <span className="tnum shrink-0 text-12 text-content-dim">
                      {formatPercent(c.relevance, 0)}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
          {hidden > 0 && (
            <p className="px-4 py-2 text-12 text-content-dim">
              + {formatNumber(hidden)} more evidencing case(s) not shown.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
