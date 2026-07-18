import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Field, SectionCard } from "@/routes/intake/components";
import { toOptions } from "@/routes/intake/intakeQueries";
import type { StepProps } from "@/routes/intake/fir/stepTypes";

const SOURCE_METHODS = [
  { value: "walk_in", label: "Walk-in complaint" },
  { value: "phone", label: "Phone / control room" },
  { value: "online", label: "Online / e-FIR" },
  { value: "transfer", label: "Transfer from another unit" },
  { value: "suo_moto", label: "Suo-moto (police initiated)" },
];

/** Step 1 — source & category. The case kind drives category + valid lifecycle. */
export function SourceCategoryStep({ editor, lookups, workflow }: StepProps) {
  const { payload, caseKind, setCaseKind, update, isEditable } = editor;
  const kindMeta = workflow?.kinds.find((k) => k.kind === caseKind);
  const kindOptions = (workflow?.kinds ?? []).map((k) => ({ value: k.kind, label: k.label }));

  return (
    <div className="space-y-4">
      <SectionCard title="Case type" description="Determines the category and the lifecycle the case may follow.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Case kind" required>
            <NativeSelect value={caseKind} onChange={setCaseKind} options={kindOptions}
              placeholder="Select a case kind" aria-label="Case kind" />
          </Field>
          <Field label="Resolved category" hint="Set automatically from the case kind.">
            <Input value={kindMeta?.category ?? ""} readOnly aria-label="Resolved category" className="h-8 bg-surface" />
          </Field>
        </div>
        {kindMeta && (
          <p className="mt-2 text-12 text-content-dim">{kindMeta.description}</p>
        )}
      </SectionCard>

      <SectionCard title="Source & method" description="How this information reached the police.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Source method">
            <NativeSelect value={payload.source.source_method ?? ""}
              onChange={(v) => update("source", { source_method: v || null })}
              options={SOURCE_METHODS} placeholder="Select method" aria-label="Source method" />
          </Field>
          <Field label="External source id" hint="Source-system reference (used for duplicate detection).">
            <Input value={payload.source.external_source_id ?? ""} disabled={!isEditable}
              onChange={(e) => update("source", { external_source_id: e.target.value || null })}
              placeholder="e.g. CCTNS-SYN-000123" className="h-8" />
          </Field>
        </div>
        {caseKind === "zero_fir" && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="Originating unit" hint="Where the Zero FIR was first registered.">
              <NativeSelect value={String(payload.source.originating_unit_id ?? "")}
                onChange={(v) => update("source", { originating_unit_id: v ? Number(v) : null })}
                options={toOptions(lookups?.units)} placeholder="Select unit" aria-label="Originating unit" />
            </Field>
            <Field label="Receiving unit" hint="Jurisdiction unit the case transfers to.">
              <NativeSelect value={String(payload.source.receiving_unit_id ?? "")}
                onChange={(v) => update("source", { receiving_unit_id: v ? Number(v) : null })}
                options={toOptions(lookups?.units)} placeholder="Select unit" aria-label="Receiving unit" />
            </Field>
          </div>
        )}
      </SectionCard>
    </div>
  );
}
