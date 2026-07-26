import { useMemo, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  keepPreviousData,
} from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileUp,
  Loader2,
  PlayCircle,
  RotateCcw,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { cn, formatNumber } from "@/lib/utils";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { NativeSelect } from "@/components/ui/native-select";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/routes/intake/components";
import type {
  ImpBatch,
  ImpMoneyAlert,
  ImpStagingRow,
} from "@/api/types";


/** Trigger a client-side download of text content (error/row export). */
function downloadText(name: string, text: string, mime = "text/csv") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function rowsToCsv(rows: ImpStagingRow[]): string {
  const head = "row_number,status,reject_reason,mapped_json";
  const body = rows.map((r) =>
    [r.row_number ?? "", r.status, JSON.stringify(r.reject_reason ?? ""),
     JSON.stringify(JSON.stringify(r.mapped ?? {}))].join(","),
  );
  return [head, ...body].join("\n");
}

const STATUS_VARIANT: Record<string, "neutral" | "primary" | "low" | "medium" | "high"> = {
  staged: "neutral", dry_run: "primary", committed: "low", partial: "medium",
  rolled_back: "high", superseded: "neutral", failed: "high",
  valid: "low", rejected: "high", duplicate: "medium",
  open: "medium", reviewed: "low", dismissed: "neutral", escalated: "high",
  confirmed_pattern: "high", false_positive: "neutral", candidate: "medium",
};

