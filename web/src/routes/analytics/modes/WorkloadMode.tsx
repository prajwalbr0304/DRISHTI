import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, CheckCircle2, Cpu, Gauge, Layers, ShieldCheck,
  SlidersHorizontal, Target, XCircle,
} from "lucide-react";
import { api } from "@/api";
import type {
  WorkloadBenchmarkRow, WorkloadEvaluationResponse, WorkloadMetricBlock,
} from "@/api/endpoints/workload";
import { cn, formatNumber, formatPercent } from "@/lib/utils";
import { Widget } from "@/components/widget/Widget";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";

/* Aggregate case-review WORKLOAD band (Phase 13). The approved replacement for
   the retired synthetic individual offender-risk score: an ordinal, DISTRICT-
   level band that projects next-quarter case-review demand for supervisory
   resource planning. Every claim here is aggregate, reviewed by a human, and
   evaluated on held-out data against transparent baselines. */

function bandVariant(band?: string | null): "critical" | "high" | "medium" | "low" | "neutral" {
  switch ((band ?? "").toLowerCase()) {
    case "high": return "critical";
    case "elevated": return "high";
    case "moderate": return "medium";
    case "low": return "low";
    default: return "neutral";
  }
}

export function WorkloadMode() {
  const task = useQuery({ queryKey: ["workload", "task"], queryFn: ({ signal }) => api.workload.task(signal) });
  const evalQ = useQuery({ queryKey: ["workload", "evaluation"], queryFn: ({ signal }) => api.workload.evaluation({}, signal) });
  const models = useQuery({ queryKey: ["workload", "models"], queryFn: ({ signal }) => api.workload.models(signal) });
  const preds = useQuery({ queryKey: ["workload", "predictions"], queryFn: ({ signal }) => api.workload.predictions({ page_size: 50 }, signal) });
  const bench = useQuery({ queryKey: ["workload", "benchmarks"], queryFn: ({ signal }) => api.workload.benchmarks(signal) });

  const served = models.data?.models.find((m) => m.model_version_id === models.data?.served_model_version_id);

  return (
    <div className="space-y-4">
      {/* Retirement + scope banner */}
      <div className="rounded-card border border-hairline bg-surface px-3.5 py-3 text-12 text-content-dim">
        <ShieldCheck className="mr-1 inline size-3.5 -translate-y-px text-severity-low" />
        This is the approved <span className="font-medium text-content">aggregate case-review workload band</span>{" "}
        that replaced the retired synthetic per-person offender-risk score. It projects a police
        district&rsquo;s next-quarter case-review demand for resource planning — aggregate, human-reviewed,
        and <span className="font-medium text-content">never a person-level judgement</span>.
      </div>

      {/* Task / model card */}
      <TaskCard task={task} served={served} />

      {/* Held-out evaluation */}
      <EvaluationPanel q={evalQ} />

      {/* Governed per-district predictions */}
      <PredictionsPanel q={preds} />

      {/* Benchmarks */}
      <BenchmarkPanel q={bench} />

      <p className="rounded-card border border-hairline bg-surface/60 p-3 text-12 text-content-dim">
        <AlertTriangle className="mr-1 inline size-3.5 -translate-y-px text-severity-medium" />
        Limitations: an aggregate, area/period workload band for review-queue and resource planning
        only. It is not evidence of an offence, not an individual&rsquo;s risk, and never drives an
        arrest, detention, bail or guilt decision. Bands are ordinal and uncertain; the production
        foundation backend is Google TabFM on GPU (Prompt 14), with a CPU foundation candidate and a
        deterministic in-context fallback used in this demo. Every result ties to an immutable feature
        snapshot and requires human review.
      </p>
    </div>
  );
}

