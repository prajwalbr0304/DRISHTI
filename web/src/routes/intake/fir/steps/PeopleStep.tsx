import { useState } from "react";
import { Trash2, UserPlus } from "lucide-react";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, SectionCard } from "@/routes/intake/components";
import { errorMessage } from "@/api/contracts";
import type { StepProps } from "@/routes/intake/fir/stepTypes";
import type { IntakePartyInput } from "@/api/types";

const GENDERS = [
  { value: "1", label: "Male" }, { value: "2", label: "Female" },
  { value: "3", label: "Trans / other" },
];
const NATURES = [
  { value: "person", label: "Person" }, { value: "organisation", label: "Organisation" },
  { value: "unknown", label: "Unknown / unidentified" },
];

const blank: IntakePartyInput = {
  role_type: "complainant", party_nature: "person", is_unknown: false,
  display_name: "", attributes: {},
};

/** Step 5 — people & organisations. Every party becomes a canonical identity +
    CasePartyRole on approval (no name-based joins). */
export function PeopleStep({ editor, workflow }: StepProps) {
  const { caseKind, parties, addParty, removeParty, isEditable } = editor;
  const [form, setForm] = useState<IntakePartyInput>({ ...blank });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const roles = workflow?.kinds.find((k) => k.kind === caseKind)?.allowed_party_roles ?? [];
  const roleOpts = roles.map((r) => ({ value: r, label: r.replace(/_/g, " ") }));

  const setAttr = (patch: Record<string, unknown>) =>
    setForm((f) => ({ ...f, attributes: { ...f.attributes, ...patch } }));

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const isUnknown = form.party_nature === "unknown";
      await addParty({
        ...form,
        is_unknown: isUnknown,
        display_name: isUnknown ? null : (form.display_name || null),
      });
      setForm({ ...blank, role_type: form.role_type });
    } catch (e) {
      setErr(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <SectionCard title="Case parties" description="Complainant, victim, accused/suspect, witness, informant, guardian or organisation.">
        {parties.length === 0 ? (
          <p className="text-12 text-content-dim">No parties added yet. At least one complainant or informant is required.</p>
        ) : (
          <ul className="divide-y divide-hairline">
            {parties.map((p) => (
              <li key={p.intake_draft_party_id} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <span className="text-13 font-medium text-content">
                    {p.is_unknown ? "Unknown / unidentified" : p.display_name || "—"}
                  </span>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-12 text-content-dim">
                    <Badge variant="primary" className="capitalize">{p.role_type.replace(/_/g, " ")}</Badge>
                    <span className="capitalize">{p.party_nature}</span>
                    {typeof p.attributes?.age === "number" && <span>Age {String(p.attributes.age)}</span>}
                  </div>
                </div>
                {isEditable && (
                  <Button type="button" variant="ghost" size="icon-sm"
                    onClick={() => removeParty(p.intake_draft_party_id)} aria-label="Remove party">
                    <Trash2 />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {isEditable && (
        <SectionCard title="Add a party">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Role" required>
              <NativeSelect value={form.role_type} onChange={(v) => setForm((f) => ({ ...f, role_type: v }))}
                options={roleOpts} placeholder="Select role" aria-label="Party role" />
            </Field>
            <Field label="Nature">
              <NativeSelect value={form.party_nature}
                onChange={(v) => setForm((f) => ({ ...f, party_nature: v }))}
                options={NATURES} placeholder="Person" aria-label="Party nature" />
            </Field>
            {form.party_nature !== "unknown" && (
              <>
                <Field label={form.party_nature === "organisation" ? "Organisation name" : "Full name"} required>
                  <Input value={form.display_name ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
                    placeholder={form.party_nature === "organisation" ? "e.g. XYZ Traders" : "Name"} className="h-8" />
                </Field>
                {form.party_nature === "person" && (
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="Age">
                      <Input type="number" min={0} value={(form.attributes.age as number) ?? ""}
                        onChange={(e) => setAttr({ age: e.target.value ? Number(e.target.value) : undefined })}
                        className="h-8" />
                    </Field>
                    <Field label="Gender">
                      <NativeSelect value={String(form.attributes.gender_id ?? "")}
                        onChange={(v) => setAttr({ gender_id: v ? Number(v) : undefined })}
                        options={GENDERS} placeholder="—" aria-label="Gender" />
                    </Field>
                  </div>
                )}
              </>
            )}
          </div>
          {err && <p className="mt-2 text-12 text-severity-high">{err}</p>}
          <div className="mt-3">
            <Button type="button" size="sm" onClick={submit} disabled={busy}>
              <UserPlus /> Add party
            </Button>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
