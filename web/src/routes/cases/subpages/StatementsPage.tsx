import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Lock, MessageSquareText, Pencil, Plus, ShieldAlert } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { CwStatement, CwStatementCreate } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/common/EmptyState";
import { formatDateTime, timeAgo } from "@/lib/utils";
import {
  caseworkKeys, pretty, toISO, useCanWriteCasework, useCaseworkLookups,
} from "./casework/caseworkShared";

export function StatementsPage({ caseId }: { caseId: number }) {
  const canWrite = useCanWriteCasework();
  const [adding, setAdding] = useState(false);
  const q = useQuery({
    queryKey: caseworkKeys.statements(caseId),
    queryFn: ({ signal }) => api.casework.listStatements(caseId, signal),
  });
  const items = q.data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-14 font-semibold text-content">Statements ({q.data?.count ?? 0})</h3>
        {canWrite && (
          <Button variant="primary" size="sm" onClick={() => setAdding(true)}>
            <Plus /> Record statement
          </Button>
        )}
      </div>
      <p className="text-12 text-content-dim">
        Typed statements are entered manually and versioned. Restricted statements are limited to
        assigned investigators/supervisors. An uploaded document/audio file may be linked as a reference only.
      </p>

      {q.isLoading && <Skeleton className="h-24 w-full" />}
      {q.error && <p className="text-13 text-content-dim">{errorMessage(q.error)}</p>}
      {!q.isLoading && items.length === 0 && (
        <EmptyState icon={MessageSquareText} title="No statements recorded"
                    description={canWrite ? "Record a witness/complainant/accused/expert statement." : "No statements yet."} />
      )}

      <div className="space-y-2">
        {items.map((s) => <StatementCard key={s.statement_id} s={s} caseId={caseId} canWrite={canWrite} />)}
      </div>

      {adding && <AddStatement caseId={caseId} open={adding} onOpenChange={setAdding} />}
    </div>
  );
}

function StatementCard({ s, caseId, canWrite }: { s: CwStatement; caseId: number; canWrite: boolean }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const invalidate = () => qc.invalidateQueries({ queryKey: caseworkKeys.statements(caseId) });

  const review = useMutation({
    mutationFn: () => api.casework.reviewStatement(s.statement_id),
    onSuccess: invalidate,
  });

  return (
    <div className="rounded-card border border-hairline bg-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="neutral" className="capitalize">{pretty(s.statement_type)}</Badge>
        <Badge variant={s.state === "reviewed" ? "low" : "neutral"}>{pretty(s.state)}</Badge>
        {s.is_restricted && (
          <Badge variant="high"><Lock className="size-3" /> Restricted</Badge>
        )}
        <span className="text-12 text-content-dim">
          {s.speaker_label ?? s.speaker_ref ?? "Speaker not linked"}
          {s.recorded_at ? ` · ${formatDateTime(s.recorded_at)}` : ""}
          {` · v${s.current_version_no ?? 1}`}
        </span>
        <div className="ml-auto flex gap-1">
          {canWrite && s.state !== "reviewed" && (
            <>
              <Button variant="ghost" size="sm" onClick={() => setCorrecting((v) => !v)}><Pencil /> Correct</Button>
              <Button variant="ghost" size="sm" onClick={() => review.mutate()} disabled={review.isPending}>
                <CheckCircle2 /> Review
              </Button>
            </>
          )}
        </div>
      </div>

      <p className={`mt-2 whitespace-pre-wrap text-13 ${s.access_limited ? "italic text-severity-high" : "text-content"}`}>
        {s.access_limited && <ShieldAlert className="mr-1 inline size-3.5" />}
        {s.current_text}
      </p>

      {s.versions.length > 1 && (
        <button className="mt-1 text-12 text-primary hover:underline" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Hide" : "Show"} version history ({s.versions.length})
        </button>
      )}
      {expanded && (
        <ol className="mt-2 space-y-1 border-l border-hairline pl-3">
          {s.versions.slice().reverse().map((v) => (
            <li key={v.statement_version_id} className="text-12">
              <span className="tnum font-medium text-content">v{v.version_no}</span>
              {v.correction_reason && <span className="text-content-dim"> · {v.correction_reason}</span>}
              {v.created_at && <span className="text-content-dim"> · {timeAgo(v.created_at)}</span>}
            </li>
          ))}
        </ol>
      )}

      {correcting && (
        <CorrectStatement sid={s.statement_id} onDone={() => { setCorrecting(false); invalidate(); }} />
      )}
    </div>
  );
}

