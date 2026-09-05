import { useState } from "react";
import { Building2, Radar, ShieldCheck, TrendingUp } from "lucide-react";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { TrendChart } from "@/components/charts/TrendChart";
import { ForecastSummary } from "@/components/dashboard/ForecastSummary";
import { DashboardGrid, type DashTile } from "@/components/dashboard/DashboardGrid";
import { useForecastMap, useSocio, useTrends } from "@/routes/home/useDashboardData";
import { socioTiles } from "@/routes/home/socioTiles";
import { STATE_WIDE_NOTE } from "@/stores/useScopeStore";
import { useScopeChips } from "@/routes/home/useScopeChips";
import { defaultCrimeCategory } from "@/lib/socio";

/* Policymaker Command Center (doc 01 §4.1 + §7): AGGREGATE-ONLY. District-level
   KPIs, trends, forecasts and socio-economic signal. No case list, no point-level
   map, no individual profiles — de-anonymisation is designed out. */
export function PolicymakerHome() {
  const scopeChip = useScopeChips();
  const trends = useTrends();
  const forecast = useForecastMap();

  /* Page-level default crime type for the socio band. Empty = follow the
     service's narrative category; each indicator box may override it. */
  const [category, setCategory] = useState("");

  /* One request feeds the whole band: the response carries the district panel
     and a fit per cell, so every indicator box builds its own series client-side
     instead of re-querying per indicator. */
  const socio = useSocio();
  const socioData = socio.data;
  const activeCategory = category || (socioData ? defaultCrimeCategory(socioData) : "");

  const predicted = (forecast.data?.cells ?? []).reduce((s, c) => s + (c.predicted_count ?? 0), 0);

  const tiles: DashTile[] = [
    {
      key: "kpi-incidents", handle: "self", x: 0, y: 0, w: 3, h: 2, minW: 2, minH: 2, xl: { x: 0, y: 0, w: 4, h: 2 },
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
      key: "kpi-predicted", handle: "self", x: 3, y: 0, w: 3, h: 2, minW: 2, minH: 2, xl: { x: 4, y: 0, w: 4, h: 2 },
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
      key: "kpi-districts", handle: "self", x: 6, y: 0, w: 3, h: 2, minW: 2, minH: 2, xl: { x: 8, y: 0, w: 4, h: 2 },
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
      key: "kpi-suppressed", handle: "self", x: 9, y: 0, w: 3, h: 2, minW: 2, minH: 2, xl: { x: 12, y: 0, w: 4, h: 2 },
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
      key: "state-trend", handle: "header", x: 0, y: 2, w: 8, h: 7, minW: 4, minH: 4, xl: { x: 0, y: 2, w: 16, h: 7 },
      el: (
        <Widget
          gridTile
          title="State crime trend"
          contextChip={scopeChip.scoped}
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
      key: "district-forecast", handle: "header", x: 8, y: 2, w: 4, h: 7, minW: 3, minH: 4, xl: { x: 16, y: 0, w: 8, h: 9 },
      el: (
        <Widget
          gridTile
          title="District forecast"
          contextChip={scopeChip.scoped}
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
    /* Socio-economic band: a read-out plus one box per indicator, each with its own
       crime-type selector; geography is the shared top-bar district selector.
       Separate tiles rather than one container, so a seat can move, resize or
       dismiss individual indicators. */
    ...socioTiles({
      data: socioData,
      loading: socio.isLoading,
      error: socio.error,
      onRefresh: () => socio.refetch(),
      category: activeCategory,
      onCategoryChange: setCategory,
      stateWideChip: scopeChip.stateWide,
      startY: 9,
      xlStartY: 9,
    }),
  ];

  return <DashboardGrid id="policymaker" tiles={tiles} />;
}
