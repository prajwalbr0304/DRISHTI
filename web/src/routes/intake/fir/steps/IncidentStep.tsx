import { Input } from "@/components/ui/input";
import { Field, SectionCard } from "@/routes/intake/components";
import { LocationPicker } from "@/routes/intake/fir/LocationPicker";
import type { StepProps } from "@/routes/intake/fir/stepTypes";

/** Step 3 — incident: temporal window, location (map + jurisdiction), context. */
export function IncidentStep({ editor, errorFor }: StepProps) {
  const { payload, update, isEditable } = editor;
  const inc = payload.incident;

  return (
    <div className="space-y-4">
      <SectionCard title="When it happened" description="Occurrence window and when the information reached the station.">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Occurrence from">
            <Input type="datetime-local" value={inc.incident_from ?? ""} disabled={!isEditable}
              onChange={(e) => update("incident", { incident_from: e.target.value || null })} className="h-8" />
          </Field>
          <Field label="Occurrence to" error={errorFor("incident.incident_to")}>
            <Input type="datetime-local" value={inc.incident_to ?? ""} disabled={!isEditable}
              onChange={(e) => update("incident", { incident_to: e.target.value || null })} className="h-8" />
          </Field>
          <Field label="Information received">
            <Input type="datetime-local" value={inc.info_received_at ?? ""} disabled={!isEditable}
              onChange={(e) => update("incident", { info_received_at: e.target.value || null })} className="h-8" />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title="Where it happened" description="Pin the location; the district/jurisdiction is validated live.">
        <LocationPicker
          latitude={inc.latitude} longitude={inc.longitude}
          assignedDistrictId={payload.registration.district_id}
          disabled={!isEditable}
          onChange={(lat, lon) => update("incident", { latitude: lat, longitude: lon })}
          onUseDetectedDistrict={(districtId) => {
            // Reassign the registering district to the detected one and clear any
            // stale override reason (the mismatch is now resolved cleanly).
            update("registration", { district_id: districtId });
            if (inc.jurisdiction_override_reason) update("incident", { jurisdiction_override_reason: null });
          }}
          overrideReason={inc.jurisdiction_override_reason}
          onOverrideReasonChange={(reason) =>
            update("incident", { jurisdiction_override_reason: reason || null })}
        />
        {errorFor("incident.location") && (
          <p className="mt-2 text-12 text-severity-high">{errorFor("incident.location")}</p>
        )}

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field label="Address">
            <Input value={inc.address ?? ""} disabled={!isEditable}
              onChange={(e) => update("incident", { address: e.target.value || null })}
              placeholder="Street / area" className="h-8" />
          </Field>
          <Field label="Landmark">
            <Input value={inc.landmark ?? ""} disabled={!isEditable}
              onChange={(e) => update("incident", { landmark: e.target.value || null })}
              placeholder="Nearby landmark" className="h-8" />
          </Field>
          <Field label="Beat / SHO jurisdiction">
            <Input value={inc.beat ?? ""} disabled={!isEditable}
              onChange={(e) => update("incident", { beat: e.target.value || null })}
              placeholder="Beat or SHO note" className="h-8" />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title="What happened" description="A short description of the occurrence.">
        <textarea
          value={inc.occurrence_description ?? ""}
          disabled={!isEditable}
          onChange={(e) => update("incident", { occurrence_description: e.target.value || null })}
          rows={3}
          placeholder="Brief occurrence description…"
          className="w-full rounded-control border border-hairline bg-surface-2 px-3 py-2 text-13 text-content placeholder:text-content-dim focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        />
      </SectionCard>
    </div>
  );
}