function Pill({ status }: { status: string }) {
  return (
    <Badge variant={STATUS_VARIANT[status] ?? "neutral"} className="capitalize">
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

/* ==========================================================================
   1. Import inbox + new-import wizard (dry-run -> commit -> rollback)
   ========================================================================== */
export function ImportInboxPanel() {
  const { role } = useRole();
  const qc = useQueryClient();
  const canReview = roleCan(role, "imports_review");

  const [tvId, setTvId] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [fmt, setFmt] = useState<"csv" | "json">("csv");
  const [caseId, setCaseId] = useState<string>("");
  const [batch, setBatch] = useState<ImpBatch | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const templatesQ = useQuery({
    queryKey: ["imports", "templates"],
    queryFn: ({ signal }) => api.imports.templates(signal),
  });
  const batchesQ = useQuery({
    queryKey: ["imports", "batches"],
    queryFn: ({ signal }) => api.imports.listBatches({ page_size: 25 }, signal),
    placeholderData: keepPreviousData,
  });

  const versionOptions = useMemo(() => {
    const opts: { value: string; label: string }[] = [];
    for (const t of templatesQ.data?.templates ?? []) {
      for (const v of t.versions) {
        if (v.status === "approved")
          opts.push({ value: String(v.import_template_version_id), label: `${t.code} · ${v.version} (${t.domain})` });
      }
    }
    return opts;
  }, [templatesQ.data]);

  const dryRun = useMutation({
    mutationFn: () =>
      api.imports.createBatch({
        import_template_version_id: Number(tvId),
        content,
        source_format: fmt,
        source_file_name: fileName || undefined,
        case_master_id: caseId ? Number(caseId) : undefined,
        created_by_actor: role,
      }),
    onSuccess: (b) => { setBatch(b); setMsg(null); qc.invalidateQueries({ queryKey: ["imports", "batches"] }); },
    onError: (e) => setMsg(errorMessage(e)),
  });

  const commit = useMutation({
    mutationFn: (id: number) => api.imports.commit(id, role),
    onSuccess: (res) => {
      setMsg(`Committed ${res.committed} row(s) to ${res.target_table} — ${res.candidate_entity_links} candidate entity link(s) created for review.`);
      qc.invalidateQueries({ queryKey: ["imports"] });
      if (batch) void api.imports.getBatch(batch.import_batch_id).then(setBatch).catch(() => {});
    },
    onError: (e) => setMsg(errorMessage(e)),
  });

  const rollback = useMutation({
    mutationFn: (id: number) => api.imports.rollback(id, { actor: role, reason: "reverted from UI" }),
    onSuccess: (res) => {
      setMsg(`Rolled back — ${res.canonical_rows_deleted} canonical row(s) deleted, ${res.source_records_retracted} source record(s) retracted.`);
      qc.invalidateQueries({ queryKey: ["imports"] });
      if (batch) void api.imports.getBatch(batch.import_batch_id).then(setBatch).catch(() => {});
    },
    onError: (e) => setMsg(errorMessage(e)),
  });

  const onFile = async (file: File) => {
    setMsg(null);
    setBatch(null);
    try {
      const text = await file.text();
      setContent(text);
      setFileName(file.name);
      setFmt(file.name.toLowerCase().endsWith(".json") ? "json" : "csv");
    } catch (e) {
      setMsg(errorMessage(e));
    }
  };

  const downloadErrors = async (id: number) => {
    const [rej, dup] = await Promise.all([
      api.imports.rows(id, { status: "rejected", page_size: 500 }),
      api.imports.rows(id, { status: "duplicate", page_size: 500 }),
    ]);
    downloadText(`import_${id}_errors.csv`, rowsToCsv([...rej.items, ...dup.items]));
  };

  const t = batch?.totals ?? {};

  return (
    <div className="space-y-4">
      <SectionCard
        title="New structured import"
        description="Upload a CSV/JSON file (stored as evidence), pick a template version, and dry-run before committing. Structured data only — file contents are never OCR-extracted."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block space-y-1">
            <span className="text-12 font-medium text-content-dim">Template / schema version</span>
            <NativeSelect value={tvId} onChange={setTvId} options={versionOptions}
              placeholder={templatesQ.isLoading ? "Loading…" : "Choose a template version"} aria-label="template version" />
          </label>
          <label className="block space-y-1">
            <span className="text-12 font-medium text-content-dim">Link to case (optional)</span>
            <input value={caseId} onChange={(e) => setCaseId(e.target.value.replace(/[^0-9]/g, ""))}
              placeholder="Case master id"
              className="h-8 w-full rounded-control border border-hairline bg-surface-2 px-2.5 text-13 text-content focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60" />
          </label>
        </div>

        <label className="mt-3 flex cursor-pointer items-center gap-2 rounded-control border border-dashed border-hairline bg-surface-2 px-4 py-5 text-13 text-content-dim hover:bg-surface-2/70">
          <UploadCloud className="size-5" />
          <span>{fileName || "Choose a .csv or .json file"}</span>
          <input type="file" accept=".csv,.json" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void onFile(f); }} />
        </label>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={!tvId || !content || dryRun.isPending} onClick={() => dryRun.mutate()}>
            {dryRun.isPending ? <Loader2 className="animate-spin" /> : <PlayCircle />} Dry run
          </Button>
          {batch && (batch.status === "staged" || batch.status === "dry_run") && canReview && (
            <Button size="sm" variant="outline" disabled={commit.isPending || (t.valid ?? 0) === 0}
              onClick={() => commit.mutate(batch.import_batch_id)}>
              {commit.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Approve & commit {t.valid ?? 0}
            </Button>
          )}
          {batch && !canReview && (batch.status === "staged" || batch.status === "dry_run") && (
            <span className="text-12 text-content-dim">A supervisor approves the commit.</span>
          )}
          {batch && (batch.status === "committed" || batch.status === "partial") && canReview && (
            <Button size="sm" variant="ghost" disabled={rollback.isPending}
              onClick={() => rollback.mutate(batch.import_batch_id)}>
              {rollback.isPending ? <Loader2 className="animate-spin" /> : <RotateCcw />} Roll back
            </Button>
          )}
        </div>

        {msg && <p className="mt-2 text-12 text-content">{msg}</p>}
        {dryRun.error && <p className="mt-2 flex items-center gap-1 text-12 text-severity-high"><AlertTriangle className="size-3" />{errorMessage(dryRun.error)}</p>}
      </SectionCard>

      {batch && <DryRunReport batch={batch} onDownloadErrors={() => downloadErrors(batch.import_batch_id)} />}

      <SectionCard title="Import inbox" description="Recent import batches across digital and financial domains.">
        {batchesQ.error ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load batches" description={errorMessage(batchesQ.error)} />
        ) : (batchesQ.data?.items.length ?? 0) === 0 ? (
          <EmptyState icon={FileUp} title="No import batches yet" description="Dry-run a file above to create the first batch." />
        ) : (
          <div className="overflow-x-auto rounded-control border border-hairline">
            <table className="w-full text-13">
              <thead className="bg-surface-2 text-12 text-content-dim">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Batch</th>
                  <th className="px-3 py-2 text-left font-medium">Domain</th>
                  <th className="px-3 py-2 text-left font-medium">Template</th>
                  <th className="px-3 py-2 text-left font-medium">Status</th>
                  <th className="px-3 py-2 text-right font-medium">Valid</th>
                  <th className="px-3 py-2 text-right font-medium">Rejected</th>
                  <th className="px-3 py-2 text-right font-medium">Dupes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {batchesQ.data?.items.map((b) => (
                  <tr key={b.import_batch_id} className="hover:bg-surface-2/50">
                    <td className="px-3 py-2 tnum text-content-dim">#{b.import_batch_id}</td>
                    <td className="px-3 py-2 capitalize text-content-dim">{b.domain.replace(/_/g, " ")}</td>
                    <td className="px-3 py-2 text-content-dim">{b.template_code ?? "—"}</td>
                    <td className="px-3 py-2"><Pill status={b.status} /></td>
                    <td className="px-3 py-2 text-right tnum">{formatNumber(b.totals.valid ?? b.totals.committed ?? 0)}</td>
                    <td className="px-3 py-2 text-right tnum text-severity-high">{formatNumber(b.totals.rejected ?? 0)}</td>
                    <td className="px-3 py-2 text-right tnum text-severity-medium">{formatNumber(b.totals.duplicate ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}

function DryRunReport({ batch, onDownloadErrors }: { batch: ImpBatch; onDownloadErrors: () => void }) {
  const t = batch.totals;
  const fields = (batch.mapping?.fields as Array<Record<string, unknown>>) ?? [];
  const hasErrors = (t.rejected ?? 0) + (t.duplicate ?? 0) > 0;
  return (
    <SectionCard
      title={`Dry-run report — batch #${batch.import_batch_id}`}
      description={`${batch.template_code} · target ${batch.target_table} · ${batch.status}`}
    >
      <div className="mb-3 flex flex-wrap gap-2">
        <Stat label="Parsed" value={t.parsed ?? 0} />
        <Stat label="Valid" value={t.valid ?? 0} tone="low" />
        <Stat label="Rejected" value={t.rejected ?? 0} tone="high" />
        <Stat label="Duplicate" value={t.duplicate ?? 0} tone="medium" />
        {t.committed != null && <Stat label="Committed" value={t.committed} tone="low" />}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-12 font-medium text-content-dim">Column mapping (canonical ← source)</div>
          <div className="rounded-control border border-hairline">
            <table className="w-full text-12">
              <tbody className="divide-y divide-hairline">
                {fields.map((f, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1 text-content">{String(f.canonical)}</td>
                    <td className="px-2 py-1 text-content-dim">← {String(f.source)}</td>
                    <td className="px-2 py-1 text-right text-content/60">
                      {f.required ? "required" : "optional"} · {String(f.type)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-12 font-medium text-content-dim">Sample rows</span>
            {hasErrors && (
              <Button size="sm" variant="ghost" onClick={onDownloadErrors}><Download /> Download errors</Button>
            )}
          </div>
          <div className="max-h-64 overflow-auto rounded-control border border-hairline">
            <table className="w-full text-12">
              <thead className="sticky top-0 bg-surface-2 text-content-dim">
                <tr><th className="px-2 py-1 text-left">#</th><th className="px-2 py-1 text-left">Status</th><th className="px-2 py-1 text-left">Detail</th></tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {batch.sample_rows.map((r) => (
                  <tr key={r.import_staging_row_id ?? r.row_number}>
                    <td className="px-2 py-1 tnum text-content-dim">{r.row_number}</td>
                    <td className="px-2 py-1"><Pill status={r.status} /></td>
                    <td className="px-2 py-1 text-content-dim">
                      {r.reject_reason ?? Object.entries(r.mapped).slice(0, 2).map(([k, v]) => `${k}=${v}`).join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "low" | "medium" | "high" }) {
  const toneCls = tone === "high" ? "text-severity-high" : tone === "medium" ? "text-severity-medium"
    : tone === "low" ? "text-severity-low" : "text-content";
  return (
    <div className="rounded-control border border-hairline bg-surface-2 px-3 py-1.5">
      <div className={cn("text-16 font-semibold tnum", toneCls)}>{formatNumber(value)}</div>
      <div className="text-11 text-content-dim">{label}</div>
    </div>
  );
}

/* ==========================================================================
   2. Reviewed entity-link queue
   ========================================================================== */
export function EntityLinksPanel() {
  const { role } = useRole();
  const qc = useQueryClient();
  const canReview = roleCan(role, "imports_review");
  const [status, setStatus] = useState<string>("candidate");

  const q = useQuery({
    queryKey: ["imports", "entity-links", status],
    queryFn: ({ signal }) => api.imports.entityLinks({ review_status: status || undefined, page_size: 100 }, signal),
    placeholderData: keepPreviousData,
  });

  const review = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: "accept" | "reject" }) =>
      api.imports.reviewEntityLink(id, decision, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["imports", "entity-links"] }),
  });

  return (
    <SectionCard
      title="Reviewed entity-link queue"
      description="Evidence→entity links created by imports are CANDIDATES until reviewed. Accepting promotes a link to reviewed; a link is never confirmed automatically."
    >
      <div className="mb-3 w-56">
        <NativeSelect value={status} onChange={setStatus} placeholder="All"
          options={[{ value: "candidate", label: "Candidate" }, { value: "reviewed", label: "Reviewed" }, { value: "rejected", label: "Rejected" }]}
          aria-label="review status" />
      </div>
      {q.error ? (
        <EmptyState icon={AlertTriangle} title="Couldn't load links" description={errorMessage(q.error)} />
      ) : (q.data?.items.length ?? 0) === 0 ? (
        <EmptyState icon={CheckCircle2} title="Queue clear" description="No entity links in this state." />
      ) : (
        <div className="overflow-x-auto rounded-control border border-hairline">
          <table className="w-full text-13">
            <thead className="bg-surface-2 text-12 text-content-dim">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Entity</th>
                <th className="px-3 py-2 text-left font-medium">Kind</th>
                <th className="px-3 py-2 text-left font-medium">Link</th>
                <th className="px-3 py-2 text-left font-medium">Evidence</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Review</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {q.data?.items.map((l) => (
                <tr key={l.evidence_entity_link_id} className="hover:bg-surface-2/50">
                  <td className="px-3 py-2 text-content">{l.entity_label ?? l.entity_ref ?? l.canonical_entity_id}</td>
                  <td className="px-3 py-2 capitalize text-content-dim">{l.entity_kind ?? "—"}</td>
                  <td className="px-3 py-2 text-content-dim">{l.link_type}</td>
                  <td className="px-3 py-2 text-content-dim">{l.evidence_title ?? (l.evidence_item_id ? `#${l.evidence_item_id}` : "—")}</td>
                  <td className="px-3 py-2"><Pill status={l.review_status} /></td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1.5">
                      {canReview && l.review_status === "candidate" ? (
                        <>
                          <Button size="sm" variant="outline" disabled={review.isPending}
                            onClick={() => review.mutate({ id: l.evidence_entity_link_id, decision: "accept" })}>Accept</Button>
                          <Button size="sm" variant="ghost" disabled={review.isPending}
                            onClick={() => review.mutate({ id: l.evidence_entity_link_id, decision: "reject" })}>Reject</Button>
                        </>
                      ) : (
                        <span className="text-12 text-content-dim">{l.reviewed_by_actor ?? "—"}</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

/* ==========================================================================
   3. Accounts & transactions (money_trail permission, server-side)
   ========================================================================== */
export function AccountsPanel() {
  const [flagged, setFlagged] = useState<string>("");
  const accountsQ = useQuery({
    queryKey: ["imports", "accounts", flagged],
    queryFn: ({ signal }) => api.imports.accounts({ flagged: flagged === "" ? undefined : flagged === "true", page_size: 25 }, signal),
    placeholderData: keepPreviousData,
  });
  const txnQ = useQuery({
    queryKey: ["imports", "transactions"],
    queryFn: ({ signal }) => api.imports.transactions({ page_size: 25 }, signal),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="space-y-4">
      <SectionCard title="Accounts" description="Bank / wallet accounts (financial data is permission-gated).">
        <div className="mb-3 w-48">
          <NativeSelect value={flagged} onChange={setFlagged} placeholder="All accounts"
            options={[{ value: "true", label: "Flagged only" }, { value: "false", label: "Not flagged" }]} aria-label="flagged" />
        </div>
        {accountsQ.error ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load accounts" description={errorMessage(accountsQ.error)} />
        ) : (
          <div className="overflow-x-auto rounded-control border border-hairline">
            <table className="w-full text-13">
              <thead className="bg-surface-2 text-12 text-content-dim">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Account</th>
                  <th className="px-3 py-2 text-left font-medium">Type</th>
                  <th className="px-3 py-2 text-left font-medium">Bank</th>
                  <th className="px-3 py-2 text-left font-medium">Owner review</th>
                  <th className="px-3 py-2 text-right font-medium">Flagged</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {accountsQ.data?.items.map((a) => (
                  <tr key={a.account_id} className="hover:bg-surface-2/50">
                    <td className="px-3 py-2 tnum text-content">{a.account_no ?? a.account_id}</td>
                    <td className="px-3 py-2 capitalize text-content-dim">{a.account_type ?? "—"}</td>
                    <td className="px-3 py-2 text-content-dim">{a.bank ?? "—"}</td>
                    <td className="px-3 py-2"><Pill status={a.owner_review_status ?? "candidate"} /></td>
                    <td className="px-3 py-2 text-right">{a.is_flagged ? <Badge variant="high">flagged</Badge> : <span className="text-content-dim">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Transactions" description="Directed money movements. Reviewed links carry provenance.">
        {txnQ.error ? (
          <EmptyState icon={AlertTriangle} title="Couldn't load transactions" description={errorMessage(txnQ.error)} />
        ) : (
          <div className="overflow-x-auto rounded-control border border-hairline">
            <table className="w-full text-13">
              <thead className="bg-surface-2 text-12 text-content-dim">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Txn</th>
                  <th className="px-3 py-2 text-right font-medium">Amount</th>
                  <th className="px-3 py-2 text-left font-medium">Channel</th>
                  <th className="px-3 py-2 text-left font-medium">When</th>
                  <th className="px-3 py-2 text-left font-medium">Review</th>
                  <th className="px-3 py-2 text-right font-medium">Flag</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {txnQ.data?.items.map((t) => (
                  <tr key={t.transaction_id} className="hover:bg-surface-2/50">
                    <td className="px-3 py-2 tnum text-content-dim">#{t.transaction_id}</td>
                    <td className="px-3 py-2 text-right tnum text-content">{t.currency ?? "INR"} {formatNumber(t.amount)}</td>
                    <td className="px-3 py-2 text-content-dim">{t.normalized_channel ?? t.channel ?? "—"}</td>
                    <td className="px-3 py-2 tnum text-content-dim">{t.txn_timestamp?.slice(0, 16).replace("T", " ") ?? "—"}</td>
                    <td className="px-3 py-2"><Pill status={t.review_status ?? "candidate"} /></td>
                    <td className="px-3 py-2 text-right">{t.is_flagged ? <Badge variant="high">{t.flag_reason ?? "flagged"}</Badge> : <span className="text-content-dim">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </div>
  );
}

/* ==========================================================================
   4. Money alerts (rule-based, reason-coded, evidence-backed, reviewable)
   ========================================================================== */
export function MoneyAlertsPanel({ caseId }: { caseId?: number }) {
  const { role } = useRole();
  const qc = useQueryClient();
  const canReview = roleCan(role, "imports_review");

  const alertsQ = useQuery({
    queryKey: ["imports", "money-alerts", caseId ?? "all"],
    queryFn: ({ signal }) => api.imports.moneyAlerts({ case_id: caseId, page_size: 50 }, signal),
    placeholderData: keepPreviousData,
  });

  const scan = useMutation({
    mutationFn: () => api.imports.moneyScan({ structuring_min_count: 4, structuring_window_days: 14 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["imports", "money-alerts"] }),
  });
  const dispose = useMutation({
    mutationFn: ({ id, disposition }: { id: number; disposition: string }) =>
      api.imports.moneyDisposition(id, { disposition, actor: role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["imports", "money-alerts"] }),
  });

  return (
    <SectionCard
      title="Money alerts"
      description="Rule-based structuring / layering / circular patterns with an explicit reason code, source + evidence provenance and a reviewer disposition. A pattern is investigation support only — never proof of guilt."
    >
      <div className="mb-3 flex items-center gap-2">
        {canReview && (
          <Button size="sm" variant="outline" disabled={scan.isPending} onClick={() => scan.mutate()}>
            {scan.isPending ? <Loader2 className="animate-spin" /> : <PlayCircle />} Run detection scan
          </Button>
        )}
        {scan.data && <span className="text-12 text-content-dim">{scan.data.result.answer}</span>}
        {scan.error && <span className="text-12 text-severity-high">{errorMessage(scan.error)}</span>}
      </div>
      {alertsQ.error ? (
        <EmptyState icon={AlertTriangle} title="Couldn't load alerts" description={errorMessage(alertsQ.error)} />
      ) : (alertsQ.data?.items.length ?? 0) === 0 ? (
        <EmptyState icon={CheckCircle2} title="No money alerts" description="Run a detection scan to surface rule-based patterns." />
      ) : (
        <div className="space-y-2">
          {alertsQ.data?.items.map((a) => (
            <AlertCard key={a.money_alert_id} alert={a} canReview={canReview}
              busy={dispose.isPending}
              onDispose={(d) => dispose.mutate({ id: a.money_alert_id, disposition: d })} />
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function AlertCard({ alert, canReview, busy, onDispose }: {
  alert: ImpMoneyAlert; canReview: boolean; busy: boolean; onDispose: (d: string) => void;
}) {
  const sevVariant = alert.severity === "critical" || alert.severity === "high" ? "high"
    : alert.severity === "medium" ? "medium" : "neutral";
  return (
    <div className="rounded-control border border-hairline bg-surface-2 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={sevVariant} className="capitalize">{alert.severity}</Badge>
        <span className="text-13 font-medium text-content">{alert.title}</span>
        <code className="rounded bg-surface px-1.5 py-0.5 text-11 text-content-dim">{alert.reason_code}</code>
        <Pill status={alert.status} />
      </div>
      <p className="mt-1.5 text-12 text-content-dim">{alert.message}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-11 text-content/60">
        {alert.account_id != null && <span>account #{alert.account_id}</span>}
        {alert.case_master_id != null && <span>case #{alert.case_master_id}</span>}
        {alert.evidence_item_id != null && <span>evidence #{alert.evidence_item_id}</span>}
        <span>{alert.transaction_ids.length} txn</span>
        <span>{alert.source_record_ids.length} source record(s)</span>
      </div>
      {canReview && alert.status === "open" && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onDispose("acknowledge")}>Acknowledge</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDispose("escalate")}>Escalate</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDispose("false_positive")}>False positive</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDispose("dismiss")}>Dismiss</Button>
        </div>
      )}
      {alert.latest_disposition && (
        <p className="mt-1.5 text-11 text-content-dim">Latest disposition: {alert.latest_disposition}</p>
      )}
    </div>
  );
}
