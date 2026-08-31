import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Loader2, Radio, ShieldAlert } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { SendToBoard } from "@/components/board/SendToBoard";
import { districtName } from "@/stores/useDisasterStore";
import {
  ConfidenceChip, DistrictPicker, FreshnessBanner, KpiTile, Panel, SeverityBadge,
  StatusBadge, SyntheticNote, useErCapabilities,
} from "@/routes/emergency/erShared";

/* Situation Overview — role-adaptive home: active hazards, alerts, readiness
   KPIs, allocated-vs-required, open tasks, unavailable resources, low-confidence
   warnings and a data-freshness banner (Prompt 17 §H). */
export function SituationOverview() {
  const qc = useQueryClient();
  const { canWrite, activeDistrict } = useErCapabilities();

  const overview = useQuery({
    queryKey: ["er", "overview", activeDistrict],
    queryFn: ({ signal }) => api.disaster.overview(activeDistrict ?? undefined, signal),
  });
  const alerts = useQuery({
    queryKey: ["er", "alerts", activeDistrict],
    queryFn: ({ signal }) => api.disaster.alerts({ district_id: activeDistrict ?? undefined }, signal),
  });

  const seed = useMutation({
    mutationFn: () => api.disaster.seed(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["er"] }),
  });
  const liveFeed = useMutation({
    mutationFn: () => api.disaster.ingestFeed("open_meteo_live"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["er"] }),
  });
  const ackAlert = useMutation({
    mutationFn: (alertId: number) => api.disaster.approveAlert(alertId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["er"] }),
  });

  const ov = overview.data;
  const empty = ov && ov.active_hazards === 0 && (ov.hazards?.length ?? 0) === 0
    && ov.feed_freshness.length === 0;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Situation Overview"
        description={`Emergency Response — ${districtName(activeDistrict)}`}
        actions={
          <>
            <DistrictPicker />
            {canWrite && (
              <>
                <Button size="sm" variant="outline" disabled={liveFeed.isPending}
                        onClick={() => liveFeed.mutate()}
                        title="Fetch live rainfall/weather from Open-Meteo (CC BY 4.0)">
                  {liveFeed.isPending ? <Loader2 className="animate-spin" /> : <Radio />}
                  Fetch live feed
                </Button>
                <Button size="sm" variant={empty ? "primary" : "outline"} disabled={seed.isPending}
                        onClick={() => seed.mutate()}>
                  {seed.isPending ? <Loader2 className="animate-spin" /> : <Database />}
                  Seed demo scenario
                </Button>
              </>
            )}
          </>
        }
      />
      {liveFeed.isError && <p className="text-12 text-severity-critical">{errorMessage(liveFeed.error)}</p>}
      {liveFeed.data && (
        <p className="text-11 text-content-dim">
          Live feed ingested (Open-Meteo, CC BY 4.0): status {String((liveFeed.data as { status?: string }).status)},
          {" "}{String((liveFeed.data as { accepted_count?: number }).accepted_count ?? 0)} readings accepted.
        </p>
      )}

      {overview.isError && <p className="text-13 text-severity-critical">{errorMessage(overview.error)}</p>}
      {ov && <FreshnessBanner feeds={ov.feed_freshness} />}

      {/* readiness KPIs */}
      {ov && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <KpiTile label="Active hazards" value={ov.active_hazards}
                   tone={ov.active_hazards ? "warn" : "neutral"}
                   info="Hazards currently in an active or watch state for this district. Area- and period-level only — this is decision support, not an official warning." />
          <KpiTile label="Open alerts" value={ov.open_alerts}
                   tone={ov.open_alerts ? "critical" : "neutral"}
                   info="Alerts raised for this district that no one has acknowledged yet. Every alert needs a human to confirm or dismiss it before it becomes a warning." />
          <KpiTile label="Low-confidence" value={ov.low_confidence_warnings}
                   tone={ov.low_confidence_warnings ? "warn" : "neutral"}
                   hint="escalated to a human"
                   info="Predictions whose confidence fell below the escalation threshold. Rather than acting automatically, these are routed to a human for a decision." />
          <KpiTile label="Stale feeds" value={ov.stale_feeds}
                   tone={ov.stale_feeds ? "warn" : "good"}
                   info="External data feeds that have not refreshed inside their expected window. Stale inputs are surfaced rather than hidden, so you can judge how much to trust the figures above." />
          <KpiTile label="Available resources" value={ov.readiness.available_resources ?? 0} tone="good"
                   info="Resources in this district recorded as available for allocation — neither already dispatched nor marked unavailable." />
          <KpiTile label="Open tasks" value={ov.open_tasks}
                   info="Response-plan tasks for this district that are not yet complete, across every active hazard." />
        </div>
      )}

      {empty && (
        <Panel>
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <ShieldAlert className="size-8 text-content-dim" />
            <p className="text-14 text-content">No Emergency Response data yet.</p>
            {canWrite
              ? <p className="text-12 text-content-dim">Use “Seed demo scenario” to load the synthetic Karnataka hazards.</p>
              : <p className="text-12 text-content-dim">Ask a disaster coordinator to seed the demo scenario.</p>}
          </div>
        </Panel>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* active hazards */}
        <Panel title="Active hazards">
          {overview.isLoading && <Loader2 className="size-4 animate-spin text-content-dim" />}
          <ul className="space-y-2">
            {ov?.hazards.map((h) => (
              <li key={h.hazard_event_id}
                  className="flex items-center gap-2 rounded-control border border-hairline px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-13 font-medium text-content">{h.hazard_code}</span>
                    <StatusBadge status={h.status} />
                    <SeverityBadge severity={h.severity} />
                  </div>
                  <p className="mt-0.5 truncate text-11 text-content-dim">
                    {districtName(h.district_id)} · {h.description}
                  </p>
                </div>
                <SendToBoard size="icon-sm" variant="ghost"
                  target={{ refTable: "HazardEvent", refId: h.hazard_event_id,
                            nodeKind: "hazard_event", label: `${h.hazard_code} · ${districtName(h.district_id)}` }} />
              </li>
            ))}
            {ov && ov.hazards.length === 0 && !empty &&
              <li className="text-12 text-content-dim">No active hazards in scope.</li>}
          </ul>
        </Panel>

        {/* alert acknowledgement (red-zone review queue) */}
        <Panel title="Alerts — review &amp; acknowledge">
          {alerts.isLoading && <Loader2 className="size-4 animate-spin text-content-dim" />}
          <ul className="space-y-2">
            {alerts.data?.alerts.map((a) => (
              <li key={a.alert_id}
                  className="flex items-center gap-2 rounded-control border border-hairline px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-13 font-medium text-content">{a.title}</span>
                    <Badge variant={a.status === "proposed" ? "high" : "critical"}>{a.status}</Badge>
                    <ConfidenceChip value={a.confidence} />
                    <Badge variant="neutral">synthetic</Badge>
                  </div>
                  {a.message && <p className="mt-0.5 truncate text-11 text-content-dim">{a.message}</p>}
                </div>
                {canWrite && a.status === "proposed" && (
                  <Button size="sm" variant="outline" disabled={ackAlert.isPending}
                          onClick={() => ackAlert.mutate(a.alert_id)}>
                    Confirm warning
                  </Button>
                )}
              </li>
            ))}
            {alerts.data && alerts.data.alerts.length === 0 &&
              <li className="text-12 text-content-dim">No hazard alerts.</li>}
          </ul>
          {ackAlert.isError && <p className="mt-2 text-12 text-severity-critical">{errorMessage(ackAlert.error)}</p>}
        </Panel>
      </div>

      <SyntheticNote />
    </div>
  );
}
