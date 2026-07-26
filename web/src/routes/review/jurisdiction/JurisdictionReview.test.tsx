import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const jurisdictionIssues = vi.fn();
const jurisdictionFreshness = vi.fn();
vi.mock("@/api", () => ({
  api: {
    geo: {
      jurisdictionIssues: (...a: unknown[]) => jurisdictionIssues(...a),
      jurisdictionFreshness: (...a: unknown[]) => jurisdictionFreshness(...a),
      jurisdictionScan: vi.fn(),
      jurisdictionReassign: vi.fn(),
    },
  },
}));

import { JurisdictionReview } from "@/routes/review/jurisdiction/JurisdictionReview";
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

describe("JurisdictionReview", () => {
  beforeEach(() => {
    jurisdictionIssues.mockReset();
    jurisdictionFreshness.mockReset();
    localStorage.clear();
    jurisdictionFreshness.mockResolvedValue({
      boundaries: {
        state: { count: 1, version: 1, as_of: null, source: "KGIS" },
        district: { count: 32, version: 1, as_of: null, source: "KGIS" },
        taluk: { count: 230, version: 1, as_of: null, source: "KGIS" },
      },
      unit_locations: 1000, last_scan: null, open_jurisdiction_issues: 1,
      environment_label: "Synthetic Hackathon Demo",
    });
  });

  it("lists an open mismatch with a reviewed reassignment affordance", async () => {
    localStorage.setItem("drishti.role", "dysp_acp");
    jurisdictionIssues.mockResolvedValue({
      total: 1, page: 1, page_size: 100, status: "open",
      items: [{
        data_quality_issue_id: 11, issue_type: "invalid_jurisdiction_district",
        severity: "error", status: "open", case_master_id: 42, crime_no: "SYN-CRIME-42",
        assigned_district_id: 5, assigned_district_name: "Ballari",
        resolved_district_id: 9, resolved_district_name: "Mysuru", detail: {}, created_at: null,
      }],
    });
    wrap(<JurisdictionReview />);
    expect(screen.getByText("Jurisdiction review")).toBeInTheDocument();
    expect(await screen.findByText("SYN-CRIME-42")).toBeInTheDocument();
    const btn = await screen.findByRole("button", { name: /Reassign to detected \(Mysuru\)/i });
    expect(btn).toBeEnabled();
    // freshness panel reflects the persisted, versioned geography
    expect(screen.getByText("Synthetic Hackathon Demo")).toBeInTheDocument();
  });

  // Interim access model: every command role holds every capability, so the
  // queue opens for a field seat too (the server enforces the real decision).
  it("opens for the investigating-officer seat", async () => {
    localStorage.setItem("drishti.role", "investigating_officer");
    jurisdictionIssues.mockResolvedValue({ total: 0, page: 1, page_size: 100, status: "open", items: [] });
    wrap(<JurisdictionReview />);
    expect(screen.getByText("Jurisdiction review")).toBeInTheDocument();
    expect(screen.queryByText(/Not available for this role/i)).not.toBeInTheDocument();
  });
});
