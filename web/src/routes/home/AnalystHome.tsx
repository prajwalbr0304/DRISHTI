import { useNavigate } from "react-router-dom";
import { AlertTriangle, Flame, Network as NetworkIcon, Sparkles, TrendingUp, Users } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { usePeekStore } from "@/stores/usePeekStore";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { TrendChart } from "@/components/charts/TrendChart";
import { EventList, alertToEvent } from "@/components/dashboard/EventList";
import { PersonsOfInterest } from "@/components/dashboard/PersonsOfInterest";
import { SavedCohorts } from "@/components/dashboard/SavedCohorts";
import { useAlerts, useCentrality, useHotspots, useTrends } from "@/routes/home/useDashboardData";

const EMERGING_TYPES = ["emerging_hotspot", "spike", "anomaly", "emerging", "trend"];

/* Analyst Command Center (doc 01 §4.1): saved cohorts · emerging-trend feed ·
   network-of-interest shortcut · aggregate trends. Also serves super_admin. */
export function AnalystHome() {
  const navigate = useNavigate();
  const askAbout = useUIStore((s) => s.askAbout);
  const push = usePeekStore((s) => s.push);

  const trends = useTrends();
  const hotspots = useHotspots();
  const alerts = useAlerts();
  const centrality = useCentrality(12);

  const poi = centrality.data?.persons_of_interest ?? [];
  const emergingAll = alerts.data?.alerts ?? [];
  const emerging = emergingAll.filter((a) =>
    EMERGING_TYPES.some((t) => a.alert_type?.toLowerCase().includes(t)),
  );
  const feed = emerging.length ? emerging : emergingAll;

  return (
    <div className="space-y-4">
      {/* KPI band */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          icon={<TrendingUp />}
          label="Incidents (window)"
          value={trends.data?.total}
          delta={trends.data?.mom_pct ?? null}
          spark={trends.data?.series.map((p) => p.count)}
          loading={trends.isLoading}
          error={trends.error}
        />
        <KpiCard
          icon={<Flame />}
          label="Active hotspots"
          value={hotspots.data?.count}
          loading={hotspots.isLoading}
          error={hotspots.error}
        />
        <KpiCard
          icon={<AlertTriangle />}
          label="Active alerts"
          value={alerts.data?.count}
          loading={alerts.isLoading}
          error={alerts.error}
        />
        <KpiCard
          icon={<Users />}
          label="Persons of interest"
          value={centrality.data ? poi.length : undefined}
          loading={centrality.isLoading}
          error={centrality.error}
          hint="Top entities by graph centrality (PageRank / betweenness)."
        />
      </div>

      {/* Trend + network of interest */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Widget
          className="lg:col-span-2"
          title="Emerging trend"
          contextChip="window"
          provenance={trends.data?.result}
          loading={trends.isLoading}
          error={trends.error}
          empty={!trends.isLoading && !trends.error && (trends.data?.series.length ?? 0) === 0}
          onRefresh={() => trends.refetch()}
          menuItems={[
            {
              label: "Ask DRISHTI about this",
              icon: <Sparkles />,
              onSelect: () => askAbout("Explain the recent crime trend and any anomalies"),
            },
          ]}
          info={
            <p className="text-content-dim">
              Monthly incidents with a rolling-mean band; red dots are statistical anomalies (the
              emerging-trend signal).
            </p>
          }
        >
          {trends.data && <TrendChart series={trends.data.series} />}
        </Widget>

        <Widget
          title="Network of interest"
          provenance={centrality.data?.result}
          loading={centrality.isLoading}
          error={centrality.error}
          empty={!centrality.isLoading && !centrality.error && poi.length === 0}
          emptyLabel="No centrality results yet."
          onRefresh={() => centrality.refetch()}
          menuItems={[
            { label: "Open in Network Analysis", icon: <NetworkIcon />, onSelect: () => navigate("/network") },
          ]}
          flush
        >
          {centrality.data && (
            <div className="px-2 py-1">
              <PersonsOfInterest
                people={poi}
                onSelect={(p) =>
                  push({
                    kind: "person",
                    id: p.entity_id,
                    label: p.label ?? `Entity ${p.entity_id}`,
                    sublabel: p.entity_type,
                  })
                }
              />
            </div>
          )}
        </Widget>
      </div>

      {/* Emerging feed + saved cohorts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Widget
          title="Emerging-trend feed"
          contextChip={feed.length ? String(feed.length) : undefined}
          provenance={alerts.data?.result}
          loading={alerts.isLoading}
          error={alerts.error}
          empty={!alerts.isLoading && !alerts.error && feed.length === 0}
          emptyLabel="No emerging signals right now."
          onRefresh={() => alerts.refetch()}
          flush
        >
          {alerts.data && (
            <div className="px-2 py-1">
              <EventList
                items={feed
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

        <Widget
          title="Saved lenses"
          info={<p className="text-content-dim">Named, reusable scopes. Save the current time window and re-apply it anywhere.</p>}
        >
          <SavedCohorts />
        </Widget>
      </div>
    </div>
  );
}
