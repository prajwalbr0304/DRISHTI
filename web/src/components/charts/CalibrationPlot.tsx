import { ArrowDown, ArrowUp } from "lucide-react";
import { cn, formatPercent } from "@/lib/utils";

/* ============================================================================
   Calibration plot (doc 01 §4.6 "model cards + calibration plot"). Compares the
   deployed foundation model against its baseline across the calibration metrics
   actually recorded on the held-out set — accuracy / macro-F1 (higher = better)
   and Brier / ECE (lower = better, the direct calibration-error metrics). A
   grouped comparison (doc 03 §2.14), never colour-alone: each bar is labelled
   with its model and value, and every metric states which direction is better.
   ========================================================================== */

type Dir = "up" | "down";
const METRICS: { key: string; label: string; better: Dir; hint: string }[] = [
  { key: "accuracy", label: "Accuracy", better: "up", hint: "correct class share" },
  { key: "macro_f1", label: "Macro F1", better: "up", hint: "balanced precision/recall" },
  { key: "auc", label: "AUC", better: "up", hint: "ranking quality" },
  { key: "brier", label: "Brier", better: "down", hint: "mean squared prob. error" },
  { key: "ece", label: "ECE", better: "down", hint: "expected calibration error" },
  { key: "log_loss", label: "Log loss", better: "down", hint: "probabilistic loss" },
];

function num(d: Record<string, unknown>, k: string): number | null {
  const v = d?.[k];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function CalibrationPlot({
  foundation,
  baseline,
  agreement,
}: {
  foundation: Record<string, unknown>;
  baseline: Record<string, unknown>;
  agreement?: number | null;
}) {
  const foundationName = String(foundation?.model ?? "Foundation");
  const baselineName = String(baseline?.model ?? "Baseline");

  const rows = METRICS.map((m) => ({
    ...m,
    f: num(foundation, m.key),
    b: num(baseline, m.key),
  })).filter((m) => m.f != null || m.b != null);

  if (!rows.length) {
    return (
      <p className="text-13 text-content-dim">
        No comparative calibration metrics recorded for this model.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {/* legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-12">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-primary" /> <span className="text-content">{foundationName}</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-content-dim" /> <span className="text-content-dim">{baselineName}</span>
        </span>
      </div>

      <div className="space-y-2.5">
        {rows.map((m) => {
          const scale = Math.max(1, m.f ?? 0, m.b ?? 0);
          const better =
            m.f != null && m.b != null
              ? m.better === "up"
                ? m.f >= m.b
                : m.f <= m.b
              : null;
          return (
            <div key={m.key}>
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-13 font-medium text-content">{m.label}</span>
                <span className="inline-flex items-center gap-0.5 text-12 text-content-dim">
                  {m.better === "up" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
                  better
                </span>
                <span className="text-12 text-content-dim">· {m.hint}</span>
                {better != null && (
                  <span
                    className={cn(
                      "ml-auto text-12 font-medium",
                      better ? "text-severity-low" : "text-content-dim",
                    )}
                  >
                    {better ? "foundation leads" : "baseline leads"}
                  </span>
                )}
              </div>
              <Bar label={foundationName} value={m.f} scale={scale} tone="primary" />
              <Bar label={baselineName} value={m.b} scale={scale} tone="dim" />
            </div>
          );
        })}
      </div>

      {agreement != null && (
        <p className="border-t border-hairline pt-2 text-12 text-content-dim">
          Model agreement:{" "}
          <span className="tnum font-medium text-content">{formatPercent(agreement, 0)}</span> of held-out
          offenders receive the same band from both models.
        </p>
      )}
    </div>
  );
}

function Bar({
  label,
  value,
  scale,
  tone,
}: {
  label: string;
  value: number | null;
  scale: number;
  tone: "primary" | "dim";
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 truncate text-12 text-content-dim" title={label}>
        {label}
      </span>
      <span className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
        {value != null && (
          <span
            className={cn("absolute inset-y-0 left-0 rounded-full", tone === "primary" ? "bg-primary" : "bg-content-dim")}
            style={{ width: `${Math.max(2, (value / scale) * 100)}%` }}
          />
        )}
      </span>
      <span className="tnum w-12 shrink-0 text-right text-12 font-medium text-content">
        {value != null ? value.toFixed(3) : "—"}
      </span>
    </div>
  );
}
