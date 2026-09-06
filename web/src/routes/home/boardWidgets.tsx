import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { MapPinned, Sparkles } from "lucide-react";
import { api } from "@/api";
import { Widget } from "@/components/widget/Widget";
import { TrendChart } from "@/components/charts/TrendChart";
import { ForecastSummary } from "@/components/dashboard/ForecastSummary";
import { JurisdictionMap } from "@/components/dashboard/JurisdictionMap";
import { StatusPipeline, CASE_STAGES } from "@/components/dashboard/StatusPipeline";
import { EventList, alertToEvent } from "@/components/dashboard/EventList";
import { RecentActivity } from "@/components/dashboard/RecentActivity";
import { DistrictBars, type BarDatum } from "@/components/dashboard/DistrictBars";
import { SocioNarrativeCard } from "@/components/dashboard/SocioNarrativeCard";
import { StationPerformance } from "@/routes/home/StationPerformance";
import {
  useAlerts, useCaseload, useForecastMap, useHotspots, useSocio, useTrends,
} from "@/routes/home/useDashboardData";
import { useScopeChips } from "@/routes/home/useScopeChips";
import { useMyScope } from "@/hooks/useMyScope";
import { usePeekStore } from "@/stores/usePeekStore";
import { useUIStore } from "@/stores/useUIStore";
import { STATE_WIDE_NOTE, useScopeStore } from "@/stores/useScopeStore";
import { formatNumber } from "@/lib/utils";

/* ============================================================================
   Board widgets: the id -> component map behind `BoardSpec.widgets`.

   `roleBoards.ts` declares WHICH widgets a seat gets and how big they are; this
   file is the only place that knows what each id actually renders. Before this,
   the widget list was declared and then ignored — every board rendered its KPI
   band and nothing else.

   Each widget is a self-contained component that owns its own query, rather than
   one hook fetching everything and the board picking from the result. That matters
   for correctness, not tidiness: hooks cannot be called conditionally, so a shared
   hook would fetch socio-economic correlations and forecast rasters for a station
   board that shows neither. Self-contained means a widget that is not on the board
   issues no request at all.

   Height budget, for choosing `h` in roleBoards.ts: at the base board width a tile
   is about `h*44 + (h-1)*20` pixels, less ~56 for the Widget header. So h:6 gives
   roughly 308px of body and h:7 about 350px.
   ========================================================================== */

export interface BoardWidgetProps {
  /** Heading from the board spec, so one component can serve several ids —
   *  the same map is "Hotspots" to a DIG and "My jurisdiction" to an IO. */
  label: string;
}

/* --------------------------------- trend ---------------------------------- */
function TrendWidget({ label }: BoardWidgetProps) {
  const trends = useTrends();
  const chip = useScopeChips();
  return (
    <Widget
      gridTile
      title={label}
      contextChip={chip.scoped}
      provenance={trends.data?.result}
      loading={trends.isLoading}
      error={trends.error}
      empty={!trends.isLoading && !trends.error && (trends.data?.series.length ?? 0) === 0}
      onRefresh={() => trends.refetch()}
      info={
        <p className="text-content-dim">
          Registered crimes per period in the selected window, for this seat's
          jurisdiction. Scoped server-side, so the series never includes districts
          outside your command.
        </p>
      }
    >
      {trends.data && (
        <div className="h-full min-h-[220px] w-full">
          <TrendChart series={trends.data.series} fill />
        </div>
      )}
    </Widget>
  );
}

/* -------------------------------- forecast -------------------------------- */
function ForecastWidget({ label }: BoardWidgetProps) {
  const forecast = useForecastMap();
  const chip = useScopeChips();
  return (
    <Widget
      gridTile
      title={label}
      contextChip={chip.scoped}
      provenance={forecast.data?.result}
      loading={forecast.isLoading}
      error={forecast.error}
      empty={!forecast.isLoading && !forecast.error && (forecast.data?.cells.length ?? 0) === 0}
      emptyLabel="No forecast written yet."
      onRefresh={() => forecast.refetch()}
    >
      {forecast.data && <ForecastSummary data={forecast.data} />}
    </Widget>
  );
}

