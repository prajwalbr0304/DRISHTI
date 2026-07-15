import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendDecomposition } from "@/api/types";
import { assertChart, axisProps, gridProps, seriesColor, tooltipStyle, useChartTheme } from "@/lib/chart-theme";

/* ============================================================================
   Classic additive decomposition (doc 03 §2.3 — the "STL toggle"). Three small
   multiples sharing one time axis: trend, seasonal, residual. Small multiples
   (not three lines on one axis) so each component is read on its own scale — the
   honest way to show a decomposition. Single Y axis each, no rainbow.
   ========================================================================== */

type Part = { key: "trend" | "seasonal" | "residual"; label: string; hint: string };
const PARTS: Part[] = [
  { key: "trend", label: "Trend", hint: "long-run level (centered moving average)" },
  { key: "seasonal", label: "Seasonal", hint: "month-of-year effect" },
  { key: "residual", label: "Residual", hint: "what trend + seasonal don't explain" },
];

export function DecompositionChart({ data }: { data: TrendDecomposition }) {
  const theme = useChartTheme();
  assertChart({ kind: "line", yAxes: 1, threeD: false, usesRainbow: false, redundantEncoding: true });

  return (
    <div className="space-y-2">
      {PARTS.map((part, i) => {
        const rows = data.periods.map((period, idx) => ({ period, value: data[part.key][idx] }));
        const isLast = i === PARTS.length - 1;
        const color = seriesColor(i);
        return (
          <div key={part.key}>
            <div className="mb-0.5 flex items-baseline gap-2 px-1">
              <span className="text-12 font-semibold text-content">{part.label}</span>
              <span className="text-12 text-content-dim">{part.hint}</span>
            </div>
            <ResponsiveContainer width="100%" height={isLast ? 96 : 78}>
              <LineChart data={rows} margin={{ top: 4, right: 8, bottom: isLast ? 0 : 0, left: -12 }}>
                <CartesianGrid {...gridProps(theme)} />
                <XAxis
                  dataKey="period"
                  {...axisProps(theme)}
                  minTickGap={28}
                  hide={!isLast}
                />
                <YAxis {...axisProps(theme)} width={44} />
                <Tooltip {...tooltipStyle(theme)} />
                {part.key === "residual" && (
                  <ReferenceLine y={0} stroke={theme.grid} strokeDasharray="2 4" />
                )}
                <Line
                  type="monotone"
                  dataKey="value"
                  name={part.label}
                  stroke={color}
                  strokeWidth={1.75}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        );
      })}
    </div>
  );
}
