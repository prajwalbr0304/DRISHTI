import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { IntakeWorkflowMetaResponse } from "@/api/types";
import { emptyPayload } from "@/routes/intake/useDraftEditor";
import type { Editor } from "@/routes/intake/fir/stepTypes";
import { NarrativeStep } from "@/routes/intake/fir/steps/NarrativeStep";
import { SourceCategoryStep } from "@/routes/intake/fir/steps/SourceCategoryStep";
import { ReviewStep } from "@/routes/intake/fir/steps/ReviewStep";

function makeEditor(over: Partial<Editor> = {}): Editor {
  return {
    loading: false, error: null, draft: undefined,
    payload: emptyPayload(), caseKind: "fir_standard", status: "draft", isEditable: true,
    saveState: "idle", validation: null, validating: false, parties: [], revisionNo: 0,
    update: vi.fn(), setCaseKind: vi.fn(), saveNow: vi.fn(), refetch: vi.fn(),
    addParty: vi.fn(), updateParty: vi.fn(), removeParty: vi.fn(),
    validate: vi.fn().mockResolvedValue({ ok: true, can_submit: true }),
    ...over,
  } as unknown as Editor;
}

const KINDS: IntakeWorkflowMetaResponse["kinds"] = [
  { kind: "fir_standard", category: "FIR", label: "Standard FIR", allow_accused: true, allow_arrest: true, allow_chargesheet: true, allow_court: true, initial_event: "registered", initial_status: "under_investigation", description: "", allowed_party_roles: ["complainant", "accused"] },
  { kind: "zero_fir", category: "Zero FIR", label: "Zero FIR", allow_accused: true, allow_arrest: true, allow_chargesheet: true, allow_court: true, initial_event: "zero_fir_registered", initial_status: "under_investigation", description: "", allowed_party_roles: ["complainant"] },
  { kind: "udr", category: "UDR", label: "UDR", allow_accused: false, allow_arrest: false, allow_chargesheet: false, allow_court: false, initial_event: "registered", initial_status: "under_investigation", description: "", allowed_party_roles: ["complainant"] },
  { kind: "missing_person", category: "FIR", label: "Missing Person", allow_accused: false, allow_arrest: false, allow_chargesheet: false, allow_court: false, initial_event: "missing_reported", initial_status: "missing_under_trace", description: "", allowed_party_roles: ["complainant", "victim"] },
];
const workflow = { kinds: KINDS, statuses: [], party_roles: [], transitions_by_category: {}, event_labels: {} } as IntakeWorkflowMetaResponse;
const noErr = () => undefined;

describe("NarrativeStep (form validation)", () => {
  it("shows an inline error for brief facts and edits update the draft", () => {
    const editor = makeEditor();
    const errorFor = (f: string) => (f === "narrative.brief_facts" ? "Brief facts of the case are required." : undefined);
    render(<NarrativeStep editor={editor} errorFor={errorFor} />);
    expect(screen.getByText("Brief facts of the case are required.")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Describe the reported facts/i), {
      target: { value: "A house was broken into overnight." },
    });
    expect(editor.update).toHaveBeenCalledWith("narrative", { brief_facts: "A house was broken into overnight." });
  });
});

describe("SourceCategoryStep (category is server-driven per kind)", () => {
  it.each([
    ["fir_standard", "FIR"],
    ["zero_fir", "Zero FIR"],
    ["udr", "UDR"],
    ["missing_person", "FIR"],
  ])("kind %s resolves to category %s", (kind, category) => {
    render(<SourceCategoryStep editor={makeEditor({ caseKind: kind })} workflow={workflow} errorFor={noErr} />);
    expect((screen.getByLabelText("Resolved category") as HTMLInputElement).value).toBe(category);
  });
});

describe("ReviewStep (blocking vs warning + submit gate)", () => {
  it("disables submit when there are blocking errors", () => {
    const editor = makeEditor({
      validation: { ok: false, can_submit: false, jurisdiction: { has_point: false }, duplicate_candidates: [],
        errors: [{ field: "narrative.brief_facts", code: "required", message: "Brief facts required", severity: "error" }],
        warnings: [{ field: "classification.gravity_id", code: "recommended", message: "Gravity not set", severity: "warning" }] } as never,
    });
    render(<ReviewStep editor={editor} submitEnabled submitting={false} onSubmit={vi.fn()} />);
    expect(screen.getByText(/1 blocking error/i)).toBeInTheDocument();
    expect(screen.getByText(/1 review warning/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Submit for review/i })).toBeDisabled();
  });

  it("enables submit only when valid AND submit is enabled", () => {
    const ok = { ok: true, can_submit: true, errors: [], warnings: [], jurisdiction: { has_point: false }, duplicate_candidates: [] };
    const enabled = makeEditor({ validation: ok as never });
    const { rerender } = render(<ReviewStep editor={enabled} submitEnabled submitting={false} onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Submit for review/i })).toBeEnabled();
    rerender(<ReviewStep editor={enabled} submitEnabled={false} submitReason="Gated until Prompt 3" submitting={false} onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Submit for review/i })).toBeDisabled();
    expect(screen.getByText(/Gated until Prompt 3/i)).toBeInTheDocument();
  });
});