/* ------------------------- jurisdiction / hotspot map --------------------- */
function HotspotMapWidget({ label }: BoardWidgetProps) {
  const hotspots = useHotspots();
  const navigate = useNavigate();
  const askAbout = useUIStore((s) => s.askAbout);

  /* Pre-filtered here as well as inside the map, because the `empty` decision
     needs the mappable count: a scope with hotspots that all lack a centroid must
     say "nothing mapped", not render a blank map. */
  const mappable = (hotspots.data?.hotspots ?? []).filter(
    (h) => h.centroid_lon != null && h.centroid_lat != null,
  );

  return (
    <Widget
      gridTile
      flush
      title={label}
      contextChip="last window"
      provenance={hotspots.data?.result}
      loading={hotspots.isLoading}
      error={hotspots.error}
      empty={!hotspots.isLoading && !hotspots.error && mappable.length === 0}
      emptyLabel="No mapped incidents in this scope."
      onRefresh={() => hotspots.refetch()}
      info={
        <p className="text-content-dim">
          Hotspot centroids for districts in your command. Resolves to DISTRICT
          grain — a station board shows its district's hotspots, because hotspots
          are computed per district and not per station.
        </p>
      }
      menuItems={[
        { label: "Open in Map & Hotspots", icon: <MapPinned />, onSelect: () => navigate("/map") },
        {
          label: "Ask DRISHTI about this",
          icon: <Sparkles />,
          onSelect: () => askAbout("Summarise incident hotspots in my jurisdiction"),
        },
      ]}
    >
      {hotspots.data && <JurisdictionMap hotspots={mappable} />}
    </Widget>
  );
}

/* ------------------------- pipeline / my caseload ------------------------- */
function PipelineWidget({ label }: BoardWidgetProps) {
  const caseload = useCaseload();
  const stages = CASE_STAGES.map((s) => ({
    ...s,
    count: caseload.data?.stages.find((x) => x.key === s.key)?.count ?? null,
  }));
  return (
    <Widget
      gridTile
      title={label}
      contextChip={caseload.data ? `${formatNumber(caseload.data.total)} cases` : undefined}
      loading={caseload.isLoading}
      error={caseload.error}
      empty={!caseload.isLoading && !caseload.error && (caseload.data?.total ?? 0) === 0}
      emptyLabel="No cases in your scope yet."
      onRefresh={() => caseload.refetch()}
      info={
        <p className="text-content-dim">
          The FIR lifecycle across cases in your scope. Each case sits at exactly
          one stage, so the per-stage counts sum to the total.
        </p>
      }
    >
      {caseload.data && (
        <div className="py-2">
          <StatusPipeline stages={stages} funnel />
          <p className="mt-3 text-12 text-content-dim">
            <span className="font-medium text-content">
              {formatNumber(caseload.data.open_total)}
            </span>{" "}
            open ·{" "}
            <span className="font-medium text-content">
              {formatNumber(caseload.data.disposed_total)}
            </span>{" "}
            disposed
          </p>
        </div>
      )}
    </Widget>
  );
}

/* ----------------------------- attention queue ---------------------------- */
function AttentionWidget({ label }: BoardWidgetProps) {
  const alerts = useAlerts();
  const push = usePeekStore((s) => s.push);
  return (
    <Widget
      gridTile
      flush
      title={label}
      contextChip={alerts.data ? String(alerts.data.count) : undefined}
      provenance={alerts.data?.result}
      loading={alerts.isLoading}
      error={alerts.error}
      empty={!alerts.isLoading && !alerts.error && (alerts.data?.alerts.length ?? 0) === 0}
      emptyLabel="Nothing needs your attention right now."
      onRefresh={() => alerts.refetch()}
    >
      {alerts.data && (
        <div className="px-2 py-1">
          <EventList
            items={alerts.data.alerts.slice(0, 20).map((a) =>
              alertToEvent(a, () =>
                push({
                  kind: "alert", id: a.alert_id, label: a.title,
                  sublabel: a.district_name ?? a.alert_type,
                }),
              ),
            )}
          />
        </div>
      )}
    </Widget>
  );
}

/* ---------------------------- recent activity ----------------------------- */
function RecentActivityWidget({ label }: BoardWidgetProps) {
  return (
    <Widget
      gridTile
      flush
      title={label}
      info={
        <p className="text-content-dim">
          Records you have opened in this session, most recent first. A local trail
          to get back to what you were working on — not an audit log.
        </p>
      }
    >
      <div className="px-2 py-1">
        <RecentActivity />
      </div>
    </Widget>
  );
}

/* ------------------------------ league tables ----------------------------- */
/** Sum hotspot case load by a chosen key. The one aggregation all three league
 *  tables share; only the grouping differs. */
