import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const listDrafts = vi.fn();
vi.mock("@/api", () => ({ api: { intake: { listDrafts: (...a: unknown[]) => listDrafts(...a), review: vi.fn() } } }));

import { IntakeInbox } from "@/routes/intake/IntakeInbox";
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

describe("IntakeInbox", () => {
  beforeEach(() => listDrafts.mockReset());

  it("lists drafts and offers a New FIR action", async () => {
    listDrafts.mockResolvedValue({
      items: [{
        intake_draft_id: 1, draft_key: "DR-ABC123", status: "submitted", case_kind: "fir_standard",
        case_category_code: "FIR", crime_no: null, case_master_id: null, party_count: 3,
        validation_ok: true, revision_no: 2, created_at: null, updated_at: null, submitted_at: null,
      }],
      total: 1, page: 1, page_size: 50,
    });
    wrap(<IntakeInbox />);
    expect(screen.getByText("Intake inbox")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /New FIR/i }).length).toBeGreaterThan(0);
    expect(await screen.findByText("DR-ABC123")).toBeInTheDocument();
  });
});
