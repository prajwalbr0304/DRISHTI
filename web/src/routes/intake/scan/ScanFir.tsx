import { useCallback, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle, ArrowRight, FileText, Info, Keyboard, Loader2,
  Printer, ScanLine, Trash2, Upload,
} from "lucide-react";
import { api } from "@/api";
import { ApiError, errorMessage } from "@/api/contracts";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/routes/intake/components";
import { ScanFieldTable, ScanSummary } from "@/routes/intake/scan/ScanFieldTable";
import { useScanCapability } from "@/routes/intake/scan/scanQueries";
import type {
  IntakeDraftPayload, IntakePartyInput, IntakeScanResponse,
} from "@/api/types";

/* ============================================================================
   Scanned-FIR intake (Catalyst Zia OCR).

   Reading a page never registers a case. This screen produces a PROPOSAL, the
   officer corrects it, and "Continue" creates an ordinary draft that goes through
   the same validate -> submit -> approve gate as a typed FIR. The manual lane is
   always one click away, including when OCR is switched off or fails.
   ========================================================================== */

const LANGUAGE_CHOICES = [
  { value: "auto", label: "Detect automatically" },
  { value: "en", label: "English only" },
  { value: "kn", label: "Kannada only" },
  { value: "en,kn", label: "English + Kannada" },
];

/** Apply the officer's inline corrections back onto the payload / parties. */
function applyEdits(
  payload: IntakeDraftPayload,
  parties: IntakePartyInput[],
  edits: Record<string, string>,
): { payload: IntakeDraftPayload; parties: IntakePartyInput[]; editedFields: string[] } {
  const nextPayload: IntakeDraftPayload = JSON.parse(JSON.stringify(payload));
  const nextParties: IntakePartyInput[] = JSON.parse(JSON.stringify(parties));
  const editedFields: string[] = [];

  for (const [path, rawValue] of Object.entries(edits)) {
    const value = rawValue.trim();
    editedFields.push(path);

    if (path.startsWith("__")) {
      const body = path.slice(2);
      const idx = body.indexOf("_");
      const role = idx === -1 ? body : body.slice(0, idx);
      const attr = idx === -1 ? "name" : body.slice(idx + 1);
      let party = nextParties.find((p) => p.role_type === role);
      if (!party) {
        if (!value) continue;
        party = { role_type: role, party_nature: "person", is_unknown: false, attributes: {} };
        nextParties.push(party);
      }
      if (attr === "name") {
        party.display_name = value || null;
        party.is_unknown = !value;
      } else {
        party.attributes = { ...(party.attributes ?? {}) };
        if (value) party.attributes[attr] = attr === "age" ? Number(value) || value : value;
        else delete party.attributes[attr];
      }
      continue;
    }

    const [section, key] = path.split(".");
    if (!section || !key) continue;
    const bucket = (nextPayload as unknown as Record<string, Record<string, unknown>>)[section];
    if (!bucket) continue;
    // Numeric reference ids arrive from the candidate pickers as strings.
    if (key.endsWith("_id")) bucket[key] = value ? Number(value) : null;
    else bucket[key] = value || null;
  }

  return { payload: nextPayload, parties: nextParties, editedFields };
}

