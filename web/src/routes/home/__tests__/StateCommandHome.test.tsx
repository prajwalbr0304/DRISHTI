import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";

/* ============================================================================
   DGP / State Command KPI band. Every assertion here is about a CLAIM the card
   makes: which field feeds it, what scale the service uses, and whether a
   missing number can be mistaken for a zero. The three chart panels are stubbed
   because they are unchanged by this slice.
   ========================================================================== */

const trends = vi.fn();
const hotspots = vi.fn();
const alerts = vi.fn();
const caseload = vi.fn();
const socioeconomic = vi.fn();
const patterns = vi.fn();
const forecastMap = vi.fn();
const backtest = vi.fn();
const contract = vi.fn();
const qualityIssues = vi.fn();
const jurisdictionFreshness = vi.fn();
const overview = vi.fn();
const communitiesList = vi.fn();
const notificationsList = vi.fn();
const tasks = vi.fn();
const outcomesOverview = vi.fn();

vi.mock("@/api", () => ({
  api: {
    geo: {
      trends: (...a: unknown[]) => trends(...a),
      hotspots: (...a: unknown[]) => hotspots(...a),
      alerts: (...a: unknown[]) => alerts(...a),
      jurisdictionFreshness: (...a: unknown[]) => jurisdictionFreshness(...a),
    },
    cases: { caseload: (...a: unknown[]) => caseload(...a) },
    analytics: {
      socioeconomic: (...a: unknown[]) => socioeconomic(...a),
      patterns: (...a: unknown[]) => patterns(...a),
    },
    forecast: {
      map: (...a: unknown[]) => forecastMap(...a),
      backtest: (...a: unknown[]) => backtest(...a),
    },
    explain: { contract: (...a: unknown[]) => contract(...a) },
    intake: { qualityIssues: (...a: unknown[]) => qualityIssues(...a) },
    performance: { overview: (...a: unknown[]) => overview(...a) },
    outcomes: { overview: (...a: unknown[]) => outcomesOverview(...a) },
    graph: { communitiesList: (...a: unknown[]) => communitiesList(...a) },
    notifications: {
      list: (...a: unknown[]) => notificationsList(...a),
      tasks: (...a: unknown[]) => tasks(...a),
    },
  },
}));

vi.mock("@/components/charts/TrendChart", () => ({ TrendChart: () => <div /> }));
vi.mock("@/components/dashboard/ForecastSummary", () => ({ ForecastSummary: () => <div /> }));
// The socio band is now one box per indicator; each renders a scatter, which is
// unchanged by this slice and expensive to lay out in jsdom.
vi.mock("@/components/dashboard/IndicatorCrimeCard", () => ({
  IndicatorCrimeCard: () => <div />,
}));
vi.mock("@/components/charts/CorrelationBars", () => ({ CorrelationBars: () => <div /> }));

import { StateCommandHome } from "@/routes/home/StateCommandHome";
import { useDashboardStore } from "@/stores/useDashboardStore";

// Arrangement and dismissal are PERSISTED, so they leak between tests unless the
// store is reset. Hiding a card in one test must not blank it in the next.
beforeEach(() => {
  useDashboardStore.setState({ layouts: {}, hidden: {} });
  localStorage.clear();
});

const RESULT = {
  answer: "synthetic",
  confidence: 0.9,
  source_record_ids: ["CaseMaster"],
  reasoning_summary: "synthetic",
  model_version: "test@1",
};

const TRENDS = {
  result: RESULT,
  scope: {},
  total: 12480,
  latest_period: "2025-12",
  mom_delta: -420,
  mom_pct: -3.4,
  yoy_delta: 1390,
  yoy_pct: 12.5,
  series: [
    { period: "2025-07", count: 1900, is_anomaly: false },
    { period: "2025-08", count: 2100, is_anomaly: true },
    { period: "2025-09", count: 2050, is_anomaly: false },
    { period: "2025-10", count: 2200, is_anomaly: false },
    { period: "2025-11", count: 2180, is_anomaly: true },
    { period: "2025-12", count: 2050, is_anomaly: false },
  ],
  decomposition: null,
};

