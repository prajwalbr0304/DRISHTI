import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const candidates = vi.fn();
const stats = vi.fn();
vi.mock("@/api", () => ({
  api: {
    identity: {
      candidates: (...a: unknown[]) => candidates(...a),
      stats: (...a: unknown[]) => stats(...a),
      generate: vi.fn(),
      reviewCandidate: vi.fn(),
      searchPersons: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 }),
      createPerson: vi.fn(),
    },
  },
}));

import { EntityResolution } from "@/routes/review/entities/EntityResolution";
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

describe("EntityResolution", () => {
  beforeEach(() => {
    candidates.mockReset();
    stats.mockReset();
    stats.mockResolvedValue({
      canonical_person: 210883, canonical_person_merged: 10, case_party_role: 374272,
      graph_person_nodes: 205610, graph_person_linked: 205610,
      network_edges: 2411, network_edges_provenanced: 2411,
      resolution_candidates_pending: 1, merge_history: 13,
    });
  });

  it("renders pending candidates side-by-side for review", async () => {
    candidates.mockResolvedValue({
      items: [{
        entity_resolution_candidate_id: 1,
        person_a: { canonical_person_id: 101, public_ref: "SYN-PERSON-A", display_label: "Ravi Kumar", case_count: 2, alias_count: 0 },
        person_b: { canonical_person_id: 202, public_ref: "SYN-PERSON-B", display_label: "Ravi Kumar", case_count: 1, alias_count: 0 },
        method: "deterministic", score: 0.95,
        match_features: { feature: "display_label_similarity" },
        status: "pending", reviewed_by_actor: null, reviewed_at: null, created_at: null,
      }],
      total: 1, page: 1, page_size: 50,
    });
    wrap(<EntityResolution />);
    expect(screen.getByText("Entity resolution")).toBeInTheDocument();
    expect(await screen.findByText("SYN-PERSON-A")).toBeInTheDocument();
    expect(screen.getByText("SYN-PERSON-B")).toBeInTheDocument();
    // the merge affordance is present (label mentions merge into A)
    expect(screen.getByRole("button", { name: /merge into A/i })).toBeInTheDocument();
  });
});
