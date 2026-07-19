import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gauge, Loader2, Play } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { ForecastRunResponse } from "@/api/endpoints/disaster";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { PageHeader } from "@/components/common/PageHeader";
import { SendToBoard } from "@/components/board/SendToBoard";
import { DISTRICT_NAMES, districtName } from "@/stores/useDisasterStore";
import {
  ConfidenceChip, DistrictPicker, Panel, QualityBadge, SeverityBadge, SyntheticNote,
  useErCapabilities,
} from "@/routes/emergency/erShared";

const HAZARDS = ["flood", "urban_flood", "landslide", "drought", "heatwave", "cyclone",
                 "forest_fire", "dam_breach", "lightning"];

export function ForecastRisk() {
  const qc = useQueryClient();
  const { canWrite, activeDistrict } = useErCapabilities();
  const [hazard, setHazard] = useState("flood");
  const [horizon, setHorizon] = useState(48);
  const [district, setDistrict] = useState(String(activeDistrict ?? 24));

  const run = useMutation({
    mutationFn: () => api.disaster.runForecast({
      hazard_code: hazard, district_id: Number(district), horizon_hours: horizon }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["er", "predictions"] }),
  });
  const preds = useQuery({
    queryKey: ["er", "predictions", hazard],
    queryFn: ({ signal }) => api.disaster.predictions({ hazard_code: hazard }, signal),
  });
  const validation = useQuery({
    queryKey: ["er", "validate", hazard],
    queryFn: ({ signal }) => api.disaster.validate(hazard, signal),
  });

  const result: ForecastRunResponse | undefined = run.data;

  return (
    <div className="space-y-4">
      <PageHeader title="Forecast & Risk"
        description="Transparent baselines with visible confidence, factors and model evidence."
        actions={<DistrictPicker />} />

      <Panel title="Run a forecast">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-12 text-content-dim">
            Hazard
            <NativeSelect className="mt-1 w-44" aria-label="Hazard" value={hazard} onChange={setHazard}
              options={HAZARDS.map((h) => ({ value: h, label: h }))} placeholder="flood" />
          </label>
          <label className="text-12 text-content-dim">
            District
            <NativeSelect className="mt-1 w-52" aria-label="District" value={district} onChange={setDistrict}
              options={Object.entries(DISTRICT_NAMES).map(([id, n]) => ({ value: id, label: n }))} />
          </label>
          <label className="text-12 text-content-dim">
            Horizon (h)
            <NativeSelect className="mt-1 w-28" aria-label="Horizon" value={String(horizon)}
              onChange={(v) => setHorizon(Number(v))}
              options={["24", "48", "72"].map((h) => ({ value: h, label: h }))} />
          </label>
          {canWrite ? (
            <Button size="sm" disabled={run.isPending} onClick={() => run.mutate()}>
              {run.isPending ? <Loader2 className="animate-spin" /> : <Play />} Run forecast
            </Button>
          ) : <Badge variant="neutral">read-only role</Badge>}
        </div>
        {run.isError && <p className="mt-2 text-12 text-severity-critical">{errorMessage(run.error)}</p>}
      </Panel>

      {result && (
        <div className="grid gap-4 lg:grid-cols-3">
          {/* risk gauge + confidence + escalation */}
          <Panel title="Result"
            actions={<SendToBoard size="sm" variant="outline"
              target={{ refTable: "HazardPrediction", refId: result.prediction.hazard_prediction_id,
                        nodeKind: "hazard_prediction",
                        label: `${hazard} forecast · ${districtName(Number(district))}` }} />}>
            <div className="flex items-center gap-3">
              <RiskGauge value={result.prediction.probability ?? 0} />
              <div className="space-y-1">
                <SeverityBadge severity={result.prediction.predicted_severity} />
                <ConfidenceChip value={result.prediction.confidence} />
                <QualityBadge quality={result.prediction.quality_state} />
              </div>
            </div>
            {result.escalation && (
              <p className="mt-3 rounded-control border border-severity-high/40 bg-severity-high/10 px-2.5 py-2 text-12 text-content">
                {result.escalation}
              </p>
            )}
            <p className="mt-2 text-12 text-content-dim">{result.result.answer}</p>
          </Panel>

          {/* factor bars (RTM / threshold explanation) */}
          <Panel title="Why — factors">
            <FactorBars factors={result.prediction.factors} />
          </Panel>

          {/* evidence trail */}
          <Panel title="Evidence Trail">
            <dl className="space-y-1.5 text-12">
              <Row k="Model / rule" v={result.prediction.model_version_label} />
              <Row k="Feature snapshot" v={result.prediction.feature_snapshot_id} />
              <Row k="Data as-of" v={fmt(result.prediction.data_as_of)} />
              <Row k="Forecast window"
                   v={`${fmt(result.prediction.forecast_start)} → ${fmt(result.prediction.forecast_end)}`} />
              <Row k="Quality" v={result.prediction.quality_state} />
            </dl>
            <p className="mt-2 text-11 text-content-dim">
              Sources: {result.result.source_record_ids.join(", ")}
            </p>
          </Panel>
        </div>
      )}

      {/* baseline comparison (MVP path) */}
      <Panel title={`Model vs baseline — ${hazard}`}>
        {validation.isLoading && <Loader2 className="size-4 animate-spin text-content-dim" />}
        {validation.data && <BaselineComparison data={validation.data} />}
      </Panel>

      {/* recent predictions */}
      <Panel title="Recent forecasts">
        <div className="overflow-x-auto">
          <table className="w-full text-12">
            <thead className="text-content-dim">
              <tr className="border-b border-hairline text-left">
                <th className="px-2 py-1.5">District</th><th className="px-2 py-1.5">Prob</th>
                <th className="px-2 py-1.5">Severity</th><th className="px-2 py-1.5">Confidence</th>
                <th className="px-2 py-1.5">Quality</th><th className="px-2 py-1.5">Model</th>
              </tr>
            </thead>
            <tbody>
              {preds.data?.predictions.map((p) => (
                <tr key={p.hazard_prediction_id} className="border-b border-hairline/60">
                  <td className="px-2 py-1.5">{districtName(p.district_id)}</td>
                  <td className="px-2 py-1.5 tabular-nums">{(p.probability ?? 0).toFixed(2)}</td>
                  <td className="px-2 py-1.5"><SeverityBadge severity={p.predicted_severity} /></td>
                  <td className="px-2 py-1.5 tabular-nums">{((p.confidence ?? 0) * 100).toFixed(0)}%</td>
                  <td className="px-2 py-1.5"><QualityBadge quality={p.quality_state} /></td>
                  <td className="px-2 py-1.5 text-content-dim">{p.model_version_label}</td>
                </tr>
              ))}
              {preds.data && preds.data.predictions.length === 0 && (
                <tr><td colSpan={6} className="px-2 py-3 text-content-dim">No forecasts yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <SyntheticNote />
    </div>
  );
}

function Row({ k, v }: { k: string; v?: string | null }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-content-dim">{k}</dt>
      <dd className="truncate text-right text-content">{v || "—"}</dd>
    </div>
  );
}

function RiskGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.75 ? "#be123c" : value >= 0.5 ? "#ef4444"
    : value >= 0.35 ? "#f59e0b" : "#16a34a";
  return (
    <div className="relative grid size-24 place-items-center rounded-full"
         style={{ background: `conic-gradient(${color} ${pct * 3.6}deg, var(--surface-2, #1f2937) 0deg)` }}
         role="img" aria-label={`Probability ${pct} percent`}>
      <div className="grid size-16 place-items-center rounded-full bg-surface text-center">
        <span className="text-18 font-semibold tabular-nums text-content">{pct}%</span>
      </div>
    </div>
  );
}

function FactorBars({ factors }: { factors: Record<string, unknown> }) {
  const numeric = Object.entries(factors)
    .filter(([, v]) => typeof v === "number")
    .slice(0, 6) as [string, number][];
  if (numeric.length === 0) {
    return <p className="text-12 text-content-dim">{String(factors.rule ?? "No numeric factors.")}</p>;
  }
  const max = Math.max(...numeric.map(([, v]) => Math.abs(v)), 1);
  return (
    <div className="space-y-1.5">
      {numeric.map(([k, v]) => (
        <div key={k}>
          <div className="flex justify-between text-11 text-content-dim">
            <span>{k}</span><span className="tabular-nums">{v}</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-primary/70" style={{ width: `${(Math.abs(v) / max) * 100}%` }} />
          </div>
        </div>
      ))}
      {typeof factors.rule === "string" && <p className="pt-1 text-11 text-content-dim">Rule: {factors.rule}</p>}
    </div>
  );
}

function BaselineComparison({ data }: { data: Record<string, unknown> }) {
  const skill = (data.skill_vs_baseline ?? {}) as Record<string, unknown>;
  const metrics = (data.metrics ?? {}) as Record<string, number>;
  const baselines = (data.baselines ?? {}) as Record<string, Record<string, number>>;
  const beats = Boolean(skill.beats_baselines);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Badge variant={beats ? "low" : "high"}>
          {beats ? "Model beats baselines" : "Model comparable to baselines"}
        </Badge>
        <span className="text-11 text-content-dim">{String(data.holdout ?? "")}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-12">
          <thead className="text-content-dim">
            <tr className="border-b border-hairline text-left">
              <th className="px-2 py-1.5">Model</th><th className="px-2 py-1.5">Precision</th>
              <th className="px-2 py-1.5">Recall</th><th className="px-2 py-1.5">False alarm</th>
              <th className="px-2 py-1.5">Missed</th><th className="px-2 py-1.5">Brier</th>
            </tr>
          </thead>
          <tbody>
            <MetricRow name={String(data.model_version_label ?? "model")} m={metrics} highlight />
            <MetricRow name="persistence" m={baselines.persistence ?? {}} />
            <MetricRow name="seasonal" m={baselines.seasonal ?? {}} />
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MetricRow({ name, m, highlight }: { name: string; m: Record<string, number>; highlight?: boolean }) {
  return (
    <tr className={highlight ? "border-b border-hairline/60 bg-primary/5" : "border-b border-hairline/60"}>
      <td className="px-2 py-1.5 font-medium text-content">{name}</td>
      <td className="px-2 py-1.5 tabular-nums">{fmtNum(m.precision)}</td>
      <td className="px-2 py-1.5 tabular-nums">{fmtNum(m.recall)}</td>
      <td className="px-2 py-1.5 tabular-nums">{fmtNum(m.false_alarm_rate)}</td>
      <td className="px-2 py-1.5 tabular-nums">{fmtNum(m.missed_event_rate)}</td>
      <td className="px-2 py-1.5 tabular-nums">{fmtNum(m.brier)}</td>
    </tr>
  );
}

const fmtNum = (v?: number) => (v == null ? "—" : v.toFixed(3));
const fmt = (v?: string | null) => (v ? new Date(v).toLocaleString() : "—");
