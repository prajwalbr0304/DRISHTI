import { useNavigate } from "react-router-dom";
import { AlertTriangle, FileText, Flame, MapPinned, Sparkles } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { usePeekStore } from "@/stores/usePeekStore";
import { formatNumber } from "@/lib/utils";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { StatusPipeline, CASE_STAGES } from "@/components/dashboard/StatusPipeline";
import { JurisdictionMap } from "@/components/dashboard/JurisdictionMap";
import { EventList, alertToEvent } from "@/components/dashboard/EventList";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { DashboardGrid, type DashTile } from "@/components/dashboard/DashboardGrid";
import { useAlerts, useCaseload, useHotspots, useTrends } from "@/routes/home/useDashboardData";

/* Investigator Command Center (doc 01 §4.1): caseload · jurisdiction map ·
   KPI band · attention queue · recent activity. Jurisdiction-scoped server-side.
   Cards are movable/resizable (AWS-style) via DashboardGrid. */
export function InvestigatorHome() {
  const navigate = useNavigate();
  const askAbout = useUIStore((s) => s.askAbout);
  const push = usePeekStore((s) => s.push);

  const trends = useTrends();
  const hotspots = useHotspots();
  const alerts = useAlerts();
  const caseload = useCaseload();

  // Merge live per-stage counts onto the canonical pipeline stages.
  const caseloadStages = CASE_STAGES.map((s) => ({
    ...s,
    count: caseload.data?.stages.find((x) => x.key === s.key)?.count ?? null,
  }));

  const urgent = (alerts.data?.alerts ?? []).filter(
    (a) => a.severity === "critical" || a.severity === "high",
  ).length;

  const mappableHotspots = (hotspots.data?.hotspots ?? []).filter(
    (h) => h.centroid_lon != null && h.centroid_lat != null,
  );

  const tiles: DashTile[] = [
    {
      key: "kpi-firs", handle: "self", x: 0, y: 0, w: 3, h: 2, minW: 2, minH: 2,
      el: (
        <KpiCard
          className="h-full"
          icon={<FileText />}
          label="New FIRs (window)"
          value={trends.data?.total}
          delta={trends.data?.mom_pct ?? null}
          spark={trends.data?.series.map((p) => p.count)}
          loading={trends.isLoading}
          error={trends.error}
          hint="Registered crimes in the selected time window; delta is month-on-month."
        />
      ),
    },
    {
      key: "kpi-myalerts", handle: "self", x: 3, y: 0, w: 3, h: 2, minW: 2, minH: 2,
      el: (
        <KpiCard
          className="h-full"
          icon={<AlertTriangle />}
          label="My alerts"
          value={alerts.data?.count}
          loading={alerts.isLoading}
          error={alerts.error}
          improveWhenDown
          hint="Open alerts raised on cases or areas in your jurisdiction. This is a live queue, so it ignores the time window."
        />
      ),
    },
    {
      key: "kpi-urgent", handle: "self", x: 6, y: 0, w: 3, h: 2, minW: 2, minH: 2,
      el: (
        <KpiCard
          className="h-full"
          icon={<AlertTriangle />}
          label="Urgent alerts"
          value={alerts.data ? urgent : undefined}
          loading={alerts.isLoading}
          error={alerts.error}
          hint="The subset of your open alerts at critical or high severity — the queue to work first."
        />
      ),
    },
    {
      key: "kpi-hotspots", handle: "self", x: 9, y: 0, w: 3, h: 2, minW: 2, minH: 2,
      el: (
        <KpiCard
          className="h-full"
          icon={<Flame />}
          label="Hotspots"
          value={hotspots.data?.count}
          loading={hotspots.isLoading}
          error={hotspots.error}
          hint="Spatial clusters detected in your jurisdiction for the selected window. A hotspot is an area-level pattern, never an individual-level judgement."
        />
      ),
    },
    {
      key: "caseload", handle: "header", x: 0, y: 2, w: 6, h: 6, minW: 3, minH: 4,
      el: (
        <Widget
          gridTile
          title="My caseload"
          contextChip={caseload.data ? `${formatNumber(caseload.data.total)} cases` : undefined}
          info={
            <p className="text-content-dim">
              The FIR lifecycle across your cases. Each case sits at exactly one stage, so the
              per-stage counts sum to your total caseload. Live from the Cases API.
            </p>
          }
          loading={caseload.isLoading}
          error={caseload.error}
          empty={!caseload.isLoading && !caseload.error && (caseload.data?.total ?? 0) === 0}
          emptyLabel="No cases in your scope yet."
          onRefresh={() => caseload.refetch()}
        >
          {caseload.data && (
            <div className="py-2">
              <StatusPipeline stages={caseloadStages} funnel />
              <p className="mt-3 text-12 text-content-dim">
                <span className="font-medium text-content">
                  {formatNumber(caseload.data.open_total)}
                </span>{" "}
                open ·{" "}
                <span className="font-medium text-content">
                  {formatNumber(caseload.data.disposed_total)}
                </span>{" "}
                disposed
              </p>
            </div>
          )}
        </Widget>
      ),
    },
    {
      key: "jurisdiction", handle: "header", x: 6, y: 2, w: 6, h: 6, minW: 3, minH: 4,
      el: (
        <Widget
          gridTile
          flush
          title="My jurisdiction"
          contextChip="last window"
          provenance={hotspots.data?.result}
          loading={hotspots.isLoading}
          error={hotspots.error}
          empty={!hotspots.isLoading && !hotspots.error && mappableHotspots.length === 0}
          emptyLabel="No mapped incidents in this scope."
          onRefresh={() => hotspots.refetch()}
          menuItems={[
            { label: "Open in Map & Hotspots", icon: <MapPinned />, onSelect: () => navigate("/map") },
            {
              label: "Ask DRISHTI about this",
              icon: <Sparkles />,
              onSelect: () => askAbout("Summarise incident hotspots in my jurisdiction"),
            },
          ]}
        >
          {hotspots.data && <JurisdictionMap hotspots={mappableHotspots} />}
        </Widget>
      ),
    },
    {
      key: "attention", handle: "header", x: 0, y: 8, w: 6, h: 7, minW: 3, minH: 4,
      el: (
        <Widget
          gridTile
          title="Attention queue"
          contextChip={alerts.data ? String(alerts.data.count) : undefined}
          provenance={alerts.data?.result}
          loading={alerts.isLoading}
          error={alerts.error}
          empty={!alerts.isLoading && !alerts.error && (alerts.data?.alerts.length ?? 0) === 0}
          emptyLabel="Nothing needs your attention right now."
          onRefresh={() => alerts.refetch()}
          flush
        >
          {alerts.data && (
            <div className="px-2 py-1">
              <EventList
                items={alerts.data.alerts
                  .slice(0, 20)
                  .map((a) =>
                    alertToEvent(a, () =>
                      push({ kind: "alert", id: a.alert_id, label: a.title, sublabel: a.district_name ?? a.alert_type }),
                    ),
                  )}
              />
            </div>
          )}
        </Widget>
      ),
    },
    {
      key: "recent", handle: "header", x: 6, y: 8, w: 6, h: 7, minW: 3, minH: 4,
      el: (
        <Widget gridTile title="Recent activity" flush>
          <div className="px-2 py-1">
            <RecentActivity />
          </div>
        </Widget>
      ),
    },
  ];

  return <DashboardGrid id="investigator" tiles={tiles} />;
}
