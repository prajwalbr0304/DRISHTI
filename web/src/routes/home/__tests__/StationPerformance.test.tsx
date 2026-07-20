import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const overview = vi.fn();
vi.mock("@/api", () => ({ api: { performance: { overview: (...a: unknown[]) => overview(...a) } } }));

import { StationPerformance } from "@/routes/home/StationPerformance";

function wrap(node: ReactNode) {
  // A no-op onError consumes query errors so an intentionally-rejected mock is
  // not flagged as an unhandled rejection by the test runner.
  const qc = new QueryClient({
    queryCache: new QueryCache({ onError: () => {} }),
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

const SAMPLE = {
  scope: { district_id: 1 },
  as_of: "2025-12-31",
  data_age_days: 202,
  stale: true,
  empty: false,
  window_days: 90,
  totals: {
    total_cases: 15320, active_workload: 6419, new_cases_in_window: 817,
    overdue_reviews: 6070, overdue_threshold_days: 90,
    stations_in_scope: 156, officers_in_scope: 1808, disposed_or_closed: 8901,
  },
  ageing: [
    { bucket: "0-30d", count: 123 }, { bucket: "31-90d", count: 230 },
    { bucket: "91-180d", count: 314 }, { bucket: ">180d", count: 5752 },
  ],
  chargesheet: {
    filed_in_window: 557, new_cases_in_window: 817, throughput_ratio: 0.682,
    throughput_ratio_denominator: "chargesheets filed / new cases, same window",
    median_days_to_chargesheet: 86, avg_days_to_chargesheet: 84.7,
  },
  officers: {
    officers_with_open_cases: 1541, median_open_per_officer: 3, p90_open_per_officer: 10,
    max_open_per_officer: 28, heavy_load_officers: 65, heavy_load_threshold: 15,
    note: "Aggregate distribution of open-case load; not an individual ranking.",
  },
  workload_balance: {
    stations_compared: 156, stations_in_scope: 156, median_open: 40, max_open: 66,
    total_open_across_stations: 6419, imbalance_ratio_max_over_median: 1.65,
    note: "Comparative load only.",
  },
  stations: [
    { unit_id: 90, unit_name: "Bengaluru City PS-58", district_name: "Bengaluru City",
      total: 134, open_cases: 66, new_cases: 8, overdue: 60 },
  ],
  limitations: [
    "Synthetic hackathon data; not an operational HR appraisal.",
    "Windows are relative to the dataset as-of date, not today.",
    "Disposal time is measured to chargesheet filing (time-to-chargesheet), not final court disposal.",
    "Officer load is an aggregate distribution — never a punitive per-officer rank.",
  ],
  dataset: "synthetic",
};

describe("StationPerformance (Prompt 20 Part C)", () => {
  beforeEach(() => overview.mockReset());

  it("renders real metrics with denominators, freshness and no placeholder", async () => {
    overview.mockResolvedValue(SAMPLE);
    wrap(<StationPerformance districtId={1} />);
    expect(await screen.findByText("6,419")).toBeInTheDocument(); // active workload
    expect(screen.getByText("Chargesheet rate")).toBeInTheDocument();
    expect(screen.getByText("68%")).toBeInTheDocument();          // throughput ratio
    expect(screen.getByText(/557\/817 filed\/new/)).toBeInTheDocument(); // denominator
    expect(screen.getByText(/as of 2025-12-31/)).toBeInTheDocument();     // freshness
    expect(screen.getByText(/data 202d old/)).toBeInTheDocument();        // stale flag
    expect(screen.getByText(/not an individual ranking/i)).toBeInTheDocument();
    expect(screen.getByText("Bengaluru City PS-58")).toBeInTheDocument(); // per-station
    // the old placeholder must be gone
    expect(screen.queryByText(/awaiting the performance api/i)).toBeNull();
  });

  it("renders an honest empty state when there are no cases in scope", async () => {
    overview.mockResolvedValue({
      ...SAMPLE, empty: true, as_of: null,
      limitations: ["Synthetic hackathon data.", "No cases in the requested scope."],
    });
    wrap(<StationPerformance districtId={999999} />);
    expect(await screen.findByText(/no cases in the current scope/i)).toBeInTheDocument();
  });

  it("surfaces a fresh (non-stale) as-of window without the stale badge", async () => {
    overview.mockResolvedValue({
      ...SAMPLE, stale: false, data_age_days: 3, as_of: "2026-07-18",
    });
    wrap(<StationPerformance districtId={1} />);
    expect(await screen.findByText(/as of 2026-07-18/)).toBeInTheDocument();
    // when fresh, the "data Nd old" stale badge is not shown
    expect(screen.queryByText(/data 3d old/)).toBeNull();
  });
});
