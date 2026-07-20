import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const ask = vi.fn();
const brief = vi.fn();
vi.mock("@/api", () => ({ api: { investigate: { ask: (...a: unknown[]) => ask(...a), brief: (...a: unknown[]) => brief(...a) } } }));
// Stub SendToBoard so the test doesn't need RoleProvider / Router internals.
vi.mock("@/components/board/SendToBoard", () => ({
  SendToBoard: ({ label }: { label?: string }) => <button data-testid="send-to-board">{label}</button>,
}));

import { AssistantPage } from "@/routes/cases/subpages/AssistantPage";
import { TooltipProvider } from "@/components/ui/tooltip";

function wrap(node: ReactNode) {
  const qc = new QueryClient({
    queryCache: new QueryCache({ onError: () => {} }),
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>{node}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const ANSWER = {
  case_id: 1, crime_no: "SYN-1", question: "Have similar cases happened before?",
  language: "en", intent: "similar_cases",
  answer: "2 similar case(s) found by shared modus-operandi (leads, not identity matches).",
  confidence: 0.81,
  facts: [
    { type: "case_overview", label: "SYN-1", detail: "Theft — Under Investigation", source_ids: ["CaseMaster:1"], basis: "evidence" },
    { type: "reviewed_identity_link", label: "X also in SYN-9", detail: "shared REVIEWED canonical person across cases", source_ids: ["CanonicalPerson:5", "CaseMaster:9"], basis: "evidence" },
  ],
  hypotheses: [
    { type: "lead:expand_network", label: "Expand the network", detail: "name matches a gang member — sameness never from embedding alone", source_ids: ["CaseMaster:1"], basis: "hypothesis", confidence: 0.78 },
  ],
  citable_objects: [
    { ref_table: "CaseMaster", ref_id: "1", label: "SYN-1", kind: "case" },
    { ref_table: "CanonicalPerson", ref_id: "5", label: "X", kind: "entity" },
  ],
  citations: ["CaseMaster:1", "CanonicalPerson:5", "CaseMaster:9"],
  reasoning_summary: "Composed from existing case APIs; facts separated from hypotheses.",
  limitations: ["Similar cases are leads by shared context/MO, not proof of a shared offender."],
  planner_source: "case-orchestrator",
};

describe("AssistantPage (Prompt 20 Part D)", () => {
  beforeEach(() => { ask.mockReset(); brief.mockReset(); });

  it("separates facts from hypotheses, shows citations and send-to-board", async () => {
    ask.mockResolvedValue(ANSWER);
    wrap(<AssistantPage caseId={1} />);
    // click the flagship quick question
    fireEvent.click(screen.getByText("Similar cases?"));
    expect(await screen.findByText(/2 similar case\(s\) found/)).toBeInTheDocument();
    // facts + hypotheses sections both render with their items
    expect(screen.getByText(/Facts & evidence/)).toBeInTheDocument();
    expect(screen.getByText(/Hypotheses & suggestions/)).toBeInTheDocument();
    expect(screen.getByText("X also in SYN-9")).toBeInTheDocument();       // fact
    expect(screen.getByText("Expand the network")).toBeInTheDocument();    // hypothesis
    // intent + citations surfaced
    expect(screen.getByText("similar cases")).toBeInTheDocument();
    expect(screen.getByText("3 citations")).toBeInTheDocument();
    // cited objects can be sent to a board
    expect(screen.getAllByTestId("send-to-board").length).toBeGreaterThanOrEqual(2);
    expect(ask).toHaveBeenCalledWith(1, "Have similar cases happened before?");
  });

  it("asks a typed bilingual question", async () => {
    ask.mockResolvedValue({ ...ANSWER, language: "kn", question: "ಹಿಂದೆ?" });
    wrap(<AssistantPage caseId={1} />);
    const input = screen.getByLabelText("case question");
    fireEvent.change(input, { target: { value: "ಇದೇ ರೀತಿಯ ಪ್ರಕರಣಗಳು ಹಿಂದೆ?" } });
    fireEvent.click(screen.getByText("Ask"));
    expect(await screen.findByText("ಕನ್ನಡ")).toBeInTheDocument();
    expect(ask).toHaveBeenCalledWith(1, "ಇದೇ ರೀತಿಯ ಪ್ರಕರಣಗಳು ಹಿಂದೆ?");
  });
});
