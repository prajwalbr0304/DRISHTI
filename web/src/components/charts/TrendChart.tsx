import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "@/api/types";
import {
  assertChart,
  axisProps,
  gridProps,
  SERIES_DASH,
  seriesColor,
  tooltipStyle,
  useChartTheme,
} from "@/lib/chart-theme";

/* ============================================================================
   Crime trend chart. Obeys the house rules: single Y axis, no 3D, no rainbow,
   and series are distinguished by more than colour (the rolling mean is dashed;
   anomalies are marked with a labelled dot).
   ========================================================================== */

export function TrendChart({ series, height = 240 }: { series: TrendPoint[]; height?: number }) {
  const theme = useChartTheme();
  assertChart({ kind: "area", yAxes: 1, threeD: false, usesRainbow: false, redundantEncoding: true });

  const countColor = seriesColor(0);
  const meanColor = seriesColor(1);
  const anomalies = series.filter((p) => p.is_anomaly);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={countColor} stopOpacity={0.35} />
            <stop offset="100%" stopColor={countColor} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid {...gridProps(theme)} />
        <XAxis dataKey="period" {...axisProps(theme)} minTickGap={24} />
        <YAxis {...axisProps(theme)} width={44} allowDecimals={false} />
        <Tooltip {...tooltipStyle(theme)} />
        <Area
          type="monotone"
          dataKey="count"
          name="Incidents"
          stroke={countColor}
          strokeWidth={2}
          fill="url(#trendFill)"
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="rolling_mean"
          name="Rolling mean"
          stroke={meanColor}
          strokeWidth={1.5}
          strokeDasharray={SERIES_DASH[1]}
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
        {anomalies.map((p) => (
          <ReferenceDot
            key={p.period}
            x={p.period}
            y={p.count}
            r={4}
            fill="var(--sev-critical)"
            stroke="var(--surface)"
            strokeWidth={1.5}
            ifOverflow="extendDomain"
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
