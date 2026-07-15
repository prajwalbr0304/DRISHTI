import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Gauge, Layers, Radar, Sparkles, TrendingUp } from "lucide-react";
import type { LayerPrediction } from "@/api/types";
import { errorMessage } from "@/api/contracts";
import { api } from "@/api";
import { useUIStore } from "@/stores/useUIStore";
import { cn, formatNumber, formatPercent } from "@/lib/utils";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { EmptyState } from "@/components/common/EmptyState";
import { FanChart, type TrajectoryStep } from "@/components/charts/FanChart";
import {
  useDistrictForecast,
  useFilterOptions,
  useForecastFused,
} from "@/routes/analytics/useAnalyticsData";

/* Forecasts (doc 01 §4.6 / doc 03 §2.15): district forecasts rendered as a fan
   chart (median + widening confidence band) with the per-layer table behind it.
   Area/period decision support with visible confidence — never certainty, never
   individual targeting. Empty until the pipeline has been run. */

const LAYER_LABEL: Record<string, string> = {
  tabfm: "TabFM · district risk",
  timesfm: "TimesFM · trajectory",
  near_repeat: "Near-repeat · Hawkes",
  st_gnn: "ST-GNN · spillover",
  fused: "Fused · stacked",
};

function riskVariant(rc?: string | null): "critical" | "high" | "medium" | "low" | "neutral" {
  switch ((rc ?? "").toLowerCase()) {
    case "severe":
      return "critical";
    case "high":
      return "high";
    case "medium":
      return "medium";
    case "low":
      return "low";
    default:
      return "neutral";
  }
}

export function ForecastsMode() {
  const askAbout = useUIStore((s) => s.askAbout);
  const qc = useQueryClient();
  const filters = useFilterOptions();
  const fused = useForecastFused();
  const [selected, setSelected] = useState<string>("");

  const districtName = (id: number) =>
    filters.data?.districts.find((d) => d.id === id)?.name ?? `District ${id}`;

  // Districts that actually carry a fused forecast, ranked by predicted volume.
  const districtsWithData = useMemo(() => {
    const by = new Map<number, { predicted: number; conf: number; n: number }>();
    for (const c of fused.data?.cells ?? []) {
      if (c.district_id == null) continue;
      const cur = by.get(c.district_id) ?? { predicted: 0, conf: 0, n: 0 };
      cur.predicted += c.predicted_count ?? 0;
      cur.conf += c.confidence ?? 0;
      cur.n += 1;
      by.set(c.district_id, cur);
    }
    return [...by.entries()]
      .map(([id, v]) => ({ id, name: districtName(id), predicted: v.predicted, confidence: v.conf / v.n }))
      .sort((a, b) => b.predicted - a.predicted);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fused.data, filters.data]);

  const effectiveId = selected ? Number(selected) : districtsWithData[0]?.id ?? null;
  const districtQ = useDistrictForecast(effectiveId);

  const run = useMutation({
    mutationFn: () => api.forecast.run(undefined, 30),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["forecast"] }),
  });

  // ---- No forecast written yet: honest empty state + run action -----------
  if (!fused.isLoading && !fused.error && (fused.data?.count ?? 0) === 0) {
    return (
      <EmptyState
        icon={Radar}
        title="No forecast has been run yet"
        description="The stacked forecast pipeline (TabFM · TimesFM · near-repeat · ST-GNN, fused) hasn't written any predictions. Running it writes typed CrimePrediction rows with confidence — this can take a few minutes."
        action={
          <div className="flex flex-col items-center gap-2">
            <Button onClick={() => run.mutate()} disabled={run.isPending}>
              <Radar className={cn(run.isPending && "animate-spin")} />
              {run.isPending ? "Running the pipeline…" : "Run forecast pipeline"}
            </Button>
            {run.error != null && (
              <p className="max-w-sm text-12 text-severity-high">{errorMessage(run.error)}</p>
            )}
          </div>
        }
      />
    );
  }

  const layers = districtQ.data?.layers ?? [];
  const timesfm = layers.find((l) => l.layer === "timesfm");
  const trajectory = ((timesfm?.features?.trajectory as TrajectoryStep[] | undefined) ?? []);
  const history = (timesfm?.features?.history_tail as number[] | undefined) ?? undefined;
  const fusedLayer = layers.find((l) => l.layer === "fused");
  const ff = fusedLayer?.features ?? {};
  const riskClass = (ff.tabfm_risk_class as string | undefined) ?? (ff.risk_class as string | undefined) ?? null;
  const contributing = (ff.contributing_models as unknown[] | undefined) ?? [];
  const nearSpike = Boolean(ff.near_term_spike);
  const selectedName = effectiveId != null ? districtName(effectiveId) : "";

  const explainSeed =
    `Explain the crime forecast for ${selectedName}: the fused next-period expectation, its ` +
    `confidence and which models contributed. Note it is area/period decision support, not certainty.`;
  const explainItem = { label: "Explain this in Ask DRISHTI", icon: <Sparkles />, onSelect: () => askAbout(explainSeed) };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-12 font-medium text-content-dim">District</span>
          <NativeSelect
            value={effectiveId != null ? String(effectiveId) : ""}
            onChange={setSelected}
            options={districtsWithData.map((d) => ({
              value: String(d.id),
              label: `${d.name} (~${formatNumber(Math.round(d.predicted))})`,
            }))}
            placeholder="Pick a district"
            aria-label="District"
            className="w-64"
          />
        </label>
        <Badge variant="neutral">
          {districtsWithData.length} district(s) with a forecast
        </Badge>
      </div>

      {/* KPI band for the selected district */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          icon={<TrendingUp />}
          label="Next-period forecast"
          value={fusedLayer?.predicted_count != null ? Math.round(fusedLayer.predicted_count) : undefined}
          loading={districtQ.isLoading}
          error={districtQ.error}
          hint="Fused expected incidents for the next window."
        />
        <KpiCard
          icon={<Gauge />}
          label="Confidence"
          value={fusedLayer?.confidence != null ? Math.round(fusedLayer.confidence * 100) : undefined}
          unit="%"
          loading={districtQ.isLoading}
          error={districtQ.error}
          hint="Higher = tighter agreement across layers."
        />
        <div className="flex flex-col justify-between rounded-card border border-hairline bg-surface p-3.5 shadow-card">
          <div className="flex items-center gap-2 text-12 text-content-dim">
            <Radar className="size-4" /> Risk class
          </div>
          <div className="mt-2">
            {riskClass ? (
              <Badge variant={riskVariant(riskClass)} className="text-14">{riskClass}</Badge>
            ) : (
              <span className="text-16 text-content-dim">—</span>
            )}
            {nearSpike && (
              <Badge variant="high" className="ml-2">
                <AlertTriangle className="size-3" /> near-term spike
              </Badge>
            )}
          </div>
        </div>
        <KpiCard
          icon={<Layers />}
          label="Contributing models"
          value={districtQ.data ? contributing.length : undefined}
          loading={districtQ.isLoading}
          error={districtQ.error}
          hint="Layers fused into this district's forecast."
        />
      </div>

      {/* Fan chart */}
      <Widget
        title="Forecast fan chart"
        contextChip={selectedName || undefined}
        provenance={districtQ.data?.result}
        loading={districtQ.isLoading}
        error={districtQ.error}
        empty={!districtQ.isLoading && !districtQ.error && trajectory.length === 0}
        emptyLabel="No trajectory forecast for this district (the TimesFM layer produces the fan)."
        onRefresh={() => districtQ.refetch()}
        menuItems={[explainItem]}
        info={
          <p className="text-content-dim">
            Observed history then the forecast median, with 50% and 80% confidence bands that widen
            with the horizon. Area/period decision support — confidence is shown, never hidden.
          </p>
        }
      >
        {trajectory.length > 0 && <FanChart trajectory={trajectory} history={history} height={300} />}
      </Widget>

      {/* Per-layer table */}
      <Widget
        title="Forecast layers"
        contextChip={`${layers.length} layer(s)`}
        provenance={districtQ.data?.result}
        loading={districtQ.isLoading}
        error={districtQ.error}
        empty={!districtQ.isLoading && !districtQ.error && layers.length === 0}
        emptyLabel="No layers for this district."
        onRefresh={() => districtQ.refetch()}
        info={
          <p className="text-content-dim">
            Each layer is a separately-auditable model version; the fused row combines them
            transparently, recording every contributor + confidence.
          </p>
        }
        flush
      >
        <LayerTable layers={layers} />
      </Widget>
    </div>
  );
}

