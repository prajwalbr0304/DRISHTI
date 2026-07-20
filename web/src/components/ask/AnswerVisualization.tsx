import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChevronDown, Network, Share2, Table2 } from "lucide-react";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { api } from "@/api";
import type { TrendPoint, VizSpec } from "@/api/types";
import type { AskMessage } from "@/stores/useAskStore";
import { cn, formatDateTime, formatNumber, formatPercent } from "@/lib/utils";
import {
  assertChart,
  axisProps,
  gridProps,
  seriesColor,
  tooltipStyle,
  useChartTheme,
} from "@/lib/chart-theme";
import { TrendChart } from "@/components/charts/TrendChart";
import { MapCanvas, type MapViewState } from "@/components/map/MapCanvas";
import {
  BLUE_RAMP_RGB,
  HEAT_RAMP_RGB,
  KARNATAKA_VIEW,
} from "@/components/map/mapConfig";
import {
  districtBoundaries,
  districtChoropleth,
  normalizeDistrictName,
  pickDistrictName,
  stateBoundary,
} from "@/components/map/layers";

/* ============================================================================
   Ask DRISHTI answer visualization (Prompt 19 §F). The server hands back a
   typed, validated `visualization` spec whose dimension/measure `index` fields
   point into the SAME `columns` / `rows_preview` the answer already carries. We
   render it DETERMINISTICALLY by kind — never eval, never dangerouslySetInnerHTML,
   never execute model-authored code — reusing the product's chart, map and table
   components. Beneath every chart/map we always keep an accessible data table
   (the accessible_table fallback), and for a null spec we preserve the existing
   collapsible results table so there is no regression.
   ========================================================================== */

export function AnswerVisualization({ message }: { message: AskMessage }) {
  const viz = message.visualization ?? null;
  const columns = message.columns ?? [];
  const rows = message.rowsPreview ?? [];
  const total = message.rowCount ?? rows.length;

  // No typed spec: keep the existing collapsible results table (or nothing).
  if (!viz) {
    if (rows.length > 0 && columns.length > 0) {
      return <ResultPreview columns={columns} rows={rows} total={total} />;
    }
    return null;
  }

  switch (viz.kind) {
    case "number":
      return (
        <ChartWithTable message={message} viz={viz}>
          <NumberViz viz={viz} rows={rows} />
        </ChartWithTable>
      );
    case "bar":
      return (
        <ChartWithTable message={message} viz={viz}>
          <BarViz viz={viz} rows={rows} />
        </ChartWithTable>
      );
    case "line":
      return (
        <ChartWithTable message={message} viz={viz}>
          <LineViz viz={viz} rows={rows} />
        </ChartWithTable>
      );
    case "timeline":
      // A timeline with a time dimension reads as a trend; otherwise a table.
      return hasTimeDimension(viz) ? (
        <ChartWithTable message={message} viz={viz}>
          <LineViz viz={viz} rows={rows} />
        </ChartWithTable>
      ) : (
        <TableViz message={message} viz={viz} />
      );
    case "choropleth":
    case "heatmap":
      return <ChoroplethViz message={message} viz={viz} />;
    case "network":
      return <TableViz message={message} viz={viz} note={<OpenInViewNote kind="network" />} />;
    case "sankey":
      return <TableViz message={message} viz={viz} note={<OpenInViewNote kind="sankey" />} />;
    case "link":
      return <TableViz message={message} viz={viz} note={<OpenInViewNote kind="link" />} />;
    case "table":
    default:
      return <TableViz message={message} viz={viz} />;
  }
}

/* --------------------------------------------------------------------------
   Layout frames
   ------------------------------------------------------------------------ */

/** Chart/map kinds: title + chart + metadata footer + a details-wrapped
 *  accessible data table (always present, never visually duplicated). */
function ChartWithTable({
  message,
  viz,
  children,
}: {
  message: AskMessage;
  viz: VizSpec;
  children: ReactNode;
}) {
  const columns = message.columns ?? [];
  const rows = message.rowsPreview ?? [];
  const total = message.rowCount ?? rows.length;
  return (
    <div className="space-y-2">
      <VizTitle title={viz.title} />
      {children}
      <VizFooter viz={viz} sourceCount={sourceCount(message, viz)} />
      <details className="overflow-hidden rounded-control border border-hairline">
        <summary className="flex cursor-pointer items-center gap-2 bg-surface-2/50 px-2.5 py-1.5 text-12 text-content-dim transition-colors hover:text-content">
          <Table2 className="size-3.5" />
          <span className="font-medium text-content">Show data table</span>
        </summary>
        <div className="border-t border-hairline">
          <DataTable columns={columns} rows={rows} total={total} caption={viz.title} />
        </div>
      </details>
    </div>
  );
}