const ALERTS = {
  result: RESULT,
  count: 4,
  alerts: [
    { alert_id: 1, alert_type: "spike", severity: "critical", title: "A", status: "open" },
    { alert_id: 2, alert_type: "spike", severity: "critical", title: "B", status: "open" },
    { alert_id: 3, alert_type: "spike", severity: "high", title: "C", status: "open" },
    { alert_id: 4, alert_type: "spike", severity: "medium", title: "D", status: "open" },
  ],
};

const PERFORMANCE = {
  scope: {},
  as_of: "2025-12-31",
  data_age_days: 246,
  stale: true,
  empty: false,
  window_days: 90,
  totals: {
    total_cases: 15320,
    active_workload: 6419,
    new_cases_in_window: 817,
    overdue_reviews: 6070,
    overdue_threshold_days: 90,
    stations_in_scope: 156,
    officers_in_scope: 1808,
    disposed_or_closed: 8901,
  },
  ageing: [],
  chargesheet: {
    filed_in_window: 557,
    new_cases_in_window: 817,
    throughput_ratio: 0.682,
    throughput_ratio_denominator: "chargesheets filed / new cases, same window",
    median_days_to_chargesheet: 86,
    avg_days_to_chargesheet: 84.7,
  },
  officers: { median_open_per_officer: 3, p90_open_per_officer: 10, max_open_per_officer: 28 },
  workload_balance: {
    stations_compared: 156,
    median_open: 40,
    max_open: 66,
    imbalance_ratio_max_over_median: 1.65,
  },
  stations: [],
  limitations: ["Synthetic hackathon data."],
  dataset: "synthetic",
};

const BACKTEST = {
  result: RESULT,
  scope: {},
  n_series: 30,
  origins: ["2025-07", "2025-08"],
  scored_points: 480,
  cells_considered: 1200,
  abstained_cells: 164,
  abstention_rate: 0.137,
  model: {
    name: "timesfm",
    family: "foundation",
    mae: 2.5,
    rmse: 3.1,
    wape: 0.284,
    smape: 31.2,
    coverage_80: 0.812,
    coverage_50: 0.51,
    n: 480,
  },
  baselines: {},
  skill_vs_baselines: {},
  beats_all_baselines: true,
  error_by_district: [],
  error_by_season: {},
  error_by_head: {},
  geo_holdout: {},
};

const SOCIO = {
  result: RESULT,
  indicators: ["literacy_rate"],
  crime_categories: ["All Crime", "Crimes Against Property"],
  districts_analysed: 30,
  k_threshold: 5,
  suppressed_cells: 14,
  focus_indicator: "literacy_rate",
  correlation_matrix: [],
  scatter: [],
  narrative: { crime_category: "Crimes Against Property" },
  // The district panel each indicator box builds its own series from.
  districts: [],
};

function seedHappyPath() {
  trends.mockResolvedValue(TRENDS);
  hotspots.mockResolvedValue({ result: RESULT, count: 37, hotspots: [] });
  alerts.mockResolvedValue(ALERTS);
  caseload.mockResolvedValue({
    stages: [], by_status: [], total: 15320, open_total: 8420, disposed_total: 6900,
  });
  socioeconomic.mockResolvedValue(SOCIO);
  patterns.mockResolvedValue({
    result: RESULT, total: 42,
    pattern_types: ["serial", "temporal", "spatial"], by_type: {}, items: [],
  });
  forecastMap.mockResolvedValue({
    result: RESULT, layer: "fused", count: 2,
    cells: [{ predicted_count: 120.4 }, { predicted_count: 180.2 }],
  });
  backtest.mockResolvedValue(BACKTEST);
  contract.mockResolvedValue({
    result: RESULT, total: 124, conforming: 118, non_conforming: 6, routes: [],
  });
  qualityIssues.mockResolvedValue({
    items: [], total: 431, by_severity: { high: 12, medium: 300, low: 119 }, page: 1, page_size: 1,
  });
  jurisdictionFreshness.mockResolvedValue({
    boundaries: {}, unit_locations: 900, open_jurisdiction_issues: 24,
    environment_label: "synthetic",
  });
  overview.mockResolvedValue(PERFORMANCE);
  communitiesList.mockResolvedValue({
    communities: [
      { community: 1, size: 40, gang_members: 3 },
      { community: 2, size: 30, gang_members: 0 },
      { community: 3, size: 20, gang_members: 1 },
    ],
  });
  notificationsList.mockResolvedValue({ total: 60, unread: 7, items: [] });
  tasks.mockResolvedValue({ total: 19, items: [] });
  /* Court outcomes. The two rates are deliberately different denominators, which
     is the whole point of the endpoint: conviction is over VERDICTS
     (1,340 / 2,482 = 53.99%), prosecution is over ALL FINAL DISPOSALS
     (2,482 / 8,901 = 27.9%). Folding B-reports and C-reports into the conviction
     denominator would report 15.1% and confuse "never prosecuted" with "lost". */
  outcomesOverview.mockResolvedValue({
    result: RESULT,
    scope: {},
    total_disposed: 8901,
    verdicts: 2482,
    convicted: 1340,
    acquitted: 1142,
    conviction_rate: 0.5399,
    prosecution_rate: 0.2789,
  });
}

