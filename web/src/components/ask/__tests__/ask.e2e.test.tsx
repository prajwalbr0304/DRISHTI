import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState, type ReactNode } from "react";

/* ============================================================================
   Deterministic-provider end-to-end for Ask DRISHTI (Prompt 19 §G.4).

   Drives the REAL pipeline — Composer -> useAskStore.send() -> provider ->
   answerFromResponse -> AnswerCard -> AnswerVisualization — against a DETERMINISTIC
   local provider (the API is mocked to return a fixed grounded answer with a typed
   visualization). No network, no WebGL. A full headless-browser (Playwright) E2E
   against the LIVE Catalyst QuickML provider is the retained Prompt 23 step.
   ========================================================================== */

const ask = vi.fn();
vi.mock("@/api", () => ({
  api: { chat: { ask: (...a: unknown[]) => ask(...a) }, geo: { boundaries: vi.fn() } },
}));
// Web Speech is unavailable in jsdom; keep the mic feature-detected off.
vi.mock("@/components/ask/useSpeech", () => ({
  useSpeech: () => ({ supported: false, listening: false, confidence: null, start() {}, stop() {}, toggle() {} }),
  speechLocale: (l: string) => (l === "kn" ? "kn-IN" : "en-IN"),
}));

import { Composer } from "@/components/ask/Composer";
import { AnswerCard } from "@/components/ask/AnswerCard";
import { useAskStore } from "@/stores/useAskStore";
import { RoleProvider } from "@/providers/RoleProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { AskResponse } from "@/api/types";

const GROUNDED = {
  result: {
    answer: "There are 42 cyber-crime FIRs.",
    confidence: 0.82,
    source_record_ids: ["CaseMaster:12"],
    reasoning_summary: "grounded",
    model_version: "drishti-nlsql@1.0.0",
  },
  session_id: 1,
  reply: "There are 42 cyber-crime FIRs.",
  language: "en",
  sql: 'SELECT COUNT(*) AS case_count FROM "CaseMaster"',
  cited_record_ids: ["CaseMaster:12", "CaseMaster:13"],
  confidence: 0.82,
  needs_clarification: false,
  blocked: false,
  model_version: "drishti-nlsql@1.0.0",
  row_count: 1,
  columns: ["case_count"],
  rows_preview: [[42]],
  planner_source: "catalyst-quickml-llm",
  planner_primary: "catalyst-quickml-llm",
  planner_degraded: false,
  visualization: {
    kind: "number",
    title: "Total FIRs",
    dimensions: [],
    measures: [{ field: "case_count", label: "FIRs", index: 0, unit: "cases" }],
    time_field: null,
    geo_field: null,
    source_ids: ["CaseMaster(aggregated)"],
    as_of: "2026-07-21T00:00:00Z",
    dataset: "synthetic",
    suppressed: 0,
    confidence: 0.82,
    scope_role: "analyst",
    row_total: 1,
    language: "en",
    accessible_table: { columns: ["case_count"], row_ref: "rows_preview" },
  },
} as unknown as AskResponse;

/** Minimal, router-free harness that wires the real store to the real Composer
 *  and AnswerCard — the same data flow as ChatView, without PDF/router deps. */
function AskHarness() {
  const messages = useAskStore((s) => s.messages);
  const send = useAskStore((s) => s.send);
  const language = useAskStore((s) => s.language);
  const languageMode = useAskStore((s) => s.languageMode);
  const setLanguageMode = useAskStore((s) => s.setLanguageMode);
  const [input, setInput] = useState("");
  return (
    <div>
      {messages
        .filter((m) => m.sender === "assistant")
        .map((m) => (
          <AnswerCard key={m.id} message={m} />
        ))}
      <Composer
        value={input}
        onChange={setInput}
        onSend={() => {
          void send(input);
          setInput("");
        }}
        language={language}
        languageMode={languageMode}
        onLanguageModeChange={setLanguageMode}
      />
    </div>
  );
}

function renderApp(): void {
  const ui: ReactNode = (
    <TooltipProvider>
      <RoleProvider>
        <AskHarness />
      </RoleProvider>
    </TooltipProvider>
  );
  render(ui);
}

describe("Ask DRISHTI deterministic-provider E2E (Prompt 19 §G.4)", () => {
  beforeEach(() => {
    ask.mockReset();
    ask.mockResolvedValue(GROUNDED);
    useAskStore.getState().reset();
  });

  it("asks a question and renders a grounded, cited answer with a typed visualization", async () => {
    renderApp();

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "how many cyber crime FIRs in Bengaluru City" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^send$/i }));

    // the deterministic provider was called with the question
    await waitFor(() => expect(ask).toHaveBeenCalledTimes(1));
    expect(ask).toHaveBeenCalledWith(
      expect.objectContaining({ question: "how many cyber crime FIRs in Bengaluru City" }),
    );

    // grounded reply
    expect(await screen.findByText(/42 cyber-crime FIRs/i)).toBeInTheDocument();
    // typed visualization (number) + unit ("42" also appears in the data table)
    expect(screen.getAllByText("42").length).toBeGreaterThan(0);
    expect(screen.getByText("cases")).toBeInTheDocument();
    // read-only SQL proof
    expect(screen.getByText(/SQL executed/i)).toBeInTheDocument();
    // confidence surfaced (chip + viz footer)
    expect(screen.getAllByText(/82%/).length).toBeGreaterThan(0);
    // citations surfaced (sources row + viz footer)
    expect(screen.getAllByText(/sources:/i).length).toBeGreaterThan(0);
    // accessible data table is always present (behind the details toggle here)
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("labels a degraded (fallback) answer so the primary/fallback split is visible", async () => {
    ask.mockResolvedValue({
      ...GROUNDED,
      planner_source: "deterministic-fallback",
      planner_primary: "catalyst-quickml-llm",
      planner_degraded: true,
    } as unknown as AskResponse);
    renderApp();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "how many thefts in Mysuru" } });
    fireEvent.click(screen.getByRole("button", { name: /^send$/i }));

    expect(await screen.findByText(/offline fallback/i)).toBeInTheDocument();
  });
});
