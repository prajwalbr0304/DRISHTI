import { useState } from "react";
import {
  AlertTriangle, CheckCircle2, Info, ScanFace, Trash2, UserPlus, X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, SectionCard } from "@/routes/intake/components";
import { errorMessage } from "@/api/contracts";
import { FaceScanDialog } from "@/components/face/FaceScanDialog";
import type { FaceConfirmation } from "@/components/face/FaceScanner";
import { useFaceStatus } from "@/components/face/faceShared";
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

/** Roles where checking the face against existing records actually pays off:
    a suspect/accused (or an unidentified body) is the party most likely to
    already be on file under a different name. */
const FACE_ROLES = new Set(["accused", "suspect", "victim", "unknown"]);

/** Roles whose photo is worth ADDING to the searchable gallery when the person
    turns out not to be on file. Keeping this narrower than FACE_ROLES is the
    point: an accused or an unidentified body is who a later scan needs to find,
    whereas putting a victim's or a complainant's biometrics into a searchable
    criminal gallery is a materially different act and is left to an explicit
    decision on their record instead of being the default here. */
const FACE_ENROL_DEFAULT_ROLES = new Set(["accused", "suspect", "unknown"]);

/** Step 5 — people & organisations. Every party becomes a canonical identity +
    CasePartyRole on approval (no name-based joins). */
