import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CorrelationCell } from "@/api/types";
import { assertChart, axisProps, gridProps, tooltipStyle, useChartTheme } from "@/lib/chart-theme";
import { DIVERGING, sampleRamp } from "@/lib/palette";
import { humanizeKey } from "@/lib/utils";

/* ============================================================================
   Correlation bars (doc 03 §2.10). For ONE crime category, Pearson r against
   every socio-economic indicator, ranked by strength and diverging around zero
   so sign is read from position, not just hue. Bars share the CVD-safe DIVERGING
   ramp with the correlation-matrix heatmap, and the r value is printed at the
   end of every bar — meaning never rides on colour alone (doc 03 §7).

   Indicators whose r is null (suppressed cell / too few districts to fit) are
   left OUT and counted in the caption. A missing correlation is never drawn as
   a zero-length bar, which would read as "no relationship".
   ========================================================================== */

type BarRow = {
  indicator: string;
  label: string;
  r: number;
  strength: string | null;
  n: number;
  p_value: number | null;
};

export function CorrelationBars({
  cells,
  crimeCategory,
  focusIndicator,
  onSelectIndicator,
  maxRows = 10,
}: {
  cells: CorrelationCell[];
  crimeCategory: string;
  focusIndicator?: string;
  onSelectIndicator?: (indicator: string) => void;
  maxRows?: number;
}) {
  const theme = useChartTheme();
  assertChart({ kind: "bar", yAxes: 1, threeD: false, usesRainbow: false, redundantEncoding: true });

  const { rows, unavailable } = useMemo(() => {
    const forCategory = cells.filter((c) => c.crime_category === crimeCategory);
    const usable: BarRow[] = forCategory
      .filter((c) => c.r != null)
      .map((c) => ({
        indicator: c.indicator,
        label: humanizeKey(c.indicator),
        r: c.r as number,
        strength: c.strength ?? null,
        n: c.n,
        p_value: c.p_value ?? null,
      }))
      .sort((a, b) => Math.abs(b.r) - Math.abs(a.r))
      .slice(0, maxRows);
    return { rows: usable, unavailable: forCategory.length - usable.length };
  }, [cells, crimeCategory, maxRows]);

  if (!rows.length) {
    return (
      <p className="py-6 text-center text-13 text-content-dim">
        No indicator cleared the suppression threshold for {crimeCategory.toLowerCase()}.
      </p>
    );
  }

  const height = Math.max(150, rows.length * 26 + 28);
  const clickable = Boolean(onSelectIndicator);

  return (
    <div className="space-y-1.5">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 4, right: 44, bottom: 2, left: 2 }}
          barCategoryGap="20%"
        >
          <CartesianGrid {...gridProps(theme)} vertical horizontal={false} />
          <XAxis
            type="number"
            dataKey="r"
            domain={[-1, 1]}
            ticks={[-1, -0.5, 0, 0.5, 1]}
            tickFormatter={(v: number) => v.toFixed(1)}
            height={18}
            {...axisProps(theme)}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={122}
            interval={0}
            {...axisProps(theme)}
            tick={{ fill: theme.textDim, fontSize: 11 }}
          />
          <ReferenceLine x={0} stroke={theme.axis} strokeWidth={1} />
          <Tooltip {...tooltipStyle(theme)} content={<BarTooltip crimeCategory={crimeCategory} />} />
          <Bar
            dataKey="r"
            barSize={13}
            radius={2}
            isAnimationActive={false}
            className={clickable ? "cursor-pointer" : undefined}
            onClick={(entry: unknown) => {
              const key = (entry as { indicator?: string; payload?: { indicator?: string } } | undefined);
              const indicator = key?.indicator ?? key?.payload?.indicator;
              if (indicator) onSelectIndicator?.(indicator);
            }}
          >
            {rows.map((row) => {
              const focused = row.indicator === focusIndicator;
              return (
                <Cell
                  key={row.indicator}
                  fill={sampleRamp(DIVERGING, (row.r + 1) / 2)}
                  stroke={focused ? theme.primary : undefined}
                  strokeWidth={focused ? 1.5 : 0}
                />
              );
            })}
            <LabelList dataKey="r" content={<RValueLabel fill={theme.text} />} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <p className="px-1 text-12 italic text-content-dim">
        Pearson r against per-capita {crimeCategory.toLowerCase()} across districts
        {clickable ? "; click a bar to focus the scatter" : ""}.
        {unavailable > 0 && (
          <>
            {" "}
            <span className="tnum not-italic">{unavailable}</span> indicator
            {unavailable === 1 ? "" : "s"} omitted (suppressed or too few districts).
          </>
        )}{" "}
        Correlational, not causal.
      </p>
    </div>
  );
}

/** r printed at the open end of each bar, so the value is never colour-only. */
function RValueLabel({
  x,
  y,
  width,
  height,
  value,
  fill,
}: {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  height?: number | string;
  value?: number | string;
  fill?: string;
}) {
  const r = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(r)) return null;

  // Recharts may hand back a negative width for left-of-zero bars; normalise.
  const bx = Number(x) || 0;
  const bw = Number(width) || 0;
  const left = bw < 0 ? bx + bw : bx;
  const right = bw < 0 ? bx : bx + bw;
  const positive = r >= 0;

  return (
    <text
      x={positive ? right + 6 : left - 6}
      y={(Number(y) || 0) + (Number(height) || 0) / 2}
      dy={4}
      textAnchor={positive ? "start" : "end"}
      className="tnum"
      fill={fill}
      fontSize={11}
      fontWeight={500}
    >
      {positive ? "+" : "−"}
      {Math.abs(r).toFixed(2)}
    </text>
  );
}

function BarTooltip({
  active,
  payload,
  crimeCategory,
}: {
  active?: boolean;
  payload?: Array<{ payload: BarRow }>;
  crimeCategory?: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-card border border-hairline bg-surface-2 px-2.5 py-1.5 text-12 shadow-pop">
      <div className="font-medium text-content">
        {row.label} <span className="text-content-dim">↔</span> {crimeCategory}
      </div>
      <div className="tnum mt-0.5 text-content-dim">
        r = <span className="text-content">{row.r >= 0 ? "+" : "−"}{Math.abs(row.r).toFixed(3)}</span>
        {row.strength && <span className="capitalize"> · {row.strength}</span>}
      </div>
      <div className="tnum text-content-dim">
        {row.p_value != null && (
          <>
            p = <span className="text-content">{row.p_value.toFixed(3)}</span> ·{" "}
          </>
        )}
        n = <span className="text-content">{row.n}</span> districts
      </div>
    </div>
  );
}
