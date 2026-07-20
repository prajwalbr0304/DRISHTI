import { useQuery } from "@tanstack/react-query";
import { Activity, RefreshCw, ShieldCheck } from "lucide-react";
import { api } from "@/api";
import { Badge } from "@/components/ui/badge";

/* Prompt 20 Part E — Live Command Center freshness strip. Shows the committed-FIR
   projection flow's transport, processed count, per-projection freshness and the
   no-person-rescore / no-auto-dispatch guarantees. Polls locally (Catalyst Signal
   in Prompt 23). Non-blocking: renders nothing on error. */

const LABELS: Record<string, string> = {
  district_statistic: "District stats",
  supervisor_workload: "Supervisor workload",
  hotspot_near_repeat: "Hotspot / near-repeat",
};

function fresh(seconds?: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

export function LiveFreshness() {
  const q = useQuery({
    queryKey: ["livefeed", "freshness"],
    queryFn: ({ signal }) => api.livefeed.freshness(signal),
    refetchInterval: 15000,           // poll locally; single Catalyst Signal in Prompt 23
  });

  if (q.error || !q.data) return null;
  const d = q.data;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-card border border-hairline bg-surface px-3 py-2 text-12">
      <span className="inline-flex items-center gap-1 font-medium text-content">
        <Activity className="size-3.5 text-primary" /> Live updates
      </span>
      <Badge variant="neutral">{d.processed_count} committed FIR(s) this session</Badge>
      {d.duplicate_suppressed > 0 && (
        <Badge variant="neutral">{d.duplicate_suppressed} duplicate(s) suppressed</Badge>
      )}
      {Object.entries(d.projections).map(([k, st]) => (
        <span key={k} className="inline-flex items-center gap-1 text-content-dim">
          <RefreshCw className="size-3" />
          {LABELS[k] ?? k}: {st.processed_count > 0 ? fresh(st.freshness_seconds) : "idle"}
        </span>
      ))}
      <span className="inline-flex items-center gap-1 text-content-dim">
        <ShieldCheck className="size-3" />
        no person re-scoring · no auto-dispatch
      </span>
      <span className="ml-auto text-11 text-content-dim">{d.transport}</span>
    </div>
  );
}
