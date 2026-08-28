import * as React from "react";
import { ArrowDownRight, ArrowUpRight, Info, Minus } from "lucide-react";
import { cn, formatCompact, formatNumber } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { SimpleTooltip } from "@/components/ui/tooltip";

/* ============================================================================
   KPI stat card (doc 03 §2.1): big tabular number + label + signed delta vs.
   prior period + 12-point sparkline. Delta shows an ARROW and a SIGN, never
   colour alone. Supports loading / error / and an honest "awaiting API" state.
   ========================================================================== */

export interface KpiCardProps {
  icon?: React.ReactNode;
  label: string;
  value?: number | null;
  unit?: string;
  /** signed percent change vs. prior period */
  delta?: number | null;
  /** when true, a downward move is the good direction (e.g. crime counts) */
  improveWhenDown?: boolean;
  /** recent values for the sparkline */
  spark?: number[];
  loading?: boolean;
  error?: unknown;
  /** endpoint not built yet — show honestly rather than fabricate */
  pending?: boolean;
  pendingNote?: string;
  hint?: React.ReactNode;
  className?: string;
}

export function KpiCard({
  icon,
  label,
  value,
  unit,
  delta,
  improveWhenDown = true,
  spark,
  loading,
  error,
  pending,
  pendingNote,
  hint,
  className,
}: KpiCardProps) {
  return (
    <div className={cn("flex flex-col justify-between rounded-card border border-hairline bg-surface p-5 shadow-card", className)}>
      <div className="flex items-center gap-2 text-body-s text-content-dim">
        {icon && <span className="[&_svg]:size-4">{icon}</span>}
        <span className="truncate">{label}</span>
        {(hint || pending) && (
          <SimpleTooltip label={pending ? pendingNote ?? "Awaiting a Wave-B endpoint." : hint}>
            <span className="ml-auto cursor-help text-content-dim/70">
              <Info className="size-3.5" />
            </span>
          </SimpleTooltip>
        )}
      </div>

      <div className="mt-2 flex items-end justify-between gap-2">
        <div className="min-w-0">
          {loading ? (
            <Skeleton className="h-8 w-24" />
          ) : pending ? (
            <div className="flex items-baseline gap-2">
              <span className="text-28 font-bold leading-none text-content-dim">—</span>
              <span className="rounded-badge bg-surface-2 px-1.5 py-0.5 text-body-s text-content-dim">
                awaiting API
              </span>
            </div>
          ) : error ? (
            <span className="text-heading-s text-content-dim">—</span>
          ) : (
            <span className="tnum text-28 font-bold leading-none text-content">
              {value == null ? "—" : value >= 100000 ? formatCompact(value) : formatNumber(value)}
              {unit && <span className="ml-0.5 text-heading-s font-bold text-content-dim">{unit}</span>}
            </span>
          )}
          {!loading && !pending && !error && delta != null && (
            <Delta pct={delta} improveWhenDown={improveWhenDown} />
          )}
        </div>

        {!pending && spark && spark.length > 1 && <Sparkline values={spark} />}
      </div>
    </div>
  );
}

function Delta({ pct, improveWhenDown }: { pct: number; improveWhenDown: boolean }) {
  const flat = Math.abs(pct) < 0.05;
  const up = pct > 0;
  const good = flat ? false : improveWhenDown ? !up : up;
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  return (
    <div
      className={cn(
        "mt-1.5 inline-flex items-center gap-0.5 text-body-s font-bold tnum",
        flat ? "text-content-dim" : good ? "text-severity-low" : "text-severity-high",
      )}
    >
      <Icon className="size-3.5" />
      <span>
        {up ? "+" : ""}
        {pct.toFixed(1)}%
      </span>
      <span className="ml-1 font-normal text-content-dim">vs. prior</span>
    </div>
  );
}

/** 12-point sparkline (doc 03 §2.1). Single hue, no axes. */
export function Sparkline({
  values,
  width = 88,
  height = 32,
}: {
  values: number[];
  width?: number;
  height?: number;
}) {
  const pts = values.slice(-12);
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const step = pts.length > 1 ? width / (pts.length - 1) : width;
  const d = pts
    .map((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / span) * (height - 4) - 2;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const lastX = (pts.length - 1) * step;
  const lastY = height - ((pts[pts.length - 1] - min) / span) * (height - 4) - 2;

  return (
    <svg width={width} height={height} className="shrink-0 overflow-visible" aria-hidden>
      <path d={d} fill="none" stroke="var(--primary)" strokeWidth={1.5} strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r={2} fill="var(--primary)" />
    </svg>
  );
}