function wrap(node: ReactNode) {
  const qc = new QueryClient({
    queryCache: new QueryCache({ onError: () => {} }),
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  // Mirrors the production tree: AppShell supplies the router and the ambient
  // TooltipProvider that Widget's overflow menu needs.
  return render(
    <MemoryRouter>
      <TooltipProvider>
        <QueryClientProvider client={qc}>{node}</QueryClientProvider>
      </TooltipProvider>
    </MemoryRouter>,
  );
}

/** The card carrying `label` — KpiCard's root is the nearest .rounded-card. */
function kpi(label: string): HTMLElement {
  const root = screen.getByText(label).closest(".rounded-card");
  expect(root, `no KPI card found for "${label}"`).toBeTruthy();
  return root as HTMLElement;
}

/** The big number on that card, including its unit suffix. Empty while the card
 *  is still loading, because KpiCard renders a Skeleton in place of the value. */
function kpiValue(label: string): string {
  return kpi(label).querySelector(".text-28")?.textContent ?? "";
}

/** Wait for a card to settle on a value. Each card has its own request, so they
 *  do not resolve together and a bare assertion would race the slowest one. */
async function expectKpi(label: string, expected: string) {
  await waitFor(() => expect(kpiValue(label), `KPI "${label}"`).toBe(expected));
}

describe("StateCommandHome — band A: state pulse", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedHappyPath();
  });

  it("uses the YEAR-ON-YEAR change as the delta and labels it as such", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Incidents (window)", "12,480");

    const card = kpi("Incidents (window)");
    expect(card.textContent).toContain("+12.5%");
    // short enough to sit beside the sparkline without overflowing the card,
    // and still naming the comparison rather than implying the prior period
    expect(card.textContent).toContain("vs. last year");
    // the month-on-month figure must NOT be the delta on this card
    expect(card.textContent).not.toContain("-3.4");
    expect(card.textContent).not.toContain("vs. prior");
  });

  it("prints month-on-month as its own value rather than a second delta", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Month-on-month change", "-3.4%");
  });

  it("counts CRITICAL alerts only, excluding high", async () => {
    wrap(<StateCommandHome />);
    // fixture: 2 critical, 1 high, 1 medium
    await expectKpi("Critical alerts", "2");
  });

  it("counts the periods flagged as anomalous in the series", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Anomalous periods", "2");
  });
});