/** Table-first kinds (table / network / sankey / link / plain timeline). */
function TableViz({
  message,
  viz,
  note,
}: {
  message: AskMessage;
  viz: VizSpec;
  note?: ReactNode;
}) {
  const columns = message.columns ?? [];
  const rows = message.rowsPreview ?? [];
  const total = message.rowCount ?? rows.length;
  return (
    <div className="space-y-2">
      <VizTitle title={viz.title} />
      <ResultPreview columns={columns} rows={rows} total={total} defaultOpen />
      {note}
      <VizFooter viz={viz} sourceCount={sourceCount(message, viz)} />
    </div>
  );
}

/* --------------------------------------------------------------------------
   Kind renderers
   ------------------------------------------------------------------------ */

function NumberViz({ viz, rows }: { viz: VizSpec; rows: unknown[][] }) {
  const measure = viz.measures[0];
  const idx = measure?.index ?? 0;
  const raw = rows[0]?.[idx];
  const value = Number(raw);
  return (
    <div className="rounded-control border border-hairline bg-surface-2/40 px-4 py-3">
      <div className="text-11 uppercase tracking-wide text-content-dim">
        {measure?.label ?? viz.title}
      </div>
      <div className="tnum text-28 font-semibold leading-tight text-content">
        {Number.isFinite(value) ? formatNumber(value) : String(raw ?? "—")}
        {measure?.unit ? (
          <span className="ml-1.5 text-14 font-normal text-content-dim">{measure.unit}</span>
        ) : null}
      </div>
    </div>
  );
}

