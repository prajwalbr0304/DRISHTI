import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  assertChart,
  axisProps,
  gridProps,
  SERIES_DASH,
  seriesColor,
  tooltipStyle,
  useChartTheme,
} from "@/lib/chart-theme";
import { formatNumber } from "@/lib/utils";

/* ============================================================================
   Forecast fan chart (doc 03 §2.15). Observed history as a solid line, then the
   forecast MEDIAN as a dashed line with two nested confidence ribbons (p25–p75
   inner, p10–p90 outer) that WIDEN with the horizon. Uncertainty is shown, never
   hidden; the median is dashed (not colour-alone) and a marker labels where the
   forecast begins. Single Y axis, no rainbow — house rules enforced.
   ========================================================================== */

export interface TrajectoryStep {
  step: number;
  period: string;
  median: number;
  p10: number;
  p25: number;
  p75: number;
  p90: number;
}

/** Shift a "YYYY-MM" period by `delta` months (delta may be negative). */
function shiftMonth(period: string, delta: number): string {
  const [y, m] = period.split("-").map(Number);
  const idx = y * 12 + (m - 1) + delta;
  const ny = Math.floor(idx / 12);
  const nm = (idx % 12) + 1;
  return `${ny.toString().padStart(4, "0")}-${nm.toString().padStart(2, "0")}`;
}

type Row = {
  period: string;
  actual?: number | null;
  median?: number | null;
  band90?: [number, number] | null;
  band50?: [number, number] | null;
};

export function FanChart({
  trajectory,
  history,
  height = 260,
}: {
  trajectory: TrajectoryStep[];
  /** last N monthly actual counts, oldest-first, ending the month before trajectory[0]. */
  history?: number[];
  height?: number;
}) {
  const theme = useChartTheme();
  assertChart({ kind: "area", yAxes: 1, threeD: false, usesRainbow: false, redundantEncoding: true });

  if (!trajectory.length) return null;

  const actualColor = seriesColor(1); // teal — observed
  const medianColor = theme.primary; // blue — forecast median

  const firstForecast = trajectory[0].period;
  const hist = history ?? [];
  const histRows: Row[] = hist.map((count, i) => ({
    period: shiftMonth(firstForecast, -(hist.length - i)),
    actual: count,
  }));

  // Anchor the fan at the last observed value so the ribbons widen from zero.
  if (histRows.length) {
    const last = histRows[histRows.length - 1];
    last.median = last.actual ?? undefined;
    last.band90 = [last.actual ?? 0, last.actual ?? 0];
    last.band50 = [last.actual ?? 0, last.actual ?? 0];
  }

  const fcRows: Row[] = trajectory.map((t) => ({
    period: t.period,
    median: t.median,
    band90: [t.p10, t.p90],
    band50: [t.p25, t.p75],
  }));

  const data: Row[] = [...histRows, ...fcRows];

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid {...gridProps(theme)} />
        <XAxis dataKey="period" {...axisProps(theme)} minTickGap={24} />
        <YAxis {...axisProps(theme)} width={44} allowDecimals={false} />
        <Tooltip
          {...tooltipStyle(theme)}
          formatter={(value: unknown, name: string) => {
            if (Array.isArray(value)) {
              const [lo, hi] = value as [number, number];
              return [`${formatNumber(Math.round(lo))} – ${formatNumber(Math.round(hi))}`, name];
            }
            return [formatNumber(Math.round(Number(value))), name];
          }}
        />
        {/* Outer 80% band (p10–p90) then inner 50% band (p25–p75) */}
        <Area
          type="monotone"
          dataKey="band90"
          name="80% interval"
          stroke="none"
          fill={medianColor}
          fillOpacity={0.12}
          isAnimationActive={false}
          connectNulls
        />
        <Area
          type="monotone"
          dataKey="band50"
          name="50% interval"
          stroke="none"
          fill={medianColor}
          fillOpacity={0.22}
          isAnimationActive={false}
          connectNulls
        />
        <ReferenceLine
          x={firstForecast}
          stroke={theme.textDim}
          strokeDasharray="3 3"
          label={{ value: "forecast", position: "insideTopRight", fill: theme.textDim, fontSize: 11 }}
        />
        <Line
          type="monotone"
          dataKey="actual"
          name="Observed"
          stroke={actualColor}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="median"
          name="Forecast median"
          stroke={medianColor}
          strokeWidth={2}
          strokeDasharray={SERIES_DASH[1]}
          dot={{ r: 2, fill: medianColor }}
          isAnimationActive={false}
          connectNulls
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