describe("StateCommandHome — bands B and C: volume, load, outcomes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedHappyPath();
  });

  it("reads the accountability band off /performance/overview at a 90-day window", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Active workload", "6,419");

    expect(overview).toHaveBeenCalled();
    expect(overview.mock.calls[0][0]).toMatchObject({ window_days: 90 });

    await expectKpi("Hotspots", "37");
    await expectKpi("Open cases", "8,420");
    await expectKpi("New FIRs (90d)", "817");
    await expectKpi("Overdue reviews", "6,070");
    await expectKpi("Stations in scope", "156");
    await expectKpi("Station load imbalance", "1.65×");
    await expectKpi("Median days to chargesheet", "86d");
  });

  it("scales the 0..1 throughput ratio to a percentage and derives the disposal rate", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Chargesheet throughput", "68.2%"); // 0.682 -> 68.2%
    await expectKpi("Disposal rate", "58.1%"); // 8901 / 15320
  });

  it("treats a real zero as a number, not as a missing value", async () => {
    overview.mockResolvedValue({
      ...PERFORMANCE,
      totals: { ...PERFORMANCE.totals, active_workload: 0, overdue_reviews: 0 },
      chargesheet: { ...PERFORMANCE.chargesheet, throughput_ratio: 0 },
    });
    wrap(<StateCommandHome />);

    await expectKpi("Active workload", "0");
    await expectKpi("Overdue reviews", "0");
    await expectKpi("Chargesheet throughput", "0%");
  });

  it("shows an em-dash when the service has no number and never invents a 0", async () => {
    overview.mockResolvedValue({
      ...PERFORMANCE,
      // an empty scope: the service answers, but with nothing to measure
      empty: true,
      totals: { total_cases: 0, disposed_or_closed: 0 },
      chargesheet: {
        ...PERFORMANCE.chargesheet,
        throughput_ratio: null,
        median_days_to_chargesheet: null,
      },
      workload_balance: { ...PERFORMANCE.workload_balance, imbalance_ratio_max_over_median: null },
    });
    wrap(<StateCommandHome />);

    await expectKpi("Active workload", "—"); // absent from totals
    await expectKpi("Chargesheet throughput", "—"); // null ratio
    await expectKpi("Median days to chargesheet", "—");
    await expectKpi("Station load imbalance", "—");
    // a zero denominator is undefined, not 0%
    await expectKpi("Disposal rate", "—");
    // the request succeeded, so this is an empty scope and not an error state
    expect(overview).toHaveBeenCalled();
  });
});

describe("StateCommandHome — band D: forecast and model trust", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedHappyPath();
  });

  it("renders the 0..1 backtest metrics as percentages", async () => {
    wrap(<StateCommandHome />);

    await expectKpi("Forecast error (WAPE)", "28.4%"); // wape 0.284
    await expectKpi("80% interval coverage", "81.2%"); // coverage_80 0.812
    await expectKpi("Forecast abstention", "13.7%"); // abstention_rate 0.137
  });

  it("never triggers a forecast write and derives contract conformance", async () => {
    wrap(<StateCommandHome />);

    await expectKpi("Predicted next period", "301"); // 120.4 + 180.2, rounded
    await expectKpi("Contract conformance", "95.2%"); // 118 of 124
    expect(backtest.mock.calls[0][0]).toMatchObject({ persist: false });
  });
});

describe("StateCommandHome — band E: data integrity", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedHappyPath();
  });

  it("surfaces staleness, the quality ledger and containment failures", async () => {
    wrap(<StateCommandHome />);

    await expectKpi("Case-data age", "246d");
    await expectKpi("Data-quality issues", "431");
    await expectKpi("Jurisdiction issues", "24");
  });

  it("requests the quality queue UNFILTERED so total and by_severity agree", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Data-quality issues", "431");

    // a status filter would narrow `total` while by_severity stayed full-table
    expect(qualityIssues.mock.calls[0][0]).not.toHaveProperty("status");
  });

  it("moves the socio counters out of the top band into data integrity", async () => {
    wrap(<StateCommandHome />);

    await expectKpi("Cells suppressed", "14");
    await expectKpi("Districts analysed", "30");

    // tiles render in declaration order, so DOM order proves the band moved down
    const text = document.body.textContent ?? "";
    expect(text.indexOf("Incidents (window)")).toBeLessThan(text.indexOf("Cells suppressed"));
    expect(text.indexOf("Chargesheet throughput")).toBeLessThan(text.indexOf("Districts analysed"));
  });
});