function TaskCard({ task, served }: { task: ReturnType<typeof useQuery<Awaited<ReturnType<typeof api.workload.task>>>>; served?: { status?: string | null; version: string } }) {
  const t = task.data;
  return (
    <Widget title="Task & model card" loading={task.isLoading} error={task.error} onRefresh={() => task.refetch()}
      info={<p className="text-content-dim">The approved task definition, its feature schema and governance.</p>}>
      {t && (
        <div className="space-y-3 text-13">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="primary">{t.task}</Badge>
            <Badge variant={t.schema_approved ? "low" : "high"}>
              {t.schema_approved ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
              schema {t.schema_name} v{t.schema_version} {t.schema_approved ? "approved" : "unapproved"}
            </Badge>
            <Badge variant="neutral">subject · {t.subject_kind}</Badge>
            {served?.status && <Badge variant="neutral">lifecycle · {served.status}</Badge>}
            <Badge variant="neutral">{t.environment_label}</Badge>
          </div>
          <p className="text-content-dim">{t.label_definition}</p>
          <div className="flex flex-wrap gap-1.5">
            {t.bands.map((b, i) => (
              <Badge key={b} variant={bandVariant(b)}>{i}. {b}</Badge>
            ))}
            <Badge variant="neutral">horizon · {t.label_horizon_months} months</Badge>
          </div>
          <div>
            <div className="mb-1 text-12 font-medium text-content-dim">
              Features ({t.features.length}) — aggregate, non-protected
            </div>
            <div className="flex flex-wrap gap-1.5">
              {t.features.map((f) => (
                <span key={f.name} title={f.description ?? f.name}
                  className="rounded-control border border-hairline bg-surface-2/50 px-2 py-0.5 text-12 text-content-dim">
                  {f.name}
                  <span className={cn("ml-1", f.sensitivity === "normal" ? "text-severity-low" : "text-severity-high")}>
                    · {f.sensitivity}
                  </span>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </Widget>
  );
}

function metricCols(m?: WorkloadMetricBlock | null) {
  return m ?? { n: 0, accuracy: 0, macro_f1: 0, qwk: 0, ece: 0 };
}

function EvaluationPanel({ q }: { q: { data?: WorkloadEvaluationResponse; isLoading: boolean; error: unknown; refetch: () => void } }) {
  const e = q.data;
  const model = e?.model;
  const cal = metricCols(model?.calibrated);
  const baselineRows = Object.entries(e?.baselines ?? {});
  const geo = (e?.geo_holdout ?? {}) as { metrics?: WorkloadMetricBlock; skipped?: boolean };

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (!e && !q.error) return <EmptyState icon={Gauge} title="No evaluation yet" description="Run the workload pipeline to persist a held-out evaluation." />;

  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard icon={<Target />} label="Accuracy (held-out)" value={Math.round(cal.accuracy * 100)} unit="%" hint="Correct band on the time-held-out test split." />
        <KpiCard icon={<Layers />} label="Macro-F1" value={Math.round(cal.macro_f1 * 100)} unit="%" hint="Class-balanced F1 across the bands." />
        <div className="flex flex-col justify-between rounded-card border border-hairline bg-surface p-3.5 shadow-card">
          <div className="flex items-center gap-2 text-12 text-content-dim">
            <span className="[&_svg]:size-4"><Gauge /></span>
            <span className="truncate">Quadratic weighted κ</span>
          </div>
          <span className="mt-2 tnum text-28 font-semibold leading-none text-content">{cal.qwk.toFixed(3)}</span>
        </div>
        <KpiCard icon={<SlidersHorizontal />} label="Calibration error" value={Math.round(cal.ece * 100)} unit="%" hint="Lower is better-calibrated confidence (ECE)." />
      </div>

      <Widget title="Foundation model vs baselines" contextChip={model ? `${model.name} · ${model.foundation_kind}` : undefined}
        loading={false} error={q.error} onRefresh={() => q.refetch()}
        info={<p className="text-content-dim">Walk-forward time split + a held-out district (geographic) split. Every foundation candidate is measured against a prior-period rule, a majority-class floor and gradient-boosted trees.</p>}
        flush>
        {e && (
          <div className="space-y-3 p-3.5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={e.beats_all_baselines ? "low" : "medium"}>
                {e.beats_all_baselines ? <CheckCircle2 className="size-3" /> : <AlertTriangle className="size-3" />}
                {e.beats_all_baselines ? "Beats all baselines" : "Does not beat every baseline"}
              </Badge>
              <Badge variant={e.leakage.leakage_safe ? "low" : "high"}>
                <ShieldCheck className="size-3" /> {e.leakage.leakage_safe ? "leakage-safe" : "leakage risk"}
              </Badge>
              {!e.leakage.has_protected_or_proxy && <Badge variant="neutral">no protected/proxy features</Badge>}
              {geo.metrics && (
                <Badge variant="neutral"><Target className="size-3" /> geo-holdout QWK {geo.metrics.qwk.toFixed(3)}</Badge>
              )}
              <Badge variant="neutral">abstention {formatPercent(e.abstention.abstention_rate, 0)}</Badge>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-13">
                <thead>
                  <tr className="border-b border-hairline text-left text-12 text-content-dim">
                    <th className="px-3 py-2 font-medium">Model</th>
                    <th className="px-3 py-2 text-right font-medium">Accuracy</th>
                    <th className="px-3 py-2 text-right font-medium">Macro-F1</th>
                    <th className="px-3 py-2 text-right font-medium">QWK</th>
                    <th className="px-3 py-2 text-right font-medium">ECE</th>
                  </tr>
                </thead>
                <tbody>
                  <MetricRow label={`${model?.name ?? "foundation"} (model)`} m={cal} highlight />
                  {baselineRows.map(([k, b]) => (
                    <MetricRow key={k} label={`${b.name} (baseline)`} m={b} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Widget>
    </>
  );
}

function MetricRow({ label, m, highlight }: { label: string; m: WorkloadMetricBlock; highlight?: boolean }) {
  return (
    <tr className="border-b border-hairline/60 last:border-0">
      <td className="px-3 py-2">
        <span className={cn("font-medium", highlight ? "text-primary" : "text-content-dim")}>{label}</span>
      </td>
      <td className="tnum px-3 py-2 text-right text-content">{formatPercent(m.accuracy, 0)}</td>
      <td className="tnum px-3 py-2 text-right text-content">{formatPercent(m.macro_f1, 0)}</td>
      <td className="tnum px-3 py-2 text-right text-content">{m.qwk.toFixed(3)}</td>
      <td className="tnum px-3 py-2 text-right text-content">{formatPercent(m.ece, 0)}</td>
    </tr>
  );
}

function PredictionsPanel({ q }: { q: { data?: Awaited<ReturnType<typeof api.workload.predictions>>; isLoading: boolean; error: unknown; refetch: () => void } }) {
  const rows = q.data?.predictions ?? [];
  return (
    <Widget title="District workload bands (next quarter)" contextChip={q.data?.cutoff_period ? `as of ${q.data.cutoff_period}` : undefined}
      loading={q.isLoading} error={q.error} empty={!q.isLoading && !q.error && rows.length === 0}
      emptyLabel="No governed workload predictions yet — run the pipeline." onRefresh={() => q.refetch()}
      info={<p className="text-content-dim">Each row ties to an immutable feature snapshot and a governed prediction result. Aggregate, decision-support only.</p>}
      flush>
      <div className="overflow-x-auto">
        <table className="w-full text-13">
          <thead>
            <tr className="border-b border-hairline text-left text-12 text-content-dim">
              <th className="px-4 py-2 font-medium">District</th>
              <th className="px-4 py-2 font-medium">Workload band</th>
              <th className="px-4 py-2 text-right font-medium">Confidence</th>
              <th className="px-4 py-2 text-right font-medium">Recent quarter</th>
              <th className="px-4 py-2 font-medium">Review</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.prediction_result_id} className="border-b border-hairline/60 last:border-0">
                <td className="px-4 py-2 text-content">{r.unit_name ?? `District ${r.unit_id}`}</td>
                <td className="px-4 py-2"><Badge variant={bandVariant(r.workload_band)}>{r.workload_band ?? "—"}</Badge></td>
                <td className="tnum px-4 py-2 text-right text-content">{r.confidence != null ? formatPercent(r.confidence, 0) : "—"}</td>
                <td className="tnum px-4 py-2 text-right text-content-dim">{r.recent_case_volume != null ? formatNumber(Math.round(r.recent_case_volume)) : "—"}</td>
                <td className="px-4 py-2">
                  {r.abstained ? <Badge variant="medium">abstained</Badge> : <Badge variant="neutral">pending review</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Widget>
  );
}

function BenchmarkPanel({ q }: { q: { data?: { benchmarks: WorkloadBenchmarkRow[] }; isLoading: boolean; error: unknown; refetch: () => void } }) {
  const rows = q.data?.benchmarks ?? [];
  return (
    <Widget title="Benchmarks — runtime, memory, cost, metrics" loading={q.isLoading} error={q.error}
      empty={!q.isLoading && !q.error && rows.length === 0} emptyLabel="No benchmark runs recorded yet."
      onRefresh={() => q.refetch()}
      info={<p className="text-content-dim">Small/medium/full-row (500/5,000/full) computational scaling. Google TabFM at scale is deferred to AWS GPU (Prompt 14) and shown as such.</p>}
      flush>
      <div className="overflow-x-auto">
        <table className="w-full text-13">
          <thead>
            <tr className="border-b border-hairline text-left text-12 text-content-dim">
              <th className="px-3 py-2 font-medium">Model</th>
              <th className="px-3 py-2 font-medium">Scale</th>
              <th className="px-3 py-2 text-right font-medium">Rows</th>
              <th className="px-3 py-2 text-right font-medium">Total s</th>
              <th className="px-3 py-2 text-right font-medium">Rows/s</th>
              <th className="px-3 py-2 text-right font-medium">RSS MB</th>
              <th className="px-3 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 24).map((b, i) => (
              <tr key={`${b.model_name}-${b.scale_label}-${i}`} className="border-b border-hairline/60 last:border-0">
                <td className="px-3 py-2 text-content">{b.model_name}</td>
                <td className="px-3 py-2 text-content-dim">{b.scale_label}</td>
                <td className="tnum px-3 py-2 text-right text-content-dim">{formatNumber(b.row_scale)}</td>
                <td className="tnum px-3 py-2 text-right text-content">{b.total_seconds != null ? b.total_seconds.toFixed(2) : "—"}</td>
                <td className="tnum px-3 py-2 text-right text-content">{b.throughput_rows_per_sec != null ? formatNumber(Math.round(b.throughput_rows_per_sec)) : "—"}</td>
                <td className="tnum px-3 py-2 text-right text-content-dim">{b.peak_rss_mb != null ? Math.round(b.peak_rss_mb) : "—"}</td>
                <td className="px-3 py-2">
                  {b.available ? <Badge variant="low">measured</Badge> : <Badge variant="neutral" title={b.note ?? ""}><Cpu className="size-3" /> deferred</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Widget>
  );
}
