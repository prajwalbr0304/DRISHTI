import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Paperclip, Plus, X } from "lucide-react";
import { api } from "@/api";
import { ApiError, errorMessage } from "@/api/contracts";
import type { EvidenceCreateRequest, EvidenceItem } from "@/api/types";
import { formatDateTime, timeAgo } from "@/lib/utils";
import { useRole } from "@/providers/RoleProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";

/* Evidence sub-page (doc 01 §4.2 / §6): "+ Add evidence" is an IO action.
   Reads work for all permitted roles. The table CaseEvidence is additive (Phase
   15c migration 004). */

const EV_TYPES = [
  { value: "note", label: "Note" },
  { value: "seizure", label: "Seizure" },
  { value: "attachment", label: "Attachment" },
  { value: "statement", label: "Statement" },
  { value: "exhibit", label: "Exhibit" },
];

export function EvidencePage({ caseId }: { caseId: number }) {
  const { role } = useRole();
  const canWrite = role === "investigator" || role === "super_admin";
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);

  const q = useQuery({
    queryKey: ["cases", "evidence", caseId],
    queryFn: ({ signal }) => api.cases.evidence(caseId, signal),
  });

  if (!q.isLoading && q.data && !q.data.available) {
    return (
      <EmptyState
        icon={Paperclip}
        title="Evidence store not provisioned"
        description="Apply migration 004_case_evidence.sql to enable the evidence store."
      />
    );
  }

  const items = q.data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-14 font-semibold text-content">Evidence ({items.length})</h3>
        {canWrite && !adding && (
          <Button variant="primary" size="sm" onClick={() => setAdding(true)}>
            <Plus /> Add evidence
          </Button>
        )}
      </div>

      {adding && (
        <AddForm
          caseId={caseId}
          onDone={() => {
            setAdding(false);
            qc.invalidateQueries({ queryKey: ["cases", "evidence", caseId] });
          }}
          onCancel={() => setAdding(false)}
        />
      )}

      {q.isLoading && (
        <div className="space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      )}
      {q.error && <p className="text-13 text-content-dim">{errorMessage(q.error)}</p>}

      {!q.isLoading && items.length === 0 && !adding && (
        <EmptyState
          icon={FileText}
          title="No evidence recorded"
          description={
            canWrite
              ? 'Use "+ Add evidence" to record seizures, statements, exhibits or notes.'
              : "No evidence items have been added to this case yet."
          }
        />
      )}

      {items.length > 0 && (
        <div className="divide-y divide-hairline rounded-card border border-hairline bg-surface">
          {items.map((e) => (
            <EvidenceRow key={e.evidence_id} item={e} />
          ))}
        </div>
      )}
    </div>
  );
}

function EvidenceRow({ item }: { item: EvidenceItem }) {
  return (
    <div className="px-4 py-3">
      <div className="flex items-start gap-2">
        <Badge variant="neutral" className="mt-0.5 shrink-0 capitalize">
          {item.evidence_type}
        </Badge>
        <div className="min-w-0 flex-1">
          <div className="text-13 font-medium text-content">{item.title}</div>
          {item.description && (
            <div className="mt-0.5 text-13 text-content-dim">{item.description}</div>
          )}
          {item.reference && (
            <div className="mt-0.5 tnum text-12 text-content-dim">Ref: {item.reference}</div>
          )}
        </div>
        <div className="shrink-0 text-right">
          {item.created_at && (
            <div className="tnum text-12 text-content-dim" title={formatDateTime(item.created_at)}>
              {timeAgo(item.created_at)}
            </div>
          )}
          {item.created_by_role && (
            <div className="text-12 capitalize text-content-dim">{item.created_by_role}</div>
          )}
        </div>
      </div>
    </div>
  );
}

function AddForm({
  caseId,
  onDone,
  onCancel,
}: {
  caseId: number;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [type, setType] = useState("note");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [reference, setReference] = useState("");

  const mut = useMutation({
    mutationFn: () => {
      const body: EvidenceCreateRequest = {
        evidence_type: type,
        title: title.trim(),
        description: description.trim() || undefined,
        reference: reference.trim() || undefined,
      };
      return api.cases.addEvidence(caseId, body);
    },
    onSuccess: () => onDone(),
  });

  const forbidden = mut.error instanceof ApiError && mut.error.status === 403;

  return (
    <div className="rounded-card border border-hairline bg-surface p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-13 font-semibold text-content">New evidence</span>
        <Button variant="ghost" size="icon-sm" onClick={onCancel} aria-label="Cancel">
          <X />
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className="mb-1 block text-12 text-content-dim">Type</label>
          <NativeSelect
            value={type}
            onChange={setType}
            options={EV_TYPES}
            aria-label="Evidence type"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1 block text-12 text-content-dim">Title *</label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} className="h-8" placeholder="e.g. 'Recovered two-wheeler'" />
        </div>
      </div>
      <div>
        <label className="mb-1 block text-12 text-content-dim">Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="w-full rounded-control border border-hairline bg-surface-2 px-3 py-2 text-13 text-content placeholder:text-content-dim focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          placeholder="Optional detail…"
        />
      </div>
      <div>
        <label className="mb-1 block text-12 text-content-dim">Reference / seizure no.</label>
        <Input value={reference} onChange={(e) => setReference(e.target.value)} className="h-8" placeholder="e.g. SEIZ-0045" />
      </div>

      {mut.error && !forbidden && (
        <p className="text-12 text-severity-critical">{errorMessage(mut.error)}</p>
      )}
      {forbidden && (
        <p className="text-12 text-severity-high">
          Your role does not have permission to add evidence — this is an investigating-officer action.
        </p>
      )}

      <div className="flex items-center justify-end gap-2 pt-1">
        <Button variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          size="sm"
          disabled={!title.trim() || mut.isPending}
          onClick={() => mut.mutate()}
        >
          {mut.isPending ? "Saving…" : "Save evidence"}
        </Button>
      </div>
    </div>
  );
}
