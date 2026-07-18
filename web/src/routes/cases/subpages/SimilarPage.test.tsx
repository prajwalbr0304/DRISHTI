import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const similar = vi.fn();
vi.mock("@/api", () => ({ api: { cases: { similar: (...a: unknown[]) => similar(...a) } } }));

import { SimilarPage } from "@/routes/cases/subpages/SimilarPage";
import { TooltipProvider } from "@/components/ui/tooltip";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>{node}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("SimilarPage (Phase 11 demo-context + why-match)", () => {
  beforeEach(() => {
    similar.mockReset();
    similar.mockResolvedValue({
      result: { answer: "x", confidence: 0.8, source_record_ids: [], reasoning_summary: "", model_version: "m@1" },
      query_case_id: 1, model_name: "drishti-embed-hashing", model_version_id: 3, corpus_size: 400,
      scope: "district", scope_district_id: 1,
      limitations: "Similar cases are decision-support leads, not an identity match.",
      results: [{
        case_id: 42, crime_no: "SYN-CR-42", crime_group: "Drug Offences", crime_subhead: null,
        district: "Bengaluru City", status: null, disposition: null, accused_count: 1, arrest_count: 0,
        similarity: 0.91, distance: 0.09,
        why_match: ["same crime group (Drug Offences)", "same district (Bengaluru City)"],
        source_links: ["CaseMaster:42"],
      }],
    });
  });

  it("renders the demo-context scope toggle and per-hit why-match chips", async () => {
    wrap(<SimilarPage caseId={1} />);
    // the matched case renders once the query resolves (Widget shows content)
    expect(await screen.findByText("SYN-CR-42")).toBeInTheDocument();
    // demo case/unit context filter
    expect(screen.getByRole("button", { name: /This district/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /All districts/i })).toBeInTheDocument();
    // per-hit why-match explanation (shared context/MO, never outcome)
    expect(screen.getByText(/same crime group \(Drug Offences\)/i)).toBeInTheDocument();
  });
});
