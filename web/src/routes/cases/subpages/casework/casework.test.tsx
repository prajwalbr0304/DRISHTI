import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const listStatements = vi.fn();
const court = vi.fn();
const lookups = vi.fn();
vi.mock("@/api", () => ({
  api: {
    casework: {
      listStatements: (...a: unknown[]) => listStatements(...a),
      court: (...a: unknown[]) => court(...a),
      lookups: (...a: unknown[]) => lookups(...a),
    },
  },
}));

import { StatementsPage } from "@/routes/cases/subpages/StatementsPage";
import { CourtLifecyclePage } from "@/routes/cases/subpages/CourtLifecyclePage";
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

const LOOKUPS = {
  statement_types: [], property_item_types: [], property_statuses: [],
  court_event_types: [], bail_statuses: [], disposition_types: [], lab_test_types: [],
  lab_statuses: [], access_classifications: [], courts: [],
};

describe("StatementsPage (Phase 7)", () => {
  beforeEach(() => { listStatements.mockReset(); lookups.mockReset(); lookups.mockResolvedValue(LOOKUPS); });

  it("shows a restricted statement as access-limited (server-redacted) text", async () => {
    listStatements.mockResolvedValue({
      case_master_id: 5, count: 1,
      items: [{
        statement_id: 1, case_master_id: 5, statement_type: "witness", access_classification: "restricted",
        state: "recorded", is_restricted: true, access_limited: true,
        current_text: "[Restricted — limited to assigned investigators / supervisors]",
        current_version_no: 1, versions: [{ statement_version_id: 1, version_no: 1, redacted: false }],
      }],
    });
    wrap(<StatementsPage caseId={5} />);
    expect(await screen.findByText(/Restricted/)).toBeInTheDocument();
    expect(screen.getByText(/limited to assigned investigators/i)).toBeInTheDocument();
  });
});

describe("CourtLifecyclePage (Phase 7)", () => {
  beforeEach(() => { court.mockReset(); lookups.mockReset(); lookups.mockResolvedValue(LOOKUPS); });

  it("shows the current status and gates outcome until a final event", async () => {
    court.mockResolvedValue({
      case_master_id: 9, category: "FIR", current_status: "under_investigation",
      current_status_label: "Under investigation", legacy_status: "Under Investigation",
      has_case_version: false, prior_event_types: [], allowed_transitions: [],
      court_events: [], bail_events: [], dispositions: [], outcomes: [],
      has_final_disposition: false, can_record_outcome: false,
    });
    wrap(<CourtLifecyclePage caseId={9} />);
    expect(await screen.findByText("Under investigation")).toBeInTheDocument();
    expect(screen.getByText(/only after a verified final event/i)).toBeInTheDocument();
  });
});
