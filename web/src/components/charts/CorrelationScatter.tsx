import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { ScatterSeries } from "@/api/types";
import { assertChart, axisProps, gridProps, tooltipStyle, useChartTheme } from "@/lib/chart-theme";
import { categoryColor } from "@/lib/palette";
import { formatNumber } from "@/lib/utils";

/* ============================================================================
   Socio-economic scatter (doc 03 §2.10). One district = one point (x = the
   indicator, y = crime rate per 100k), with the fitted regression line and a
   clearly-labelled "correlational, not causal" caption. A fit line is the only
   overlay — never a second axis that would imply a manufactured correlation.
   ========================================================================== */

export function CorrelationScatter({ series, height = 280 }: { series: ScatterSeries; height?: number }) {
  const theme = useChartTheme();
  assertChart({ kind: "scatter", yAxes: 1, threeD: false, usesRainbow: false, redundantEncoding: true });

  const pts = series.points ?? [];
  const color = categoryColor(series.crime_category);

  const xs = pts.map((p) => p.x);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const hasFit = series.fit_slope != null && series.fit_intercept != null && pts.length >= 2;
  const yAt = (x: number) => (series.fit_intercept ?? 0) + (series.fit_slope ?? 0) * x;

  return (
    <div className="space-y-1.5">
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 8, right: 12, bottom: 16, left: -8 }}>
          <CartesianGrid {...gridProps(theme)} vertical />
          <XAxis
            type="number"
            dataKey="x"
            name={series.indicator}
            {...axisProps(theme)}
            domain={["dataMin", "dataMax"]}
            tickFormatter={(v: number) => formatNumber(Math.round(v))}
            label={{ value: series.indicator, position: "insideBottom", offset: -8, fill: theme.textDim, fontSize: 12 }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Crime rate /100k"
            {...axisProps(theme)}
            width={52}
            tickFormatter={(v: number) => formatNumber(Math.round(v))}
          />
          <ZAxis type="number" dataKey="crime_count" range={[40, 260]} name="cases" />
          <Tooltip {...tooltipStyle(theme)} content={<PointTooltip indicator={series.indicator} />} />
          {hasFit && (
            <ReferenceLine
              stroke={theme.textDim}
              strokeWidth={1.5}
              strokeDasharray="5 4"
              ifOverflow="extendDomain"
              segment={[
                { x: xMin, y: yAt(xMin) },
                { x: xMax, y: yAt(xMax) },
              ]}
            />
          )}
          <Scatter data={pts} fill={color} fillOpacity={0.8} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
      <p className="px-1 text-12 italic text-content-dim">
        Each dot is a district (dot size = case volume); the dashed line is the linear fit
        {series.r != null && (
          <>
            {" "}
            (r = <span className="tnum not-italic font-medium text-content">{series.r.toFixed(2)}</span>)
          </>
        )}
        . Correlational, not causal.
      </p>
    </div>
  );
}

function PointTooltip({
  active,
  payload,
  indicator,
}: {
  active?: boolean;
  payload?: Array<{ payload: { district_name: string; x: number; y: number; crime_count: number } }>;
  indicator: string;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-card border border-hairline bg-surface-2 px-2.5 py-1.5 text-12 shadow-pop">
      <div className="font-medium text-content">{p.district_name}</div>
      <div className="tnum mt-0.5 text-content-dim">
        {indicator}: <span className="text-content">{formatNumber(Math.round(p.x))}</span>
      </div>
      <div className="tnum text-content-dim">
        Rate /100k: <span className="text-content">{formatNumber(Math.round(p.y))}</span>
      </div>
      <div className="tnum text-content-dim">
        Cases: <span className="text-content">{formatNumber(p.crime_count)}</span>
      </div>
    </div>
  );
}
