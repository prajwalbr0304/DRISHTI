import {
  Activity, AlarmClock, AlertTriangle, BadgeCheck, Building2, CalendarClock,
  CheckCircle2, Clock, Cpu, EyeOff, FileCheck2, FilePlus2, Flame, FolderOpen,
  Gauge, Gavel, GitBranch, Landmark, Layers, ListChecks, Lock, MapPinOff,
  Radar, Scale, Search, ShieldCheck, Siren, Target, TrafficCone, TrendingUp,
  Users, Waves, Wallet, Workflow,
} from "lucide-react";
import type { ReactNode } from "react";
import type { KpiCardProps } from "@/components/dashboard/KpiCard";
import type { KpiSpec } from "@/config/kpi/registry";
import { STATE_WIDE_NOTE } from "@/stores/useScopeStore";
import {
  useAlerts, useCaseload, useForecastMap, useHotspots, useSocio, useTrends,
} from "@/routes/home/useDashboardData";
import {
  COMMUNITY_LIMIT, useCommunities, useContractAudit, useDataQualitySummary,
  useDashboardRollup, useJurisdictionFreshness, useNextHearings, useOpenTasks,
  useOutcomes, useStatePerformance,
} from "@/routes/home/useStateCommandData";
import { useCentrality } from "@/routes/home/useDashboardData";
import {
  kpiSources, useFlaggedFinance, useIdentityStats, useModelRegistry,
  useReviewQueue, useSeatCount, useStagedImports, useUiOverrideCount,
} from "@/routes/home/usePlatformData";
import { usePatterns, useForecastBacktest } from "@/routes/analytics/useAnalyticsData";
import type { ScopeType } from "@/config/roles";

/* ============================================================================
   One hook that fetches every shared source once, and resolves a registry card
   id to the props its KpiCard needs.

   This is the piece that lets boards be composed from data (config/kpi/*) rather
   than hand-written five times. react-query dedupes by key, so mounting this on a
   board that shows eight of these cards costs eight requests, not one per card.

   A card the resolver does not know about renders in KpiCard's honest `pending`
   state rather than as a blank or a zero — a registry entry with no binding is a
   gap to be seen, not hidden.
   ========================================================================== */

const WINDOW_DAYS = 90;

const round1 = (v: number) => Math.round(v * 10) / 10;

/** A 0..1 fraction as a percentage. Returns null — never 0 — when the service had
 *  no number to give, so "no answer" cannot masquerade as "zero percent". */
function pct(fraction: number | null | undefined): number | null {
  return fraction == null ? null : round1(fraction * 100);
}

/** a/b as a percentage. Null unless both sides are present and b is non-zero; a
 *  zero denominator is undefined, not 0%. */
function ratioPct(a: number | null | undefined, b: number | null | undefined): number | null {
  if (a == null || b == null || b === 0) return null;
  return round1((a / b) * 100);
}

const ICONS: Record<string, ReactNode> = {
  "kpi-incidents": <TrendingUp />,
  "kpi-mom": <Activity />,
  "kpi-anomalies": <Waves />,
  "kpi-new-firs": <FilePlus2 />,
  "kpi-open-cases": <FolderOpen />,
  "kpi-workload": <Layers />,
  "kpi-my-open": <FolderOpen />,
  "kpi-my-new": <FilePlus2 />,
  "kpi-critical-alerts": <Siren />,
  "kpi-open-alerts": <AlertTriangle />,
  "kpi-my-alerts": <Siren />,
  "kpi-hotspots": <Flame />,
  "kpi-chargesheet": <FileCheck2 />,
  "kpi-days-to-chargesheet": <Clock />,
  "kpi-disposal": <CheckCircle2 />,
  "kpi-conviction": <Gavel />,
  "kpi-prosecution-rate": <Scale />,
  "kpi-overdue": <AlarmClock />,
  "kpi-ageing-180": <CalendarClock />,
  "kpi-imbalance": <Scale />,
  "kpi-stations": <Building2 />,
  "kpi-officers": <Users />,
  "kpi-officer-p90": <Gauge />,
  "kpi-heavy-load": <Users />,
  "kpi-predicted": <Radar />,
  "kpi-wape": <Target />,
  "kpi-coverage": <ShieldCheck />,
  "kpi-abstention": <EyeOff />,
  "kpi-data-age": <CalendarClock />,
  "kpi-data-quality": <AlertTriangle />,
  "kpi-jurisdiction": <MapPinOff />,
  "kpi-suppressed": <Lock />,
  "kpi-districts": <Landmark />,
  "kpi-conformance": <BadgeCheck />,
  "kpi-patterns": <GitBranch />,
  "kpi-groups": <Users />,
  "kpi-poi": <Search />,
  "kpi-tasks": <ListChecks />,
  "kpi-flagged-txn": <Wallet />,
  "kpi-money-trails": <Workflow />,
  "kpi-linked-accounts": <Cpu />,
  "kpi-traffic-incidents": <TrafficCone />,
  "kpi-accident-hotspots": <Flame />,
  "kpi-review-queue": <ListChecks />,
  "kpi-next-hearing": <Gavel />,
  "kpi-evidence-pending": <FileCheck2 />,
  "kpi-active-seats": <Users />,
  "kpi-imports": <FilePlus2 />,
  "kpi-models": <BadgeCheck />,
  "kpi-ui-overrides": <ShieldCheck />,
};

