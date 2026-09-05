import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, CheckCircle2, Download, FileText, Gavel, RefreshCw, ScrollText,
  ShieldCheck, ShieldAlert, XCircle,
} from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { runtime } from "@/config/runtime";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/routes/intake/components";

function fmt(ts?: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
}
function ErrLine({ e }: { e: unknown }) {
  return <p className="flex items-center gap-1 text-12 text-severity-high"><AlertTriangle className="size-3" />{errorMessage(e)}</p>;
}
function YesNo({ v }: { v: boolean }) {
  return v
    ? <Badge variant="low"><CheckCircle2 className="size-3" /> yes</Badge>
    : <Badge variant="neutral"><XCircle className="size-3" /> no</Badge>;
}

/* ============================ Status / indicators ======================== */
export function StatusPanel() {
  const statusQ = useQuery({ queryKey: ["admin", "status"], queryFn: ({ signal }) => api.admin.status(signal) });
  const rlsQ = useQuery({ queryKey: ["admin", "rls"], queryFn: ({ signal }) => api.admin.rlsStatus(signal) });
  const s = statusQ.data;
  const c = s?.components;
  return (
    <div className="space-y-4">
      <SectionCard title="Hackathon status indicators"
        description="Visible HACKATHON_MODE / DEMO_DATA_ONLY / synthetic-DB / RLS-disabled state for the deployed synthetic demo.">
        {statusQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : statusQ.error ? <ErrLine e={statusQ.error} />
          : s ? (
          <div className="flex flex-wrap gap-2 text-12">
            <Badge variant="primary">{s.environment_label}</Badge>
            <span className="inline-flex items-center gap-1">HACKATHON_MODE <YesNo v={s.hackathon_mode} /></span>
            <span className="inline-flex items-center gap-1">DEMO_DATA_ONLY <YesNo v={s.demo_data_only} /></span>
            <span className="inline-flex items-center gap-1">Synthetic DB <YesNo v={s.synthetic_db} /></span>
            <span className="inline-flex items-center gap-1">RLS disabled <YesNo v={s.rls_disabled} /></span>
            <span className="inline-flex items-center gap-1">Database <YesNo v={s.database_ok} /></span>
          </div>
        ) : null}
      </SectionCard>

      <SectionCard title="Catalyst component flags"
        description="Which Catalyst capabilities are enabled at runtime (Signals, Mail/Push, QuickML RAG, Data Store, Stratus, SmartBrowz).">
        {c ? (
          <div className="flex flex-wrap gap-2 text-12">
            <span className="inline-flex items-center gap-1">Signals <YesNo v={c.signals_enabled} /></span>
            <span className="inline-flex items-center gap-1">Mail/Push <YesNo v={c.notify_enabled} /></span>
            <span className="inline-flex items-center gap-1">QuickML RAG <YesNo v={c.rag_enabled} /></span>
            <span className="inline-flex items-center gap-1">Data Store <YesNo v={c.use_catalyst_datastore} /></span>
            <span className="inline-flex items-center gap-1">Stratus <YesNo v={c.use_catalyst_stratus} /></span>
            <span className="inline-flex items-center gap-1">SmartBrowz <YesNo v={c.use_catalyst_smartbrowz} /></span>
          </div>
        ) : <p className="text-12 text-content-dim">—</p>}
      </SectionCard>

      <SectionCard title="RLS-disabled verification"
        description="Every DRISHTI application table must report RLS + FORCE RLS disabled (hackathon posture).">
        {rlsQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : rlsQ.error ? <ErrLine e={rlsQ.error} />
          : rlsQ.data ? (
          <div className="flex flex-wrap items-center gap-2 text-12">
            {rlsQ.data.rls_disabled
              ? <Badge variant="low"><ShieldCheck className="size-3" /> RLS disabled on all {rlsQ.data.tables_checked} tables</Badge>
              : <Badge variant="high"><ShieldAlert className="size-3" /> {rlsQ.data.tables_enabled} table(s) still enabled</Badge>}
            {rlsQ.data.offenders.length > 0 && <span className="text-severity-high">{rlsQ.data.offenders.join(", ")}</span>}
          </div>
        ) : null}
      </SectionCard>

      {s && (
        <SectionCard title="Data counts">
          <div className="grid grid-cols-2 gap-2 text-12 sm:grid-cols-4">
            {Object.entries(s.counts).map(([k, v]) => (
              <div key={k} className="rounded-card border border-hairline p-2">
                <div className="text-content-dim">{k.replace(/_/g, " ")}</div>
                <div className="tnum text-16 font-semibold text-content">{v}</div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}

/* ============================ Identity / authorization matrix ============ */
export function IdentityPanel() {
  const q = useQuery({ queryKey: ["admin", "identity"], queryFn: ({ signal }) => api.admin.identity(signal) });
  const d = q.data;
  return (
    <SectionCard title="Catalyst identity → demo role authorization matrix"
      description="A Catalyst-authenticated user maps to a synthetic demo role. RLS is disabled, so this server-side matrix is the authorization boundary the API enforces.">
      {q.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
        : q.error ? <ErrLine e={q.error} />
        : d ? (
        <div className="overflow-x-auto">
          <table className="w-full text-12">
            <thead className="text-content-dim">
              <tr className="border-b border-hairline text-left">
                <th className="py-1.5 pr-3 font-medium">Permission</th>
                {d.roles.map((r) => (
                  <th key={r} className="py-1.5 pr-3 font-medium">
                    {r}{r === d.resolved_role ? " *" : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.permissions.map((p) => (
                <tr key={p} className="border-b border-hairline/60">
                  <td className="py-1.5 pr-3 font-medium text-content">{p}</td>
                  {d.roles.map((r) => (
                    <td key={r} className="py-1.5 pr-3">
                      {d.matrix[r]?.[p]
                        ? <CheckCircle2 className="size-3.5 text-severity-low" />
                        : <XCircle className="size-3.5 text-content-dim" />}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-11 text-content-dim">* your resolved demo role</p>
        </div>
      ) : null}
    </SectionCard>
  );
}

/* ============================ Source reconciliation ====================== */
export function ReconciliationPanel() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "recon"], queryFn: ({ signal }) => api.admin.reconciliation(signal) });
  const [msg, setMsg] = useState<string | null>(null);
  const repair = useMutation({
    mutationFn: (id: number) => api.admin.repair({ ingestion_job_id: id, reason: "admin console repair" }),
    onSuccess: (r) => { setMsg(JSON.stringify(r)); qc.invalidateQueries({ queryKey: ["admin", "recon"] }); },
    onError: (e) => setMsg(errorMessage(e)),
  });
  return (
    <SectionCard title="Source reconciliation"
      description="Per-source committed/rejected/duplicate/pending records + partial/failed jobs. Repair re-stages rejected rows for review (non-destructive).">
      {q.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
        : q.error ? <ErrLine e={q.error} />
        : (q.data?.items ?? []).length === 0 ? <EmptyState icon={RefreshCw} title="No source systems" />
        : (
        <div className="overflow-x-auto">
          <table className="w-full text-12">
            <thead className="text-content-dim">
              <tr className="border-b border-hairline text-left">
                <th className="py-1.5 pr-3 font-medium">Source</th>
                <th className="py-1.5 pr-3 font-medium">Committed</th>
                <th className="py-1.5 pr-3 font-medium">Rejected</th>
                <th className="py-1.5 pr-3 font-medium">Duplicate</th>
                <th className="py-1.5 pr-3 font-medium">Pending</th>
                <th className="py-1.5 pr-3 font-medium">Partial/Failed jobs</th>
              </tr>
            </thead>
            <tbody>
              {q.data!.items.map((r) => (
                <tr key={r.source_system_id} className="border-b border-hairline/60">
                  <td className="py-1.5 pr-3 font-medium text-content">{r.code}</td>
                  <td className="py-1.5 pr-3 tnum">{r.committed_records}</td>
                  <td className="py-1.5 pr-3 tnum">{r.rejected_records}</td>
                  <td className="py-1.5 pr-3 tnum">{r.duplicate_records}</td>
                  <td className="py-1.5 pr-3 tnum">{r.pending_records}</td>
                  <td className="py-1.5 pr-3 tnum">{r.partial_jobs + r.failed_jobs}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {msg && <p className="mt-2 text-11 text-content-dim">{msg}</p>}
        </div>
      )}
    </SectionCard>
  );
}

/* ============================ Retention / legal hold ===================== */
export function RetentionPanel() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "retention"], queryFn: ({ signal }) => api.admin.retention(signal) });
  const [subjectId, setSubjectId] = useState("");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const place = useMutation({
    mutationFn: () => api.admin.placeLegalHold({ subject_kind: "evidence", subject_ref_id: subjectId.trim(), reason: reason.trim() }),
    onSuccess: () => { setErr(null); setSubjectId(""); setReason(""); qc.invalidateQueries({ queryKey: ["admin", "retention"] }); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const release = useMutation({
    mutationFn: (id: number) => api.admin.releaseLegalHold(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "retention"] }),
    onError: (e) => setErr(errorMessage(e)),
  });
  const d = q.data;
  return (
    <div className="space-y-4">
      <SectionCard title="Retention & archival policies"
        description="Synthetic-demo retention config. Non-destructive by design: expiry only flags/archives for review — records are never auto-deleted.">
        {q.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : q.error ? <ErrLine e={q.error} />
          : d ? (
          <>
            <Badge variant="low" className="mb-2"><ShieldCheck className="size-3" /> Non-destructive: no automatic deletion</Badge>
            <div className="overflow-x-auto">
              <table className="w-full text-12">
                <thead className="text-content-dim">
                  <tr className="border-b border-hairline text-left">
                    <th className="py-1.5 pr-3 font-medium">Applies to</th>
                    <th className="py-1.5 pr-3 font-medium">Retention (days)</th>
                    <th className="py-1.5 pr-3 font-medium">Archive after</th>
                    <th className="py-1.5 pr-3 font-medium">Expiry action</th>
                  </tr>
                </thead>
                <tbody>
                  {d.policies.map((p) => (
                    <tr key={p.retention_policy_id} className="border-b border-hairline/60">
                      <td className="py-1.5 pr-3 font-medium text-content">{p.applies_to}</td>
                      <td className="py-1.5 pr-3 tnum">{p.retention_days}</td>
                      <td className="py-1.5 pr-3 tnum">{p.archive_after_days ?? "—"}</td>
                      <td className="py-1.5 pr-3"><Badge variant="neutral">{p.expiry_action}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-11 text-content-dim">
              Evidence: {d.evidence_summary.total ?? 0} items · {d.evidence_summary.expiry_flagged ?? 0} expiry-flagged · {d.evidence_summary.on_legal_hold ?? 0} on legal hold
            </p>
          </>
        ) : null}
      </SectionCard>

      <SectionCard title="Legal holds"
        description="An active legal hold always suppresses any expiry/archival flag on its subject.">
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <label className="text-12 text-content-dim">Evidence item ID
            <input value={subjectId} onChange={(e) => setSubjectId(e.target.value)} placeholder="e.g. 1"
              className="mt-1 block h-8 w-28 rounded-control border border-hairline bg-surface px-2 text-13" />
          </label>
          <label className="text-12 text-content-dim">Reason
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="why (audited)"
              className="mt-1 block h-8 w-64 rounded-control border border-hairline bg-surface px-2 text-13" />
          </label>
          <Button size="sm" disabled={!subjectId.trim() || reason.trim().length < 3 || place.isPending}
            onClick={() => place.mutate()}><Gavel className="size-3.5" /> Place hold</Button>
        </div>
        {err && <p className="mb-2"><ErrLine e={err} /></p>}
        {(d?.legal_holds ?? []).length === 0 ? <p className="text-12 text-content-dim">No legal holds.</p>
          : (
          <ul className="space-y-1.5 text-12">
            {d!.legal_holds.map((h) => (
              <li key={h.legal_hold_id} className="flex items-center justify-between rounded-card border border-hairline p-2">
                <span>{h.subject_kind} #{h.subject_ref_id} · <span className="text-content-dim">{h.reason}</span>{" "}
                  <Badge variant={h.status === "active" ? "medium" : "neutral"}>{h.status}</Badge></span>
                {h.status === "active" && (
                  <Button size="sm" variant="ghost" disabled={release.isPending}
                    onClick={() => release.mutate(h.legal_hold_id)}>Release</Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

/* ============================ Model lifecycle / review-due =============== */
export function ModelsPanel() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "models"], queryFn: ({ signal }) => api.admin.models(signal) });
  const review = useMutation({
    mutationFn: (id: number) => api.admin.reviewModel(id, { review_kind: "independent", status: "completed", findings: { note: "reviewed in admin console" } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "models"] }),
  });
  const stateVariant: Record<string, "low" | "medium" | "high" | "neutral"> = {
    completed: "low", waived: "low", overdue: "high", due: "medium", in_progress: "medium",
    no_review_scheduled: "neutral",
  };
  return (
    <SectionCard title="Model lifecycle & independent-review due"
      description="Governed model versions with periodic independent-review / drift state. Full model registry + rollback live in Model governance (/governance).">
      {q.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
        : q.error ? <ErrLine e={q.error} />
        : (q.data?.items ?? []).length === 0 ? <EmptyState icon={ShieldCheck} title="No governed models" />
        : (
        <ul className="space-y-2">
          {q.data!.items.map((m) => (
            <li key={m.model_version_id} className="rounded-card border border-hairline p-2.5 text-12">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-content">{m.model_name}@{m.version}</span>
                <Badge variant={m.approval_status === "approved" ? "low" : m.approval_status === "rolled_back" ? "high" : "neutral"}>
                  {m.approval_status ?? "ungoverned"}</Badge>
                <Badge variant={stateVariant[m.effective_review_state] ?? "neutral"}>{m.effective_review_state.replace(/_/g, " ")}</Badge>
                {m.due_at && <span className="text-content-dim">due {fmt(m.due_at)}</span>}
                {(m.effective_review_state === "due" || m.effective_review_state === "overdue") && (
                  <Button size="sm" variant="ghost" className="ml-auto" disabled={review.isPending}
                    onClick={() => review.mutate(m.model_version_id)}>Mark reviewed</Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

/* ============================ Queues ===================================== */
export function QueuesPanel() {
  const q = useQuery({ queryKey: ["admin", "queues"], queryFn: ({ signal }) => api.admin.queues(signal) });
  const d = q.data;
  return (
    <SectionCard title="Ingestion / data-quality / evidence queues"
      description="Import + data-quality review + evidence quarantine/security-scan queues, plus the intake-form reading queue when scanning is enabled.">
      {q.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
        : q.error ? <ErrLine e={q.error} />
        : d ? (
        <div className="space-y-3 text-12">
          <div className="grid grid-cols-4 gap-2">
            <div className="rounded-card border border-hairline p-2"><div className="text-content-dim">Data-quality open</div><div className="tnum text-16 font-semibold">{d.data_quality_open}</div></div>
            <div className="rounded-card border border-hairline p-2"><div className="text-content-dim">Ingestion partial/failed</div><div className="tnum text-16 font-semibold">{d.ingestion_partial_failed}</div></div>
            <div className="rounded-card border border-hairline p-2"><div className="text-content-dim">Evidence quarantine</div><div className="tnum text-16 font-semibold">{d.evidence_quarantine}</div></div>
            <div className="rounded-card border border-hairline p-2"><div className="text-content-dim">Scans awaiting review</div><div className="tnum text-16 font-semibold">{d.intake_scan_pending ?? 0}</div></div>
          </div>
          {/* Two different things both get called "extraction". Keep them apart:
              reading an intake FORM is in scope; parsing evidence MEDIA is not. */}
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={d.extraction_queue_present ? "primary" : "neutral"}>
              {d.extraction_queue_present
                ? "Intake-form reading queue active"
                : "No intake-form reading queue (scanning off)"}
            </Badge>
            <Badge variant="low">
              {d.evidence_extraction_enabled
                ? "Evidence extraction ENABLED"
                : "Evidence media never parsed"}
            </Badge>
          </div>
        </div>
      ) : null}
    </SectionCard>
  );
}

/* ============================ Usage / budgets / feature flags ============ */
export function UsagePanel() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "usage"], queryFn: ({ signal }) => api.admin.usage(signal) });
  const toggle = useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) => api.admin.setFeatureFlag(key, enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "usage"] }),
  });
  const d = q.data;
  const pb = d?.plan_baseline as { envelope_inr?: number; period?: string } | undefined;
  return (
    <div className="space-y-4">
      <SectionCard title="Catalyst / AWS usage & budget"
        description="Credited plan baseline + budget alert thresholds. Catalyst billing is console-only; AWS uses AWS Budgets + CloudWatch.">
        {q.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : q.error ? <ErrLine e={q.error} />
          : d ? (
          <div className="text-12">
            <p>Plan envelope: <span className="font-semibold text-content">INR {pb?.envelope_inr ?? "—"}</span>{" "}
              <span className="text-content-dim">({pb?.period ?? ""})</span></p>
            <ul className="mt-1 space-y-0.5 text-content-dim">
              {d.budget_alerts.map((a, i) => {
                const alert = a as { threshold_pct?: number; amount_inr?: number };
                return <li key={i}>Alert at {alert.threshold_pct}% (INR {alert.amount_inr})</li>;
              })}
            </ul>
            <p className="mt-2 text-11 text-content-dim">{d.note}</p>
          </div>
        ) : null}
      </SectionCard>

      <SectionCard title="Feature flags"
        description="Toggle optional capabilities. Some (RAG, Mail/Push) also require a server env gate — runtime-effective shows the combined state.">
        {(d?.feature_flags ?? []).length === 0 ? <p className="text-12 text-content-dim">—</p>
          : (
          <ul className="space-y-1.5 text-12">
            {d!.feature_flags.map((f) => (
              <li key={f.key} className="flex items-center justify-between rounded-card border border-hairline p-2">
                <span>
                  <span className="font-medium text-content">{f.key}</span>{" "}
                  <Badge variant="neutral">{f.category}</Badge>{" "}
                  {f.runtime_effective != null && (
                    <Badge variant={f.runtime_effective ? "low" : "neutral"}>runtime {f.runtime_effective ? "on" : "off"}</Badge>
                  )}
                  {f.description && <span className="block text-11 text-content-dim">{f.description}</span>}
                </span>
                <Button size="sm" variant={f.enabled ? "secondary" : "primary"} disabled={toggle.isPending}
                  onClick={() => toggle.mutate({ key: f.key, enabled: !f.enabled })}>
                  {f.enabled ? "Disable" : "Enable"}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

/* ============================ Audit search / export ====================== */
export function AuditPanel() {
  const [action, setAction] = useState("");
  const [text, setText] = useState("");
  const q = useQuery({
    queryKey: ["admin", "audit", action, text],
    queryFn: ({ signal }) => api.admin.audit({ action: action || undefined, text: text || undefined, page_size: 50 }, signal),
  });
  const exportUrl = `${runtime.apiBaseUrl.replace(/\/$/, "")}/admin/audit/export?fmt=csv${action ? `&action=${encodeURIComponent(action)}` : ""}${text ? `&text=${encodeURIComponent(text)}` : ""}`;
  return (
    <SectionCard title="Audit search & export"
      description="Append-only audit trail (create/update/delete, imports, evidence, model runs, reviews, exports). Never contains secrets, narratives or file contents.">
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <label className="text-12 text-content-dim">Action
          <input value={action} onChange={(e) => setAction(e.target.value)} placeholder="e.g. export"
            className="mt-1 block h-8 w-40 rounded-control border border-hairline bg-surface px-2 text-13" />
        </label>
        <label className="text-12 text-content-dim">Search
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="resource / detail text"
            className="mt-1 block h-8 w-56 rounded-control border border-hairline bg-surface px-2 text-13" />
        </label>
        <a href={exportUrl} className="inline-flex h-8 items-center gap-1 rounded-control border border-hairline px-2 text-12 hover:bg-surface-2">
          <Download className="size-3.5" /> CSV
        </a>
      </div>
      {q.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
        : q.error ? <ErrLine e={q.error} />
        : (q.data?.items ?? []).length === 0 ? <EmptyState icon={ScrollText} title="No audit events" />
        : (
        <div className="overflow-x-auto">
          <table className="w-full text-12">
            <thead className="text-content-dim">
              <tr className="border-b border-hairline text-left">
                <th className="py-1.5 pr-3 font-medium">When</th>
                <th className="py-1.5 pr-3 font-medium">Actor</th>
                <th className="py-1.5 pr-3 font-medium">Action</th>
                <th className="py-1.5 pr-3 font-medium">Resource</th>
              </tr>
            </thead>
            <tbody>
              {q.data!.items.slice(0, 50).map((a) => (
                <tr key={a.audit_event_id} className="border-b border-hairline/60">
                  <td className="py-1.5 pr-3 text-content-dim">{fmt(a.occurred_at)}</td>
                  <td className="py-1.5 pr-3">{a.actor ?? "—"} <span className="text-content-dim">{a.actor_role ?? ""}</span></td>
                  <td className="py-1.5 pr-3"><Badge variant="neutral">{a.action}</Badge></td>
                  <td className="py-1.5 pr-3 text-content-dim">{a.resource ?? "—"} {a.resource_id ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-11 text-content-dim">{q.data!.total} event(s)</p>
        </div>
      )}
    </SectionCard>
  );
}

/* ============================ Reports ==================================== */
export function ReportsPanel() {
  const qc = useQueryClient();
  const templatesQ = useQuery({ queryKey: ["reports", "templates"], queryFn: ({ signal }) => api.reports.templates(signal) });
  const listQ = useQuery({ queryKey: ["reports", "list"], queryFn: ({ signal }) => api.reports.list({ limit: 25 }, signal) });
  const [template, setTemplate] = useState("");
  const [scopeRef, setScopeRef] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const templates = templatesQ.data?.items ?? [];
  const selected = templates.find((t) => t.code === template);

  const generate = useMutation({
    mutationFn: () => api.reports.generate({
      template_code: template, scope_kind: selected?.scope_kind ?? "global",
      scope_ref_id: scopeRef.trim() || undefined,
    }),
    onSuccess: (r) => {
      setErr(null);
      setMsg(`Report #${r.report_snapshot_id} — watermark "${r.watermark}", hash ${r.content_hash.slice(0, 10)}…, object ${(r.object_sha256 ?? "").slice(0, 10)}…`);
      qc.invalidateQueries({ queryKey: ["reports", "list"] });
    },
    onError: (e) => { setMsg(null); setErr(errorMessage(e)); },
  });
  const download = useMutation({
    mutationFn: (id: number) => api.reports.download(id),
    onSuccess: (r) => setMsg(`Short-lived URL (${r.expires_in_seconds}s): ${r.url}`),
    onError: (e) => setErr(errorMessage(e)),
  });

  const needsScope = selected && selected.scope_kind !== "global";
  return (
    <div className="space-y-4">
      <SectionCard title="Generate a report"
        description="Reports are built from structured database fields only (no OCR/file parsing), carry source/version citations + a synthetic watermark, and are stored in private Stratus.">
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-12 text-content-dim">Template
            <select value={template} onChange={(e) => setTemplate(e.target.value)}
              className="mt-1 block h-8 w-56 rounded-control border border-hairline bg-surface px-2 text-13 text-content">
              <option value="">Select…</option>
              {templates.map((t) => <option key={t.code} value={t.code}>{t.name} ({t.scope_kind})</option>)}
            </select>
          </label>
          {needsScope && (
            <label className="text-12 text-content-dim">{selected!.scope_kind} ID
              <input value={scopeRef} onChange={(e) => setScopeRef(e.target.value)} placeholder="e.g. 1"
                className="mt-1 block h-8 w-28 rounded-control border border-hairline bg-surface px-2 text-13" />
            </label>
          )}
          <Button size="sm" disabled={!template || (needsScope && !scopeRef.trim()) || generate.isPending}
            onClick={() => generate.mutate()}><FileText className="size-3.5" /> Generate</Button>
        </div>
        {msg && <p className="mt-2 break-all text-12 text-severity-low">{msg}</p>}
        {err && <p className="mt-2"><ErrLine e={err} /></p>}
      </SectionCard>

      <SectionCard title="Generated reports"
        description="Reproducible structured snapshots with a SHA-256 + Stratus object hash + synthetic watermark. Every generation/download is audited.">
        {listQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : (listQ.data?.items ?? []).length === 0 ? <EmptyState icon={FileText} title="No reports yet" />
          : (
          <ul className="space-y-1.5 text-12">
            {listQ.data!.items.map((r) => (
              <li key={r.report_snapshot_id} className="flex items-center justify-between gap-2 rounded-card border border-hairline p-2">
                <span className="min-w-0">
                  <span className="font-medium text-content">{r.title}</span>{" "}
                  <Badge variant="neutral">{r.template_code}</Badge>{" "}
                  <span className="text-content-dim">{r.render_backend}</span>
                  <span className="block truncate font-mono text-11 text-content-dim">hash {r.content_hash.slice(0, 16)}… · obj {(r.object_sha256 ?? "").slice(0, 16)}…</span>
                </span>
                <Button size="sm" variant="ghost" disabled={download.isPending}
                  onClick={() => download.mutate(r.report_snapshot_id)}><Download className="size-3.5" /></Button>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

/* ============================ Notifications ============================== */
export function NotificationsPanel() {
  const qc = useQueryClient();
  const notifQ = useQuery({ queryKey: ["notif", "list"], queryFn: ({ signal }) => api.notifications.list({ limit: 25 }, signal) });
  const tasksQ = useQuery({ queryKey: ["notif", "tasks"], queryFn: ({ signal }) => api.notifications.tasks({ limit: 25 }, signal) });
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["notif", "list"] });
    qc.invalidateQueries({ queryKey: ["notif", "tasks"] });
  };
  const createTask = useMutation({
    mutationFn: () => api.notifications.createTask({ task_type: "case_review", title: title.trim(), assignee_actor: assignee.trim() || undefined, priority: "medium" }),
    onSuccess: () => { setErr(null); setTitle(""); setAssignee(""); refresh(); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const escalate = useMutation({ mutationFn: () => api.notifications.runEscalations(), onSuccess: refresh, onError: (e) => setErr(errorMessage(e)) });
  const markRead = useMutation({ mutationFn: (id: number) => api.notifications.markRead(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["notif", "list"] }) });

  return (
    <div className="space-y-4">
      <SectionCard title="Assign a work task"
        description="Optional case/evidence/review task assignments. Titles are short non-sensitive synthetic summaries — never evidence content or narratives.">
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-12 text-content-dim">Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="short summary"
              className="mt-1 block h-8 w-64 rounded-control border border-hairline bg-surface px-2 text-13" />
          </label>
          <label className="text-12 text-content-dim">Assignee
            <input value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="demo actor"
              className="mt-1 block h-8 w-40 rounded-control border border-hairline bg-surface px-2 text-13" />
          </label>
          <Button size="sm" disabled={title.trim().length < 3 || createTask.isPending} onClick={() => createTask.mutate()}>Create task</Button>
          <Button size="sm" variant="secondary" disabled={escalate.isPending} onClick={() => escalate.mutate()}>Run escalations</Button>
        </div>
        {err && <p className="mt-2"><ErrLine e={err} /></p>}
      </SectionCard>

      <SectionCard title={`Tasks (${tasksQ.data?.total ?? 0})`}>
        {(tasksQ.data?.items ?? []).length === 0 ? <p className="text-12 text-content-dim">No tasks.</p>
          : (
          <ul className="space-y-1 text-12">
            {tasksQ.data!.items.map((t) => (
              <li key={t.work_task_id} className="flex items-center gap-2 rounded-card border border-hairline p-2">
                <Badge variant={t.status === "escalated" ? "high" : t.status === "done" ? "low" : "neutral"}>{t.status}</Badge>
                <span className="truncate text-content">{t.title}</span>
                <span className="ml-auto text-content-dim">{t.assignee_actor ?? "—"}{t.due_at ? ` · due ${fmt(t.due_at)}` : ""}</span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard title={`Notifications (${notifQ.data?.unread ?? 0} unread)`}
        description="In-app + (when enabled) email/push. Bodies are data-minimized synthetic summaries only.">
        {(notifQ.data?.items ?? []).length === 0 ? <p className="text-12 text-content-dim">No notifications.</p>
          : (
          <ul className="space-y-1 text-12">
            {notifQ.data!.items.map((n) => (
              <li key={n.notification_message_id} className="flex items-center gap-2 rounded-card border border-hairline p-2">
                <Badge variant={n.severity === "warning" ? "medium" : n.severity === "action_required" ? "high" : "neutral"}>{n.notification_type}</Badge>
                <span className="truncate text-content">{n.summary}</span>
                <span className="ml-auto text-content-dim">{n.deliveries.map((d) => d.channel).join(", ")}</span>
                {!n.read_at && <Button size="sm" variant="ghost" onClick={() => markRead.mutate(n.notification_message_id)}>Read</Button>}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

/* ============================ Approved-text assistant (RAG) ============== */
export function AssistantPanel() {
  const statusQ = useQuery({ queryKey: ["rag", "status"], queryFn: ({ signal }) => api.rag.status(signal) });
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Awaited<ReturnType<typeof api.rag.ask>> | null>(null);
  const [evalResult, setEvalResult] = useState<Awaited<ReturnType<typeof api.rag.evaluate>> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const ask = useMutation({
    mutationFn: () => api.rag.ask({ question: question.trim() }),
    onSuccess: (r) => { setErr(null); setAnswer(r); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const evaluate = useMutation({
    mutationFn: () => api.rag.evaluate(),
    onSuccess: (r) => { setErr(null); setEvalResult(r); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const st = statusQ.data;
  return (
    <div className="space-y-4">
      <SectionCard title="Approved-text knowledge assistant (optional)"
        description="Answers ONLY from approved SOP/policy text via Catalyst QuickML when enabled. Cites source/version, refuses when unsupported, never parses uploaded files (no OCR).">
        {statusQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : st ? (
          <div className="flex flex-wrap items-center gap-2 text-12">
            <Badge variant={st.enabled ? "low" : "neutral"}>{st.enabled ? "enabled" : "disabled"}</Badge>
            <Badge variant="neutral">provider: {st.provider}</Badge>
            <span className="text-content-dim">{st.approved_sources} approved sources · KB {st.knowledge_base_version}</span>
            {st.reason && <span className="block w-full text-11 text-content-dim">{st.reason}</span>}
          </div>
        ) : null}
      </SectionCard>

      <SectionCard title="Ask (approved SOP/policy only)">
        <div className="flex flex-wrap items-end gap-2">
          <input value={question} onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. How is digital evidence integrity verified?"
            className="h-8 min-w-0 flex-1 rounded-control border border-hairline bg-surface px-2 text-13" />
          <Button size="sm" disabled={question.trim().length < 1 || ask.isPending} onClick={() => ask.mutate()}>Ask</Button>
          <Button size="sm" variant="secondary" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>Run evaluation</Button>
        </div>
        {err && <p className="mt-2"><ErrLine e={err} /></p>}
        {answer && (
          <div className="mt-3 rounded-card border border-hairline p-2.5 text-12">
            <p className="text-content">{answer.answer}</p>
            <p className="mt-1 flex flex-wrap items-center gap-1 text-11 text-content-dim">
              {answer.refused ? <Badge variant="medium">refused (no supporting source)</Badge>
                : answer.citations.map((c, i) => <Badge key={i} variant="low">{c.source}{c.version ? ` v${c.version}` : ""}</Badge>)}
            </p>
          </div>
        )}
        {evalResult && (
          <p className="mt-2 text-12">
            Fixed eval: <Badge variant={evalResult.failed === 0 ? "low" : "high"}>{evalResult.passed}/{evalResult.total} passed</Badge>{" "}
            <span className="text-content-dim">(citation + refusal correct)</span>
          </p>
        )}
      </SectionCard>
    </div>
  );
}
