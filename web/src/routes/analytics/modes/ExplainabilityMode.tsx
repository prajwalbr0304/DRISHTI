import { useState } from "react";
import { Activity, CheckCircle2, Cpu, Sparkles } from "lucide-react";
import type { ModelCard as ModelCardT } from "@/api/types";
import { useUIStore } from "@/stores/useUIStore";
import { cn, formatNumber, formatPercent } from "@/lib/utils";
import { Widget } from "@/components/widget/Widget";
import { Badge } from "@/components/ui/badge";
import { CalibrationPlot } from "@/components/charts/CalibrationPlot";
import { DriftChart } from "@/components/charts/DriftChart";
import { useModelDetail, useModels, useRiskCalibration } from "@/routes/analytics/useAnalyticsData";

/* Model Explainability (doc 01 §4.6): the model registry as cards, a held-out
   calibration plot (foundation vs baseline, incl. ECE/Brier), and per-model
   drift (mean confidence over time from the audit log). Trust is the product —
   which model, which version, how well calibrated, is it drifting. */

const DRIFT_META: Record<string, { label: string; variant: "neutral" | "low" | "high" | "medium" }> = {
  stable: { label: "Stable", variant: "low" },
  rising_confidence: { label: "Rising confidence", variant: "medium" },
  falling_confidence: { label: "Falling confidence", variant: "high" },
  insufficient: { label: "Insufficient data", variant: "neutral" },
};

export function ExplainabilityMode() {
  const askAbout = useUIStore((s) => s.askAbout);
  const models = useModels();
  const calib = useRiskCalibration();

  const cards = models.data?.models ?? [];
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const effectiveId = selectedId ?? (cards.length ? cards[0].model_version_id : null);
  const detail = useModelDetail(effectiveId);
  const selected = detail.data?.model ?? cards.find((c) => c.model_version_id === effectiveId);

  const drift = detail.data?.drift ?? [];
  const driftMeta = detail.data ? DRIFT_META[detail.data.drift_flag] ?? DRIFT_META.insufficient : null;

  const explainItem = selected
    ? {
        label: "Explain this in Ask DRISHTI",
        icon: <Sparkles />,
        onSelect: () =>
          askAbout(
            `Explain model ${selected.model_name}@${selected.version}: what it predicts, how well ` +
              `calibrated it is, and whether its confidence is drifting.`,
          ),
      }
    : undefined;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Model registry */}
        <Widget
          title="Model registry"
          contextChip={models.data ? `${models.data.count}` : undefined}
          provenance={models.data?.result}
          loading={models.isLoading}
          error={models.error}
          empty={!models.isLoading && !models.error && cards.length === 0}
          emptyLabel="No model versions registered."
          onRefresh={() => models.refetch()}
          info={<p className="text-content-dim">Every ModelVersion, its calibration metrics and its inference volume/confidence. Select one for detail.</p>}
          flush
          bodyClassName="max-h-[560px] overflow-y-auto"
        >
          <div className="space-y-2 px-3 py-2">
            {cards.map((c) => (
              <ModelCardItem
                key={c.model_version_id}
                card={c}
                active={c.model_version_id === effectiveId}
                onClick={() => setSelectedId(c.model_version_id)}
              />
            ))}
          </div>
        </Widget>

        {/* Selected model detail + drift */}
        <Widget
          className="lg:col-span-2"
          title={selected ? `${selected.model_name} · v${selected.version}` : "Model detail"}
          contextChip={selected?.model_type ?? undefined}
          provenance={detail.data?.result}
          loading={detail.isLoading}
          error={detail.error}
          empty={!effectiveId}
          emptyLabel="Select a model to inspect."
          onRefresh={() => detail.refetch()}
          menuItems={explainItem ? [explainItem] : undefined}
          actions={
            driftMeta && (
              <Badge variant={driftMeta.variant}>
                <Activity className="size-3" /> {driftMeta.label}
              </Badge>
            )
          }
        >
          {selected && (
            <div className="space-y-3">
              {/* metric chips */}
              <MetricChips calibration={selected.calibration} />
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-12 text-content-dim">
                <span className="tnum">{formatNumber(selected.inferences)} inference(s)</span>
                {selected.mean_confidence != null && (
                  <span className="tnum">mean confidence {formatPercent(selected.mean_confidence, 0)}</span>
                )}
                {selected.framework && <span>framework: {selected.framework}</span>}
                {selected.status && <span>status: {selected.status}</span>}
              </div>

              {/* drift */}
              <div>
                <div className="mb-1 text-12 font-semibold text-content-dim">
                  Confidence drift (monthly)
                </div>
                {drift.length > 1 ? (
                  <DriftChart drift={drift} />
                ) : (
                  <p className="py-6 text-center text-13 text-content-dim">
                    Not enough inference history to plot drift.
                  </p>
                )}
              </div>
              {detail.data?.notes && (
                <p className="border-t border-hairline pt-2 text-12 text-content-dim">{detail.data.notes}</p>
              )}
            </div>
          )}
        </Widget>
      </div>

      {/* Calibration — foundation vs baseline (the flagship risk model) */}
      <Widget
        title="Calibration — foundation vs. baseline"
        contextChip="risk model"
        provenance={calib.data?.result}
        loading={calib.isLoading}
        error={calib.error}
        onRefresh={() => calib.refetch()}
        info={
          <p className="text-content-dim">
            Held-out calibration of the TabFM-family risk model against its gradient-boosted baseline.
            Brier and ECE are calibration-error metrics (lower is better); accuracy and macro-F1 are
            discrimination metrics (higher is better).
          </p>
        }
      >
        {calib.data && (
          <div className="space-y-2">
            <CalibrationPlot
              foundation={calib.data.foundation}
              baseline={calib.data.baseline}
              agreement={calib.data.agreement}
            />
            <p className="text-12 text-content-dim">
              Evaluated on {formatNumber(calib.data.n_test)} held-out offenders (trained on{" "}
              {formatNumber(calib.data.n_train)}).
            </p>
          </div>
        )}
      </Widget>
    </div>
  );
}