export type KpiResolver = (spec: KpiSpec) => KpiCardProps;

/** @param scope the seat's scope type. Decides which of the non-operational
 *  sources are FETCHED — the platform counters, the station approval inbox and the
 *  financial-intelligence reads. Every hook below is still called unconditionally
 *  (hooks must be); it is the request that is gated. Without it a station board
 *  would issue admin requests it never asked for and render their 403s as errors. */
export function useKpiValues(scope: ScopeType): { resolve: KpiResolver } {
  const want = kpiSources(scope);
  const trends = useTrends();
  const alerts = useAlerts();
  const hotspots = useHotspots();
  const caseload = useCaseload();
  const perf = useStatePerformance(WINDOW_DAYS);
  const outcomes = useOutcomes();
  const forecast = useForecastMap();
  const backtest = useForecastBacktest();
  const contract = useContractAudit();
  const quality = useDataQualitySummary();
  const jurisdiction = useJurisdictionFreshness();
  const socio = useSocio();
  const patterns = usePatterns({});
  const communities = useCommunities();
  const tasks = useOpenTasks();
  const centrality = useCentrality(12);
  const hearings = useNextHearings();
  const rollup = useDashboardRollup(WINDOW_DAYS);
  const rollupTotals = rollup.data?.totals;

  /* Non-operational sources, fetched only on the boards that carry their cards. */
  const seats = useSeatCount(want.platform);
  const imports = useStagedImports(want.platform);
  const models = useModelRegistry(want.platform);
  const uiOverrides = useUiOverrideCount(want.platform);
  const reviewQueue = useReviewQueue(want.review);
  const flagged = useFlaggedFinance(want.financial);
  const identity = useIdentityStats(want.financial);

  const totals = perf.data?.totals;
  const chargesheet = perf.data?.chargesheet;
  const balance = perf.data?.workload_balance;
  const officers = perf.data?.officers;
  const model = backtest.data?.model;

  const criticalAlerts = (alerts.data?.alerts ?? [])
    .filter((a) => a.severity === "critical").length;
  const anomalies = (trends.data?.series ?? []).filter((p) => p.is_anomaly).length;
  const predicted = (forecast.data?.cells ?? [])
    .reduce((s, c) => s + (c.predicted_count ?? 0), 0);
  const gangCommunities = (communities.data?.communities ?? [])
    .filter((c) => c.gang_members > 0).length;
  const ageing180 = (perf.data?.ageing ?? [])
    .find((b) => b.bucket === ">180d")?.count;

  /* Every /performance card shares one honesty caveat: the numbers come from the
     committed case record over a fixed window, and the service says when that
     record is stale rather than pretending it ends today. */
  const staleNote = perf.data?.stale
    ? ` The service flags this record as STALE (${perf.data.data_age_days} days old, as of ${perf.data.as_of}), so the window is relative to that as-of date and not to today.`
    : "";

  /* Where the figure came from. Worth saying on the card rather than only in the
     payload: the rollup lags the base tables by up to one refresh, so a number that
     disagrees with a case list by a few rows has an explanation. */
  const rollupNote = rollup.data?.rollup?.refreshed_at
    ? ` Served from the pre-aggregated rollup, last refreshed ${rollup.data.rollup.refreshed_at}.`
    : "";

  /* The corpus is discontinuous — the generated bulk ends 2025-12-31 and a few
     later test records sit months after it — so a window anchored on the latest
     registration can open inside that gap and report a near-zero. The server
     detects it and explains; the card repeats the explanation instead of showing a
     bare 3 that reads as a collapse in registrations. */
  const windowNote = rollup.data?.data_notes?.length
    ? ` ${rollup.data.data_notes.join(" ")}`
    : staleNote;

  function resolve(spec: KpiSpec): KpiCardProps {
    const base = {
      icon: ICONS[spec.id],
      label: spec.label,
      unit: spec.unit,
      improveWhenDown: spec.improveWhenDown,
      hint: spec.reach === "none" ? `${spec.hint} ${STATE_WIDE_NOTE}` : spec.hint,
    };

    // A registry card the service cannot answer yet keeps its declared pending
    // note, so the gap stays visible on the board.
    if (spec.pending) {
      return { ...base, pending: true, pendingNote: spec.pendingNote };
    }

    switch (spec.id) {
      /* --- volume ------------------------------------------------------- */
      case "kpi-incidents":
        return {
          ...base, value: trends.data?.total,
          delta: trends.data?.yoy_pct ?? null, deltaLabel: "vs. last year",
          spark: trends.data?.series.map((p) => p.count),
          loading: trends.isLoading, error: trends.error,
        };
      case "kpi-mom":
        return {
          ...base,
          value: trends.data?.mom_pct == null ? null : round1(trends.data.mom_pct),
          loading: trends.isLoading, error: trends.error,
        };
      case "kpi-anomalies":
        return {
          ...base, value: trends.data ? anomalies : undefined,
          loading: trends.isLoading, error: trends.error,
        };
      case "kpi-new-firs":
        return {
          ...base, label: `New FIRs (${WINDOW_DAYS}d)`,
          value: totals?.new_cases_in_window,
          loading: perf.isLoading, error: perf.error,
          hint: `${spec.hint}${staleNote}`,
        };
      case "kpi-open-cases":
      case "kpi-my-open":
        return {
          ...base, value: caseload.data?.open_total,
          loading: caseload.isLoading, error: caseload.error,
        };
      case "kpi-workload":
        return {
          ...base,
          /* Rollup first, live second. The two reconcile exactly (asserted in
             services/ml/tests/test_dashboard_rollup.py), so preferring the rollup
             changes the cost and not the number. The `??` is a real fallback, not
             defensive noise: /dashboard/summary legitimately returns 503 when its
             policy attestation is stale, and the card must still show a figure. */
          value: rollupTotals?.open_cases ?? totals?.active_workload,
          loading: rollup.isLoading && perf.isLoading,
          error: rollup.data ? undefined : perf.error,
          hint: `${spec.hint}${staleNote}${rollupNote}`,
        };
      case "kpi-my-new":
        return {
          ...base,
          value: rollupTotals?.new_cases_in_window ?? totals?.new_cases_in_window,
          loading: rollup.isLoading && perf.isLoading,
          error: rollup.data ? undefined : perf.error,
          hint: `${spec.hint}${windowNote}`,
        };

      /* --- alerts ------------------------------------------------------- */
      case "kpi-critical-alerts":
        return {
          ...base, value: alerts.data ? criticalAlerts : undefined,
          loading: alerts.isLoading, error: alerts.error,
        };
      case "kpi-open-alerts":
      case "kpi-my-alerts":
        return {
          ...base, value: alerts.data?.count,
          loading: alerts.isLoading, error: alerts.error,
        };
      case "kpi-hotspots":
      case "kpi-accident-hotspots":
        return {
          ...base, value: hotspots.data?.count,
          loading: hotspots.isLoading, error: hotspots.error,
        };

      /* --- outcomes ----------------------------------------------------- */
      case "kpi-chargesheet":
        return {
          ...base, value: pct(chargesheet?.throughput_ratio),
          loading: perf.isLoading, error: perf.error,
          hint: `${spec.hint}${staleNote}`,
        };
      case "kpi-days-to-chargesheet":
        return {
          ...base, value: chargesheet?.median_days_to_chargesheet,
          loading: perf.isLoading, error: perf.error,
        };
      case "kpi-disposal":
        return {
          ...base, value: ratioPct(totals?.disposed_or_closed, totals?.total_cases),
          loading: perf.isLoading, error: perf.error,
        };
      case "kpi-next-hearing":
        return {
          ...base,
          /* null, not 0, when nothing is listed. "No hearing on the calendar" and
             "a hearing today" are different facts and must not render alike —
             KpiCard shows an em-dash for null. */
          value: hearings.data?.days_to_next_hearing ?? null,
          loading: hearings.isLoading,
          error: hearings.error,
          improveWhenDown: false,
          hint:
            hearings.data?.pending_hearings
              ? `Days until the soonest scheduled hearing in your scope — ${hearings.data.next_hearing_on}, one of ${hearings.data.pending_hearings.toLocaleString()} listed across ${hearings.data.cases_awaiting_hearing.toLocaleString()} cases awaiting trial. Counted from the record's as-of date (${hearings.data.as_of}), not today: the corpus ends before the current date, so counting from today would report every hearing as long overdue.`
              : spec.hint,
        };

      case "kpi-conviction":
        return {
          ...base, value: pct(outcomes.data?.conviction_rate),
          loading: outcomes.isLoading, error: outcomes.error,
          hint: `${spec.hint}${
            outcomes.data
              ? ` Here: ${outcomes.data.convicted} of ${outcomes.data.verdicts} verdicts.`
              : ""}`,
        };
      case "kpi-prosecution-rate":
        return {
          ...base, value: pct(outcomes.data?.prosecution_rate),
          loading: outcomes.isLoading, error: outcomes.error,
          hint: `${spec.hint}${
            outcomes.data
              ? ` Here: ${outcomes.data.verdicts} of ${outcomes.data.total_disposed} disposals.`
              : ""}`,
        };
      case "kpi-overdue":
        return {
          ...base, value: totals?.overdue_reviews,
          loading: perf.isLoading, error: perf.error,
          hint: `${spec.hint}${staleNote}`,
        };
      case "kpi-ageing-180":
        return {
          ...base, value: ageing180,
          loading: perf.isLoading, error: perf.error,
        };
      case "kpi-imbalance":
        return {
          ...base, value: balance?.imbalance_ratio_max_over_median,
          loading: perf.isLoading, error: perf.error,
          hint: `${spec.hint}${
            balance?.stations_compared != null
              ? ` Across ${balance.stations_compared} stations compared.` : ""}`,
        };
      case "kpi-stations":
        return {
          ...base, value: totals?.stations_in_scope,
          loading: perf.isLoading, error: perf.error,
        };
      case "kpi-officers":
        return {
          ...base, value: totals?.officers_in_scope,
          loading: perf.isLoading, error: perf.error,
        };
      case "kpi-officer-p90":
        return {
          ...base, value: officers?.p90_open_per_officer,
          loading: perf.isLoading, error: perf.error,
        };
      case "kpi-heavy-load":
        return {
          ...base, value: officers?.heavy_load_officers,
          loading: perf.isLoading, error: perf.error,
          hint: `${spec.hint}${
            officers?.heavy_load_threshold != null
              ? ` Threshold: more than ${officers.heavy_load_threshold} open cases.` : ""}`,
        };

      /* --- forecast ----------------------------------------------------- */
      case "kpi-predicted":
        return {
          ...base, value: forecast.data ? Math.round(predicted) : undefined,
          loading: forecast.isLoading, error: forecast.error,
        };
      case "kpi-wape":
        return {
          ...base, value: pct(model?.wape),
          loading: backtest.isLoading, error: backtest.error,
        };
      case "kpi-coverage":
        return {
          ...base, value: pct(model?.coverage_80),
          loading: backtest.isLoading, error: backtest.error,
        };
      case "kpi-abstention":
        return {
          ...base, value: pct(backtest.data?.abstention_rate),
          loading: backtest.isLoading, error: backtest.error,
        };

      /* --- integrity ---------------------------------------------------- */
      case "kpi-data-age":
        return {
          ...base, value: perf.data?.data_age_days,
          loading: perf.isLoading, error: perf.error,
          hint: perf.data?.stale
            ? `The case record behind every accountability figure is ${perf.data.data_age_days} days old (as of ${perf.data.as_of}) and the service flags it STALE. Windows on this board are relative to that as-of date, not to today.`
            : spec.hint,
        };
      case "kpi-data-quality":
        return {
          ...base, value: quality.data?.total,
          loading: quality.isLoading, error: quality.error,
        };
      case "kpi-jurisdiction":
        return {
          ...base, value: jurisdiction.data?.open_jurisdiction_issues,
          loading: jurisdiction.isLoading, error: jurisdiction.error,
        };
      case "kpi-suppressed":
        return {
          ...base, value: socio.data?.suppressed_cells,
          loading: socio.isLoading, error: socio.error,
        };
      case "kpi-districts":
        return {
          ...base, value: socio.data?.districts_analysed,
          loading: socio.isLoading, error: socio.error,
        };
      case "kpi-conformance":
        return {
          ...base, value: ratioPct(contract.data?.conforming, contract.data?.total),
          loading: contract.isLoading, error: contract.error,
        };

      /* --- patterns ----------------------------------------------------- */
      case "kpi-patterns":
        return {
          ...base, value: patterns.data?.total,
          loading: patterns.isLoading, error: patterns.error,
        };
      case "kpi-groups":
        return {
          ...base, value: communities.data ? gangCommunities : undefined,
          loading: communities.isLoading, error: communities.error,
          hint: `${spec.hint} Among the ${COMMUNITY_LIMIT} largest communities.`,
        };
      case "kpi-poi":
        return {
          ...base, value: centrality.data?.persons_of_interest?.length,
          loading: centrality.isLoading, error: centrality.error,
        };
      case "kpi-tasks":
        return {
          ...base, value: tasks.data?.total,
          loading: tasks.isLoading, error: tasks.error,
        };

      /* --- traffic wing ------------------------------------------------- */
      case "kpi-traffic-incidents":
        return {
          ...base, value: trends.data?.total,
          spark: trends.data?.series.map((p) => p.count),
          loading: trends.isLoading, error: trends.error,
          hint: `${spec.hint} The series is already confined to this wing's crime heads server-side.`,
        };

      /* --- cyber and financial ------------------------------------------ */
      case "kpi-flagged-txn":
        return {
          ...base, value: flagged.data?.total,
          loading: flagged.isLoading, error: flagged.error,
          hint: `${spec.hint}${
            flagged.data
              ? ` Split by reason: ${Object.entries(flagged.data.by_reason)
                  .map(([reason, n]) => `${reason} ${n}`)
                  .join(", ")}.`
              : ""}`,
        };
      case "kpi-money-trails":
        return {
          ...base,
          /* Read off the same payload as the card above, not fetched separately.
             `?? null` and not `?? 0`: an absent key means the detector recorded no
             circular reason at all, which is a different fact from a run that found
             none, and KpiCard shows an em-dash rather than a confident zero. */
          value: flagged.data ? flagged.data.by_reason.circular ?? null : undefined,
          loading: flagged.isLoading, error: flagged.error,
          hint: `${spec.hint} Counted from the same flagged-transaction feed as the card beside it, so the two cannot disagree.`,
        };
      case "kpi-linked-accounts":
        return {
          ...base, value: identity.data?.network_edges,
          loading: identity.isLoading, error: identity.error,
          hint: `Entity-resolution links in the canonical graph${
            identity.data
              ? `, all ${identity.data.network_edges_provenanced.toLocaleString()} of them carrying provenance`
              : ""}. An aggregate edge count — no persons, no identifiers.`,
        };

      /* --- station case work -------------------------------------------- */
      case "kpi-review-queue":
        return {
          ...base, value: reviewQueue.data?.total,
          loading: reviewQueue.isLoading, error: reviewQueue.error,
        };

      /* --- platform ----------------------------------------------------- */
      case "kpi-active-seats":
        return {
          ...base, value: seats.data?.total,
          loading: seats.isLoading, error: seats.error,
        };
      case "kpi-imports":
        return {
          ...base, value: imports.data?.total,
          loading: imports.isLoading, error: imports.error,
        };
      case "kpi-models":
        return {
          ...base, value: models.data?.total,
          loading: models.isLoading, error: models.error,
        };
      case "kpi-ui-overrides":
        return {
          ...base, value: uiOverrides.data?.items.length,
          loading: uiOverrides.isLoading, error: uiOverrides.error,
          hint: `${spec.hint} Counted across every role, not just this seat's: the question is how far this deployment has drifted from the shipped defaults.`,
        };

      /* --- not yet bound ------------------------------------------------ */
      default:
        return {
          ...base, pending: true,
          pendingNote:
            `No data binding for '${spec.id}' yet. Declared in the KPI registry (${spec.source}) but not wired to a hook, so it is shown as pending rather than blank — an unbound card is a gap to see, not to hide.`,
        };
    }
  }

  return { resolve };
}