function sumHotspots(
  rows: { case_count?: number | null }[],
  keyOf: (r: never) => string | null | undefined,
): BarDatum[] {
  const by = new Map<string, number>();
  for (const r of rows) {
    const k = keyOf(r as never);
    if (!k) continue;
    by.set(k, (by.get(k) ?? 0) + (r.case_count ?? 1));
  }
  return [...by.entries()].map(([label, value]) => ({ key: label, label, value }));
}

/** Per-district case load, from /performance/districts.
 *
 *  Previously summed HOTSPOT case counts per district client-side. That answered a
 *  different question — a hotspot is a modelled concentration, not a workload — so
 *  a district with dispersed crime read as idle. Now real case counts, confined
 *  server-side to the seat's districts. */
function useDistrictPerformance() {
  return useQuery({
    queryKey: ["performance", "districts"],
    queryFn: ({ signal }) => api.performance.districts({ window_days: 90 }, signal),
    staleTime: 5 * 60_000,
  });
}

function DistrictLeagueWidget({ label }: BoardWidgetProps) {
  const q = useDistrictPerformance();
  /* Clicking a bar drills the whole board into that district. This is the only
     drill-in entry point that makes sense here: the table exists to answer "which
     district needs attention", and the next question is always "why that one". */
  const setDistrictId = useScopeStore((s) => s.setDistrictId);
  const data: BarDatum[] = useMemo(
    () => (q.data?.districts ?? []).map((d) => ({
      key: String(d.district_id),
      label: d.district_name ?? `District ${d.district_id}`,
      value: d.open_cases,
      onClick: () => setDistrictId(d.district_id),
    })),
    [q.data, setDistrictId],
  );
  const median = q.data?.totals.median_open_per_district;
  return (
    <Widget
      gridTile
      title={label}
      contextChip={data.length ? `${data.length} districts` : undefined}
      loading={q.isLoading}
      error={q.error}
      empty={!q.isLoading && !q.error && data.length === 0}
      onRefresh={() => q.refetch()}
      info={
        <p className="text-content-dim">
          Open cases per district in your command, highest first. A comparison for
          directing attention, NOT a ranking: districts differ in population,
          urbanisation and reporting rate, so a longer bar is more work, not worse
          policing.
        </p>
      }
    >
      <DistrictBars data={data} max={10} unit=" open" />
      {median != null && (
        /* The median is the reference that makes a bar mean something. A max would
           be dominated by one outlier and make every other district look fine. */
        <p className="mt-2 text-11 text-content-dim">
          Median {median.toLocaleString()} open per district
          {q.data?.window_days ? ` · ${q.data.window_days}d window` : ""}
        </p>
      )}
    </Widget>
  );
}

function RangeLeagueWidget({ label }: BoardWidgetProps) {
  const q = useDistrictPerformance();
  /* Districts carry no range, so the range dimension comes from the org tree and
     the two are joined here. */
  const ranges = useQuery({
    queryKey: ["org", "ranges"],
    queryFn: ({ signal }) => api.org.ranges(signal),
    staleTime: 30 * 60_000,
  });

  const { data, unranged } = useMemo(() => {
    const rangeOf = new Map<number, string>();
    for (const r of ranges.data?.items ?? []) {
      for (const d of r.districts) rangeOf.set(d.district_id, r.range_name);
    }
    const by = new Map<string, number>();
    let outside = 0;
    for (const d of q.data?.districts ?? []) {
      const name = rangeOf.get(d.district_id);
      if (!name) { outside += d.open_cases; continue; }
      by.set(name, (by.get(name) ?? 0) + d.open_cases);
    }
    return {
      data: [...by.entries()].map(([label, value]) => ({ key: label, label, value })),
      unranged: outside,
    };
  }, [q.data, ranges.data]);

  const loading = q.isLoading || ranges.isLoading;
  return (
    <Widget
      gridTile
      title={label}
      contextChip={data.length ? `${data.length} ranges` : undefined}
      loading={loading}
      error={q.error ?? ranges.error}
      empty={!loading && data.length === 0}
      onRefresh={() => { q.refetch(); ranges.refetch(); }}
      info={
        <p className="text-content-dim">
          Open cases per range, summed from the districts each range covers. The
          city Commissionerates sit outside the range hierarchy, so their load is
          reported separately rather than folded into a range.
        </p>
      }
    >
      <DistrictBars data={data} max={10} unit=" open" />
      {unranged > 0 && (
        /* Stated rather than dropped. Silently omitting the Commissionerates would
           make the bars fail to sum to the state total with no explanation. */
        <p className="mt-2 text-11 text-content-dim">
          {unranged.toLocaleString()} open cases in city Commissionerates, which sit
          outside the range hierarchy.
        </p>
      )}
    </Widget>
  );
}

