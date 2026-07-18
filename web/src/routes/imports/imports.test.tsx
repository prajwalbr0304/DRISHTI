import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const templates = vi.fn();
const listBatches = vi.fn();
const moneyAlerts = vi.fn();
vi.mock("@/api", () => ({
  api: {
    imports: {
      templates: (...a: unknown[]) => templates(...a),
      listBatches: (...a: unknown[]) => listBatches(...a),
      moneyAlerts: (...a: unknown[]) => moneyAlerts(...a),
      // referenced by mutations but not invoked during render
      moneyScan: vi.fn(),
      moneyDisposition: vi.fn(),
      createBatch: vi.fn(),
      commit: vi.fn(),
      rollback: vi.fn(),
    },
  },
}));

import { ImportsWorkspace } from "@/routes/imports/ImportsWorkspace";
import { MoneyAlertsPanel } from "@/routes/imports/panels";
import { RoleProvider } from "@/providers/RoleProvider";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RoleProvider>
        <MemoryRouter>{node}</MemoryRouter>
      </RoleProvider>
    </QueryClientProvider>,
  );
}

describe("ImportsWorkspace (Phase 8)", () => {
  beforeEach(() => {
    templates.mockReset();
    listBatches.mockReset();
    templates.mockResolvedValue({ count: 0, templates: [] });
    listBatches.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  });

  it("renders the import workspace with tabs and the import inbox", async () => {
    wrap(<ImportsWorkspace />);
    expect(await screen.findByText("Digital & financial imports")).toBeInTheDocument();
    expect(screen.getByText("New structured import")).toBeInTheDocument();
    // tab labels present
    expect(screen.getByText("Entity-link review")).toBeInTheDocument();
    expect(screen.getByText("Money alerts")).toBeInTheDocument();
  });
});

describe("MoneyAlertsPanel (Phase 8)", () => {
  beforeEach(() => { moneyAlerts.mockReset(); });

  it("shows a reason-coded, evidence-backed alert with a reviewer disposition", async () => {
    moneyAlerts.mockResolvedValue({
      total: 1, page: 1, page_size: 50, by_status: { open: 1 },
      items: [{
        money_alert_id: 1, alert_type: "structuring", reason_code: "STRUCT_SUBTHRESHOLD_FANIN",
        severity: "high", title: "Repeated sub-threshold deposits into account 42",
        message: "Review required; a pattern is not by itself evidence of an offence.",
        account_id: 42, case_master_id: 7, evidence_item_id: 9,
        transaction_ids: [1, 2, 3], source_record_ids: [11, 12], status: "open",
      }],
    });
    wrap(<MoneyAlertsPanel />);
    expect(await screen.findByText("STRUCT_SUBTHRESHOLD_FANIN")).toBeInTheDocument();
    expect(screen.getByText(/not by itself evidence/i)).toBeInTheDocument();
    // provenance surfaced
    expect(screen.getByText(/3 txn/)).toBeInTheDocument();
    expect(screen.getByText(/2 source record/)).toBeInTheDocument();
    // reviewer disposition available (analyst default role can review)
    expect(screen.getByText("Acknowledge")).toBeInTheDocument();
  });
});