export function PeopleStep({ editor, workflow }: StepProps) {
  const { caseKind, parties, addParty, removeParty, isEditable, draft } = editor;
  const [form, setForm] = useState<IntakePartyInput>({ ...blank });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [scanOpen, setScanOpen] = useState(false);
  /** The face-confirmed identity currently attached to the party being added. */
  const [faceHit, setFaceHit] = useState<FaceConfirmation | null>(null);
  const [faceChecked, setFaceChecked] = useState(false);
  /** Probe handle from a scan that found nobody. The descriptor is retained
      server-side against this ref, so the photo can be enrolled onto the identity
      this party mints on approval without re-uploading anything. */
  const [unmatchedProbeRef, setUnmatchedProbeRef] = useState<string | null>(null);
  const [enrolFace, setEnrolFace] = useState(false);
  const faceStatus = useFaceStatus();

  const roles = workflow?.kinds.find((k) => k.kind === caseKind)?.allowed_party_roles ?? [];
  const roleOpts = roles.map((r) => ({ value: r, label: r.replace(/_/g, " ") }));

  const setAttr = (patch: Record<string, unknown>) =>
    setForm((f) => ({ ...f, attributes: { ...f.attributes, ...patch } }));

  const faceRelevant = form.party_nature === "person" && FACE_ROLES.has(form.role_type);
  const faceReady = !!faceStatus.data?.search_ready;

  const clearFaceHit = () => {
    setFaceHit(null);
    setForm((f) => ({ ...f, canonical_person_id: null }));
  };

  const resetFaceState = () => {
    setFaceHit(null);
    setFaceChecked(false);
    setUnmatchedProbeRef(null);
    setEnrolFace(false);
  };

  /** A scan that matched nobody. Keep the probe so the officer can choose to make
      this face searchable under the identity about to be created — otherwise the
      descriptor is discarded and the next scan of the same person reports "not on
      file" all over again. */
  const onFaceNoMatch = (probeRef: string) => {
    setFaceChecked(true);
    setUnmatchedProbeRef(probeRef);
    setEnrolFace(FACE_ENROL_DEFAULT_ROLES.has(form.role_type));
    setScanOpen(false);
  };

  /** A confirmed match pre-fills the party from the EXISTING record, so the case
      links to that canonical identity instead of minting a near-duplicate. */
  const onFaceConfirm = (c: FaceConfirmation) => {
    const p = c.match.person;
    setFaceHit(c);
    setFaceChecked(true);
    // The party now reuses an existing identity, so there is no new person to
    // enrol against; the scanner already offers to add a strong pose to that
    // person's own gallery.
    setUnmatchedProbeRef(null);
    setEnrolFace(false);
    setForm((f) => ({
      ...f,
      canonical_person_id: p.canonical_person_id,
      display_name: p.is_unknown ? f.display_name : (p.display_label ?? f.display_name),
      attributes: {
        ...f.attributes,
        gender_id: p.primary_gender_id ?? f.attributes.gender_id,
        // Provenance for the link, so a reviewer can see WHY this party was
        // bound to an existing identity rather than a fresh one.
        face_probe_ref: c.probeRef,
        face_match_similarity: Number(c.similarity.toFixed(4)),
        face_match_band: c.match.band,
        identity_source: "face_match",
        ...(c.entityResolutionCandidateId
          ? { face_entity_resolution_candidate_id: c.entityResolutionCandidateId }
          : {}),
      },
    }));
    setScanOpen(false);
  };

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const isUnknown = form.party_nature === "unknown";
      // Carry the capture on the PARTY, not the draft: a draft can hold several
      // scanned people, and the server must never have to guess which probe
      // belongs to which person before enrolling biometrics.
      const enrolAttrs = (unmatchedProbeRef && enrolFace)
        ? {
          face_probe_ref: unmatchedProbeRef,
          face_enrol_on_approval: true,
          identity_source: "intake_face_capture",
        }
        : {};
      await addParty({
        ...form,
        is_unknown: isUnknown,
        display_name: isUnknown ? null : (form.display_name || null),
        attributes: { ...form.attributes, ...enrolAttrs },
      });
      setForm({ ...blank, role_type: form.role_type });
      resetFaceState();
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
                    {p.canonical_person_id && (
                      <Badge variant="outline" className="gap-1">
                        <CheckCircle2 className="size-3" aria-hidden />
                        Linked to existing record
                      </Badge>
                    )}
                    {p.attributes?.identity_source === "face_match" && (
                      <Badge variant="accent" className="gap-1">
                        <ScanFace className="size-3" aria-hidden />
                        face match
                        {typeof p.attributes?.face_match_similarity === "number"
                          && ` ${Math.round(Number(p.attributes.face_match_similarity) * 100)}%`}
                      </Badge>
                    )}
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
              {/* Changing role or nature discards a pending face capture: a probe
                  taken while recording an accused must not silently follow the
                  form over to a witness or an organisation. */}
              <NativeSelect value={form.role_type}
                onChange={(v) => { resetFaceState(); setForm((f) => ({ ...f, role_type: v, canonical_person_id: null })); }}
                options={roleOpts} placeholder="Select role" aria-label="Party role" />
            </Field>
            <Field label="Nature">
              <NativeSelect value={form.party_nature}
                onChange={(v) => { resetFaceState(); setForm((f) => ({ ...f, party_nature: v, canonical_person_id: null })); }}
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

          {/* ---- face check: does this person already exist in the records? ---- */}
          {faceRelevant && (
            <div className="mt-3 rounded-card border border-hairline bg-surface-2/40 p-3">
              {faceHit ? (
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-severity-low" aria-hidden />
                    <div className="min-w-0">
                      <p className="text-13 font-medium text-content">
                        Linked to {faceHit.match.person.display_label
                          ?? faceHit.match.person.public_ref}
                      </p>
                      <p className="mt-0.5 text-12 text-content-dim">
                        {faceHit.match.person.public_ref} ·{" "}
                        {Math.round(faceHit.similarity * 100)}% face similarity ·{" "}
                        {faceHit.match.person.case_count} case
                        {faceHit.match.person.case_count === 1 ? "" : "s"} on record.
                        {" "}This party will reuse that canonical identity instead of
                        creating a new one.
                      </p>
                      {faceHit.entityResolutionCandidateId && (
                        <p className="mt-1 flex items-start gap-1 text-12 text-severity-medium">
                          <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
                          A match candidate was raised for review — identities are
                          never merged on a face score alone.
                        </p>
                      )}
                    </div>
                  </div>
                  <Button type="button" variant="ghost" size="sm" onClick={clearFaceHit}>
                    <X /> Unlink
                  </Button>
                </div>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2">
                    <ScanFace className="mt-0.5 size-4 shrink-0 text-content-dim" aria-hidden />
                    <div className="min-w-0">
                      <p className="text-13 font-medium text-content">
                        Check this face against existing records
                      </p>
                      <p className="mt-0.5 text-12 text-content-dim">
                        {faceReady
                          ? "Take or upload a photo to see whether this person is already"
                            + " on file under another name, before creating a new identity."
                          : faceStatus.data?.unavailable_reason
                            ?? "No reference photos are enrolled yet, so there is nothing"
                              + " to match against."}
                      </p>
                      {faceChecked && !faceHit && (
                        <p className="mt-1 flex items-start gap-1 text-12 text-content-dim">
                          <Info className="mt-0.5 size-3 shrink-0" aria-hidden />
                          Recorded as not on file — this party will be created as a
                          new identity.
                        </p>
                      )}
                      {/* Not on file is the case that matters: without enrolling,
                          the photo just taken is discarded and the next scan of
                          this person reports "not on file" again. */}
                      {unmatchedProbeRef && (
                        <label className="mt-2 flex cursor-pointer items-start gap-2 rounded-control border border-hairline bg-surface-1 p-2">
                          <input
                            type="checkbox"
                            className="mt-0.5 size-3.5 shrink-0 accent-accent"
                            checked={enrolFace}
                            onChange={(e) => setEnrolFace(e.target.checked)}
                          />
                          <span className="min-w-0">
                            <span className="block text-12 font-medium text-content">
                              Add this photo to the face records for this person
                            </span>
                            <span className="mt-0.5 block text-11 leading-4 text-content-dim">
                              {enrolFace
                                ? "On approval, this face is enrolled against the new"
                                  + " identity, so scanning this person later returns"
                                  + " their name and this case. Only the 512-dim"
                                  + " descriptor already computed for the search is"
                                  + " stored — never the photograph."
                                : "The photo will be discarded when this scan closes,"
                                  + " so a later scan of this person will report \u201cnot"
                                  + " on file\u201d again."}
                            </span>
                          </span>
                        </label>
                      )}
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setScanOpen(true)}
                    disabled={!faceReady}
                  >
                    <ScanFace /> Scan face
                  </Button>
                </div>
              )}
            </div>
          )}

          {err && <p className="mt-2 text-12 text-severity-high">{err}</p>}
          <div className="mt-3">
            <Button type="button" size="sm" onClick={submit} disabled={busy}>
              <UserPlus /> Add party
            </Button>
          </div>
        </SectionCard>
      )}

      <FaceScanDialog
        open={scanOpen}
        onOpenChange={setScanOpen}
        origin="intake_fir"
        intakeDraftKey={draft?.draft_key ?? null}
        caseId={draft?.case_master_id ?? null}
        existingCanonicalPersonId={form.canonical_person_id ?? null}
        onConfirm={onFaceConfirm}
        confirmLabel="Use this record"
        onNoMatch={onFaceNoMatch}
        title="Check the face against person records"
        description="Photograph or upload the person's face. DRISHTI searches enrolled
          records and shows any existing identity, so the FIR links to it instead of
          creating a duplicate. If nobody matches, you can add this face to the new
          person's record so a later scan identifies them."
      />
    </div>
  );
}
