import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive, ArchiveRestore, Download, ExternalLink, Eye, FileText, History, Link2, Loader2, Pencil, Unlink,
} from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { EvItem, EvMetadataUpdate } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { formatDateTime, timeAgo } from "@/lib/utils";
import { formatBytes } from "@/lib/evidenceUpload";
import { ACTIVITY_LABEL, EV_STATE_LABEL, evidenceKeys, prettyType, stateBadgeVariant } from "./evidenceShared";

export function EvidenceDetailsDialog({
  itemId, caseId, canWrite, open, onOpenChange,
}: {
  itemId: number | null;
  caseId: number;
  canWrite: boolean;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [preview, setPreview] = useState<{ url: string; mime: string; text?: string } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const q = useQuery({
    queryKey: itemId ? evidenceKeys.item(itemId) : ["evidence", "item", "none"],
    queryFn: ({ signal }) => api.evidence.get(itemId as number, signal),
    enabled: open && itemId != null,
  });
  const item = q.data;

  function invalidate() {
    if (itemId) qc.invalidateQueries({ queryKey: evidenceKeys.item(itemId) });
    qc.invalidateQueries({ queryKey: ["evidence", "list", caseId] });
  }

  const download = useMutation({
    mutationFn: async (opts: { versionNo?: number; inline?: boolean }) => {
      const res = await api.evidence.downloadUrl(itemId as number, {
        versionNo: opts.versionNo, disposition: opts.inline ? "inline" : "attachment",
      });
      return { res, inline: opts.inline };
    },
    onError: (e) => setActionError(errorMessage(e)),
    onSuccess: async ({ res, inline }) => {
      setActionError(null);
      if (!inline) {
        window.open(res.url, "_blank", "noopener,noreferrer");
        invalidate();
        return;
      }
      const mime = res.mime_type ?? "";
      if (mime.startsWith("text/") || mime === "application/json") {
        try {
          const txt = await fetch(res.url).then((r) => r.text());
          setPreview({ url: res.url, mime, text: txt.slice(0, 20000) });
        } catch {
          setPreview({ url: res.url, mime, text: "(could not load preview)" });
        }
      } else {
        setPreview({ url: res.url, mime });
      }
      invalidate();
    },
  });

  const archive = useMutation({
    mutationFn: () => api.evidence.archive(itemId as number, {}),
    onError: (e) => setActionError(errorMessage(e)),
    onSuccess: () => { setActionError(null); invalidate(); },
  });
  const restore = useMutation({
    mutationFn: () => api.evidence.restore(itemId as number),
    onError: (e) => setActionError(errorMessage(e)),
    onSuccess: () => { setActionError(null); invalidate(); },
  });
  const unlinkCase = useMutation({
    mutationFn: (cid: number) => api.evidence.unlink(itemId as number, { case_id: cid }),
    onError: (e) => setActionError(errorMessage(e)),
    onSuccess: () => { setActionError(null); invalidate(); },
  });

  function close() {
    setEditing(false);
    setPreview(null);
    setActionError(null);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={(v) => (v ? onOpenChange(true) : close())}>
      <DialogContent className="max-w-3xl">
        {q.isLoading || !item ? (
          <div className="space-y-3">
            <Skeleton className="h-6 w-64" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <>
            <DialogHeader>
              <div className="flex items-center gap-2">
                <Badge variant="neutral" className="capitalize">{prettyType(item.evidence_type)}</Badge>
                <Badge variant={stateBadgeVariant(item.state)}>{EV_STATE_LABEL[item.state] ?? item.state}</Badge>
                {!item.is_synthetic && <Badge variant="primary">Public-source · non-synthetic</Badge>}
                {item.confidentiality !== "demo_normal" && (
                  <Badge variant="high">{prettyType(item.confidentiality)}</Badge>
                )}
              </div>
              <DialogTitle>{item.title}</DialogTitle>
              <DialogDescription>
                {item.synthetic_reference} · File contents are not automatically extracted.
              </DialogDescription>
            </DialogHeader>

            <div className="max-h-[68vh] space-y-4 overflow-y-auto pr-1">
              {actionError && <p className="text-12 text-severity-critical">{actionError}</p>}
              {item.is_read_only && (
                <p className="rounded-control border border-hairline bg-surface-2/50 px-3 py-2 text-12 leading-relaxed text-content-dim">
                  This source-qualified public reference is read-only. Add a separate annotation rather than editing, relinking, archiving, or attaching a file to it.
                </p>
              )}

              {/* Current file */}
              {item.current_object ? (
                <section className="rounded-card border border-hairline bg-surface-2/50 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-13 text-content">
                        <FileText className="size-4 shrink-0 text-content-dim" />
                        <span className="truncate font-medium">{item.current_object.file_name}</span>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-12 text-content-dim">
                        <span>{item.current_object.mime_type}</span>
                        <span className="tnum">{formatBytes(item.current_object.size_bytes)}</span>
                        <span className="tnum">v{item.current_object.version_no}</span>
                        <span>{item.current_object.storage_status}</span>
                      </div>
                      <div className="mt-1 break-all font-mono text-11 text-content-dim" title="SHA-256">
                        sha256: {item.current_object.sha256}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      {item.is_previewable && (
                        <Button variant="outline" size="sm" onClick={() => download.mutate({ inline: true })}
                                disabled={download.isPending}>
                          <Eye /> Preview
                        </Button>
                      )}
                      <Button variant="primary" size="sm" onClick={() => download.mutate({})}
                              disabled={download.isPending}>
                        {download.isPending ? <Loader2 className="animate-spin" /> : <Download />} Download
                      </Button>
                    </div>
                  </div>

                  {preview && (
                    <div className="mt-3 overflow-hidden rounded-control border border-hairline bg-surface">
                      {preview.mime.startsWith("image/") ? (
                        <img src={preview.url} alt={item.title} className="mx-auto max-h-[360px]" />
                      ) : preview.mime === "application/pdf" ? (
                        <iframe title="preview" src={preview.url} className="h-[420px] w-full" />
                      ) : (
                        <pre className="max-h-[360px] overflow-auto p-3 text-11 text-content">{preview.text}</pre>
                      )}
                    </div>
                  )}
                </section>
              ) : (
                <p className="rounded-card border border-dashed border-hairline p-3 text-12 text-content-dim">
                  No file stored for this item (metadata-only / external reference).
                </p>
              )}

              {/* Metadata */}
              <section>
                <div className="mb-1 flex items-center justify-between">
                  <h4 className="text-13 font-semibold text-content">Metadata</h4>
                  {canWrite && !item.is_read_only && item.state !== "archived" && (
                    <Button variant="ghost" size="sm" onClick={() => setEditing((v) => !v)}>
                      <Pencil /> {editing ? "Close" : "Correct"}
                    </Button>
                  )}
                </div>
                {editing ? (
                  <EditForm item={item} onDone={() => { setEditing(false); invalidate(); }} />
                ) : (
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-12">
                    <Meta k="Category" v={prettyType(item.category)} />
                    <Meta k="Language" v={item.language} />
                    <Meta k="Captured" v={item.captured_at ? formatDateTime(item.captured_at) : "—"} />
                    <Meta k="Uploaded" v={item.uploaded_at ? formatDateTime(item.uploaded_at) : "—"} />
                    <Meta k="Uploader" v={item.uploader_actor} />
                    <Meta k="Tags" v={item.tags.join(", ") || "—"} />
                    {item.description && <Meta k="Description" v={item.description} span />}
                  </dl>
                )}
              </section>

              {!item.is_synthetic && (
                <PublicReferenceMetadata metadata={item.manual_metadata} />
              )}

              {/* Links */}
              <section>
                <h4 className="mb-1 flex items-center gap-1.5 text-13 font-semibold text-content">
                  <Link2 className="size-3.5" /> Linked cases & entities
                </h4>
                <div className="space-y-1">
                  {item.case_links.map((l) => (
                    <div key={l.evidence_case_link_id} className="flex items-center justify-between text-12">
                      <span className="text-content">
                        {l.crime_no?.trim() ? `Case ${l.crime_no.trim()}` : `Internal case ID #${l.case_master_id}`} · {l.link_type}
                      </span>
                      {canWrite && !item.is_read_only && item.case_links.length > 1 && (
                        <Button variant="ghost" size="icon-sm" aria-label="Unlink case"
                                onClick={() => unlinkCase.mutate(l.case_master_id)}>
                          <Unlink />
                        </Button>
                      )}
                    </div>
                  ))}
                  {item.entity_links.map((l) => (
                    <div key={l.evidence_entity_link_id} className="text-12 text-content-dim">
                      Entity {l.entity_ref ?? l.canonical_entity_id} · {l.link_type} ({l.review_status})
                    </div>
                  ))}
                  {item.case_links.length === 0 && item.entity_links.length === 0 && (
                    <p className="text-12 text-content-dim">Not linked to any case or entity.</p>
                  )}
                </div>
              </section>

              {/* Versions */}
              {item.versions.length > 0 && (
                <section>
                  <h4 className="mb-1 text-13 font-semibold text-content">Versions ({item.versions.length})</h4>
                  <div className="space-y-1">
                    {item.versions.slice().reverse().map((v) => (
                      <div key={v.evidence_version_id} className="flex items-center justify-between text-12">
                        <span className="text-content">v{v.version_no} · {v.change_reason ?? "—"}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-content-dim">{v.created_at ? timeAgo(v.created_at) : ""}</span>
                          <Button variant="ghost" size="icon-sm" aria-label={`Download v${v.version_no}`}
                                  onClick={() => download.mutate({ versionNo: v.version_no })}>
                            <Download />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Activity timeline */}
              <section>
                <h4 className="mb-1 flex items-center gap-1.5 text-13 font-semibold text-content">
                  <History className="size-3.5" /> Activity
                </h4>
                <ol className="space-y-1.5 border-l border-hairline pl-3">
                  {item.activity.map((a) => (
                    <li key={a.evidence_activity_event_id} className="relative text-12">
                      <span className="absolute -left-[15px] top-1 size-2 rounded-full bg-primary/70" />
                      <span className="text-content">{ACTIVITY_LABEL[a.event_type] ?? a.event_type}</span>
                      {a.actor && <span className="text-content-dim"> · {a.actor}</span>}
                      {a.created_at && (
                        <span className="text-content-dim" title={formatDateTime(a.created_at)}> · {timeAgo(a.created_at)}</span>
                      )}
                    </li>
                  ))}
                </ol>
              </section>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-hairline pt-3">
              {canWrite && !item.is_read_only && (item.state === "archived" ? (
                <Button variant="outline" size="sm" onClick={() => restore.mutate()} disabled={restore.isPending}>
                  <ArchiveRestore /> Restore
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => archive.mutate()} disabled={archive.isPending}>
                  <Archive /> Archive
                </Button>
              ))}
              <Button size="sm" onClick={close}>Close</Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PublicReferenceMetadata({ metadata }: { metadata: Record<string, unknown> }) {
  const sourceUrl = safeUrl(metadata.external_reference_url);
  const assetUrl = safeUrl(metadata.remote_asset_url);
  const notCaseEvidence = metadata.not_case_evidence === true;
  const rows = [
    ["Source ID", textMeta(metadata.public_source_id)],
    ["Publisher", textMeta(metadata.publisher)],
    ["Publication date", textMeta(metadata.publication_date)],
    ["Authenticity", textMeta(metadata.authenticity)],
    ["Presentation use", textMeta(metadata.presentation_use)],
    ["Rights & handling", textMeta(metadata.rights_and_handling)],
    ["Caveat", textMeta(metadata.notes)],
  ].filter((row): row is [string, string] => row[1] != null);

  return (
    <section className="rounded-card border border-hairline bg-surface-2/40 p-3">
      <h4 className="text-13 font-semibold text-content">Public-reference provenance</h4>
      {notCaseEvidence && (
        <p className="mt-1 text-12 font-medium text-severity-medium">
          Presentation/source context only — this item is explicitly not case evidence.
        </p>
      )}
      <dl className="mt-2 grid grid-cols-1 gap-2 text-12 sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <Meta key={label} k={label} v={value} span={label.length > 16} />
        ))}
      </dl>
      <div className="mt-3 flex flex-wrap gap-2">
        {sourceUrl && (
          <a href={sourceUrl} target="_blank" rel="noreferrer"
             className="inline-flex items-center gap-1 text-12 font-medium text-primary hover:underline">
            Open attributed source <ExternalLink className="size-3" />
          </a>
        )}
        {assetUrl && (
          <a href={assetUrl} target="_blank" rel="noreferrer"
             className="inline-flex items-center gap-1 text-12 font-medium text-primary hover:underline">
            Open publisher-hosted asset <ExternalLink className="size-3" />
          </a>
        )}
      </div>
    </section>
  );
}

function textMeta(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function safeUrl(value: unknown): string | null {
  const url = textMeta(value);
  return url?.startsWith("https://") ? url : null;
}

function Meta({ k, v, span }: { k: string; v?: string | null; span?: boolean }) {
  return (
    <div className={span ? "col-span-2" : ""}>
      <dt className="text-content-dim">{k}</dt>
      <dd className="text-content">{v || "—"}</dd>
    </div>
  );
}

function EditForm({ item, onDone }: { item: EvItem; onDone: () => void }) {
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description ?? "");
  const [tags, setTags] = useState(item.tags.join(", "));
  const [reason, setReason] = useState("");

  const mut = useMutation({
    mutationFn: () => {
      const body: EvMetadataUpdate = {
        title: title.trim(),
        description: description.trim(),
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        change_reason: reason.trim() || undefined,
      };
      return api.evidence.update(item.evidence_item_id, body);
    },
    onSuccess: onDone,
  });

  return (
    <div className="space-y-2 rounded-control border border-hairline bg-surface-2/40 p-3">
      <Input value={title} onChange={(e) => setTitle(e.target.value)} className="h-8" placeholder="Title" />
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2}
                className="w-full rounded-control border border-hairline bg-surface px-3 py-2 text-13 text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                placeholder="Description" />
      <Input value={tags} onChange={(e) => setTags(e.target.value)} className="h-8" placeholder="Tags (comma separated)" />
      <Input value={reason} onChange={(e) => setReason(e.target.value)} className="h-8" placeholder="Correction reason (recorded in activity)" />
      {mut.error && <p className="text-12 text-severity-critical">{errorMessage(mut.error)}</p>}
      <div className="flex justify-end">
        <Button size="sm" onClick={() => mut.mutate()} disabled={mut.isPending || !title.trim()}>
          {mut.isPending ? "Saving…" : "Save correction"}
        </Button>
      </div>
    </div>
  );
}
