import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, Info, Paperclip, Plus } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { EvListItem } from "@/api/types";
import { useRole } from "@/providers/RoleProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { formatDateTime, timeAgo } from "@/lib/utils";
import { formatBytes } from "@/lib/evidenceUpload";
import { AddEvidenceDialog } from "./evidence/AddEvidenceDialog";
import { EvidenceDetailsDialog } from "./evidence/EvidenceDetailsDialog";
import {
  EV_STATE_LABEL, evidenceKeys, prettyType, shortHash, stateBadgeVariant, useEvidenceStatus,
} from "./evidence/evidenceShared";

/* Evidence sub-page (Phase 5): digital evidence upload to private S3 + manual
   metadata. Replaces the old metadata-only CaseEvidence form. Browser -> FastAPI
   -> PostgreSQL/S3 only; file contents are never auto-extracted; an upload never
   triggers a prediction. */

const STATE_TABS = ["all", "available", "draft", "uploading", "failed", "archived"] as const;

export function EvidencePage({ caseId }: { caseId: number }) {
  const { role } = useRole();
  const canWrite = role === "investigator" || role === "supervisor" || role === "super_admin";

  const status = useEvidenceStatus();
  const [stateFilter, setStateFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);

  const filters = useMemo(
    () => ({ state: stateFilter === "all" ? undefined : stateFilter, q: search.trim() || undefined }),
    [stateFilter, search],
  );

  const q = useQuery({
    queryKey: evidenceKeys.list(caseId, filters),
    queryFn: ({ signal }) =>
      api.evidence.list({ case_id: caseId, ...filters, page_size: 200 }, signal),
  });

  const items = q.data?.items ?? [];
  const byState = q.data?.by_state ?? {};
  const total = q.data?.total ?? 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-14 font-semibold text-content">Evidence ({total})</h3>
        {canWrite && (
          <Button variant="primary" size="sm" onClick={() => setAdding(true)}>
            <Plus /> Add evidence
          </Button>
        )}
      </div>

      {/* Extraction / storage note */}
      <div className="flex items-start gap-2 rounded-card border border-hairline bg-surface-2/40 px-3 py-2 text-12 text-content-dim">
        <Info className="mt-0.5 size-3.5 shrink-0" />
        <span>
          File contents are not automatically extracted. Every file gets a system-generated
          SHA-256, size and version; all metadata is entered manually.
          {status.data && !status.data.s3_configured && (
            <> Storage is not configured yet — metadata-only evidence can still be recorded.</>
          )}
        </span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1">
          {STATE_TABS.map((s) => {
            const count = s === "all" ? total : byState[s] ?? 0;
            const active = stateFilter === s;
            return (
              <button
                key={s}
                type="button"
                onClick={() => setStateFilter(s)}
                className={`rounded-control px-2.5 py-1 text-12 font-medium transition-colors ${
                  active ? "bg-surface-2 text-content" : "text-content-dim hover:bg-surface-2/60"
                }`}
              >
                {s === "all" ? "All" : EV_STATE_LABEL[s]}{" "}
                <span className="tnum text-content-dim">{count}</span>
              </button>
            );
          })}
        </div>
        <div className="ml-auto w-full sm:w-56">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} className="h-8"
                 placeholder="Search title / reference…" />
        </div>
      </div>

      {q.isLoading && (
        <div className="space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      )}
      {q.error && <p className="text-13 text-content-dim">{errorMessage(q.error)}</p>}

      {!q.isLoading && items.length === 0 && (
        <EmptyState
          icon={q.error ? FileText : Paperclip}
          title="No evidence recorded"
          description={
            canWrite
              ? 'Use "Add evidence" to attach an already-digital file with manual metadata, or record an external reference.'
              : "No evidence items have been added to this case yet."
          }
        />
      )}

      {items.length > 0 && (
        <div className="overflow-hidden rounded-card border border-hairline bg-surface">
          <table className="w-full text-13">
            <thead>
              <tr className="border-b border-hairline text-left text-12 text-content-dim">
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Title</th>
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium">Captured</th>
                <th className="px-3 py-2 font-medium">Ver</th>
                <th className="px-3 py-2 font-medium">Hash</th>
                <th className="px-3 py-2 font-medium">State</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {items.map((e) => (
                <EvidenceRow key={e.evidence_item_id} item={e} onOpen={() => setDetailId(e.evidence_item_id)} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {adding && (
        <AddEvidenceDialog caseId={caseId} status={status.data} open={adding} onOpenChange={setAdding} />
      )}
      <EvidenceDetailsDialog
        itemId={detailId}
        caseId={caseId}
        canWrite={canWrite}
        open={detailId != null}
        onOpenChange={(v) => !v && setDetailId(null)}
      />
    </div>
  );
}

function EvidenceRow({ item, onOpen }: { item: EvListItem; onOpen: () => void }) {
  return (
    <tr className="cursor-pointer hover:bg-surface-2/50" onClick={onOpen}>
      <td className="px-3 py-2">
        <Badge variant="neutral" className="capitalize">{prettyType(item.evidence_type)}</Badge>
      </td>
      <td className="px-3 py-2">
        <div className="font-medium text-content">{item.title}</div>
        <div className="flex flex-wrap gap-1 pt-0.5">
          {item.tags.slice(0, 3).map((t) => (
            <span key={t} className="rounded bg-surface-2 px-1.5 py-0.5 text-11 text-content-dim">{t}</span>
          ))}
          {item.file_name && (
            <span className="text-11 text-content-dim">{item.file_name} · {formatBytes(item.size_bytes)}</span>
          )}
        </div>
      </td>
      <td className="px-3 py-2 text-content-dim">{item.source_label ?? "—"}</td>
      <td className="px-3 py-2 tnum text-content-dim" title={item.captured_at ? formatDateTime(item.captured_at) : ""}>
        {item.captured_at ? timeAgo(item.captured_at) : item.created_at ? timeAgo(item.created_at) : "—"}
      </td>
      <td className="px-3 py-2 tnum text-content-dim">{item.version_no ? `v${item.version_no}` : "—"}</td>
      <td className="px-3 py-2 font-mono text-11 text-content-dim" title={item.sha256 ?? ""}>
        {shortHash(item.sha256)}
      </td>
      <td className="px-3 py-2">
        <Badge variant={stateBadgeVariant(item.state)}>{EV_STATE_LABEL[item.state] ?? item.state}</Badge>
      </td>
    </tr>
  );
}
