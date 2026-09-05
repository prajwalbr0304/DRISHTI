import { useState } from "react";
import {
  Activity, AlarmClock, AlertTriangle, BadgeCheck, Building2, CalendarClock,
  CheckCircle2, Clock, EyeOff, FileCheck2, FilePlus2, Flame, FolderOpen, Gavel, GitBranch,
  Landmark, Layers, ListChecks, Lock, MapPinOff, Radar, Scale, ShieldCheck, Siren,
  Target, TrendingUp, Users, Waves,
} from "lucide-react";
import { Widget } from "@/components/widget/Widget";
import { KpiCard, type KpiCardProps } from "@/components/dashboard/KpiCard";
import { TrendChart } from "@/components/charts/TrendChart";
import { ForecastSummary } from "@/components/dashboard/ForecastSummary";
import { DashboardGrid, type DashTile } from "@/components/dashboard/DashboardGrid";
import {
  useAlerts, useCaseload, useForecastMap, useHotspots, useSocio, useTrends,
} from "@/routes/home/useDashboardData";
import { socioTiles } from "@/routes/home/socioTiles";
import {
  COMMUNITY_LIMIT, useCommunities, useContractAudit, useDataQualitySummary,
  useJurisdictionFreshness, useOpenTasks, useStatePerformance,
} from "@/routes/home/useStateCommandData";
import { usePatterns, useForecastBacktest } from "@/routes/analytics/useAnalyticsData";
import { STATE_WIDE_NOTE } from "@/stores/useScopeStore";
import { hiddenTiles, useDashboardStore } from "@/stores/useDashboardStore";
import { useScopeChips } from "@/routes/home/useScopeChips";
import { defaultCrimeCategory } from "@/lib/socio";

/* ============================================================================
   DGP / State Command Center (doc 01 §4.1 + §7).

   Its own board, not a relabelled policymaker board. The IGP and SP seats keep
   PolicymakerHome; this one answers the questions a state chief is actually
   accountable for — throughput, disposal, load balance, forecast accuracy and
   data integrity — instead of restating the forecast total and the socio-economic
   footer as KPI cards.

   AGGREGATE-ONLY, same hard constraint as the policymaker board: district-level
   and state-level counts, ratios and queue depths. No case list, no point-level
   map, no individual profiles. Every card below binds to a field that exists on
   a live response, or ships with KpiCard's honest `pending` state.

   The widget set is deliberately unchanged from PolicymakerHome — this slice is
   the KPI band only.
   ========================================================================== */

/** 12-column grid, four cards to a row, two rows tall each. w=2 was considered
 *  to halve the band height, but Sparkline holds a `min-w-[88px]` slot beside a
 *  text-28 number, so a narrower tile squeezes the metric rather than the chart. */
const KPI_W = 3;
const KPI_H = 2;
const KPI_PER_ROW = 12 / KPI_W;

/* Wide screens (the 24-column board) fit six metric cards per row instead of
   four. Same card size in pixels, more of them per row, so a large monitor
   shows more of the band above the fold rather than four very wide cards. */
const XL_KPI_W = 4;
const XL_KPI_PER_ROW = 24 / XL_KPI_W;

const WINDOW_DAYS = 90;

const round1 = (v: number) => Math.round(v * 10) / 10;

/** A 0..1 fraction as a percentage. Returns null — never 0 — when the service
 *  had no number to give, so "no answer" cannot masquerade as "zero percent". */
function pct(fraction: number | null | undefined): number | null {
  return fraction == null ? null : round1(fraction * 100);
}

/** a/b as a percentage. Null unless both sides are present and b is non-zero;
 *  a zero denominator is undefined, not 0%. */
function ratioPct(a: number | null | undefined, b: number | null | undefined): number | null {
  if (a == null || b == null || b === 0) return null;
  return round1((a / b) * 100);
}

type KpiSpec = KpiCardProps & { key: string };

