import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Package, Plus } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { CwLabResultInput, CwPropertyItem, CwPropertyItemInput } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/common/EmptyState";
import { caseworkKeys, pretty, toISO, useCanWriteCasework, useCaseworkLookups } from "./casework/caseworkShared";

const PROP_STATUS_BADGE: Record<string, "neutral" | "low" | "outline" | "primary"> = {
  seized: "primary", recovered: "low", returned: "outline", disposed: "neutral",
};

export function PropertyPage({ caseId }: { caseId: number }) {
  const canWrite = useCanWriteCasework();
  const [addSeizure, setAddSeizure] = useState(false);
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: caseworkKeys.seizures(caseId),
    queryFn: ({ signal }) => api.casework.listSeizures(caseId, signal),
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: caseworkKeys.seizures(caseId) });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-14 font-semibold text-content">Property & seizures ({q.data?.count ?? 0})</h3>
        {canWrite && (
          <Button variant="primary" size="sm" onClick={() => setAddSeizure(true)}><Plus /> Add seizure</Button>
        )}
      </div>

      {q.isLoading && <Skeleton className="h-24 w-full" />}
      {q.error && <p className="text-13 text-content-dim">{errorMessage(q.error)}</p>}
      {!q.isLoading && (q.data?.count ?? 0) === 0 && (
        <EmptyState icon={Package} title="No property or seizures"
                    description={canWrite ? "Record a seizure and its property/vehicle/weapon/substance items." : "No property recorded."} />
      )}

      {q.data?.seizures.map((s) => (
        <div key={s.seizure_id} className="rounded-card border border-hairline bg-surface p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="neutral" className="capitalize">{pretty(s.seizure_type)}</Badge>
            <span className="text-13 font-medium text-content">{s.place ?? "Seizure"}</span>
            <span className="text-12 text-content-dim">{s.seized_at ? new Date(s.seized_at).toLocaleDateString() : ""}</span>
            {s.memo_evidence_item_id && <span className="text-12 text-content-dim">Memo: EV-{s.memo_evidence_item_id}</span>}
          </div>
          <PropertyItemTable items={s.items} caseId={caseId} canWrite={canWrite} />
        </div>
      ))}

      {(q.data?.unlinked_items.length ?? 0) > 0 && (
        <div className="rounded-card border border-hairline bg-surface p-3">
          <div className="text-13 font-medium text-content">Property items (no seizure)</div>
          <PropertyItemTable items={q.data!.unlinked_items} caseId={caseId} canWrite={canWrite} />
        </div>
      )}

      <LabPanel caseId={caseId} canWrite={canWrite} />

      {addSeizure && (
        <AddSeizureDialog caseId={caseId} open={addSeizure} onOpenChange={(v) => { setAddSeizure(v); if (!v) invalidate(); }} />
      )}
    </div>
  );
}

