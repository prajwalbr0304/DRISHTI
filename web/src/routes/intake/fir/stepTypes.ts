import type { IntakeLookupsResponse, IntakeWorkflowMetaResponse } from "@/api/types";
import type { useDraftEditor } from "@/routes/intake/useDraftEditor";

export type Editor = ReturnType<typeof useDraftEditor>;

export interface StepProps {
  editor: Editor;
  lookups?: IntakeLookupsResponse;
  workflow?: IntakeWorkflowMetaResponse;
  /** Inline error message for a payload field path (e.g. "registration.station_id"). */
  errorFor: (field: string) => string | undefined;
}

/** number|"" helpers for controlled inputs backed by nullable numeric fields. */
export function numOrUndef(v: string): number | undefined {
  const n = Number(v);
  return v === "" || Number.isNaN(n) ? undefined : n;
}