export function ScanFir() {
  const navigate = useNavigate();
  const { role } = useRole();
  const capabilityQ = useScanCapability();
  const fileInput = useRef<HTMLInputElement | null>(null);

  const [language, setLanguage] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scan, setScan] = useState<IntakeScanResponse | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [applying, setApplying] = useState(false);

  const capability = capabilityQ.data;
  const threshold = capability?.auto_fill_threshold ?? 0.7;

  const onEdit = useCallback((path: string, value: string) => {
    setEdits((prev) => ({ ...prev, [path]: value }));
  }, []);

  const onPick = useCallback(async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setScan(null);
    setEdits({});
    try {
      const langs = language === "auto" ? undefined : language.split(",");
      const result = await api.intake.scanOcr(file, { languages: langs, actor: role });
      setScan(result);
    } catch (e) {
      // 409 means the server has the feature switched off; 413/422 mean the file
      // itself is the problem. Either way the manual lane is the way forward.
      setError(
        e instanceof ApiError && e.status === 413
          ? `That file is too large. Keep it under ${capability?.max_mb ?? 20} MB.`
          : errorMessage(e),
      );
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }, [language, role, capability?.max_mb]);

  const onApply = useCallback(async () => {
    if (!scan) return;
    setApplying(true);
    setError(null);
    try {
      const { payload, parties, editedFields } = applyEdits(
        scan.payload, scan.parties as unknown as IntakePartyInput[], edits);
      const result = await api.intake.applyScan(scan.scan_key, {
        payload, parties, case_kind: scan.case_kind, actor: role,
        edited_fields: editedFields,
      });
      navigate(`/intake/fir/${result.draft.draft_key}`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setApplying(false);
    }
  }, [scan, edits, role, navigate]);

  const onDiscard = useCallback(async () => {
    if (!scan) return;
    try {
      await api.intake.discardScan(scan.scan_key, role);
    } catch {
      // Discarding is a convenience; a failure here should not trap the officer.
    }
    setScan(null);
    setEdits({});
    setError(null);
  }, [scan, role]);

  const accept = useMemo(
    () => (capability?.allowed_extensions ?? ["jpeg", "png", "pdf"]).map((e) => `.${e}`).join(","),
    [capability?.allowed_extensions],
  );

  const manualButton = (
    <Button variant="outline" size="sm" onClick={() => navigate("/intake/fir/new")}>
      <Keyboard /> Enter manually
    </Button>
  );

  if (capabilityQ.isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Scan a written FIR" description="Reading a form to fill it in faster." />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  // Feature off: say so plainly and point at the lane that does work.
  if (capability && !capability.scan_ocr_enabled) {
    return (
      <div>
        <PageHeader
          title="Scan a written FIR"
          description="Reading a written form to fill the FIR in faster."
          actions={manualButton}
        />
        <EmptyState
          icon={ScanLine}
          title="Scanning is not switched on"
          description={
            capability.platform_limitation ??
            "Catalyst Zia OCR is not enabled on this server, so FIRs are entered manually."
          }
          action={manualButton}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Scan a written FIR"
        description="Read a written or printed form, check what was read, then continue into the normal FIR form."
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => navigate("/intake/scan/form")}>
              <Printer /> Printable form
            </Button>
            {manualButton}
          </>
        }
      />

      {/* The one thing every user must understand about this screen. */}
      <div className="flex items-start gap-2 rounded-card border border-primary/30 bg-primary/5 p-3 text-13">
        <Info className="mt-0.5 size-4 shrink-0 text-primary" />
        <p className="text-content">
          Reading a form is a typing shortcut, not a decision. Nothing is registered
          here — you review every field, and the case is created only after a
          supervisor approves the draft.
        </p>
      </div>

      {!scan && (
        <SectionCard
          title="Upload the page"
          description={`Photograph or scan the FIR form. ${capability?.max_mb ?? 20} MB maximum, ${(capability?.allowed_extensions ?? []).join(", ")}.`}
        >
          <div className="grid gap-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
            <div>
              <label className="mb-1 block text-12 font-medium text-content-dim">
                Language on the form
              </label>
              <NativeSelect
                value={language}
                onChange={setLanguage}
                options={LANGUAGE_CHOICES}
                placeholder="Detect automatically"
                aria-label="Language on the form"
              />
            </div>
            <div className="flex items-end gap-2">
              <input
                ref={fileInput}
                type="file"
                accept={accept}
                className="hidden"
                aria-label="Scanned FIR page"
                onChange={(e) => void onPick(e.target.files?.[0])}
              />
              <Button
                size="sm"
                disabled={busy}
                onClick={() => fileInput.current?.click()}
              >
                {busy ? <Loader2 className="animate-spin" /> : <Upload />}
                {busy ? "Reading the page…" : "Choose a scan"}
              </Button>
            </div>
          </div>

          {capability?.handwriting_caveat && (
            <p className="mt-3 flex items-start gap-1.5 text-12 text-content-dim">
              <AlertTriangle className="mt-0.5 size-3 shrink-0 text-severity-medium" />
              {capability.handwriting_caveat}
            </p>
          )}
        </SectionCard>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-card border border-severity-high/40 bg-severity-high/5 p-3 text-13">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-severity-high" />
          <div>
            <p className="text-content">{error}</p>
            <p className="mt-1 text-12 text-content-dim">
              You can always enter the FIR manually instead.
            </p>
          </div>
        </div>
      )}

      {scan && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <ScanSummary
              language={scan.detected_language}
              ocrConfidence={scan.ocr_confidence}
              templateMatched={scan.template_matched}
              needingReview={scan.fields_needing_review}
              total={scan.fields.length}
              lowConfidence={scan.ocr_low_confidence}
            />
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => void onDiscard()}>
                <Trash2 /> Discard
              </Button>
              <Button size="sm" disabled={applying} onClick={() => void onApply()}>
                {applying ? <Loader2 className="animate-spin" /> : <ArrowRight />}
                Continue to the FIR form
              </Button>
            </div>
          </div>

          {scan.notes.length > 0 && (
            <div className="rounded-card border border-severity-medium/40 bg-severity-medium/5 p-3 text-13">
              <ul className="space-y-1">
                {scan.notes.map((n, i) => (
                  <li key={i} className="flex gap-2 text-content">
                    <Info className="mt-0.5 size-3.5 shrink-0 text-severity-medium" />
                    {n}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
            <div className="min-w-0">
              <ScanFieldTable
                fields={scan.fields}
                unresolved={scan.unresolved}
                threshold={threshold}
                edits={edits}
                onEdit={onEdit}
              />
            </div>

            {/* The recognised text, verbatim. Any extracted field can be audited
                against exactly what the recogniser read. */}
            <SectionCard
              title="What the recogniser read"
              description="Verbatim output. Compare it against the page if a field looks wrong."
            >
              <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-control border border-hairline bg-surface-2 p-2.5 text-12 leading-relaxed text-content-dim">
                {scan.raw_text || "No text was recognised."}
              </pre>
              {scan.sha256 && (
                <p className="mt-2 break-all text-11 text-content-dim">
                  <FileText className="mr-1 inline size-3" />
                  {scan.file_name} · SHA-256 {scan.sha256.slice(0, 16)}…
                </p>
              )}
            </SectionCard>
          </div>
        </>
      )}
    </div>
  );
}
