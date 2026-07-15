import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DriftPoint } from "@/api/types";
import { assertChart, axisProps, gridProps, tooltipStyle, useChartTheme } from "@/lib/chart-theme";
import { formatNumber, formatPercent } from "@/lib/utils";

/* ============================================================================
   Model drift (doc 01 §4.6). Mean inference confidence per month from the audit
   log — a sustained shift flags drift for review. Confidence is the single Y
   axis (0–1); monthly inference volume rides in the tooltip only (no dual axis,
   per the house rules).
   ========================================================================== */

export function DriftChart({ drift, height = 200 }: { drift: DriftPoint[]; height?: number }) {
  const theme = useChartTheme();
  assertChart({ kind: "line", yAxes: 1, threeD: false, usesRainbow: false, redundantEncoding: true });

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={drift} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid {...gridProps(theme)} />
        <XAxis dataKey="period" {...axisProps(theme)} minTickGap={24} />
        <YAxis
          {...axisProps(theme)}
          width={44}
          domain={[0, 1]}
          tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
        />
        <Tooltip
          {...tooltipStyle(theme)}
          formatter={(value: unknown, name: string) =>
            name === "Mean confidence"
              ? [formatPercent(Number(value), 0), name]
              : [formatNumber(Number(value)), name]
          }
        />
        <Line
          type="monotone"
          dataKey="mean_confidence"
          name="Mean confidence"
          stroke={theme.primary}
          strokeWidth={2}
          dot={{ r: 2, fill: theme.primary }}
          isAnimationActive={false}
          connectNulls
        />
        {/* volume carried in the tooltip only — kept off-axis to avoid dual axes */}
        <Line dataKey="count" name="Inferences" stroke="transparent" dot={false} legendType="none" isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