function LayerTable({ layers }: { layers: LayerPrediction[] }) {
  const order = ["tabfm", "timesfm", "near_repeat", "st_gnn", "fused"];
  const sorted = [...layers].sort((a, b) => order.indexOf(a.layer) - order.indexOf(b.layer));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-13">
        <thead>
          <tr className="border-b border-hairline text-left text-12 text-content-dim">
            <th className="px-4 py-2 font-medium">Layer</th>
            <th className="px-4 py-2 font-medium">Model</th>
            <th className="px-4 py-2 text-right font-medium">Predicted</th>
            <th className="px-4 py-2 text-right font-medium">Confidence</th>
            <th className="px-4 py-2 font-medium">Window</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((l) => (
            <tr key={l.layer} className="border-b border-hairline/60 last:border-0">
              <td className="px-4 py-2">
                <span className={cn("font-medium", l.layer === "fused" ? "text-primary" : "text-content")}>
                  {LAYER_LABEL[l.layer] ?? l.layer}
                </span>
              </td>
              <td className="px-4 py-2 text-content-dim">{l.model_name ?? "—"}</td>
              <td className="tnum px-4 py-2 text-right text-content">
                {l.predicted_count != null ? formatNumber(Math.round(l.predicted_count)) : "—"}
              </td>
              <td className="tnum px-4 py-2 text-right text-content">
                {l.confidence != null ? formatPercent(l.confidence, 0) : "—"}
              </td>
              <td className="tnum px-4 py-2 text-12 text-content-dim">
                {l.prediction_start ? `${l.prediction_start.slice(0, 10)} → ${l.prediction_end?.slice(0, 10) ?? ""}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
