import { AlertTriangle, MapPin } from "lucide-react";
import type { AlertFeature, AlertSeverity } from "@/api/types";
import { cn, timeAgo } from "@/lib/utils";
import { Badge, type BadgeProps } from "@/components/ui/badge";

/* ============================================================================
   Event list (doc 01 §5 #4/#event-list). Newest-first actionable items —
   powers the Investigator attention queue, Supervisor review queue, and the
   Analyst emerging-trend feed. Severity always pairs colour with an icon + a
   label (never colour alone).
   ========================================================================== */

export interface EventItem {
  id: string | number;
  title: string;
  severity?: AlertSeverity;
  meta?: string;
  metric?: string;
  time?: string | null;
  onClick?: () => void;
}

const SEV_BADGE: Record<AlertSeverity, BadgeProps["variant"]> = {
  critical: "critical",
  high: "high",
  medium: "medium",
  low: "low",
  info: "neutral",
};

function sevIconClass(sev?: AlertSeverity) {
  switch (sev) {
    case "critical":
      return "text-severity-critical";
    case "high":
      return "text-severity-high";
    case "medium":
      return "text-severity-medium";
    default:
      return "text-content-dim";
  }
}

export function EventList({ items }: { items: EventItem[] }) {
  return (
    <div className="max-h-[280px] overflow-y-auto">
      {items.map((it) => (
        <button
          key={it.id}
          type="button"
          onClick={it.onClick}
          className="flex w-full items-start gap-2.5 rounded-control px-2 py-2 text-left transition-colors hover:bg-surface-2"
        >
          <AlertTriangle className={cn("mt-0.5 size-4 shrink-0", sevIconClass(it.severity))} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate text-13 font-medium text-content">{it.title}</span>
              {it.severity && (
                <Badge variant={SEV_BADGE[it.severity]} className="ml-auto shrink-0 capitalize">
                  {it.severity}
                </Badge>
              )}
            </div>
            {it.metric && <div className="mt-0.5 truncate text-12 text-content-dim">{it.metric}</div>}
            <div className="mt-1 flex items-center gap-2 text-12 text-content-dim">
              {it.meta && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="size-3" />
                  {it.meta}
                </span>
              )}
              {it.time && <span className="tnum">{timeAgo(it.time)}</span>}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

/** Map a live AlertFeature into an EventItem. */
export function alertToEvent(a: AlertFeature, onClick?: () => void): EventItem {
  return {
    id: a.alert_id,
    title: a.title,
    severity: a.severity,
    meta: a.district_name ?? a.alert_type,
    metric: a.message ?? undefined,
    time: a.created_at,
    onClick,
  };
}