function HeadBreakdownWidget({ label }: BoardWidgetProps) {
  const hotspots = useHotspots();
  const data = useMemo(
    () => sumHotspots(hotspots.data?.hotspots ?? [], (h: { crime_group?: string | null }) => h.crime_group),
    [hotspots.data],
  );
  return (
    <Widget
      gridTile
      title={label}
      contextChip={data.length ? `${data.length} groups` : undefined}
      provenance={hotspots.data?.result}
      loading={hotspots.isLoading}
      error={hotspots.error}
      empty={!hotspots.isLoading && !hotspots.error && data.length === 0}
      emptyLabel="No crime-group breakdown in this scope."
      onRefresh={() => hotspots.refetch()}
      info={
        <p className="text-content-dim">
          Hotspot case load by crime group within this wing's remit. Groups this
          wing does not own are excluded server-side, so the bars sum to the wing's
          load rather than the state's.
        </p>
      }
    >
      <DistrictBars data={data} max={10} unit=" cases" />
    </Widget>
  );
}

/* --------------------------- station performance -------------------------- */
function StationLeagueWidget({ label }: BoardWidgetProps) {
  /* Reads the seat rather than the top-bar selector, because StationPerformance
     does not consult the scope store itself and this widget is only on the
     district and commissionerate boards, where the posting IS the scope. The
     station board gets `officer-load` instead — a single station comparing itself
     to itself is not a league table. */
  const seat = useMyScope();
  return (
    <Widget
      gridTile
      title={label}
      info={
        <p className="text-content-dim">
          Station and officer performance for your command over a 90-day window,
          with denominators shown. Officer load is an aggregate distribution
          (median, p90, max) rather than a per-officer ranking.
        </p>
      }
    >
      <StationPerformance districtId={seat.districtId ?? undefined} />
    </Widget>
  );
}

/** Officer load on its own, for the station board, which wants the distribution
 *  without the per-station table underneath it. Shares the cached
 *  /performance/overview query with StationLeagueWidget rather than refetching. */
function OfficerLoadWidget({ label }: BoardWidgetProps) {
  const seat = useMyScope();
  const districtId = seat.districtId ?? undefined;
  const q = useQuery({
    queryKey: ["performance", "overview", districtId ?? null, null],
    queryFn: ({ signal }) =>
      api.performance.overview({ district_id: districtId, window_days: 90 }, signal),
  });
  const off = q.data?.officers;
  const bal = q.data?.workload_balance;
  return (
    <Widget
      gridTile
      title={label}
      contextChip={q.data ? `${q.data.totals.officers_in_scope} officers` : undefined}
      loading={q.isLoading}
      error={q.error}
      empty={!q.isLoading && !q.error && (q.data?.empty ?? false)}
      onRefresh={() => q.refetch()}
      info={
        <p className="text-content-dim">
          How open cases are spread across officers in your scope. Reported as a
          distribution on purpose — naming the busiest officer invites a punitive
          reading of what is usually an assignment problem.
        </p>
      }
    >
      {off && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            {[
              { k: "median", v: off.median_open_per_officer },
              { k: "p90", v: off.p90_open_per_officer },
              { k: "max", v: off.max_open_per_officer },
            ].map((s) => (
              <div key={s.k} className="rounded-card border border-hairline p-2.5">
                <div className="text-11 text-content-dim">{s.k}</div>
                <div className="tnum mt-0.5 text-20 font-semibold text-content">
                  {s.v ?? "—"}
                </div>
              </div>
            ))}
          </div>
          <p className="text-11 leading-relaxed text-content-dim">
            {off.heavy_load_officers} officer(s) hold more than{" "}
            {off.heavy_load_threshold} open cases. Station imbalance
            (busiest/median): {bal?.imbalance_ratio_max_over_median ?? "—"}×.
          </p>
          <p className="text-11 leading-relaxed text-content-dim">{off.note}</p>
        </div>
      )}
    </Widget>
  );
}

/* -------------------------------- socio ---------------------------------- */
function SocioWidget({ label }: BoardWidgetProps) {
  const socio = useSocio();
  return (
    <Widget
      gridTile
      title={label}
      contextChip="state-wide"
      provenance={socio.data?.result}
      loading={socio.isLoading}
      error={socio.error}
      empty={!socio.isLoading && !socio.error && !socio.data}
      onRefresh={() => socio.refetch()}
      info={
        <p className="text-content-dim">
          Correlation between district socio-economic indicators and crime rates.
          Correlation only — none of these is evidence of cause. {STATE_WIDE_NOTE}
        </p>
      }
    >
      {socio.data && <SocioNarrativeCard data={socio.data} compact />}
    </Widget>
  );
}