describe("StateCommandHome — band F: patterns and queue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedHappyPath();
  });

  it("counts active patterns, gang-linked communities and both queues", async () => {
    wrap(<StateCommandHome />);

    await expectKpi("Active patterns", "42");
    // 3 communities in the fixture, but only 2 carry a known gang member
    await expectKpi("Organised groups", "2");
    await expectKpi("Open tasks", "19");
  });

  it("does not render a per-seat notification counter", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Open tasks", "19");

    // Removed: /notifications is scoped to the calling actor, so on a state
    // board it measured one inbox rather than anything state-wide.
    expect(screen.queryByText("Unread notifications")).toBeNull();
    expect(notificationsList).not.toHaveBeenCalled();
  });

  it("asks the task service for the OPEN queue specifically", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Open tasks", "19");
    expect(tasks.mock.calls[0][0]).toMatchObject({ status: "open" });
  });
});

describe("StateCommandHome — removing a card", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedHappyPath();
  });

  it("offers a remove control on each card and dismisses it on click", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Hotspots", "37");

    const remove = screen.getByRole("button", { name: /remove the hotspots card/i });
    fireEvent.click(remove);

    await waitFor(() => expect(screen.queryByText("Hotspots")).toBeNull());
    // neighbours are untouched
    expect(screen.getByText("Critical alerts")).toBeInTheDocument();
  });

  it("keeps dismissal reversible via a restore control that counts what is hidden", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Hotspots", "37");

    // nothing hidden yet, so no restore affordance is taking up space
    expect(screen.queryByRole("button", { name: /hidden card/i })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /remove the hotspots card/i }));
    const restore = await screen.findByRole("button", { name: /show 1 hidden card/i });

    fireEvent.click(screen.getByRole("button", { name: /remove the open cases card/i }));
    await screen.findByRole("button", { name: /show 2 hidden cards/i });

    fireEvent.click(screen.getByRole("button", { name: /show 2 hidden cards/i }));
    await waitFor(() => expect(screen.getByText("Hotspots")).toBeInTheDocument());
    expect(screen.getByText("Open cases")).toBeInTheDocument();
    expect(restore).not.toBeInTheDocument();
  });

  it("records the dismissal against this board only", async () => {
    wrap(<StateCommandHome />);
    await expectKpi("Hotspots", "37");
    fireEvent.click(screen.getByRole("button", { name: /remove the hotspots card/i }));

    await waitFor(() =>
      expect(useDashboardStore.getState().hidden).toEqual({ dgp_state_command: ["kpi-hotspots"] }),
    );
    // the shared policymaker board is a different id and so is unaffected
    expect(useDashboardStore.getState().hidden.policymaker).toBeUndefined();
  });
});

describe("StateCommandHome — band G: conviction rate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedHappyPath();
  });

  /* This card used to be a `pending` placeholder reading "awaiting API", because
     no endpoint reported court outcomes. /outcomes/overview now does, so the card
     carries a real rate and this assertion moved with it.

     What matters is the DENOMINATOR: convictions over cases that reached a
     VERDICT — convictions plus acquittals — not over all disposals. A B-report
     (undetected) or C-report (false complaint) is a decision not to prosecute, so
     folding those in conflates "never went to court" with "lost in court". On the
     seeded data that is 53.97% versus 16.13%, so it is not a rounding matter. */
  it("reports conviction rate against verdicts, not all disposals", async () => {
    wrap(<StateCommandHome />);
    await screen.findByText("Conviction rate");

    const card = kpi("Conviction rate");
    expect(card.textContent).not.toContain("awaiting API");

    // A measured rate, not the placeholder em-dash. The denominator itself is
    // asserted server-side in services/ml/tests/test_outcomes.py, which is where
    // the convicted/(convicted+acquitted) arithmetic lives; the card only has to
    // stop claiming the metric is unavailable.
    // 1,340 of 2,482 verdicts. The service reports a 0..1 fraction and the card
    // renders a percentage, so a card reading 0.5 would mean the scale was
    // dropped somewhere.
    await expectKpi("Conviction rate", "54%");
  });

  it("reports prosecution rate beside it, on the wider denominator", async () => {
    wrap(<StateCommandHome />);
    // 2,482 verdicts of 8,901 final disposals. Shown next to the conviction rate
    // because neither is readable alone: a high conviction rate on very few
    // prosecutions is a different picture from the same rate on many.
    await expectKpi("Prosecution rate", "27.9%");
  });
});