function ModelCardItem({
  card,
  active,
  onClick,
}: {
  card: ModelCardT;
  active: boolean;
  onClick: () => void;
}) {
  const isActive = (card.status ?? "").toLowerCase() === "active";
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full flex-col gap-1.5 rounded-card border p-3 text-left transition-colors",
        active ? "border-primary bg-primary/5" : "border-hairline bg-surface-2/40 hover:bg-surface-2",
      )}
    >
      <div className="flex items-center gap-2">
        <Cpu className="size-4 shrink-0 text-content-dim" />
        <span className="min-w-0 flex-1 truncate text-13 font-semibold text-content">{card.model_name}</span>
        <span className="tnum shrink-0 text-12 text-content-dim">v{card.version}</span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {card.model_type && <Badge variant="neutral">{card.model_type}</Badge>}
        {isActive ? (
          <Badge variant="accent">
            <CheckCircle2 className="size-3" /> active
          </Badge>
        ) : (
          card.status && <Badge variant="neutral">{card.status}</Badge>
        )}
      </div>
      <div className="flex items-center gap-3 text-12 text-content-dim">
        <span className="tnum">{formatNumber(card.inferences)} inf.</span>
        {card.mean_confidence != null && (
          <span className="tnum">{formatPercent(card.mean_confidence, 0)} conf.</span>
        )}
        {Object.keys(card.calibration ?? {}).length > 0 && <span>calibrated</span>}
      </div>
    </button>
  );
}

/** Render numeric calibration metrics from ModelVersion.Metrics as chips. */
function MetricChips({ calibration }: { calibration: Record<string, unknown> }) {
  const entries = Object.entries(calibration ?? {}).filter(
    ([, v]) => typeof v === "number" && Number.isFinite(v),
  ) as [string, number][];
  if (!entries.length) {
    return <p className="text-13 text-content-dim">No stored calibration metrics for this version.</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([k, v]) => (
        <span
          key={k}
          className="inline-flex items-center gap-1.5 rounded-control border border-hairline bg-surface-2/50 px-2.5 py-1 text-12"
        >
          <span className="uppercase tracking-wide text-content-dim">{k}</span>
          <span className="tnum font-semibold text-content">{v < 1 ? v.toFixed(3) : formatNumber(v)}</span>
        </span>
      ))}
    </div>
  );
}
