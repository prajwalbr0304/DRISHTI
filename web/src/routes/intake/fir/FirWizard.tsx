import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, ArrowRight, FileText } from "lucide-react";
import { api } from "@/api";
import { ApiError, errorMessage } from "@/api/contracts";
import { cn } from "@/lib/utils";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { SaveBadge, StatusPill } from "@/routes/intake/components";
import { useDraftEditor } from "@/routes/intake/useDraftEditor";
import { useIntakeLookups, useIntakeStatus, useIntakeWorkflow } from "@/routes/intake/intakeQueries";
import { SourceCategoryStep } from "@/routes/intake/fir/steps/SourceCategoryStep";
import { RegistrationStep } from "@/routes/intake/fir/steps/RegistrationStep";
import { IncidentStep } from "@/routes/intake/fir/steps/IncidentStep";
import { ClassificationStep } from "@/routes/intake/fir/steps/ClassificationStep";
import { PeopleStep } from "@/routes/intake/fir/steps/PeopleStep";
import { NarrativeStep } from "@/routes/intake/fir/steps/NarrativeStep";
import { ReviewStep } from "@/routes/intake/fir/steps/ReviewStep";
import { CaseCreatedPanel } from "@/routes/intake/fir/CaseCreatedPanel";
import { ScanProvenanceBanner } from "@/routes/intake/scan/ScanProvenanceBanner";

const STEPS = [
  { key: "source", label: "Source & category" },
  { key: "registration", label: "Registration" },
  { key: "incident", label: "Incident" },
  { key: "classification", label: "Classification" },
  { key: "people", label: "People" },
  { key: "narrative", label: "Narrative" },
  { key: "review", label: "Review & submit" },
] as const;

export function FirWizard() {
  const { draftKey = "" } = useParams<{ draftKey: string }>();
  const navigate = useNavigate();
  const { role } = useRole();
  const editor = useDraftEditor(draftKey, role);
  const statusQ = useIntakeStatus();
  const workflowQ = useIntakeWorkflow();
  const lookupsQ = useIntakeLookups(editor.payload.registration.station_id ?? undefined);

  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitErr, setSubmitErr] = useState<string | null>(null);

  const errorFor = useMemo(() => {
    const map = new Map((editor.validation?.errors ?? []).map((e) => [e.field, e.message]));
    return (field: string) => map.get(field);
  }, [editor.validation]);

  const submitEnabled = !!statusQ.data?.submit_enabled;

  const onSubmit = async () => {
    setSubmitting(true);
    setSubmitErr(null);
    try {
      const v = await editor.validate();
      if (!v.can_submit) { setStep(6); return; }
      await api.intake.submit(draftKey, role);
      await editor.refetch();
    } catch (e) {
      setSubmitErr(e instanceof ApiError && e.status === 409
        ? "Submit is disabled until Prompt 3 finalises hackathon mode."
        : errorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (editor.error) {
    const is404 = editor.error instanceof ApiError && editor.error.status === 404;
    return (
      <EmptyState icon={is404 ? FileText : AlertTriangle}
        title={is404 ? "Draft not found" : "Couldn't load draft"}
        description={errorMessage(editor.error)}
        action={<Button variant="outline" size="sm" onClick={() => navigate("/intake")}>Back to inbox</Button>} />
    );
  }

  const stepProps = { editor, lookups: lookupsQ.data, workflow: workflowQ.data, errorFor };
  const caseId = editor.draft?.case_master_id ?? null;

  return (
    <div>
      <PageHeader
        title={editor.loading ? <Skeleton className="h-6 w-48" /> : `New ${workflowQ.data?.kinds.find((k) => k.kind === editor.caseKind)?.label ?? "case"}`}
        description={editor.draft ? `Draft ${editor.draft.draft_key}` : "Structured FIR / case intake"}
        actions={
          <div className="flex items-center gap-3">
            <SaveBadge state={editor.saveState} />
            {editor.draft && <StatusPill status={editor.status} />}
          </div>
        }
      />

      {caseId && (
        <div className="mb-4">
          <CaseCreatedPanel caseId={caseId} crimeNo={editor.draft?.crime_no ?? null} />
        </div>
      )}

      {/* Renders only for drafts prefilled by reading a scanned form, so the
          approving supervisor can tell machine-read values from typed ones. */}
      <ScanProvenanceBanner draft={editor.draft} />

      <div className="flex gap-4">
        {/* step rail */}
        <aside className="hidden w-subnav shrink-0 md:block">
          <ol className="space-y-0.5">
            {STEPS.map((s, i) => (
              <li key={s.key}>
                <button type="button" onClick={() => setStep(i)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-control px-2.5 py-2 text-13 transition-colors",
                    i === step ? "bg-surface-2 font-medium text-content" : "text-content-dim hover:bg-surface-2/60",
                  )}>
                  <span className={cn("grid size-5 shrink-0 place-items-center rounded-full text-11",
                    i === step ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim")}>{i + 1}</span>
                  <span className="truncate">{s.label}</span>
                </button>
              </li>
            ))}
          </ol>
        </aside>

        <div className="min-w-0 flex-1">
          {editor.loading ? (
            <div className="space-y-3"><Skeleton className="h-40 w-full" /><Skeleton className="h-24 w-full" /></div>
          ) : (
            <>
              {step === 0 && <SourceCategoryStep {...stepProps} />}
              {step === 1 && <RegistrationStep {...stepProps} />}
              {step === 2 && <IncidentStep {...stepProps} />}
              {step === 3 && <ClassificationStep {...stepProps} />}
              {step === 4 && <PeopleStep {...stepProps} />}
              {step === 5 && <NarrativeStep {...stepProps} />}
              {step === 6 && (
                <ReviewStep editor={editor} submitEnabled={submitEnabled}
                  submitReason={statusQ.data?.submit_disabled_reason} submitting={submitting} onSubmit={onSubmit} />
              )}
              {submitErr && <p className="mt-3 text-12 text-severity-high">{submitErr}</p>}

              <div className="mt-4 flex items-center justify-between">
                <Button variant="outline" size="sm" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>
                  <ArrowLeft /> Back
                </Button>
                {step < STEPS.length - 1 ? (
                  <Button size="sm" onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}>
                    Next <ArrowRight />
                  </Button>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => void editor.validate()}>Validate</Button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
