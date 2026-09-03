import { useState } from "react";
import { useUIStore } from "@/stores/useUIStore";
import { Building2, Radar, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { TrendChart } from "@/components/charts/TrendChart";
import { ForecastSummary } from "@/components/dashboard/ForecastSummary";
import { SocioSignalPanel } from "@/components/dashboard/SocioSignalPanel";
import { DashboardGrid, type DashTile } from "@/components/dashboard/DashboardGrid";
import { NativeSelect } from "@/components/ui/native-select";
import { useForecastMap, useSocio, useTrends } from "@/routes/home/useDashboardData";
import { STATE_WIDE_NOTE } from "@/stores/useScopeStore";
import { useScopeChips } from "@/routes/home/useScopeChips";
import { humanizeKey } from "@/lib/utils";

/* Policymaker Command Center (doc 01 §4.1 + §7): AGGREGATE-ONLY. District-level
   KPIs, trends, forecasts and socio-economic signal. No case list, no point-level
   map, no individual profiles — de-anonymisation is designed out. */
export function PolicymakerHome() {
  const askAbout = useUIStore((s) => s.askAbout);
  const scopeChip = useScopeChips();
  const trends = useTrends();
  const forecast = useForecastMap();

  /* Socio panel selection. Empty string = "let the service pick the strongest
     signal"; only an explicit override re-queries (see useSocio). */
  const [indicator, setIndicator] = useState("");
  const [category, setCategory] = useState("");

  // KPI cards read the un-focused (shared) entry so switching indicator in the
  // panel below never blanks the two counters, which don't depend on it.
  const socio = useSocio();
  const socioPanel = useSocio(indicator || undefined);
  const socioData = socioPanel.data;

  const activeIndicator = indicator || socioData?.focus_indicator || "";
  const activeCategory =
    category ||
    socioData?.narrative.crime_category ||
    socioData?.crime_categories.find((c) => c !== "All Crime") ||
    socioData?.crime_categories[0] ||
    "";

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
      key: "district-forecast", handle: "header", x: 8, y: 2, w: 4, h: 7, minW: 3, minH: 4,
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
    {
      /* h=8: the tallest pane is the 10-row bar chart (~290px) plus its caption,
         so h=10 (620px at rowHeight 44 + 20px gutters) left ~200px of dead space
         under the charts. The gridTile body scrolls, so this cannot clip. */
      key: "socio", handle: "header", x: 0, y: 9, w: 12, h: 8, minW: 4, minH: 6,
      el: (
        <Widget
          gridTile
          title="Socio-economic signal"
          contextChip={scopeChip.stateWide}
          provenance={socioData?.result}
          loading={socioPanel.isLoading}
          error={socioPanel.error}
          empty={!socioPanel.isLoading && !socioPanel.error && !socioData}
          onRefresh={() => socioPanel.refetch()}
          actions={
            <div className="flex items-center gap-2">
              <NativeSelect
                value={indicator}
                onChange={setIndicator}
                options={(socioData?.indicators ?? []).map((i) => ({ value: i, label: humanizeKey(i) }))}
                placeholder={
                  socioData?.focus_indicator
                    ? `Auto · ${humanizeKey(socioData.focus_indicator)}`
                    : "Indicator"
                }
                aria-label="Focus indicator"
                /* Wide enough for the longest "Auto · <indicator>" placeholder
                   (e.g. "Auto · population density"); w-44 clipped it mid-word. */
                className="w-56"
              />
              <NativeSelect
                value={category}
                onChange={setCategory}
                options={(socioData?.crime_categories ?? []).map((c) => ({ value: c, label: c }))}
                placeholder={activeCategory || "Crime category"}
                aria-label="Crime category"
                /* Fits the longest category ("Crimes Against Property"); w-40 clipped it. */
                className="w-48"
              />
            </div>
          }
          menuItems={[
            {
              label: "Ask DRISHTI about this",
              icon: <Sparkles />,
              onSelect: () =>
                askAbout(
                  activeIndicator && activeCategory
                    ? `Explain how ${humanizeKey(activeIndicator)} correlates with per-capita ` +
                        `${activeCategory.toLowerCase()} across districts, with caveats — make clear ` +
                        `this is correlational, not causal.`
                    : "Explain the socio-economic correlations with crime, with caveats",
                ),
            },
          ]}
          info={
            <div className="space-y-2">
              <p>
                Correlations of crime with socio-economic indicators, shown three ways: the
                plain-language read-out, r against every indicator for the chosen crime category, and
                the district scatter with its linear fit. Correlational, never causal; small counts
                are suppressed and omitted rather than estimated.
              </p>
              <p>Rates are per 100,000 population, so the charts don't just redraw the population map.</p>
              <p>{STATE_WIDE_NOTE}</p>
            </div>
          }
        >
          {socioData && activeCategory && (
            <SocioSignalPanel
              data={socioData}
              crimeCategory={activeCategory}
              focusIndicator={activeIndicator}
              onSelectIndicator={setIndicator}
            />
          )}
        </Widget>
      ),
    },
  ];

  return <DashboardGrid id="policymaker" tiles={tiles} />;
}
