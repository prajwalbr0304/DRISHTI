import { AlertTriangle, CircleDot, FileText, Gavel, UserCheck, type LucideIcon } from "lucide-react";
import type { CaseDetailResponse, CaseTimelineEntry } from "@/api/types";
import { cn, formatDate } from "@/lib/utils";
import { EmptyState } from "@/components/common/EmptyState";

/* Case Timeline (doc 01 §4.2, doc 03 §2.4): horizontal typed lifecycle events. */

const STYLE: Record<string, { icon: LucideIcon; color: string }> = {
  registered: { icon: FileText, color: "var(--primary)" },
  incident: { icon: AlertTriangle, color: "var(--sev-medium)" },
  arrest: { icon: UserCheck, color: "var(--accent)" },
  chargesheet: { icon: Gavel, color: "var(--cat-3)" },
};

export function TimelinePage({ detail }: { detail: CaseDetailResponse }) {
  const events = detail.timeline;
  if (!events.length) {
    return (
      <EmptyState
        icon={CircleDot}
        title="No dated events"
        description="This case has no registered/incident/arrest/chargesheet dates to plot yet."
      />
    );
  }

  const n = events.length;
  const inset = 50 / n;

  return (
    <div className="rounded-card border border-hairline bg-surface p-5">
      <div className="overflow-x-auto pb-2">
        <div className="min-w-[640px]">
          {/* track */}
          <div className="relative h-6">
            <div
              className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-hairline"
              style={{ left: `${inset}%`, right: `${inset}%` }}
            />
            <div className="grid" style={{ gridTemplateColumns: `repeat(${n}, minmax(0,1fr))` }}>
              {events.map((e, i) => (
                <Dot key={i} entry={e} />
              ))}
            </div>
          </div>
          {/* cards */}
          <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${n}, minmax(0,1fr))` }}>
            {events.map((e, i) => (
              <div key={i} className="px-2 text-center">
                <div className="tnum text-12 font-medium text-content">{formatDate(e.date)}</div>
                <div className="mt-0.5 text-12 capitalize text-content-dim">{e.label}</div>
                {e.detail && <div className="mt-0.5 truncate text-12 text-content-dim">{e.detail}</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Dot({ entry }: { entry: CaseTimelineEntry }) {
  const s = STYLE[entry.type] ?? { icon: CircleDot, color: "var(--text-dim)" };
  const Icon = s.icon;
  return (
    <div className="flex items-center justify-center">
      <span
        className={cn("grid size-6 place-items-center rounded-full")}
        style={{ background: s.color }}
      >
        <Icon className="size-3.5 text-white" />
      </span>
    </div>
  );
}
