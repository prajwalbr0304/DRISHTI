import { useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2, Paperclip, X } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { EvCreateRequest, EvStatus } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatBytes, putToPresignedUrl, sha256Hex } from "@/lib/evidenceUpload";
import { useEvidenceLookups } from "./evidenceShared";

type Phase = "form" | "hashing" | "creating" | "uploading" | "completing" | "error";

function guessMime(file: File): string {
  if (file.type) return file.type;
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
    gif: "image/gif", webp: "image/webp", mp4: "video/mp4", webm: "video/webm",
    mp3: "audio/mpeg", wav: "audio/wav", m4a: "audio/x-m4a", csv: "text/csv",
    json: "application/json", txt: "text/plain", xml: "application/xml",
  };
  return map[ext] ?? "application/octet-stream";
}

export function AddEvidenceDialog({
  caseId,
  status,
  open,
  onOpenChange,
}: {
  caseId: number;
  status?: EvStatus;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const lookups = useEvidenceLookups();

  const [type, setType] = useState("document");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [source, setSource] = useState("FIR_FORM");
  const [reference, setReference] = useState("");
  const [capturedAt, setCapturedAt] = useState("");
  const [language, setLanguage] = useState("en");
  const [confidentiality, setConfidentiality] = useState("demo_normal");
  const [tags, setTags] = useState("");
  const [notes, setNotes] = useState("");
  const [externalUrl, setExternalUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const [phase, setPhase] = useState<Phase>("form");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dupWarn, setDupWarn] = useState<string | null>(null);
  const createdItemId = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const uploadEnabled = !!status?.upload_enabled;
  const isExternal = type === "external_reference";
  const metadataOnly = isExternal || (!file && !uploadEnabled);
  const busy = phase !== "form" && phase !== "error";

  const allowedExt = useMemo(
    () => new Set(status?.allowed_extensions ?? []),
    [status],
  );

  function reset() {
    setType("document"); setTitle(""); setDescription(""); setCategory("");
    setSource("FIR_FORM"); setReference(""); setCapturedAt(""); setLanguage("en");
    setConfidentiality("demo_normal"); setTags(""); setNotes(""); setExternalUrl("");
    setFile(null); setPhase("form"); setProgress(0); setError(null); setDupWarn(null);
    createdItemId.current = null;
  }

  function close() {
    abortRef.current?.abort();
    reset();
    onOpenChange(false);
  }

  function validateFile(f: File): string | null {
    const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
    if (status && !allowedExt.has(ext)) {
      return `Files of type ".${ext}" are not allowed. Allowed: ${[...allowedExt].join(", ")}.`;
    }
    if (status && f.size > status.max_bytes) {
      return `File is ${formatBytes(f.size)}; the limit is ${formatBytes(status.max_bytes)}.`;
    }
    if (f.size === 0) return "Refusing to upload an empty (0-byte) file.";
    return null;
  }

  function pickFile(f: File | null) {
    setError(null);
    if (f) {
      const err = validateFile(f);
      if (err) {
        setError(err);
        return;
      }
    }
    setFile(f);
  }

  async function runUpload(itemId: number, f: File) {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const mime = guessMime(f);
    setPhase("hashing");
    const sha = await sha256Hex(f);
    setPhase("creating");
    const url = await api.evidence.uploadUrl(itemId, {
      file_name: f.name, mime_type: mime, size_bytes: f.size, sha256: sha,
    });
    setPhase("uploading");
    setProgress(0);
    await putToPresignedUrl(url.upload_url, f, {
      method: url.method, headers: url.headers,
      onProgress: (pct) => setProgress(pct), signal: ctrl.signal,
    });
    setPhase("completing");
    const done = await api.evidence.complete(itemId, {
      storage_key: url.storage_key, file_name: f.name, mime_type: mime,
      size_bytes: f.size, sha256: sha, version_no: url.version_no,
    });
    setDupWarn(done.duplicate_warning ?? null);
  }

  async function submit() {
    setError(null); setDupWarn(null);
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    if (file) {
      const err = validateFile(file);
      if (err) { setError(err); return; }
    }
    try {
      setPhase("creating");
      let itemId = createdItemId.current;
      if (itemId == null) {
        const body: EvCreateRequest = {
          case_id: caseId,
          evidence_type: type,
          title: title.trim(),
          description: description.trim() || undefined,
          category: category || undefined,
          source_system_code: source || undefined,
          synthetic_reference: reference.trim() || undefined,
          captured_at: capturedAt ? new Date(capturedAt).toISOString() : undefined,
          language,
          confidentiality,
          tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
          notes: notes.trim() || undefined,
          external_reference_url: externalUrl.trim() || undefined,
          metadata_only: metadataOnly,
        };
        const created = await api.evidence.create(body);
        itemId = created.item.evidence_item_id;
        createdItemId.current = itemId;
      }
      if (file && !isExternal) {
        await runUpload(itemId, file);
      }
      qc.invalidateQueries({ queryKey: ["evidence", "list", caseId] });
      close();
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        setPhase("error");
        setError("Upload cancelled. You can retry.");
        return;
      }
      setPhase("error");
      setError(errorMessage(e));
    }
  }

  const typeOptions = lookups.data?.evidence_types ?? [];
  const catOptions = lookups.data?.categories ?? [];
  const confOptions = lookups.data?.confidentialities ?? [];
  const langOptions = lookups.data?.languages ?? [];
  const srcOptions = lookups.data?.source_systems ?? [];

  return (
    <Dialog open={open} onOpenChange={(v) => (v ? onOpenChange(true) : close())}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add evidence</DialogTitle>
          <DialogDescription>
            Enter the metadata by hand and optionally attach an already-digital file.
            File contents are not automatically extracted.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[65vh] space-y-3 overflow-y-auto pr-1">
          {/* Dropzone */}
          {!isExternal && (
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (!busy) pickFile(e.dataTransfer.files?.[0] ?? null);
              }}
              className="rounded-card border border-dashed border-hairline bg-surface-2/50 p-4 text-center"
            >
              <input
                ref={fileInput}
                type="file"
                className="hidden"
                onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <div className="flex items-center justify-center gap-2 text-13 text-content">
                  <Paperclip className="size-4 text-content-dim" />
                  <span className="font-medium">{file.name}</span>
                  <span className="tnum text-content-dim">({formatBytes(file.size)})</span>
                  {!busy && (
                    <Button variant="ghost" size="icon-sm" onClick={() => pickFile(null)} aria-label="Remove file">
                      <X />
                    </Button>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <FileUp className="mx-auto size-6 text-content-dim" />
                  <p className="text-13 text-content-dim">
                    Drag a file here, or{" "}
                    <button
                      type="button"
                      className="text-primary hover:underline"
                      onClick={() => fileInput.current?.click()}
                      disabled={busy}
                    >
                      browse
                    </button>
                    .
                  </p>
                  {!uploadEnabled && (
                    <p className="text-12 text-severity-medium">
                      File storage is not configured — you can still save metadata-only evidence.
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Metadata form */}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Type">
              <NativeSelect
                value={type}
                onChange={setType}
                options={typeOptions.length ? typeOptions : [{ value: "document", label: "Document" }]}
                placeholder="Document"
                aria-label="Evidence type"
              />
            </Field>
            <Field label="Category">
              <NativeSelect value={category} onChange={setCategory} options={catOptions} aria-label="Category" />
            </Field>
          </div>

          <Field label="Title *">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} className="h-8"
                   placeholder="e.g. 'CCTV clip near market gate'" />
          </Field>

          <Field label="Description">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full rounded-control border border-hairline bg-surface-2 px-3 py-2 text-13 text-content placeholder:text-content-dim focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
              placeholder="Short description…"
            />
          </Field>

          {isExternal && (
            <Field label="External reference URL">
              <Input value={externalUrl} onChange={(e) => setExternalUrl(e.target.value)} className="h-8"
                     placeholder="https://… (synthetic reference)" />
            </Field>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Source system">
              <NativeSelect value={source} onChange={setSource} options={srcOptions} placeholder="FIR form"
                            aria-label="Source system" />
            </Field>
            <Field label="Synthetic reference no.">
              <Input value={reference} onChange={(e) => setReference(e.target.value)} className="h-8"
                     placeholder="auto if blank" />
            </Field>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Captured / received">
              <Input type="datetime-local" value={capturedAt} onChange={(e) => setCapturedAt(e.target.value)}
                     className="h-8" />
            </Field>
            <Field label="Language">
              <NativeSelect value={language} onChange={setLanguage}
                            options={langOptions.length ? langOptions : [{ value: "en", label: "English" }]}
                            placeholder="English" aria-label="Language" />
            </Field>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Confidentiality">
              <NativeSelect value={confidentiality} onChange={setConfidentiality}
                            options={confOptions.length ? confOptions : [{ value: "demo_normal", label: "Demo Normal" }]}
                            placeholder="Demo Normal" aria-label="Confidentiality" />
            </Field>
            <Field label="Tags (comma separated)">
              <Input value={tags} onChange={(e) => setTags(e.target.value)} className="h-8"
                     placeholder="synthetic, cctv" />
            </Field>
          </div>

          <Field label="Notes">
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} className="h-8"
                   placeholder="Optional notes (manual)" />
          </Field>

          {/* progress + errors */}
          {phase === "uploading" && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-12 text-content-dim">
                <span>Uploading to secure storage…</span>
                <span className="tnum">{progress}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}
          {(phase === "hashing" || phase === "creating" || phase === "completing") && (
            <p className="flex items-center gap-2 text-12 text-content-dim">
              <Loader2 className="size-3.5 animate-spin" />
              {phase === "hashing" ? "Hashing file…" : phase === "creating" ? "Saving metadata…" : "Verifying upload…"}
            </p>
          )}
          {error && <p className="text-12 text-severity-critical">{error}</p>}
          {dupWarn && <p className="text-12 text-severity-medium">{dupWarn}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-hairline pt-3">
          {busy && phase === "uploading" ? (
            <Button variant="outline" size="sm" onClick={() => abortRef.current?.abort()}>
              Cancel upload
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={close} disabled={busy}>
              Cancel
            </Button>
          )}
          {phase === "error" && createdItemId.current != null && file ? (
            <Button size="sm" onClick={submit}>Retry upload</Button>
          ) : (
            <Button size="sm" onClick={submit} disabled={busy || !title.trim()}>
              {busy ? "Working…" : file && !isExternal ? "Save & upload" : "Save evidence"}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-12 text-content-dim">{label}</label>
      {children}
    </div>
  );
}