function PropertyItemTable({ items, caseId, canWrite }: { items: CwPropertyItem[]; caseId: number; canWrite: boolean }) {
  const qc = useQueryClient();
  const lookups = useCaseworkLookups();
  const mut = useMutation({
    mutationFn: (v: { pid: number; status: string }) => api.casework.changePropertyStatus(v.pid, { status: v.status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: caseworkKeys.seizures(caseId) }),
  });
  if (items.length === 0) return <p className="mt-2 text-12 text-content-dim">No items.</p>;
  return (
    <table className="mt-2 w-full text-13">
      <thead>
        <tr className="text-left text-12 text-content-dim">
          <th className="py-1 font-medium">Type</th><th className="py-1 font-medium">Description</th>
          <th className="py-1 font-medium">Qty</th><th className="py-1 font-medium">Value</th>
          <th className="py-1 font-medium">Status</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-hairline">
        {items.map((it) => (
          <tr key={it.property_item_id}>
            <td className="py-1"><Badge variant="neutral" className="capitalize">{pretty(it.item_type)}</Badge></td>
            <td className="py-1 text-content">
              {it.description ?? "—"}
              {it.synthetic_identifier && <span className="text-11 text-content-dim"> · {it.synthetic_identifier}</span>}
            </td>
            <td className="py-1 tnum text-content-dim">{it.quantity ?? "—"}{it.unit ? ` ${it.unit}` : ""}</td>
            <td className="py-1 tnum text-content-dim">{it.estimated_value ?? "—"}</td>
            <td className="py-1">
              {canWrite ? (
                <NativeSelect value={it.status} onChange={(v) => mut.mutate({ pid: it.property_item_id, status: v })}
                              options={lookups.data?.property_statuses ?? []} placeholder={it.status}
                              aria-label="Property status" className="w-32" />
              ) : (
                <Badge variant={PROP_STATUS_BADGE[it.status] ?? "neutral"}>{pretty(it.status)}</Badge>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AddSeizureDialog({ caseId, open, onOpenChange }: { caseId: number; open: boolean; onOpenChange: (v: boolean) => void }) {
  const lookups = useCaseworkLookups();
  const [place, setPlace] = useState("");
  const [seizedAt, setSeizedAt] = useState("");
  const [memoId, setMemoId] = useState("");
  const [items, setItems] = useState<CwPropertyItemInput[]>([{ item_type: "property", description: "" }]);

  const mut = useMutation({
    mutationFn: () => api.casework.createSeizure(caseId, {
      place: place.trim() || undefined, seized_at: toISO(seizedAt),
      memo_evidence_item_id: memoId ? Number(memoId) : undefined,
      items: items.filter((i) => i.description || i.synthetic_identifier),
    }),
    onSuccess: () => onOpenChange(false),
  });

  function setItem(i: number, patch: Partial<CwPropertyItemInput>) {
    setItems((arr) => arr.map((it, idx) => (idx === i ? { ...it, ...patch } : it)));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add seizure</DialogTitle>
          <DialogDescription>Manual metadata. A seizure-memo file may be linked by evidence id.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <Input value={place} onChange={(e) => setPlace(e.target.value)} className="h-8" placeholder="Place" />
            <Input type="datetime-local" value={seizedAt} onChange={(e) => setSeizedAt(e.target.value)} className="h-8" />
            <Input value={memoId} onChange={(e) => setMemoId(e.target.value)} className="h-8" placeholder="Memo evidence id" />
          </div>
          <div className="space-y-2">
            {items.map((it, i) => (
              <div key={i} className="grid grid-cols-4 gap-2">
                <NativeSelect value={it.item_type} onChange={(v) => setItem(i, { item_type: v })}
                              options={lookups.data?.property_item_types ?? []} placeholder="property"
                              aria-label="Item type" />
                <Input value={it.description ?? ""} onChange={(e) => setItem(i, { description: e.target.value })}
                       className="h-8 col-span-2" placeholder="Description" />
                <Input value={it.synthetic_identifier ?? ""} onChange={(e) => setItem(i, { synthetic_identifier: e.target.value })}
                       className="h-8" placeholder="Synthetic ID" />
              </div>
            ))}
            <Button variant="ghost" size="sm" onClick={() => setItems((a) => [...a, { item_type: "property", description: "" }])}>
              <Plus /> Add item
            </Button>
          </div>
          {mut.error && <p className="text-12 text-severity-critical">{errorMessage(mut.error)}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-hairline pt-3">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button size="sm" onClick={() => mut.mutate()} disabled={mut.isPending}>Save seizure</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function LabPanel({ caseId, canWrite }: { caseId: number; canWrite: boolean }) {
  const qc = useQueryClient();
  const lookups = useCaseworkLookups();
  const [adding, setAdding] = useState(false);
  const q = useQuery({
    queryKey: caseworkKeys.labs(caseId),
    queryFn: ({ signal }) => api.casework.listLabs(caseId, signal),
  });
  const [testType, setTestType] = useState("chemical");
  const [labName, setLabName] = useState("");
  const [summary, setSummary] = useState("");
  const [status, setStatus] = useState("requested");
  const [reportId, setReportId] = useState("");

  const mut = useMutation({
    mutationFn: () => {
      const body: CwLabResultInput = {
        test_type: testType, lab_name: labName.trim() || undefined, result_summary: summary.trim() || undefined,
        status, report_evidence_item_id: reportId ? Number(reportId) : undefined,
      };
      return api.casework.createLab(caseId, body);
    },
    onSuccess: () => { setAdding(false); setLabName(""); setSummary(""); setReportId("");
      qc.invalidateQueries({ queryKey: caseworkKeys.labs(caseId) }); },
  });

  return (
    <div className="rounded-card border border-hairline bg-surface p-3">
      <div className="flex items-center justify-between">
        <h4 className="flex items-center gap-1.5 text-13 font-semibold text-content">
          <FlaskConical className="size-3.5" /> Lab results ({q.data?.count ?? 0})
        </h4>
        {canWrite && <Button variant="ghost" size="sm" onClick={() => setAdding((v) => !v)}><Plus /> Add</Button>}
      </div>
      <p className="text-12 text-content-dim">Optional manual metadata — a report file may be linked, never parsed.</p>

      {adding && (
        <div className="mt-2 grid grid-cols-2 gap-2 rounded-control border border-hairline bg-surface-2/40 p-3">
          <NativeSelect value={testType} onChange={setTestType} options={lookups.data?.lab_test_types ?? []}
                        placeholder="chemical" aria-label="Test type" />
          <NativeSelect value={status} onChange={setStatus} options={lookups.data?.lab_statuses ?? []}
                        placeholder="requested" aria-label="Status" />
          <Input value={labName} onChange={(e) => setLabName(e.target.value)} className="h-8" placeholder="Lab name" />
          <Input value={reportId} onChange={(e) => setReportId(e.target.value)} className="h-8" placeholder="Report evidence id" />
          <textarea value={summary} onChange={(e) => setSummary(e.target.value)} rows={2}
                    className="col-span-2 w-full rounded-control border border-hairline bg-surface px-3 py-2 text-13 text-content"
                    placeholder="Result summary (manual)" />
          {mut.error && <p className="col-span-2 text-12 text-severity-critical">{errorMessage(mut.error)}</p>}
          <div className="col-span-2 flex justify-end">
            <Button size="sm" onClick={() => mut.mutate()} disabled={mut.isPending}>Save lab result</Button>
          </div>
        </div>
      )}

      <div className="mt-2 space-y-1">
        {(q.data?.items ?? []).map((l) => (
          <div key={l.lab_result_id} className="flex flex-wrap items-center gap-2 text-13">
            <Badge variant="neutral" className="capitalize">{pretty(l.test_type)}</Badge>
            <Badge variant={l.status === "completed" ? "low" : "neutral"}>{pretty(l.status)}</Badge>
            <span className="text-content">{l.lab_name ?? "—"}</span>
            <span className={`text-12 ${l.access_limited ? "italic text-severity-high" : "text-content-dim"}`}>
              {l.result_summary ?? "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
