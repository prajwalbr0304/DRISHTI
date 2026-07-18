import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const status = vi.fn();
const list = vi.fn();
const lookups = vi.fn();
vi.mock("@/api", () => ({
  api: {
    evidence: {
      status: (...a: unknown[]) => status(...a),
      list: (...a: unknown[]) => list(...a),
      lookups: (...a: unknown[]) => lookups(...a),
      get: vi.fn(),
    },
  },
}));

import { EvidencePage } from "@/routes/cases/subpages/EvidencePage";
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

describe("EvidencePage (Phase 5)", () => {
  beforeEach(() => {
    status.mockReset();
    list.mockReset();
    lookups.mockReset();
    status.mockResolvedValue({
      hackathon_mode: true, demo_data_only: true, synthetic_db: true,
      writes_localhost_only: true, s3_configured: true, upload_enabled: true,
      max_bytes: 52428800, allowed_extensions: ["pdf", "jpg"], allowed_mime_types: [],
      presign_expiry_seconds: 900, extraction_disabled_note: "File contents are not automatically extracted.",
      environment_label: "Synthetic Hackathon Demo",
    });
    lookups.mockResolvedValue({
      evidence_types: [], categories: [], confidentialities: [], languages: [],
      link_types: [], source_systems: [],
    });
  });

  it("shows the no-extraction note and renders evidence rows", async () => {
    list.mockResolvedValue({
      items: [{
        evidence_item_id: 7, case_master_id: 11, evidence_type: "image",
        category: "scene_photo", title: "Scene photo near gate", synthetic_reference: "SYN-EV-7",
        source_label: "FIR_FORM", state: "available", language: "en", tags: ["synthetic"],
        version_no: 1, sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        file_name: "photo.jpg", mime_type: "image/jpeg", size_bytes: 1024,
        captured_at: null, created_at: null, updated_at: null,
      }],
      total: 1, page: 1, page_size: 200, by_state: { available: 1 },
    });
    wrap(<EvidencePage caseId={11} />);
    expect(screen.getByText(/File contents are not automatically extracted/i)).toBeInTheDocument();
    expect(await screen.findByText("Scene photo near gate")).toBeInTheDocument();
    expect(screen.getByText(/Evidence \(1\)/)).toBeInTheDocument();
  });

  it("shows an empty state when there is no evidence", async () => {
    list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 200, by_state: {} });
    wrap(<EvidencePage caseId={99} />);
    expect(await screen.findByText(/No evidence recorded/i)).toBeInTheDocument();
  });
});
