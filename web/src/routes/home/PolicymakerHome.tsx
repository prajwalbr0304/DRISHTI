import { useUIStore } from "@/stores/useUIStore";
import { Building2, Radar, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { TrendChart } from "@/components/charts/TrendChart";
import { ForecastSummary } from "@/components/dashboard/ForecastSummary";
import { SocioNarrativeCard } from "@/components/dashboard/SocioNarrativeCard";
import { DashboardGrid, type DashTile } from "@/components/dashboard/DashboardGrid";
import { useForecastMap, useSocio, useTrends } from "@/routes/home/useDashboardData";
import { STATE_WIDE_NOTE } from "@/stores/useScopeStore";
import { useScopeChips } from "@/routes/home/useScopeChips";

/* Policymaker Command Center (doc 01 §4.1 + §7): AGGREGATE-ONLY. District-level
   KPIs, trends, forecasts and socio-economic signal. No case list, no point-level
   map, no individual profiles — de-anonymisation is designed out. */
export function PolicymakerHome() {
  const askAbout = useUIStore((s) => s.askAbout);
  const scopeChip = useScopeChips();
  const trends = useTrends();
  const socio = useSocio();
  const forecast = useForecastMap();

  const predicted = (forecast.data?.cells ?? []).reduce((s, c) => s + (c.predicted_count ?? 0), 0);

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
          hint="Total recorded incidents across the range for the selected time window. The delta compares against the prior period of equal length; the sparkline shows the last 12 periods."
        />
      ),
    },
    {
      key: "kpi-predicted", handle: "self", x: 3, y: 0, w: 3, h: 2, minW: 2, minH: 2,
      el: (
        <KpiCard
          className="h-full"
          icon={<Radar />}
          label="Predicted next period"
          value={forecast.data ? Math.round(predicted) : undefined}
          loading={forecast.isLoading}
          error={forecast.error}
          hint="Sum of fused district forecasts for the next horizon."
        />
      ),
    },
    {
      key: "kpi-districts", handle: "self", x: 6, y: 0, w: 3, h: 2, minW: 2, minH: 2,
      el: (
        <KpiCard
          className="h-full"
          icon={<Building2 />}
          label="Districts analysed"
          value={socio.data?.districts_analysed}
          loading={socio.isLoading}
          error={socio.error}
          hint={`Districts with enough volume to support district-level correlation. Districts below the k-anonymity threshold are excluded rather than estimated. ${STATE_WIDE_NOTE}`}
        />
      ),
    },
    {
      key: "kpi-suppressed", handle: "self", x: 9, y: 0, w: 3, h: 2, minW: 2, minH: 2,
      el: (
        <KpiCard
          className="h-full"
          icon={<ShieldCheck />}
          label="Cells suppressed"
          value={socio.data?.suppressed_cells}
          loading={socio.isLoading}
          error={socio.error}
          hint={`Small-count cells hidden for k-anonymity — privacy by design. ${STATE_WIDE_NOTE}`}
        />
      ),
    },
    {
      key: "state-trend", handle: "header", x: 0, y: 2, w: 8, h: 7, minW: 4, minH: 4,
      el: (
        <Widget
          gridTile
          title="State crime trend"
          contextChip={`${scopeChip.trends} · window`}
          provenance={trends.data?.result}
          loading={trends.isLoading}
          error={trends.error}
          empty={!trends.isLoading && !trends.error && (trends.data?.series.length ?? 0) === 0}
          onRefresh={() => trends.refetch()}
        >
          {trends.data && (
            <div className="h-full min-h-[220px] w-full">
              <TrendChart series={trends.data.series} fill />
            </div>
          )}
        </Widget>
      ),
    },
    {
      key: "district-forecast", handle: "header", x: 8, y: 2, w: 4, h: 7, minW: 3, minH: 4,
      el: (
        <Widget
          gridTile
          title="District forecast"
          contextChip={`fused · ${scopeChip.forecast}`}
          provenance={forecast.data?.result}
          loading={forecast.isLoading}
          error={forecast.error}
          empty={!forecast.isLoading && !forecast.error && (forecast.data?.cells.length ?? 0) === 0}
          emptyLabel="No forecast written yet."
          onRefresh={() => forecast.refetch()}
        >
          {forecast.data && <ForecastSummary data={forecast.data} />}
        </Widget>
      ),
    },
    {
      key: "socio", handle: "header", x: 0, y: 9, w: 12, h: 7, minW: 4, minH: 4,
      el: (
        <Widget
          gridTile
          title="Socio-economic signal"
          contextChip={`correlational · ${scopeChip.socio}`}
          provenance={socio.data?.result}
          loading={socio.isLoading}
          error={socio.error}
          onRefresh={() => socio.refetch()}
          menuItems={[
            {
              label: "Ask DRISHTI about this",
              icon: <Sparkles />,
              onSelect: () => askAbout("Explain the socio-economic correlations with crime, with caveats"),
            },
          ]}
          info={
            <div className="space-y-2">
              <p>
                Correlations of crime with socio-economic indicators. Correlational, never causal;
                small counts are suppressed.
              </p>
              <p>{STATE_WIDE_NOTE}</p>
            </div>
          }
        >
          {socio.data && <SocioNarrativeCard data={socio.data} />}
        </Widget>
      ),
    },
  ];

  return <DashboardGrid id="policymaker" tiles={tiles} />;
}
