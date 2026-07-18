import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity, AlertTriangle, CalendarClock, CheckCircle2, Gauge, Layers, Radar,
  ShieldCheck, Sparkles, Target, TrendingUp, XCircle,
} from "lucide-react";
import type { BacktestResponse, ForecastMetric, FreshnessResponse, LayerPrediction } from "@/api/types";
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
  useForecastBacktest,
  useForecastFreshness,
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
  const backtest = useForecastBacktest();
  const fresh = useForecastFreshness();
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
      <FreshnessBanner q={fresh} />
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

      {/* Backtest: how wrong is it usually, and does it beat simple baselines? */}
      <BacktestPanel q={backtest} onExplain={askAbout} />

      <p className="rounded-card border border-hairline bg-surface/60 p-3 text-12 text-content-dim">
        <AlertTriangle className="mr-1 inline size-3.5 -translate-y-px text-severity-medium" />
        Limitations: forecasts are aggregate area/period decision support with visible uncertainty —
        not certainty and never a person-level prediction. They use only canonical valid geography
        (incidents outside the state boundary are excluded) and approved, versioned context up to the
        data cutoff. Every result is reproducible from an immutable feature snapshot and requires
        human review before any operational use.
      </p>
    </div>
  );
}

/* ---- data freshness banner ------------------------------------------------ */
function FreshnessBanner({ q }: { q: { data?: FreshnessResponse; isLoading: boolean; error: unknown } }) {
  const f = q.data;
  if (q.isLoading || q.error || !f) return null;
  const asOf = f.as_of?.cases ? String(f.as_of.cases).slice(0, 10) : "unknown";
  const stale = f.case_data_stale_days;
  const vg = (f.valid_geography?.valid_geography_filter as string | undefined) ?? "";
  const geoActive = vg === "active";
  const excluded = Number(f.valid_geography?.out_of_state_excluded ?? 0);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-card border border-hairline bg-surface px-3.5 py-2 text-12">
      <span className="flex items-center gap-1.5 text-content-dim">
        <CalendarClock className="size-3.5" /> Data as of{" "}
        <span className="tnum font-medium text-content">{asOf}</span>
        {stale != null && <span className="text-content-dim">({stale}d old)</span>}
      </span>
      <span className="flex items-center gap-1.5 text-content-dim">
        <ShieldCheck className={cn("size-3.5", geoActive ? "text-severity-low" : "text-content-dim")} />
        Valid-geography filter{" "}
        <Badge variant={geoActive ? "low" : "neutral"}>{geoActive ? "active" : "inactive"}</Badge>
        {geoActive && <span className="text-content-dim">· {formatNumber(excluded)} out-of-state excluded</span>}
      </span>
      <span className="text-content-dim">
        {(f.approved_sources?.length ?? 0)} approved context source(s)
      </span>
    </div>
  );
}

/* ---- rolling-origin backtest + baseline comparison ------------------------ */
const _METRIC_COLS: { key: keyof ForecastMetric; label: string; pct?: boolean }[] = [
  { key: "mae", label: "MAE" },
  { key: "rmse", label: "RMSE" },
  { key: "wape", label: "WAPE", pct: true },
  { key: "smape", label: "sMAPE" },
  { key: "coverage_80", label: "80% cov.", pct: true },
];

function _fmtMetric(m: ForecastMetric | null | undefined, key: keyof ForecastMetric, pct?: boolean): string {
  const v = m?.[key];
  if (v == null || typeof v !== "number") return "—";
  if (key === "smape") return `${v.toFixed(1)}%`;
  if (pct) return formatPercent(v, key === "wape" ? 1 : 0);
  return formatNumber(Math.round(v * 100) / 100);
}

