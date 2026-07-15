import { AlertTriangle, Flame, TrendingUp, UserCog } from "lucide-react";
import { usePeekStore } from "@/stores/usePeekStore";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { DistrictBars, type BarDatum } from "@/components/dashboard/DistrictBars";
import { EventList, alertToEvent } from "@/components/dashboard/EventList";
import { EmptyState } from "@/components/common/EmptyState";
import { useAlerts, useHotspots, useTrends } from "@/routes/home/useDashboardData";

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

  return (
    <div className="space-y-4">
      {/* Unit KPI band */}
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
          icon={<AlertTriangle />}
          label="Open alerts"
          value={alerts.data?.count}
          loading={alerts.isLoading}
          error={alerts.error}
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

      {/* Load by district + review queue */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Widget
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

        <Widget
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
      </div>

      {/* Officer performance — honest pending (no officer-performance endpoint yet) */}
      <Widget
        title="Station & officer performance"
        info={<p className="text-content-dim">Per-officer clearance, workload and outcomes. Requires the officer-performance API.</p>}
      >
        <EmptyState
          icon={UserCog}
          title="Awaiting the performance API"
          description="Station and officer performance metrics (clearance rate, workload balance, disposal times) land when the transactional Cases/HR endpoints are built."
        />
      </Widget>
    </div>
  );
}
