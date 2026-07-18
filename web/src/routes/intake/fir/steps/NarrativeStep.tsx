import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Field, SectionCard } from "@/routes/intake/components";
import type { StepProps } from "@/routes/intake/fir/stepTypes";

const LANGS = [{ value: "en", label: "English" }, { value: "kn", label: "Kannada" }];
const ta =
  "w-full rounded-control border border-hairline bg-surface-2 px-3 py-2 text-13 text-content placeholder:text-content-dim focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60";

/** Step 6 — narrative: brief facts, language, notes, restricted flag. */
export function NarrativeStep({ editor, errorFor }: StepProps) {
  const { payload, update, isEditable } = editor;
  const nar = payload.narrative;

  return (
    <div className="space-y-4">
      <SectionCard title="Brief facts" description="The factual summary recorded in the FIR/case.">
        <Field label="Brief facts" required error={errorFor("narrative.brief_facts")}>
          <textarea value={nar.brief_facts ?? ""} disabled={!isEditable} rows={6}
            onChange={(e) => update("narrative", { brief_facts: e.target.value || null })}
            placeholder="Describe the reported facts of the case…" className={ta} />
        </Field>
        <div className="mt-3 max-w-[12rem]">
          <Field label="Language">
            <NativeSelect value={nar.language ?? "en"}
              onChange={(v) => update("narrative", { language: v })}
              options={LANGS} placeholder="English" aria-label="Language" />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title="Notes" description="Source and reviewer notes are kept for provenance.">
        <div className="space-y-3">
          <Field label="Source notes">
            <textarea value={nar.source_notes ?? ""} disabled={!isEditable} rows={2}
              onChange={(e) => update("narrative", { source_notes: e.target.value || null })}
              placeholder="Notes about the source of information…" className={ta} />
          </Field>
          <Field label="Reviewer notes">
            <textarea value={nar.reviewer_notes ?? ""} disabled={!isEditable} rows={2}
              onChange={(e) => update("narrative", { reviewer_notes: e.target.value || null })}
              placeholder="Notes for the reviewing supervisor…" className={ta} />
          </Field>
          <label className="flex items-center gap-2 text-13 text-content">
            <input type="checkbox" checked={nar.restricted} disabled={!isEditable}
              onChange={(e) => update("narrative", { restricted: e.target.checked })}
              className="size-4 rounded border-hairline" />
            Mark narrative as restricted (sensitive case)
          </label>
        </div>
      </SectionCard>
    </div>
  );
}