function BacktestPanel({
  q,
  onExplain,
}: {
  q: { data?: BacktestResponse; isLoading: boolean; error: unknown; refetch: () => void };
  onExplain: (seed: string) => void;
}) {
  const bt = q.data;
  const model = bt?.model;
  const baselines = bt?.baselines ?? {};
  const beats = bt?.beats_all_baselines;
  const naiveSkill = bt?.skill_vs_baselines?.seasonal_naive?.mae_skill;
  const geo = (bt?.geo_holdout ?? {}) as Record<string, ForecastMetric | number | number[] | undefined>;
  const rows: { name: string; label: string; m?: ForecastMetric | null; kind: "model" | "baseline" }[] = model
    ? [
        { name: "model", label: `${model.name ?? "forecast model"} (model)`, m: model, kind: "model" },
        ...Object.entries(baselines).map(([k, m]) => ({
          name: k,
          label: `${m?.name ?? k} (baseline)`,
          m,
          kind: "baseline" as const,
        })),
      ]
    : [];

  return (
    <Widget
      title="Backtest & baselines"
      contextChip={bt ? `${bt.scored_points} held-out district-months` : undefined}
      provenance={bt?.result}
      loading={q.isLoading}
      error={q.error}
      empty={!q.isLoading && !q.error && !model}
      emptyLabel="No backtest available yet."
      onRefresh={() => q.refetch()}
      menuItems={[
        {
          label: "Explain this in Ask DRISHTI",
          icon: <Sparkles />,
          onSelect: () =>
            onExplain(
              "Explain the crime-forecast backtest: rolling-origin MAE/RMSE/WAPE/sMAPE, prediction-" +
                "interval coverage, and whether the model beats the seasonal-naive and moving-average baselines.",
            ),
        },
      ]}
      info={
        <p className="text-content-dim">
          Walk-forward (rolling-origin) evaluation: the forecaster only sees months on/before each
          cutoff and predicts the next horizon; held-out actuals score error + interval coverage,
          against seasonal-naive and moving-average baselines, with a geographic holdout.
        </p>
      }
      flush
    >
      {model && (
        <div className="space-y-3 p-3.5">
          <div className="flex flex-wrap items-center gap-2">
            {beats != null && (
              <Badge variant={beats ? "low" : "high"}>
                {beats ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
                {beats ? "Beats all baselines" : "Does not beat every baseline"}
              </Badge>
            )}
            {naiveSkill != null && (
              <Badge variant="neutral">
                <Target className="size-3" /> {formatPercent(naiveSkill, 0)} MAE skill vs seasonal-naive
              </Badge>
            )}
            {bt && bt.abstention_rate > 0 && (
              <Badge variant="medium">
                <Activity className="size-3" /> {formatPercent(bt.abstention_rate, 0)} sparse cells abstained
              </Badge>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-13">
              <thead>
                <tr className="border-b border-hairline text-left text-12 text-content-dim">
                  <th className="px-3 py-2 font-medium">Forecaster</th>
                  {_METRIC_COLS.map((c) => (
                    <th key={c.key} className="px-3 py-2 text-right font-medium">{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.name} className="border-b border-hairline/60 last:border-0">
                    <td className="px-3 py-2">
                      <span className={cn("font-medium", r.kind === "model" ? "text-primary" : "text-content-dim")}>
                        {r.label}
                      </span>
                    </td>
                    {_METRIC_COLS.map((c) => (
                      <td key={c.key} className="tnum px-3 py-2 text-right text-content">
                        {_fmtMetric(r.m, c.key, c.pct)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* geographic holdout */}
          {geo && (geo.train || geo.holdout) && (
            <div className="flex flex-wrap gap-4 text-12 text-content-dim">
              <span className="font-medium text-content">Geographic holdout:</span>
              <span>
                train MAE{" "}
                <span className="tnum text-content">{_fmtMetric(geo.train as ForecastMetric, "mae")}</span>
              </span>
              <span>
                held-out MAE{" "}
                <span className="tnum text-content">{_fmtMetric(geo.holdout as ForecastMetric, "mae")}</span>
              </span>
              {Array.isArray(geo.holdout_districts) && (
                <span>{(geo.holdout_districts as number[]).length} held-out district(s)</span>
              )}
            </div>
          )}
        </div>
      )}
    </Widget>
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
