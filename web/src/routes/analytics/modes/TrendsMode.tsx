import { useMemo, useState } from "react";
import { Activity, CalendarClock, Sparkles, TrendingUp, Waves } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { cn } from "@/lib/utils";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { NativeSelect } from "@/components/ui/native-select";
import { TrendChart } from "@/components/charts/TrendChart";
import { DecompositionChart } from "@/components/charts/DecompositionChart";
import { useFilterOptions, useTrends, type TrendScope } from "@/routes/analytics/useAnalyticsData";

/* Trends (doc 01 §4.6 / doc 03 §2.3): crime volume over time by head / sub-head /
   district, with a rolling-mean anomaly band and an STL-decomposition toggle for
   analysts investigating a seasonal spike. MoM & YoY deltas as KPI cards. */
export function TrendsMode() {
  const askAbout = useUIStore((s) => s.askAbout);
  const filters = useFilterOptions();

  const [districtId, setDistrictId] = useState<string>("");
  const [headId, setHeadId] = useState<string>("");
  const [subHeadId, setSubHeadId] = useState<string>("");
  const [stl, setStl] = useState(false);

  const scope: TrendScope = {
    district_id: districtId ? Number(districtId) : undefined,
    crime_head_id: headId ? Number(headId) : undefined,
    sub_head_id: subHeadId ? Number(subHeadId) : undefined,
    decompose: true,
  };
  const trends = useTrends(scope);
  const data = trends.data;

  const districtName = filters.data?.districts.find((d) => String(d.id) === districtId)?.name;
  const headName = filters.data?.crime_heads.find((h) => String(h.id) === headId)?.name;
  const subHeadName = filters.data?.sub_heads.find((s) => String(s.id) === subHeadId)?.name;
  const scopeText = [districtName ?? "All districts", subHeadName ?? headName ?? "all crime"]
    .filter(Boolean)
    .join(" · ");

  const series = data?.series ?? [];
  const anomalies = useMemo(() => series.filter((p) => p.is_anomaly).length, [series]);
  const latest = series.length ? series[series.length - 1].count : undefined;
  const peak = series.length ? Math.max(...series.map((p) => p.count)) : undefined;
  const rangeLabel =
    series.length >= 2 ? `${series[0].period} – ${series[series.length - 1].period}` : undefined;

  const empty = !trends.isLoading && !trends.error && series.length === 0;
  const explainSeed =
    `Explain the crime trend for ${scopeText} across all recorded months: the month-on-month ` +
    `and year-on-year change, and any anomalous spikes flagged by the rolling band.`;

  return (
    <div className="space-y-4">
      {/* Scope selectors */}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="District">
          <NativeSelect
            value={districtId}
            onChange={setDistrictId}
            options={(filters.data?.districts ?? []).map((d) => ({ value: String(d.id), label: d.name ?? `District ${d.id}` }))}
            placeholder="All districts"
            aria-label="District"
            className="w-48"
          />
        </Field>
        <Field label="Crime head">
          <NativeSelect
            value={headId}
            onChange={(v) => {
              setHeadId(v);
              setSubHeadId("");
            }}
            options={(filters.data?.crime_heads ?? []).map((h) => ({ value: String(h.id), label: h.name ?? `Head ${h.id}` }))}
            placeholder="All crime heads"
            aria-label="Crime head"
            className="w-52"
          />
        </Field>
        <Field label="Sub-head">
          <NativeSelect
            value={subHeadId}
            onChange={setSubHeadId}
            options={(filters.data?.sub_heads ?? []).map((s) => ({ value: String(s.id), label: s.name ?? `Sub-head ${s.id}` }))}
            placeholder="All sub-heads"
            aria-label="Crime sub-head"
            className="w-52"
          />
        </Field>
      </div>

      {/* KPI band */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          icon={<TrendingUp />}
          label="Incidents (all months)"
          value={data?.total}
          spark={series.map((p) => p.count)}
          loading={trends.isLoading}
          error={trends.error}
        />
        <KpiCard
          icon={<CalendarClock />}
          label="Latest month (MoM)"
          value={latest}
          delta={data?.mom_pct ?? null}
          improveWhenDown
          loading={trends.isLoading}
          error={trends.error}
          hint={data?.latest_period ? `Latest period: ${data.latest_period}` : undefined}
        />
        <KpiCard
          icon={<CalendarClock />}
          label="Latest month (YoY)"
          value={latest}
          delta={data?.yoy_pct ?? null}
          improveWhenDown
          loading={trends.isLoading}
          error={trends.error}
          hint="Change vs. the same month last year."
        />
        <KpiCard
          icon={<Activity />}
          label="Anomalous months"
          value={data ? anomalies : undefined}
          loading={trends.isLoading}
          error={trends.error}
          hint="Months above the rolling-mean + k·σ band."
        />
      </div>

      {/* Main trend widget */}
      <Widget
        title={stl ? "Trend decomposition (STL)" : "Crime volume over time"}
        contextChip={scopeText}
        provenance={data?.result}
        loading={trends.isLoading}
        error={trends.error}
        empty={empty}
        emptyLabel="No incidents recorded for this scope."
        onRefresh={() => trends.refetch()}
        actions={
          <button
            type="button"
            onClick={() => setStl((v) => !v)}
            className={cn(
              "flex items-center gap-1.5 rounded-control px-2 py-1 text-12 font-medium transition-colors",
              stl ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content",
            )}
          >
            <Waves className="size-3.5" /> STL
          </button>
        }
        menuItems={[
          {
            label: "Explain this in Ask DRISHTI",
            icon: <Sparkles />,
            onSelect: () => askAbout(explainSeed),
          },
        ]}
        info={
          <p className="text-content-dim">
            Monthly incidents with a rolling-mean band; red dots mark statistically anomalous spikes.
            Toggle <span className="font-medium text-content">STL</span> to split the series into
            trend, seasonal and residual components.
          </p>
        }
      >
        {data && !stl && <TrendChart series={series} height={300} />}
        {data && stl &&
          (data.decomposition ? (
            <DecompositionChart data={data.decomposition} />
          ) : (
            <p className="py-8 text-center text-13 text-content-dim">
              Not enough history in this scope to decompose (need at least ~14 months).
            </p>
          ))}
        {rangeLabel && (
          <p className="mt-2 px-1 text-12 text-content-dim">
            {series.length} months · {rangeLabel}. Reads the full recorded range, not the global
            time window.
          </p>
        )}
      </Widget>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-12 font-medium text-content-dim">{label}</span>
      {children}
    </label>
  );
}
