import { AlertTriangle, Flame, TrendingUp } from "lucide-react";
import { usePeekStore } from "@/stores/usePeekStore";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { DistrictBars, type BarDatum } from "@/components/dashboard/DistrictBars";
import { EventList, alertToEvent } from "@/components/dashboard/EventList";
import { DashboardGrid, type DashTile } from "@/components/dashboard/DashboardGrid";
import { useAlerts, useHotspots, useTrends } from "@/routes/home/useDashboardData";
import { StationPerformance } from "@/routes/home/StationPerformance";

const REVIEWED = ["resolved", "closed", "acknowledged", "ack", "dismissed", "actioned"];

/* Supervisor Command Center (doc 01 §4.1): swaps caseload for unit performance
   + a review queue. Unit-scoped server-side. */
export function SupervisorHome() {
  const push = usePeekStore((s) => s.push);

  const trends = useTrends();
  const hotspots = useHotspots();
  const alerts = useAlerts();

  const urgent = (alerts.data?.alerts ?? []).filter(
    (a) => a.severity === "critical" || a.severity === "high",
  ).length;

  // Load by district — sum hotspot case-load per district (single-hue comparison).
  const byDistrict = new Map<string, number>();
  for (const h of hotspots.data?.hotspots ?? []) {
    const key = h.district_name ?? "Unknown";
    byDistrict.set(key, (byDistrict.get(key) ?? 0) + (h.case_count ?? 1));
  }
  const districtBars: BarDatum[] = [...byDistrict.entries()].map(([label, value]) => ({
    key: label,
    label,
    value,
  }));

  // Review queue — alerts still needing supervisor action.
  const allAlerts = alerts.data?.alerts ?? [];
  const needsReview = allAlerts.filter((a) => !REVIEWED.includes((a.status ?? "").toLowerCase()));
  const review = needsReview.length ? needsReview : allAlerts;

  const tiles: DashTile[] = [
    {
      key: "kpi-incidents", handle: "self", x: 0, y: 0, w: 3, h: 2, minW: 2, minH: 2,
      el: (
        <KpiCard
          className="h-full"
          icon={<TrendingUp />}
          label="Incidents (window)"
          value={trends.data?.total}
          delta={trends.data?.mom_pct ?? null}
          spark={trends.data?.series.map((p) => p.count)}
          loading={trends.isLoading}
          error={trends.error}
        />
      ),
    },
    {
      key: "kpi-openalerts", handle: "self", x: 3, y: 0, w: 3, h: 2, minW: 2, minH: 2,
      el: (
        <KpiCard
          className="h-full"
          icon={<AlertTriangle />}
          label="Open alerts"
          value={alerts.data?.count}
          loading={alerts.isLoading}
          error={alerts.error}
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
        />
      ),
    },
    {
      key: "load-district", handle: "header", x: 0, y: 2, w: 6, h: 7, minW: 3, minH: 4,
      el: (
        <Widget
          gridTile
          title="Load by district"
          contextChip="hotspot case-load"
          provenance={hotspots.data?.result}
          loading={hotspots.isLoading}
          error={hotspots.error}
          empty={!hotspots.isLoading && !hotspots.error && districtBars.length === 0}
          emptyLabel="No hotspot load in this scope."
          onRefresh={() => hotspots.refetch()}
          info={
            <p className="text-content-dim">
              Aggregate hotspot case-load per district — a comparative read on where the unit's
              pressure sits. Officer-level performance arrives with the Cases API.
            </p>
          }
        >
          {hotspots.data && <DistrictBars data={districtBars} unit=" cases" />}
        </Widget>
      ),
    },
    {
      key: "review-queue", handle: "header", x: 6, y: 2, w: 6, h: 7, minW: 3, minH: 4,
      el: (
        <Widget
          gridTile
          title="Review queue"
          contextChip={review.length ? String(review.length) : undefined}
          provenance={alerts.data?.result}
          loading={alerts.isLoading}
          error={alerts.error}
          empty={!alerts.isLoading && !alerts.error && review.length === 0}
          emptyLabel="Nothing awaiting review."
          onRefresh={() => alerts.refetch()}
          flush
        >
          {alerts.data && (
            <div className="px-2 py-1">
              <EventList
                items={review
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
      key: "performance", handle: "header", x: 0, y: 9, w: 12, h: 8, minW: 4, minH: 5,
      el: (
        <Widget
          gridTile
          title="Station & officer performance"
          info={
            <p className="text-content-dim">
              Aggregate, explainable operational metrics from the committed case record —
              active workload, ageing, chargesheet throughput, time-to-chargesheet, overdue
              reviews and workload balance. Scoped server-side; no punitive per-officer ranking.
            </p>
          }
        >
          <StationPerformance />
        </Widget>
      ),
    },
  ];

  return <DashboardGrid id="supervisor" tiles={tiles} />;
}