function CorrectStatement({ sid, onDone }: { sid: number; onDone: () => void }) {
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [redact, setRedact] = useState(false);
  const mut = useMutation({
    mutationFn: () => api.casework.correctStatement(sid, {
      statement_text: text.trim() || undefined, correction_reason: reason.trim() || "correction", redact,
    }),
    onSuccess: onDone,
  });
  return (
    <div className="mt-2 space-y-2 rounded-control border border-hairline bg-surface-2/40 p-3">
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
                className="w-full rounded-control border border-hairline bg-surface px-3 py-2 text-13 text-content"
                placeholder="Corrected text (leave blank to keep, e.g. for redaction only)" />
      <Input value={reason} onChange={(e) => setReason(e.target.value)} className="h-8" placeholder="Correction reason *" />
      <label className="flex items-center gap-2 text-12 text-content-dim">
        <input type="checkbox" checked={redact} onChange={(e) => setRedact(e.target.checked)} />
        Redact (mark restricted)
      </label>
      {mut.error && <p className="text-12 text-severity-critical">{errorMessage(mut.error)}</p>}
      <div className="flex justify-end">
        <Button size="sm" onClick={() => mut.mutate()} disabled={mut.isPending || !reason.trim()}>Save correction</Button>
      </div>
    </div>
  );
}

function AddStatement({ caseId, open, onOpenChange }: { caseId: number; open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const lookups = useCaseworkLookups();
  const [type, setType] = useState("witness");
  const [text, setText] = useState("");
  const [language, setLanguage] = useState("en");
  const [access, setAccess] = useState("demo_normal");
  const [place, setPlace] = useState("");
  const [recordedAt, setRecordedAt] = useState("");
  const [personId, setPersonId] = useState("");
  const [evidenceId, setEvidenceId] = useState("");

  const mut = useMutation({
    mutationFn: () => {
      const body: CwStatementCreate = {
        statement_type: type, statement_text: text.trim(), language, access_classification: access,
        place: place.trim() || undefined, recorded_at: toISO(recordedAt),
        canonical_person_id: personId ? Number(personId) : undefined,
        evidence_item_id: evidenceId ? Number(evidenceId) : undefined,
      };
      return api.casework.createStatement(caseId, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: caseworkKeys.statements(caseId) });
      onOpenChange(false);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Record statement</DialogTitle>
          <DialogDescription>Manual entry only — content is not auto-extracted from any file.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-12 text-content-dim">Type</label>
              <NativeSelect value={type} onChange={setType}
                            options={lookups.data?.statement_types ?? [{ value: "witness", label: "Witness" }]}
                            placeholder="Witness" aria-label="Statement type" />
            </div>
            <div>
              <label className="mb-1 block text-12 text-content-dim">Access</label>
              <NativeSelect value={access} onChange={setAccess}
                            options={lookups.data?.access_classifications ?? [{ value: "demo_normal", label: "Demo Normal" }]}
                            placeholder="Demo Normal" aria-label="Access classification" />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-12 text-content-dim">Statement text *</label>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4}
                      className="w-full rounded-control border border-hairline bg-surface-2 px-3 py-2 text-13 text-content"
                      placeholder="Typed statement…" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-12 text-content-dim">Language</label>
              <NativeSelect value={language} onChange={setLanguage}
                            options={[{ value: "en", label: "English" }, { value: "kn", label: "Kannada" }, { value: "mixed", label: "Mixed" }]}
                            placeholder="English" aria-label="Language" />
            </div>
            <div>
              <label className="mb-1 block text-12 text-content-dim">Recorded at</label>
              <Input type="datetime-local" value={recordedAt} onChange={(e) => setRecordedAt(e.target.value)} className="h-8" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-12 text-content-dim">Speaker canonical person ID</label>
              <Input value={personId} onChange={(e) => setPersonId(e.target.value)} className="h-8" placeholder="optional (see People)" />
            </div>
            <div>
              <label className="mb-1 block text-12 text-content-dim">Linked evidence item ID</label>
              <Input value={evidenceId} onChange={(e) => setEvidenceId(e.target.value)} className="h-8" placeholder="optional" />
            </div>
          </div>
          <Input value={place} onChange={(e) => setPlace(e.target.value)} className="h-8" placeholder="Place recorded (optional)" />
          {mut.error && <p className="text-12 text-severity-critical">{errorMessage(mut.error)}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-hairline pt-3">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button size="sm" onClick={() => mut.mutate()} disabled={mut.isPending || !text.trim()}>
            {mut.isPending ? "Saving…" : "Save statement"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