/* ----------------------------- admin widgets ----------------------------- */
function SeatDirectoryWidget({ label }: BoardWidgetProps) {
  const q = useQuery({
    queryKey: ["org", "seats", "board"],
    queryFn: ({ signal }) => api.org.seats({ page_size: 12 }, signal),
    staleTime: 5 * 60_000,
  });
  const counts = q.data?.scope_type_counts ?? {};
  const tiers = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return (
    <Widget
      gridTile
      title={label}
      contextChip={q.data ? `${q.data.total.toLocaleString()} seats` : undefined}
      loading={q.isLoading}
      error={q.error}
      empty={!q.isLoading && !q.error && (q.data?.total ?? 0) === 0}
      onRefresh={() => q.refetch()}
      info={
        <p className="text-content-dim">
          Provisioned seats by tier. A seat is a post in the organisation, not a
          person — an unfilled post still holds its scope.
        </p>
      }
    >
      <div className="space-y-1.5">
        {tiers.map(([tier, n]) => (
          <div key={tier} className="flex items-center justify-between gap-2 text-12">
            <span className="truncate text-content-dim">{tier.replace(/_/g, " ")}</span>
            <span className="tnum font-medium text-content">{n.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </Widget>
  );
}

function RoleMatrixWidget({ label }: BoardWidgetProps) {
  const q = useQuery({
    queryKey: ["org", "scope-matrix"],
    queryFn: ({ signal }) => api.org.scopeMatrix(signal),
    staleTime: 30 * 60_000,
  });
  const rows = useMemo(() => {
    const d = q.data;
    if (!d) return [];
    return d.roles.map((role) => {
      const allowed = d.actions.filter((a) => d.matrix[role]?.[a]).length;
      return { role, allowed, total: d.actions.length };
    });
  }, [q.data]);
  return (
    <Widget
      gridTile
      title={label}
      contextChip={rows.length ? `${rows.length} roles` : undefined}
      loading={q.isLoading}
      error={q.error}
      empty={!q.isLoading && !q.error && rows.length === 0}
      onRefresh={() => q.refetch()}
      info={
        <p className="text-content-dim">
          Permitted actions per role, as a share of all actions. Summarised rather
          than shown as a full grid, which does not fit this width — open Admin →
          Org &amp; Access for the role-by-action detail.
        </p>
      }
    >
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.role}>
            <div className="flex items-center justify-between gap-2 text-11">
              <span className="truncate text-content">{r.role.replace(/_/g, " ")}</span>
              <span className="tnum shrink-0 text-content-dim">
                {r.allowed}/{r.total}
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded bg-surface-2">
              <div
                className="h-full bg-primary"
                style={{ width: `${r.total ? (r.allowed / r.total) * 100 : 0}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </Widget>
  );
}

/* ============================ the resolver ================================ */
/** Widget id -> component. Several ids share one component where the panel is the
 *  same and only the framing differs: the hotspot map is "Hotspots" to a DIG and
 *  "My jurisdiction" to an IO, and the case pipeline is "Case pipeline" to an SHO
 *  and "My caseload" to an IO.
 *
 *  An id with no entry here is DROPPED by RoleBoard rather than rendered as an
 *  empty frame, and `boardWidgets.test.tsx` asserts every id in every board spec
 *  resolves — so a typo in a spec fails a test instead of quietly leaving a gap. */
export const BOARD_WIDGETS: Record<string, (p: BoardWidgetProps) => JSX.Element> = {
  "trend": TrendWidget,
  "forecast": ForecastWidget,
  "hotspot-map": HotspotMapWidget,
  "station-jurisdiction": HotspotMapWidget,
  "my-jurisdiction": HotspotMapWidget,
  "pipeline": PipelineWidget,
  "my-caseload": PipelineWidget,
  "attention": AttentionWidget,
  "case-timeline": RecentActivityWidget,
  "district-league": DistrictLeagueWidget,
  "range-league": RangeLeagueWidget,
  "head-breakdown": HeadBreakdownWidget,
  "station-league": StationLeagueWidget,
  "officer-load": OfficerLoadWidget,
  "socio": SocioWidget,
  "seat-directory": SeatDirectoryWidget,
  "role-matrix": RoleMatrixWidget,
};

export function hasWidget(id: string): boolean {
  return id in BOARD_WIDGETS;
}
