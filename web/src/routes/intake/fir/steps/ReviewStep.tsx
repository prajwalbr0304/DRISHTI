import { AlertTriangle, CheckCircle2, Copy, Loader2, Lock, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { IssueList, SectionCard } from "@/routes/intake/components";
import type { Editor } from "@/routes/intake/fir/stepTypes";

/** Step 7 — review & submit. Blocking errors and review warnings are shown
    distinctly; submit stays gated until Prompt 3 verifies hackathon mode. */
export function ReviewStep({
  editor, submitEnabled, submitReason, submitting, onSubmit,
}: {
  editor: Editor;
  submitEnabled: boolean;
  submitReason?: string | null;
  submitting: boolean;
  onSubmit: () => void;
}) {
  const { validation, validating, validate, isEditable, payload } = editor;
  const v = validation;
  const canSubmit = !!v?.can_submit && submitEnabled && isEditable;

  return (
    <div className="space-y-4">
      <SectionCard title="Validation" description="Run validation to see blocking errors and review warnings.">
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => void validate()} disabled={validating}>
            {validating ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Re-validate
          </Button>
          {v && (
            <Badge variant={v.ok ? "low" : "high"}>
              {v.ok ? <CheckCircle2 className="size-3" /> : <AlertTriangle className="size-3" />}
              {v.ok ? "No blocking errors" : `${v.errors.length} blocking`}
            </Badge>
          )}
          {v && v.warnings.length > 0 && <Badge variant="medium">{v.warnings.length} warnings</Badge>}
        </div>
        {v && (
          <div className="mt-3 space-y-2">
            <IssueList issues={v.errors} kind="error" />
            <IssueList issues={v.warnings} kind="warning" />
            {v.ok && v.warnings.length === 0 && (
              <p className="text-12 text-content-dim">Everything looks complete.</p>
            )}
          </div>
        )}
      </SectionCard>

      {v && v.duplicate_candidates.length > 0 && (
        <SectionCard title="Possible duplicates" description="Review these before submitting.">
          <ul className="space-y-1.5">
            {v.duplicate_candidates.map((c, i) => (
              <li key={`${c.kind}-${c.id}-${i}`} className="flex items-center gap-2 text-13">
                <Copy className="size-3.5 text-severity-medium" />
                <span className="capitalize text-content">{c.kind}</span>
                {c.crime_no && <span className="tnum text-content-dim">{c.crime_no}</span>}
                <span className="text-content-dim">{c.reason}</span>
                <Badge variant={c.match_score >= 0.9 ? "high" : "medium"} className="ml-auto tnum">
                  {(c.match_score * 100).toFixed(0)}%
                </Badge>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      <SectionCard title="Provenance" description="Where this record originated (shown on review).">
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-12 text-content-dim">
          <span>Source: <span className="text-content">{payload.source.source_system_code ?? "FIR_FORM"}</span></span>
          <span>Method: <span className="text-content">{payload.source.source_method ?? "—"}</span></span>
          <span>External id: <span className="text-content">{payload.source.external_source_id ?? "—"}</span></span>
        </div>
      </SectionCard>

      <div className="rounded-card border border-hairline bg-surface p-4">
        {!submitEnabled && (
          <div className="mb-3 flex items-start gap-2 rounded-control bg-surface-2 p-3 text-12 text-content-dim">
            <Lock className="mt-0.5 size-4 shrink-0 text-severity-medium" />
            <span>{submitReason ?? "Submit is disabled during hackathon staging."}</span>
          </div>
        )}
        <div className="flex items-center justify-between gap-2">
          <span className="text-12 text-content-dim">
            Submitting routes this draft to a supervisor for review and approval.
          </span>
          <Button type="button" onClick={onSubmit} disabled={!canSubmit || submitting}>
            {submitting ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Submit for review
          </Button>
        </div>
      </div>
    </div>
  );
}