function BarViz({ viz, rows }: { viz: VizSpec; rows: unknown[][] }) {
  const theme = useChartTheme();
  assertChart({ kind: "bar", yAxes: 1, threeD: false, usesRainbow: false, redundantEncoding: true });

  const catIdx = viz.dimensions[0]?.index ?? 0;
  const measure = viz.measures[0];
  const valIdx = measure?.index ?? 1;
  const label = measure?.label ?? "Value";

  const data = useMemo(
    () =>
      rows.map((r) => ({
        category: String(r[catIdx] ?? ""),
        value: toNumber(r[valIdx]),
      })),
    [rows, catIdx, valIdx],
  );

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid {...gridProps(theme)} />
        <XAxis dataKey="category" {...axisProps(theme)} interval={0} minTickGap={8} />
        <YAxis {...axisProps(theme)} width={44} allowDecimals={false} />
        <Tooltip {...tooltipStyle(theme)} />
        <Bar
          dataKey="value"
          name={label}
          fill={seriesColor(0)}
          radius={[3, 3, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

function LineViz({ viz, rows }: { viz: VizSpec; rows: unknown[][] }) {
  const timeIdx = timeDimIndex(viz);
  const valIdx = viz.measures[0]?.index ?? 1;
  const series = useMemo<TrendPoint[]>(
    () =>
      rows.map((r) => ({
        period: String(r[timeIdx] ?? ""),
        count: toNumber(r[valIdx]),
        is_anomaly: false,
      })),
    [rows, timeIdx, valIdx],
  );
  return <TrendChart series={series} height={240} />;
}

const TOOLTIP_STYLE: Record<string, string> = {
  background: "#1d2740",
  color: "#e8ecf6",
  fontSize: "12px",
  padding: "4px 8px",
  borderRadius: "8px",
  border: "1px solid #28324d",
};

function ChoroplethViz({ message, viz }: { message: AskMessage; viz: VizSpec }) {
  const columns = message.columns ?? [];
  const rows = message.rowsPreview ?? [];
  const total = message.rowCount ?? rows.length;

  // Reference geography (fetched once, cached forever). Never blocks the answer.
  const distBndQ = useQuery({
    queryKey: ["geo", "boundary", "districts"],
    queryFn: ({ signal }) => api.geo.boundaries("districts", signal),
    staleTime: Infinity,
    retry: false,
  });
  const stateBndQ = useQuery({
    queryKey: ["geo", "boundary", "state"],
    queryFn: ({ signal }) => api.geo.boundaries("state", signal),
    staleTime: Infinity,
    retry: false,
  });

  const geoDim =
    viz.dimensions.find((d) => d.field === viz.geo_field) ??
    viz.dimensions.find((d) => /geo|district/i.test(d.role)) ??
    viz.dimensions[0];
  const geoIdx = geoDim?.index ?? 0;
  const measure = viz.measures[0];
  const valIdx = measure?.index ?? 1;

  const valuesByDistrict = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of rows) {
      const name = String(r[geoIdx] ?? "").trim();
      const v = toNumber(r[valIdx]);
      if (name && Number.isFinite(v)) m[normalizeDistrictName(name)] = v;
    }
    return m;
  }, [rows, geoIdx, valIdx]);

  const ramp = viz.kind === "heatmap" ? HEAT_RAMP_RGB : BLUE_RAMP_RGB;
  const boundaries = distBndQ.data;
  const featureCount = boundaries?.features?.length ?? 0;
  const mapReady = !distBndQ.isError && featureCount > 0;

  const layers = useMemo<Layer[]>(() => {
    if (!mapReady || !boundaries) return [];
    const L: Layer[] = [districtChoropleth(boundaries, valuesByDistrict, ramp)];
    L.push(districtBoundaries(boundaries));
    if (stateBndQ.data) L.push(stateBoundary(stateBndQ.data));
    return L;
  }, [mapReady, boundaries, valuesByDistrict, ramp, stateBndQ.data]);

  const [viewState, setViewState] = useState<MapViewState>(() => ({ ...KARNATAKA_VIEW }));

  const getTooltip = (info: PickingInfo): { html: string } | null => {
    const f = info.object as GeoJSON.Feature | undefined;
    if (!f) return null;
    const raw = pickDistrictName(f.properties);
    if (!raw) return null;
    const v = valuesByDistrict[normalizeDistrictName(raw)];
    const valueText =
      v != null
        ? `${measure?.label ?? "value"}: ${formatNumber(v)}${measure?.unit ? " " + measure.unit : ""}`
        : "no data";
    return { html: `<div style="${styleString(TOOLTIP_STYLE)}">${escapeHtml(raw)} · ${escapeHtml(valueText)}</div>` };
  };

  return (
    <div className="space-y-2">
      <VizTitle title={viz.title} />
      {mapReady ? (
        <div className="relative h-[280px] w-full overflow-hidden rounded-control border border-hairline">
          <MapCanvas
            viewState={viewState}
            onViewStateChange={setViewState}
            layers={layers}
            getTooltip={getTooltip}
          />
        </div>
      ) : distBndQ.isLoading ? (
        <div className="grid h-[280px] w-full place-items-center rounded-control border border-hairline bg-surface-2/30 text-12 text-content-dim">
          Loading map…
        </div>
      ) : (
        <p className="text-12 text-content-dim">Map unavailable — showing the data table.</p>
      )}
      <VizFooter viz={viz} sourceCount={sourceCount(message, viz)} />
      {mapReady ? (
        <details className="overflow-hidden rounded-control border border-hairline">
          <summary className="flex cursor-pointer items-center gap-2 bg-surface-2/50 px-2.5 py-1.5 text-12 text-content-dim transition-colors hover:text-content">
            <Table2 className="size-3.5" />
            <span className="font-medium text-content">Show data table</span>
          </summary>
          <div className="border-t border-hairline">
            <DataTable columns={columns} rows={rows} total={total} caption={viz.title} />
          </div>
        </details>
      ) : (
        <DataTable columns={columns} rows={rows} total={total} caption={viz.title} />
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------
   Small pieces
   ------------------------------------------------------------------------ */

function VizTitle({ title }: { title: string }) {
  if (!title) return null;
  return <div className="text-13 font-medium text-content">{title}</div>;
}

function OpenInViewNote({ kind }: { kind: "network" | "sankey" | "link" }) {
  const label = kind === "network" ? "Network" : kind === "sankey" ? "Sankey" : "Link";
  const Icon = kind === "sankey" ? Share2 : Network;
  return (
    <p className="inline-flex items-center gap-1.5 text-12 text-content-dim">
      <Icon className="size-3.5" />
      Open in {label} view for the full graph.
    </p>
  );
}

/** Compact metadata footer for chart/map kinds (as-of · dataset · scope ·
 *  confidence · sources). Citations themselves are rendered by AnswerCard. */
function VizFooter({ viz, sourceCount }: { viz: VizSpec; sourceCount: number }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-hairline pt-2 text-11 text-content-dim">
      {viz.as_of && <span>as of {formatDateTime(viz.as_of)}</span>}
      {viz.dataset && (
        <span className="rounded bg-surface-2 px-1.5 py-0.5">{viz.dataset}</span>
      )}
      {viz.scope_role && <span>scope: {viz.scope_role}</span>}
      {viz.confidence != null && (
        <span className="tnum">{formatPercent(viz.confidence, 0)} confidence</span>
      )}
      {sourceCount > 0 && <span>Sources: {sourceCount}</span>}
      {viz.suppressed > 0 && <span>{viz.suppressed} suppressed</span>}
    </div>
  );
}

/* --------------------------------------------------------------------------
   Tables — a single accessible implementation, reused everywhere.
   ------------------------------------------------------------------------ */

/** The accessible data table. Always renders real <table> markup with a caption
 *  and column scopes; this is the accessible_table fallback for every kind. */
export function DataTable({
  columns,
  rows,
  total,
  caption,
  max = 50,
}: {
  columns: string[];
  rows: unknown[][];
  total: number;
  caption?: string;
  max?: number;
}) {
  const shown = rows.slice(0, max);
  return (
    <div className="max-h-64 overflow-auto">
      <table className="w-full text-12">
        <caption className="sr-only">{caption ? `${caption} — data table` : "Answer data table"}</caption>
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b border-hairline text-left text-content-dim">
            {columns.map((c) => (
              <th key={c} scope="col" className="px-2.5 py-1.5 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((row, ri) => (
            <tr key={ri} className="border-b border-hairline/60 last:border-0">
              {row.map((cell, ci) => (
                <td key={ci} className="tnum px-2.5 py-1.5 text-content">
                  {cell == null ? "—" : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {total > shown.length && (
        <p className="px-2.5 py-1.5 text-[11px] text-content-dim">
          Showing {shown.length} of {total} rows.
        </p>
      )}
    </div>
  );
}

/** Collapsible "Results" preview used for the table kind and for answers with
 *  incidental rows but no typed spec (preserves the pre-Prompt-19 display). */
export function ResultPreview({
  columns,
  rows,
  total,
  defaultOpen = false,
}: {
  columns: string[];
  rows: unknown[][];
  total: number;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="overflow-hidden rounded-control border border-hairline">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 bg-surface-2/50 px-2.5 py-1.5 text-12 text-content-dim transition-colors hover:text-content"
      >
        <Table2 className="size-3.5" />
        <span className="font-medium text-content">Results</span>
        <span className="tnum rounded bg-surface-2 px-1.5 py-0.5 text-[11px]">{total} row(s)</span>
        <ChevronDown className={cn("ml-auto size-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && <DataTable columns={columns} rows={rows} total={total} max={10} />}
    </div>
  );
}

/* --------------------------------------------------------------------------
   Helpers
   ------------------------------------------------------------------------ */

function toNumber(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function sourceCount(message: AskMessage, viz: VizSpec): number {
  const cited = message.citedRecordIds?.length ?? 0;
  return cited > 0 ? cited : viz.source_ids.length;
}

function hasTimeDimension(viz: VizSpec): boolean {
  if (viz.time_field) return true;
  return viz.dimensions.some((d) => isTimeish(d.role) || isTimeish(d.field));
}

function timeDimIndex(viz: VizSpec): number {
  if (viz.time_field) {
    const d = viz.dimensions.find((dim) => dim.field === viz.time_field);
    if (d) return d.index;
  }
  const t = viz.dimensions.find((d) => isTimeish(d.role) || isTimeish(d.field));
  return t?.index ?? viz.dimensions[0]?.index ?? 0;
}

function isTimeish(s: string): boolean {
  return /time|date|period|month|year|day|week|quarter/i.test(s);
}

/** Serialize a style map for the deck.gl tooltip HTML (values are our own
 *  static constants, and free text is escaped by escapeHtml). */
function styleString(style: Record<string, string>): string {
  return Object.entries(style)
    .map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase())}:${v}`)
    .join(";");
}

/** Escape answer-derived text before it goes into the deck.gl tooltip HTML. */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
