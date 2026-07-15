import { cn, formatNumber } from "@/lib/utils";

/* ============================================================================
   Horizontal comparison bars (doc 03 §2.2 / §2.14). Sorted, single-hue —
   comparison is by length, not colour (30 districts must never mean 30 hues).
   ========================================================================== */

export interface BarDatum {
  key: string;
  label: string;
  value: number;
  onClick?: () => void;
}

export function DistrictBars({
  data,
  max = 8,
  unit,
}: {
  data: BarDatum[];
  max?: number;
  unit?: string;
}) {
  const rows = [...data].sort((a, b) => b.value - a.value).slice(0, max);
  const peak = Math.max(1, ...rows.map((r) => r.value));

  return (
    <div className="space-y-1.5">
      {rows.map((r) => {
        const pct = (r.value / peak) * 100;
        const Row = r.onClick ? "button" : "div";
        return (
          <Row
            key={r.key}
            onClick={r.onClick}
            className={cn(
              "flex w-full items-center gap-3 rounded-control px-1.5 py-1 text-left",
              r.onClick && "transition-colors hover:bg-surface-2",
            )}
          >
            <span className="w-28 shrink-0 truncate text-13 text-content" title={r.label}>
              {r.label}
            </span>
            <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
              <span
                className="absolute inset-y-0 left-0 rounded-full bg-primary"
                style={{ width: `${pct}%` }}
              />
            </span>
            <span className="tnum w-14 shrink-0 text-right text-13 font-medium text-content">
              {formatNumber(r.value)}
              {unit && <span className="ml-0.5 text-12 text-content-dim">{unit}</span>}
            </span>
          </Row>
        );
      })}
    </div>
  );
}
