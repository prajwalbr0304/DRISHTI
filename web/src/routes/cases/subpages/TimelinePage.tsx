import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, CircleDot, FileText, FlaskConical, Gavel, Landmark, MessageSquareText,
  Package, ShieldCheck, UserCheck, type LucideIcon,
} from "lucide-react";
import { api } from "@/api";
import type { CaseDetailResponse, CwTimelineEntry } from "@/api/types";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { caseworkKeys, pretty } from "./casework/caseworkShared";

/* Case Timeline (doc 01 §4.2): now event-backed from CaseEvent + CourtEvent
   (+ statements / seizures / dispositions / outcomes), falling back to derived
   registration/arrest/chargesheet dates for cases without event rows yet. */

const KIND_STYLE: Record<string, { icon: LucideIcon; color: string }> = {
  lifecycle: { icon: FileText, color: "var(--primary)" },
  court: { icon: Landmark, color: "var(--cat-3)" },
  statement: { icon: MessageSquareText, color: "var(--accent)" },
  seizure: { icon: Package, color: "var(--sev-medium)" },
  disposition: { icon: Gavel, color: "var(--cat-5)" },
  outcome: { icon: ShieldCheck, color: "var(--sev-low)" },
  bail: { icon: Gavel, color: "var(--cat-2)" },
  derived: { icon: CircleDot, color: "var(--text-dim)" },
};
const TYPE_ICON: Record<string, LucideIcon> = {
  arrest: UserCheck, incident: AlertTriangle,
};

export function TimelinePage({ caseId, detail }: { caseId: number; detail: CaseDetailResponse }) {
  const q = useQuery({
    queryKey: caseworkKeys.timeline(caseId),
    queryFn: ({ signal }) => api.casework.timeline(caseId, signal),
    enabled: Number.isFinite(caseId) && caseId > 0,
  });

  if (q.isLoading) return <Skeleton className="h-40 w-full" />;

  // Prefer the event-backed casework timeline; fall back to the derived detail one.
  const entries: CwTimelineEntry[] = q.data && q.data.entries.length
    ? q.data.entries
    : detail.timeline.map((e) => ({ date: e.date, kind: "derived", type: e.type, label: e.label, detail: e.detail ?? null }));

  if (!entries.length) {
    return (
      <EmptyState icon={CircleDot} title="No dated events"
                  description="This case has no lifecycle/court events or dated records to plot yet." />
    );
  }

  const eventBacked = !!q.data?.event_backed;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-12 text-content-dim">
        {eventBacked
          ? <Badge variant="primary">Event-backed</Badge>
          : <Badge variant="neutral">Derived from dated records</Badge>}
        <span>{entries.length} event{entries.length === 1 ? "" : "s"}</span>
      </div>

      <ol className="relative space-y-0 border-l border-hairline pl-5">
        {entries.map((e, i) => {
          const s = KIND_STYLE[e.kind] ?? KIND_STYLE.derived;
          const Icon = TYPE_ICON[e.type] ?? s.icon;
          return (
            <li key={`${e.kind}-${e.ref_id ?? i}`} className="relative pb-4">
              <span className="absolute -left-[27px] grid size-5 place-items-center rounded-full ring-4 ring-surface"
                    style={{ background: s.color }}>
                <Icon className="size-3 text-white" />
              </span>
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="tnum text-13 font-medium text-content">{e.date ? formatDate(e.date) : "—"}</span>
                <span className="text-13 text-content">{e.label}</span>
                <Badge variant="neutral" className="capitalize">{e.kind}</Badge>
                {e.detail && <span className="text-12 text-content-dim">{pretty(e.detail)}</span>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
