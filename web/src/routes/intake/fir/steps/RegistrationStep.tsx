import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Field, SectionCard } from "@/routes/intake/components";
import { toOptions } from "@/routes/intake/intakeQueries";
import type { StepProps } from "@/routes/intake/fir/stepTypes";

const SENSITIVITY = [
  { value: "demo_normal", label: "Normal" },
  { value: "restricted", label: "Restricted" },
];

/** Step 2 — registration: station drives district + the officer list. */
export function RegistrationStep({ editor, lookups, errorFor }: StepProps) {
  const { payload, update, isEditable } = editor;
  const reg = payload.registration;
  const districtName = lookups?.districts.find((d) => d.id === reg.district_id)?.name;

  const onStation = (v: string) => {
    const stationId = v ? Number(v) : null;
    const unit = lookups?.units.find((u) => u.id === stationId);
    update("registration", { station_id: stationId, district_id: unit?.parent_id ?? reg.district_id });
  };

  return (
    <div className="space-y-4">
      <SectionCard title="Registration" description="Where and by whom the case is being registered.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Registration date" required error={errorFor("registration.registration_date")}>
            <Input type="date" value={reg.registration_date ?? ""} disabled={!isEditable}
              onChange={(e) => update("registration", { registration_date: e.target.value || null })}
              className="h-8" />
          </Field>
          <Field label="Registration time">
            <Input type="time" value={reg.registration_time ?? ""} disabled={!isEditable}
              onChange={(e) => update("registration", { registration_time: e.target.value || null })}
              className="h-8" />
          </Field>
          <Field label="Police station" required error={errorFor("registration.station_id")}>
            <NativeSelect value={String(reg.station_id ?? "")} onChange={onStation}
              options={toOptions(lookups?.units)} placeholder="Select station" aria-label="Police station" />
          </Field>
          <Field label="District" hint="Derived from the selected station.">
            <Input value={districtName ?? ""} readOnly className="h-8 bg-surface" />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title="Officers & handling" description="Registering officer and the assigned investigating officer.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Registering officer" required error={errorFor("registration.registering_officer_id")}
            hint={reg.station_id ? undefined : "Select a station first to list its officers."}>
            <NativeSelect value={String(reg.registering_officer_id ?? "")}
              onChange={(v) => update("registration", { registering_officer_id: v ? Number(v) : null })}
              options={toOptions(lookups?.officers)} placeholder="Select officer" aria-label="Registering officer" />
          </Field>
          <Field label="Assigned IO" error={errorFor("registration.assigned_io_id")}>
            <NativeSelect value={String(reg.assigned_io_id ?? "")}
              onChange={(v) => update("registration", { assigned_io_id: v ? Number(v) : null })}
              options={toOptions(lookups?.officers)} placeholder="Select IO (optional)" aria-label="Assigned IO" />
          </Field>
          <Field label="Sensitivity">
            <NativeSelect value={reg.sensitivity ?? ""}
              onChange={(v) => update("registration", { sensitivity: v || null })}
              options={SENSITIVITY} placeholder="Normal" aria-label="Sensitivity" />
          </Field>
          <Field label="Classification note">
            <Input value={reg.classification ?? ""} disabled={!isEditable}
              onChange={(e) => update("registration", { classification: e.target.value || null })}
              placeholder="Optional handling classification" className="h-8" />
          </Field>
        </div>
      </SectionCard>
    </div>
  );
}
