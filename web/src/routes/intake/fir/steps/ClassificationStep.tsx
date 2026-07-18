import { useState } from "react";
import { Plus, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, SectionCard } from "@/routes/intake/components";
import { toOptions, subHeadOptions } from "@/routes/intake/intakeQueries";
import type { StepProps } from "@/routes/intake/fir/stepTypes";
import type { IntakeActSection } from "@/api/types";

/** Step 4 — classification: crime head/sub-head, gravity, acts/sections, and
    category-specific fields rendered from the case kind. */
export function ClassificationStep({ editor, lookups, errorFor }: StepProps) {
  const { payload, caseKind, update, isEditable } = editor;
  const cls = payload.classification;
  const [act, setAct] = useState("");
  const [section, setSection] = useState("");

  const sectionOpts = (lookups?.sections ?? [])
    .filter((s) => !act || s.act_code === act)
    .map((s) => ({ value: s.section_code, label: `${s.section_code} — ${s.description ?? ""}` }));

  const addSection = () => {
    if (!act || !section) return;
    const exists = cls.acts_sections.some((a) => a.act_code === act && a.section_code === section);
    if (!exists) update("classification", { acts_sections: [...cls.acts_sections, { act_code: act, section_code: section }] });
    setSection("");
  };
  const removeSection = (idx: number) =>
    update("classification", { acts_sections: cls.acts_sections.filter((_, i) => i !== idx) });

  const setCat = (patch: Record<string, unknown>) =>
    update("classification", { category_specific: { ...cls.category_specific, ...patch } });

  return (
    <div className="space-y-4">
      <SectionCard title="Crime classification">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Major crime head" required error={errorFor("classification.major_head_id")}>
            <NativeSelect value={String(cls.major_head_id ?? "")}
              onChange={(v) => update("classification", { major_head_id: v ? Number(v) : null, minor_head_id: null })}
              options={toOptions(lookups?.crime_heads)} placeholder="Select head" aria-label="Major crime head" />
          </Field>
          <Field label="Crime sub-head" error={errorFor("classification.minor_head_id")}>
            <NativeSelect value={String(cls.minor_head_id ?? "")}
              onChange={(v) => update("classification", { minor_head_id: v ? Number(v) : null })}
              options={subHeadOptions(lookups?.crime_subheads, cls.major_head_id)}
              placeholder="Select sub-head" aria-label="Crime sub-head" />
          </Field>
          <Field label="Gravity">
            <NativeSelect value={String(cls.gravity_id ?? "")}
              onChange={(v) => update("classification", { gravity_id: v ? Number(v) : null })}
              options={toOptions(lookups?.gravities)} placeholder="Select gravity" aria-label="Gravity" />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title="Acts & sections" description="Legal provisions applied to this case.">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[8rem]">
            <NativeSelect value={act} onChange={(v) => { setAct(v); setSection(""); }}
              options={(lookups?.acts ?? []).map((a) => ({ value: a.act_code, label: a.short_name ?? a.act_code }))}
              placeholder="Act" aria-label="Act" />
          </div>
          <div className="min-w-[14rem] flex-1">
            <NativeSelect value={section} onChange={setSection} options={sectionOpts}
              placeholder="Section" aria-label="Section" />
          </div>
          <Button type="button" size="sm" variant="outline" onClick={addSection} disabled={!isEditable || !act || !section}>
            <Plus /> Add
          </Button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {cls.acts_sections.length === 0 && <span className="text-12 text-content-dim">No sections added yet.</span>}
          {cls.acts_sections.map((a: IntakeActSection, i) => (
            <Badge key={`${a.act_code}-${a.section_code}-${i}`} variant="neutral" className="gap-1">
              {a.section_code}
              {isEditable && (
                <button type="button" onClick={() => removeSection(i)} aria-label={`Remove ${a.section_code}`}>
                  <X className="size-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
      </SectionCard>

      {caseKind === "missing_person" && (
        <SectionCard title="Missing person details">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Last seen at">
              <Input type="datetime-local" disabled={!isEditable}
                value={(cls.category_specific.last_seen_at as string) ?? ""}
                onChange={(e) => setCat({ last_seen_at: e.target.value || null })} className="h-8" />
            </Field>
            <Field label="Last seen location">
              <Input disabled={!isEditable}
                value={(cls.category_specific.last_seen_location as string) ?? ""}
                onChange={(e) => setCat({ last_seen_location: e.target.value || null })}
                placeholder="Where last seen" className="h-8" />
            </Field>
          </div>
        </SectionCard>
      )}

      {caseKind === "udr" && (
        <SectionCard title="Unnatural death details">
          <Field label="Apparent cause">
            <Input disabled={!isEditable}
              value={(cls.category_specific.apparent_cause as string) ?? ""}
              onChange={(e) => setCat({ apparent_cause: e.target.value || null })}
              placeholder="e.g. drowning, unknown" className="h-8" />
          </Field>
        </SectionCard>
      )}
    </div>
  );
}
