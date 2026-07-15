import { useNavigate } from "react-router-dom";
import { AlertTriangle, FileText, Flame, MapPinned, Sparkles } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { usePeekStore } from "@/stores/usePeekStore";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { StatusPipeline, CASE_STAGES } from "@/components/dashboard/StatusPipeline";
import { MiniDensity } from "@/components/dashboard/MiniDensity";
import { EventList, alertToEvent } from "@/components/dashboard/EventList";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { useAlerts, useHotspots, useTrends } from "@/routes/home/useDashboardData";

/* Investigator Command Center (doc 01 §4.1): caseload · jurisdiction map ·
   KPI band · attention queue · recent activity. Jurisdiction-scoped server-side. */
export function InvestigatorHome() {
  const navigate = useNavigate();
  const askAbout = useUIStore((s) => s.askAbout);
  const push = usePeekStore((s) => s.push);

  const trends = useTrends();
  const hotspots = useHotspots();
  const alerts = useAlerts();

  const urgent = (alerts.data?.alerts ?? []).filter(
    (a) => a.severity === "critical" || a.severity === "high",
  ).length;

  const densityPoints = (hotspots.data?.hotspots ?? [])
    .filter((h) => h.centroid_lon != null && h.centroid_lat != null)
    .map((h) => ({ lon: h.centroid_lon!, lat: h.centroid_lat!, weight: h.intensity ?? 0.5 }));

  return (
    <div className="space-y-4">
      {/* KPI band */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          icon={<FileText />}
          label="New FIRs (window)"
          value={trends.data?.total}
          delta={trends.data?.mom_pct ?? null}
          spark={trends.data?.series.map((p) => p.count)}
          loading={trends.isLoading}
          error={trends.error}
          hint="Registered crimes in the selected time window; delta is month-on-month."
        />
        <KpiCard
          icon={<AlertTriangle />}
          label="My alerts"
          value={alerts.data?.count}
          loading={alerts.isLoading}
          error={alerts.error}
          improveWhenDown
        />
        <KpiCard
          icon={<AlertTriangle />}
          label="Urgent alerts"
          value={alerts.data ? urgent : undefined}
          loading={alerts.isLoading}
          error={alerts.error}
        />
        <KpiCard
          icon={<Flame />}
          label="Hotspots"
          value={hotspots.data?.count}
          loading={hotspots.isLoading}
          error={hotspots.error}
        />
      </div>

      {/* Hero: caseload + jurisdiction */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Widget
          title="My caseload"
          info={
            <p className="text-content-dim">
              The FIR lifecycle for your assigned cases. Per-stage counts arrive with the Cases API
              (Phase 15c); the pipeline shape is shown now.
            </p>
          }
        >
          <div className="py-2">
            <StatusPipeline stages={CASE_STAGES} currentKey="under_investigation" pending />
            <p className="mt-3 text-12 text-content-dim">
              Caseload counts require the Cases API — coming in Phase 15c.
            </p>
          </div>
        </Widget>

        <Widget
          title="My jurisdiction"
          contextChip="last window"
          provenance={hotspots.data?.result}
          loading={hotspots.isLoading}
          error={hotspots.error}
          empty={!hotspots.isLoading && !hotspots.error && densityPoints.length === 0}
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
          {hotspots.data && <MiniDensity points={densityPoints} />}
        </Widget>
      </div>

      {/* Attention queue + recent activity */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Widget
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

        <Widget title="Recent activity" flush>
          <div className="px-2 py-1">
            <RecentActivity />
          </div>
        </Widget>
      </div>
    </div>
  );
}
