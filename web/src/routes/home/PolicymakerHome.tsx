import { useUIStore } from "@/stores/useUIStore";
import { Building2, Radar, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { TrendChart } from "@/components/charts/TrendChart";
import { ForecastSummary } from "@/components/dashboard/ForecastSummary";
import { SocioNarrativeCard } from "@/components/dashboard/SocioNarrativeCard";
import { useForecastMap, useSocio, useTrends } from "@/routes/home/useDashboardData";

/* Policymaker Command Center (doc 01 §4.1 + §7): AGGREGATE-ONLY. District-level
   KPIs, trends, forecasts and socio-economic signal. No case list, no point-level
   map, no individual profiles — de-anonymisation is designed out. */
export function PolicymakerHome() {
  const askAbout = useUIStore((s) => s.askAbout);
  const trends = useTrends();
  const socio = useSocio();
  const forecast = useForecastMap();

  const predicted = (forecast.data?.cells ?? []).reduce((s, c) => s + (c.predicted_count ?? 0), 0);

  return (
    <div className="space-y-4">
      {/* Aggregate KPI band */}
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
          icon={<Radar />}
          label="Predicted next period"
          value={forecast.data ? Math.round(predicted) : undefined}
          loading={forecast.isLoading}
          error={forecast.error}
          hint="Sum of fused district forecasts for the next horizon."
        />
        <KpiCard
          icon={<Building2 />}
          label="Districts analysed"
          value={socio.data?.districts_analysed}
          loading={socio.isLoading}
          error={socio.error}
        />
        <KpiCard
          icon={<ShieldCheck />}
          label="Cells suppressed"
          value={socio.data?.suppressed_cells}
          loading={socio.isLoading}
          error={socio.error}
          hint="Small-count cells hidden for k-anonymity — privacy by design."
        />
      </div>

      {/* State trend + district forecast */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Widget
          className="lg:col-span-2"
          title="State crime trend"
          contextChip="aggregate · window"
          provenance={trends.data?.result}
          loading={trends.isLoading}
          error={trends.error}
          empty={!trends.isLoading && !trends.error && (trends.data?.series.length ?? 0) === 0}
          onRefresh={() => trends.refetch()}
        >
          {trends.data && <TrendChart series={trends.data.series} />}
        </Widget>

        <Widget
          title="District forecast"
          contextChip="fused"
          provenance={forecast.data?.result}
          loading={forecast.isLoading}
          error={forecast.error}
          empty={!forecast.isLoading && !forecast.error && (forecast.data?.cells.length ?? 0) === 0}
          emptyLabel="No forecast written yet."
          onRefresh={() => forecast.refetch()}
        >
          {forecast.data && <ForecastSummary data={forecast.data} />}
        </Widget>
      </div>

      {/* Socio-economic narrative */}
      <Widget
        title="Socio-economic signal"
        contextChip="correlational"
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
        info={<p className="text-content-dim">Correlations of crime with socio-economic indicators. Correlational, never causal; small counts are suppressed.</p>}
      >
        {socio.data && <SocioNarrativeCard data={socio.data} />}
      </Widget>
    </div>
  );
}
