import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const freshness = vi.fn();
vi.mock("@/api", () => ({ api: { livefeed: { freshness: (...a: unknown[]) => freshness(...a) } } }));

import { LiveFreshness } from "@/components/dashboard/LiveFreshness";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe("LiveFreshness (Prompt 20 Part E)", () => {
  beforeEach(() => freshness.mockReset());

  it("renders committed-FIR freshness with the no-rescore/no-dispatch guarantees", async () => {
    freshness.mockResolvedValue({
      transport: "poll (local); Catalyst Signal `case.committed` + scoped channel in Prompt 23",
      event_type: "case.committed",
      processed_count: 2,
      duplicate_suppressed: 1,
      projections: {
        district_statistic: { processed_count: 2, freshness_seconds: 5, last_processed_ts: "x", last_success_ts: "x", last_failure_ts: null },
        supervisor_workload: { processed_count: 2, freshness_seconds: 5, last_processed_ts: "x", last_success_ts: "x", last_failure_ts: null },
        hotspot_near_repeat: { processed_count: 2, freshness_seconds: 5, last_processed_ts: "x", last_success_ts: "x", last_failure_ts: null },
      },
      recent: [],
      guarantees: { person_rescored: false, auto_dispatch: false },
    });
    wrap(<LiveFreshness />);
    expect(await screen.findByText(/2 committed FIR\(s\) this session/)).toBeInTheDocument();
    expect(screen.getByText(/1 duplicate\(s\) suppressed/)).toBeInTheDocument();
    expect(screen.getByText(/no person re-scoring/)).toBeInTheDocument();
    expect(screen.getByText(/District stats:/)).toBeInTheDocument();
  });

  it("shows idle projections before any FIR is committed this session", async () => {
    freshness.mockResolvedValue({
      transport: "poll (local); Catalyst Signal `case.committed` + scoped channel in Prompt 23",
      event_type: "case.committed", processed_count: 0, duplicate_suppressed: 0,
      projections: {
        district_statistic: { processed_count: 0, freshness_seconds: null, last_processed_ts: null, last_success_ts: null, last_failure_ts: null },
      },
      recent: [], guarantees: { person_rescored: false, auto_dispatch: false },
    });
    wrap(<LiveFreshness />);
    expect(await screen.findByText(/0 committed FIR\(s\) this session/)).toBeInTheDocument();
    expect(screen.getByText(/District stats: idle/)).toBeInTheDocument();
  });
});