/** Its own board id, so a DGP rearranging or trimming this board never disturbs
 *  the IGP and SP seats that still share "policymaker". */
const GRID_ID = "dgp_state_command";

export function StateCommandHome() {
  const scopeChip = useScopeChips();
  const hiddenKeys = useDashboardStore((s) => hiddenTiles(s, GRID_ID));

  /* --- band A: state pulse ------------------------------------------------ */
  const trends = useTrends();
  const alerts = useAlerts();

  /* --- bands B + C: volume, load, outcomes -------------------------------- */
  const hotspots = useHotspots();
  const caseload = useCaseload();
  const perf = useStatePerformance(WINDOW_DAYS);

  /* --- band D: forecast + model trust ------------------------------------ */
  const forecast = useForecastMap();
  const backtest = useForecastBacktest();
  const contract = useContractAudit();

  /* --- band E: data integrity -------------------------------------------- */
  const quality = useDataQualitySummary();
  const jurisdiction = useJurisdictionFreshness();

  /* --- band F: patterns + queue ------------------------------------------ */
  const patterns = usePatterns({});
  const communities = useCommunities();
  const tasks = useOpenTasks();

  /* Page-level default crime type for the socio band. Empty = follow the
     service's narrative category; each indicator box may override it. */
  const [category, setCategory] = useState("");

  /* One request feeds the whole band: the response carries the district panel
     and a fit per cell, so every indicator box builds its own series client-side
     instead of re-querying per indicator. */
  const socio = useSocio();
  const socioData = socio.data;

  const activeCategory = category || (socioData ? defaultCrimeCategory(socioData) : "");

  const predicted = (forecast.data?.cells ?? []).reduce((s, c) => s + (c.predicted_count ?? 0), 0);
  const criticalAlerts = (alerts.data?.alerts ?? []).filter((a) => a.severity === "critical").length;
  const anomalies = (trends.data?.series ?? []).filter((p) => p.is_anomaly).length;
  const gangCommunities = (communities.data?.communities ?? []).filter((c) => c.gang_members > 0).length;

  const totals = perf.data?.totals;
  const chargesheet = perf.data?.chargesheet;
  const balance = perf.data?.workload_balance;
  const model = backtest.data?.model;

  /* Every performance card shares one honesty caveat: the numbers come from the
     committed case record over a fixed window, and the service tells us when
     that record is stale rather than pretending it ends today. */
  const perfWindowNote = `From the committed case record over the last ${WINDOW_DAYS} days.`;
  const stalenessNote = perf.data?.stale
    ? ` The service flags this record as STALE (${perf.data.data_age_days} days old, as of ${perf.data.as_of}), so the window is relative to that as-of date and not to today.`
    : "";
  /* `empty` is the service saying "no cases in this scope" — a real answer, and
     a different statement from a failed request. */
  const perfEmptyNote = perf.data?.empty
    ? " The service reports no cases in the current scope, so this is an empty scope rather than a missing measurement."
    : "";

  const severitySplit = Object.entries(quality.data?.by_severity ?? {})
    .map(([severity, count]) => `${count} ${severity}`)
    .join(" · ");

  const kpis: KpiSpec[] = [
    /* ===== Band A — state pulse =========================================== */
    {
      key: "kpi-incidents",
      icon: <TrendingUp />,
      label: "Incidents (window)",
      value: trends.data?.total,
      // Year-on-year, not month-on-month: a state chief comparing volume needs
      // the seasonality taken out. The delta label says which comparison it is.
      delta: trends.data?.yoy_pct ?? null,
      // Kept short so it fits beside the sparkline; the hint states the full
      // comparison. "vs. prior" would have been the wrong claim entirely.
      deltaLabel: "vs. last year",
      spark: trends.data?.series.map((p) => p.count),
      loading: trends.isLoading,
      error: trends.error,
      hint: "Total recorded incidents across the state for the selected time window. The delta compares against the same period LAST YEAR, so seasonal swings do not read as trend; the sparkline shows the last 12 periods.",
    },
    {
      key: "kpi-mom",
      icon: <Activity />,
      label: "Month-on-month change",
      value: trends.data?.mom_pct == null ? null : round1(trends.data.mom_pct),
      unit: "%",
      loading: trends.isLoading,
      error: trends.error,
      hint: "Change in recorded incidents against the previous period in the series. Shown as the value rather than as a delta because it IS a delta — the year-on-year comparison sits on the incidents card, so the two are never confused.",
    },
    {
      key: "kpi-critical-alerts",
      icon: <Siren />,
      label: "Critical alerts",
      value: alerts.data ? criticalAlerts : undefined,
      loading: alerts.isLoading,
      error: alerts.error,
      hint: "Live early-warning alerts at CRITICAL severity only — high, medium, low and info are excluded, so this is the escalate-now queue rather than the whole alert list. A live queue, so it ignores the time window.",
    },
    {
      key: "kpi-anomalies",
      icon: <Waves />,
      label: "Anomalous periods",
      value: trends.data ? anomalies : undefined,
      loading: trends.isLoading,
      error: trends.error,
      hint: "Periods in the current series whose count fell outside the rolling anomaly band — the months that broke trend. A count of periods, not of crimes.",
    },

    /* ===== Band B — volume and load ======================================= */
    {
      key: "kpi-hotspots",
      icon: <Flame />,
      label: "Hotspots",
      value: hotspots.data?.count,
      loading: hotspots.isLoading,
      error: hotspots.error,
      hint: "Spatial clusters detected for the selected window. Area-level patterns only: a hotspot describes a place, never a person.",
    },
    {
      key: "kpi-open-cases",
      icon: <FolderOpen />,
      label: "Open cases",
      value: caseload.data?.open_total,
      loading: caseload.isLoading,
      error: caseload.error,
      hint: "Cases not yet disposed or closed, summed across every stage of the FIR lifecycle. A present-state snapshot, so it ignores the time window.",
    },
    {
      key: "kpi-workload",
      icon: <Layers />,
      label: "Active workload",
      value: totals?.active_workload,
      loading: perf.isLoading,
      error: perf.error,
      hint: `Open cases currently carried as live investigative work — the subset of open cases that is somebody's active file. ${perfWindowNote}${stalenessNote}${perfEmptyNote}`,
    },
    {
      key: "kpi-new-firs",
      icon: <FilePlus2 />,
      label: `New FIRs (${WINDOW_DAYS}d)`,
      value: totals?.new_cases_in_window,
      loading: perf.isLoading,
      error: perf.error,
      hint: `Cases registered in the last ${WINDOW_DAYS} days. The accountability window is fixed at ${WINDOW_DAYS} days so throughput, ageing and this intake figure all share one denominator.${stalenessNote}`,
    },

    /* ===== Band C — outcomes and accountability =========================== */
    {
      key: "kpi-chargesheet",
      icon: <FileCheck2 />,
      label: "Chargesheet throughput",
      value: pct(chargesheet?.throughput_ratio),
      unit: "%",
      improveWhenDown: false,
      loading: perf.isLoading,
      error: perf.error,
      hint: `${chargesheet?.throughput_ratio_denominator ?? "Chargesheets filed divided by new cases registered in the same window"} — a ratio between two different cohorts, so it is a throughput rate and not a per-case conversion rate. Higher is better.${stalenessNote}`,
    },
    {
      key: "kpi-days-to-chargesheet",
      icon: <Clock />,
      label: "Median days to chargesheet",
      value: chargesheet?.median_days_to_chargesheet,
      unit: "d",
      loading: perf.isLoading,
      error: perf.error,
      hint: "Median days from registration to chargesheet filing. Measured to FILING, not to final court disposal — this board cannot see court outcomes in aggregate yet.",
    },
    {
      key: "kpi-disposal",
      icon: <CheckCircle2 />,
      label: "Disposal rate",
      value: ratioPct(totals?.disposed_or_closed, totals?.total_cases),
      unit: "%",
      improveWhenDown: false,
      loading: perf.isLoading,
      error: perf.error,
      hint: "Cases disposed or closed as a share of every case on record. Derived here from two counts the service returns; cumulative rather than windowed, so it moves slowly. Higher is better.",
    },
    {
      key: "kpi-overdue",
      icon: <AlarmClock />,
      label: "Overdue reviews",
      value: totals?.overdue_reviews,
      loading: perf.isLoading,
      error: perf.error,
      hint: `Open cases past the review threshold${
        totals?.overdue_threshold_days != null ? ` of ${totals.overdue_threshold_days} days` : ""
      }. A backlog measure, so a rising number is the warning.${stalenessNote}`,
    },
    {
      key: "kpi-imbalance",
      icon: <Scale />,
      label: "Station load imbalance",
      value: balance?.imbalance_ratio_max_over_median,
      unit: "×",
      loading: perf.isLoading,
      error: perf.error,
      hint: `Busiest station's open caseload divided by the median station's${
        balance?.stations_compared != null ? `, across ${balance.stations_compared} stations compared` : ""
      }. 1× would be perfectly even load; higher means pressure is concentrated. Comparative only — never a punitive ranking.`,
    },
    {
      key: "kpi-stations",
      icon: <Building2 />,
      label: "Stations in scope",
      value: totals?.stations_in_scope,
      loading: perf.isLoading,
      error: perf.error,
      hint: `Police stations included in the accountability figures on this board${
        totals?.officers_in_scope != null ? `, staffed by ${totals.officers_in_scope} officers` : ""
      }. The denominator behind the load and throughput cards.`,
    },

    /* ===== Band D — forecast and model trust ============================== */
    {
      key: "kpi-predicted",
      icon: <Radar />,
      label: "Predicted next period",
      value: forecast.data ? Math.round(predicted) : undefined,
      loading: forecast.isLoading,
      error: forecast.error,
      hint: "Sum of the fused district forecasts for the next horizon. Read-only — opening this board never triggers a forecast run.",
    },
    {
      key: "kpi-wape",
      icon: <Target />,
      label: "Forecast error (WAPE)",
      value: pct(model?.wape),
      unit: "%",
      loading: backtest.isLoading,
      error: backtest.error,
      hint: `Weighted absolute percentage error from the rolling-origin backtest, scored on held-out district-months the model had not seen${
        backtest.data?.scored_points != null ? ` (${backtest.data.scored_points} of them)` : ""
      }. Lower is better. ${STATE_WIDE_NOTE}`,
    },
    {
      key: "kpi-coverage",
      icon: <ShieldCheck />,
      label: "80% interval coverage",
      value: pct(model?.coverage_80),
      unit: "%",
      improveWhenDown: false,
      loading: backtest.isLoading,
      error: backtest.error,
      hint: "Share of held-out actuals that landed inside the forecast's 80% band. 80% is the target, not a maximum: well below means the intervals are overconfident, well above means they are too wide to act on.",
    },
    {
      key: "kpi-abstention",
      icon: <EyeOff />,
      label: "Forecast abstention",
      value: pct(backtest.data?.abstention_rate),
      unit: "%",
      loading: backtest.isLoading,
      error: backtest.error,
      hint: `Share of candidate cells the forecaster declined to score for want of signal${
        backtest.data?.cells_considered != null ? `, out of ${backtest.data.cells_considered} considered` : ""
      }. Abstention is deliberate: the model says "I don't know" instead of guessing.`,
    },
    {
      key: "kpi-conformance",
      icon: <BadgeCheck />,
      label: "Contract conformance",
      value: ratioPct(contract.data?.conforming, contract.data?.total),
      unit: "%",
      improveWhenDown: false,
      loading: contract.isLoading,
      error: contract.error,
      hint: `Share of API routes that declare and honour a typed response model${
        contract.data ? ` (${contract.data.conforming} of ${contract.data.total}; ${contract.data.non_conforming} non-conforming)` : ""
      }. The board auditing whether its own numbers arrive under a checked contract.`,
    },

    /* ===== Band E — data integrity ======================================== */
    {
      key: "kpi-data-age",
      icon: <CalendarClock />,
      label: "Case-data age",
      value: perf.data?.data_age_days,
      unit: "d",
      loading: perf.isLoading,
      error: perf.error,
      hint: perf.data?.stale
        ? `The case record behind every accountability figure is ${perf.data.data_age_days} days old (as of ${perf.data.as_of}) and the service flags it STALE. Windows on this board are relative to that as-of date, not to today.`
        : `Age of the most recent case data behind the accountability figures${
            perf.data?.as_of ? ` (as of ${perf.data.as_of})` : ""
          }. The service does not flag it as stale.`,
    },
    {
      key: "kpi-data-quality",
      icon: <AlertTriangle />,
      label: "Data-quality issues",
      value: quality.data?.total,
      loading: quality.isLoading,
      error: quality.error,
      hint: `Records the ingestion and containment checks flagged and STAGED for review — nothing is silently corrected. All statuses, so this is the whole ledger rather than the open queue.${
        severitySplit ? ` By severity: ${severitySplit}.` : ""
      } ${STATE_WIDE_NOTE}`,
    },
    {
      key: "kpi-jurisdiction",
      icon: <MapPinOff />,
      label: "Jurisdiction issues",
      value: jurisdiction.data?.open_jurisdiction_issues,
      loading: jurisdiction.isLoading,
      error: jurisdiction.error,
      hint: `Open containment failures: cases whose incident point falls outside the district they are assigned to. Staged for reviewed, audited reassignment — never moved automatically. ${STATE_WIDE_NOTE}`,
    },
    {
      key: "kpi-suppressed",
      icon: <Lock />,
      label: "Cells suppressed",
      value: socio.data?.suppressed_cells,
      loading: socio.isLoading,
      error: socio.error,
      hint: `Small-count cells hidden for k-anonymity — privacy by design, not missing data. ${STATE_WIDE_NOTE}`,
    },
    {
      key: "kpi-districts",
      icon: <Landmark />,
      label: "Districts analysed",
      value: socio.data?.districts_analysed,
      loading: socio.isLoading,
      error: socio.error,
      hint: `Districts with enough volume to support district-level correlation. Districts below the k-anonymity threshold are excluded rather than estimated. ${STATE_WIDE_NOTE}`,
    },

    /* ===== Band F — patterns and queue ==================================== */
    {
      key: "kpi-patterns",
      icon: <GitBranch />,
      label: "Active patterns",
      value: patterns.data?.total,
      loading: patterns.isLoading,
      error: patterns.error,
      hint: `Active crime-pattern detections — serial, modus operandi, temporal, spatial, network and repeat-offender. The service returns only active patterns and caps the list at the most confident, so this is a floor rather than an exhaustive count.${
        patterns.data?.pattern_types.length ? ` Types present: ${patterns.data.pattern_types.length}.` : ""
      }`,
    },
    {
      key: "kpi-groups",
      icon: <Users />,
      label: "Organised groups",
      value: communities.data ? gangCommunities : undefined,
      loading: communities.isLoading,
      error: communities.error,
      hint: `Detected network communities containing at least one known gang member, among the ${COMMUNITY_LIMIT} largest communities. An aggregate count only — no names, no profiles on this board. ${STATE_WIDE_NOTE}`,
    },
    {
      key: "kpi-tasks",
      icon: <ListChecks />,
      label: "Open tasks",
      value: tasks.data?.total,
      loading: tasks.isLoading,
      error: tasks.error,
      hint: `Work tasks still open across the force — not only those assigned to this seat, because the task queue is scoped by status rather than by actor. ${STATE_WIDE_NOTE}`,
    },

    /* ===== Band G — the metric a DGP is judged on, not yet available ====== */
    {
      key: "kpi-conviction",
      icon: <Gavel />,
      label: "Conviction rate",
      pending: true,
      pendingNote:
        "No aggregate court-outcomes endpoint exists yet. A conviction rate needs convictions and acquittals as state-level counts over a period; court results are held per case, and reading case rows is exactly what this aggregate-only seat must not do. Blocked on an aggregate outcomes endpoint — shown here rather than omitted so the gap is visible.",
    },
  ];

  /* Positions are computed over the VISIBLE cards, not all of them. The grid
     drops a hidden tile on its own, but then the band keeps the gap where that
     card used to be and the row rhythm breaks. Re-flowing here means removing a
     card closes the hole — at both 12 and 24 columns. */
  const visibleKpis = kpis.filter((k) => !hiddenKeys.includes(k.key));
  const bodyY = Math.ceil(visibleKpis.length / KPI_PER_ROW) * KPI_H;
  const xlBodyY = Math.ceil(visibleKpis.length / XL_KPI_PER_ROW) * KPI_H;

  const tiles: DashTile[] = [
    ...visibleKpis.map(({ key, ...card }, i) => ({
      key,
      handle: "self" as const,
      x: (i % KPI_PER_ROW) * KPI_W,
      y: Math.floor(i / KPI_PER_ROW) * KPI_H,
      w: KPI_W,
      h: KPI_H,
      xl: {
        x: (i % XL_KPI_PER_ROW) * XL_KPI_W,
        y: Math.floor(i / XL_KPI_PER_ROW) * KPI_H,
        w: XL_KPI_W,
        h: KPI_H,
      },
      minW: 2,
      minH: 2,
      el: <KpiCard className="h-full" {...card} />,
    })),
    {
      key: "state-trend", handle: "header", x: 0, y: bodyY, w: 8, h: 7, minW: 4, minH: 4,
      xl: { x: 0, y: xlBodyY, w: 16, h: 7 },
      el: (
        <Widget
          gridTile
          title="State crime trend"
          contextChip={scopeChip.scoped}
          provenance={trends.data?.result}
          loading={trends.isLoading}
          error={trends.error}
          empty={!trends.isLoading && !trends.error && (trends.data?.series.length ?? 0) === 0}
          onRefresh={() => trends.refetch()}
        >
          {trends.data && (
            <div className="h-full min-h-[220px] w-full">
              <TrendChart series={trends.data.series} fill />
            </div>
          )}
        </Widget>
      ),
    },
    {
      key: "district-forecast", handle: "header", x: 8, y: bodyY, w: 4, h: 7, minW: 3, minH: 4,
      xl: { x: 16, y: xlBodyY, w: 8, h: 7 },
      el: (
        <Widget
          gridTile
          title="District forecast"
          contextChip={scopeChip.scoped}
          provenance={forecast.data?.result}
          loading={forecast.isLoading}
          error={forecast.error}
          empty={!forecast.isLoading && !forecast.error && (forecast.data?.cells.length ?? 0) === 0}
          emptyLabel="No forecast written yet."
          onRefresh={() => forecast.refetch()}
        >
          {forecast.data && <ForecastSummary data={forecast.data} />}
        </Widget>
      ),
    },
    /* Socio-economic band: a read-out plus one box per indicator, each with its own
       crime-type selector; geography is the shared top-bar district selector.
       Separate tiles rather than one container, so a chief can move, resize or
       dismiss individual indicators. */
    ...socioTiles({
      data: socioData,
      loading: socio.isLoading,
      error: socio.error,
      onRefresh: () => socio.refetch(),
      category: activeCategory,
      onCategoryChange: setCategory,
      stateWideChip: scopeChip.stateWide,
      startY: bodyY + 7,
      xlStartY: xlBodyY + 7,
    }),
  ];

  return <DashboardGrid id={GRID_ID} tiles={tiles} />;
}
