import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, CheckCircle2, Clock, Database, FlaskConical, Layers, Lock,
  Play, ShieldCheck, ShieldAlert,
} from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type {
  GovFeatureSchemaVersion, GovModelVersion, GovPredictionDetail, GovPredictionRequest,
} from "@/api/types";
import { roleCan } from "@/config/roles";
import { useRole } from "@/providers/RoleProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/routes/intake/components";


const STATUS_VARIANT: Record<string, "neutral" | "primary" | "low" | "medium" | "high"> = {
  queued: "neutral", running: "primary", completed: "low", reviewed: "low",
  failed: "high", rejected: "high", stale: "medium", superseded: "medium",
};

function StatusBadge({ status }: { status: string }) {
  return <Badge variant={STATUS_VARIANT[status] ?? "neutral"} className="capitalize">{status}</Badge>;
}

function SensitivityBadge({ sensitivity }: { sensitivity: string }) {
  const v = sensitivity === "normal" ? "low" : sensitivity === "restricted" ? "medium" : "high";
  return <Badge variant={v}>{sensitivity}</Badge>;
}

function fmt(ts?: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
}

/* ============================ Registry (features / schemas / models) ===== */
export function RegistryPanel() {
  const featuresQ = useQuery({ queryKey: ["gov", "features"], queryFn: ({ signal }) => api.governance.features(signal) });
  const schemasQ = useQuery({ queryKey: ["gov", "schemas"], queryFn: ({ signal }) => api.governance.schemas(signal) });
  const modelsQ = useQuery({ queryKey: ["gov", "models"], queryFn: ({ signal }) => api.governance.models(true, signal) });

  return (
    <div className="space-y-4">
      <SectionCard title="Feature catalogue"
        description="Every model feature is defined, classified and approved here. Protected/restricted features are excluded from prediction schemas.">
        {featuresQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : featuresQ.error ? <ErrLine e={featuresQ.error} />
          : (
          <div className="overflow-x-auto">
            <table className="w-full text-12">
              <thead className="text-content-dim">
                <tr className="border-b border-hairline text-left">
                  <th className="py-1.5 pr-3 font-medium">Feature</th>
                  <th className="py-1.5 pr-3 font-medium">Type</th>
                  <th className="py-1.5 pr-3 font-medium">Sensitivity</th>
                  <th className="py-1.5 pr-3 font-medium">Approval</th>
                  <th className="py-1.5 pr-3 font-medium">Allowed tasks</th>
                  <th className="py-1.5 pr-3 font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {(featuresQ.data?.items ?? []).map((f) => (
                  <tr key={f.feature_definition_id} className="border-b border-hairline/60">
                    <td className="py-1.5 pr-3 font-medium text-content">{f.name}</td>
                    <td className="py-1.5 pr-3 text-content-dim">{f.value_type}</td>
                    <td className="py-1.5 pr-3"><SensitivityBadge sensitivity={f.sensitivity} /></td>
                    <td className="py-1.5 pr-3 capitalize text-content-dim">{f.approval_status}</td>
                    <td className="py-1.5 pr-3 text-content-dim">{f.allowed_tasks.join(", ") || "—"}</td>
                    <td className="py-1.5 pr-3 text-content-dim">{f.source_table ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Feature schema versions"
        description="A model binds to an exact approved schema version (strict contract). A new input never affects a model until it is added to an approved schema.">
        {schemasQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : (schemasQ.data?.items ?? []).length === 0 ? <p className="text-12 text-content-dim">No schemas.</p>
          : (
          <ul className="space-y-2">
            {schemasQ.data!.items.map((s: GovFeatureSchemaVersion) => (
              <li key={s.feature_schema_version_id} className="rounded-card border border-hairline p-2.5 text-12">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-content">{s.schema_name} v{s.version}</span>
                  <Badge variant={s.status === "approved" ? "low" : "neutral"} className="capitalize">{s.status}</Badge>
                  {s.task && <Badge variant="neutral">{s.task}</Badge>}
                  <span className="text-content-dim">{s.features.length} feature(s)</span>
                  {s.has_protected_feature
                    ? <Badge variant="high"><ShieldAlert className="size-3" /> protected</Badge>
                    : <Badge variant="low"><ShieldCheck className="size-3" /> no protected</Badge>}
                </div>
                <p className="mt-1 text-11 text-content-dim">{s.features.map((f) => f.name).join(", ")}</p>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard title="Governed model versions"
        description="Approved models carry an artifact/image digest, a bound feature schema, an environment and rollback metadata.">
        {modelsQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : (modelsQ.data?.items ?? []).length === 0 ? <p className="text-12 text-content-dim">No governed models.</p>
          : (
          <ul className="space-y-2">
            {modelsQ.data!.items.map((m: GovModelVersion) => (
              <li key={m.model_version_id} className="rounded-card border border-hairline p-2.5 text-12">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-content">{m.model_name}@{m.version}</span>
                  <Badge variant={m.approval_status === "approved" ? "low" : m.approval_status === "rolled_back" ? "high" : "neutral"}
                    className="capitalize">{m.approval_status ?? "ungoverned"}</Badge>
                  {m.environment && <Badge variant="neutral">{m.environment}</Badge>}
                  {m.feature_schema_version_id != null && <span className="text-content-dim">schema #{m.feature_schema_version_id}</span>}
                </div>
                <p className="mt-1 truncate text-11 text-content-dim">
                  artifact {m.artifact_digest ?? "—"} · image {m.image_digest ?? "—"}
                </p>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

/* ============================ Snapshots (build + list) =================== */
export function SnapshotsPanel() {
  const qc = useQueryClient();
  const { role } = useRole();
  const canWrite = roleCan(role, "governance_run");
  const [schemaId, setSchemaId] = useState<number | "">("");
  const [district, setDistrict] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const schemasQ = useQuery({ queryKey: ["gov", "schemas"], queryFn: ({ signal }) => api.governance.schemas(signal) });
  const snapsQ = useQuery({
    queryKey: ["gov", "snapshots"],
    queryFn: ({ signal }) => api.governance.snapshots({ page_size: 50 }, signal),
  });
  const approvedSchemas = (schemasQ.data?.items ?? []).filter((s) => s.status === "approved");

  const build = useMutation({
    mutationFn: () => api.governance.buildSnapshot({
      feature_schema_version_id: Number(schemaId), subject_kind: "area_district", subject_ref_id: district.trim(),
    }),
    onSuccess: (r) => {
      setErr(null);
      setMsg(`Built snapshot #${r.feature_snapshot_id} (quality ${r.quality_status}, hash ${r.content_hash.slice(0, 10)}…).`);
      qc.invalidateQueries({ queryKey: ["gov", "snapshots"] });
    },
    onError: (e) => { setMsg(null); setErr(errorMessage(e)); },
  });

  return (
    <div className="space-y-4">
      <SectionCard title="Build a feature snapshot"
        description="Reads only validated canonical records known at the observation cutoff, excludes protected features, and writes one immutable, hashed snapshot.">
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-12 text-content-dim">
            Approved schema
            <select value={schemaId} onChange={(e) => setSchemaId(e.target.value ? Number(e.target.value) : "")}
              className="mt-1 block h-8 w-56 rounded-control border border-hairline bg-surface px-2 text-13 text-content">
              <option value="">Select…</option>
              {approvedSchemas.map((s) => (
                <option key={s.feature_schema_version_id} value={s.feature_schema_version_id}>
                  {s.schema_name} v{s.version}
                </option>
              ))}
            </select>
          </label>
          <label className="text-12 text-content-dim">
            District ID
            <input value={district} onChange={(e) => setDistrict(e.target.value)} placeholder="e.g. 1"
              className="mt-1 block h-8 w-28 rounded-control border border-hairline bg-surface px-2 text-13" />
          </label>
          <Button size="sm" disabled={!canWrite || !schemaId || !district.trim() || build.isPending}
            onClick={() => build.mutate()}>
            <FlaskConical className="size-3.5" /> Build snapshot
          </Button>
          {!canWrite && <span className="text-11 text-content-dim">Read-only for this demo role.</span>}
        </div>
        {msg && <p className="mt-2 text-12 text-severity-low">{msg}</p>}
        {err && <p className="mt-2 flex items-center gap-1 text-12 text-severity-high"><AlertTriangle className="size-3" />{err}</p>}
      </SectionCard>

      <SectionCard title={`Feature snapshots (${snapsQ.data?.total ?? 0})`}
        description="Immutable feature vectors with an observation cutoff (data-as-of), quality status and content hash.">
        {snapsQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
          : (snapsQ.data?.items ?? []).length === 0 ? <EmptyState icon={Database} title="No snapshots yet" />
          : (
          <div className="overflow-x-auto">
            <table className="w-full text-12">
              <thead className="text-content-dim">
                <tr className="border-b border-hairline text-left">
                  <th className="py-1.5 pr-3 font-medium">#</th>
                  <th className="py-1.5 pr-3 font-medium">Subject</th>
                  <th className="py-1.5 pr-3 font-medium">Data as-of</th>
                  <th className="py-1.5 pr-3 font-medium">Quality</th>
                  <th className="py-1.5 pr-3 font-medium">Hash</th>
                </tr>
              </thead>
              <tbody>
                {snapsQ.data!.items.map((s) => (
                  <tr key={s.feature_snapshot_id} className="border-b border-hairline/60">
                    <td className="py-1.5 pr-3 tnum">{s.feature_snapshot_id}</td>
                    <td className="py-1.5 pr-3 text-content-dim">{s.subject_kind} {s.subject_ref_id}</td>
                    <td className="py-1.5 pr-3 text-content-dim">{fmt(s.observation_cutoff)}</td>
                    <td className="py-1.5 pr-3">
                      <Badge variant={s.quality_status === "ok" ? "low" : s.quality_status === "stale" ? "medium" : "neutral"}
                        className="capitalize">{s.quality_status}</Badge>
                      {s.superseded_by_feature_snapshot_id != null && <Badge variant="medium" className="ml-1">superseded</Badge>}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-11 text-content-dim">{s.content_hash.slice(0, 12)}…</td>
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

/* ============================ Predictions (queue + detail) =============== */
export function PredictionsPanel() {
  const qc = useQueryClient();
  const { role } = useRole();
  const canWrite = roleCan(role, "governance_run");
  const canReview = roleCan(role, "governance_review");
  const [selected, setSelected] = useState<number | null>(null);
  const [modelId, setModelId] = useState<number | "">("");
  const [snapId, setSnapId] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const queueQ = useQuery({
    queryKey: ["gov", "predictions"],
    queryFn: ({ signal }) => api.governance.predictions({ page_size: 50 }, signal),
  });
  const modelsQ = useQuery({ queryKey: ["gov", "models"], queryFn: ({ signal }) => api.governance.models(true, signal) });
  const detailQ = useQuery({
    queryKey: ["gov", "prediction", selected],
    queryFn: ({ signal }) => api.governance.prediction(selected as number, signal),
    enabled: selected != null,
  });
  const approvedModels = (modelsQ.data?.items ?? []).filter(
    (m) => m.approval_status === "approved" && m.feature_schema_version_id != null);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["gov", "predictions"] });
    if (selected != null) qc.invalidateQueries({ queryKey: ["gov", "prediction", selected] });
  };

  const create = useMutation({
    mutationFn: () => api.governance.createPrediction({
      model_version_id: Number(modelId), feature_snapshot_id: Number(snapId.trim()),
    }),
    onSuccess: (d) => { setErr(null); setSelected(d.request.prediction_request_id); refresh(); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const run = useMutation({
    mutationFn: (id: number) => api.governance.runPrediction(id),
    onSuccess: () => { setErr(null); refresh(); },
    onError: (e) => setErr(errorMessage(e)),
  });

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <SectionCard title="New prediction"
          description="Binds an approved model to an immutable snapshot; the schema must match (strict compatibility). Idempotent.">
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-12 text-content-dim">
              Approved model
              <select value={modelId} onChange={(e) => setModelId(e.target.value ? Number(e.target.value) : "")}
                className="mt-1 block h-8 w-52 rounded-control border border-hairline bg-surface px-2 text-13 text-content">
                <option value="">Select…</option>
                {approvedModels.map((m) => (
                  <option key={m.model_version_id} value={m.model_version_id}>{m.model_name}@{m.version}</option>
                ))}
              </select>
            </label>
            <label className="text-12 text-content-dim">
              Snapshot ID
              <input value={snapId} onChange={(e) => setSnapId(e.target.value)} placeholder="e.g. 1"
                className="mt-1 block h-8 w-24 rounded-control border border-hairline bg-surface px-2 text-13" />
            </label>
            <Button size="sm" disabled={!canWrite || !modelId || !snapId.trim() || create.isPending}
              onClick={() => create.mutate()}>Create</Button>
          </div>
          {err && <p className="mt-2 flex items-center gap-1 text-12 text-severity-high"><AlertTriangle className="size-3" />{err}</p>}
        </SectionCard>

        <SectionCard title={`Prediction queue (${queueQ.data?.total ?? 0})`} description="Job status across the governed pipeline.">
          {queueQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
            : (queueQ.data?.items ?? []).length === 0 ? <EmptyState icon={Layers} title="No prediction requests yet" />
            : (
            <ul className="space-y-1.5">
              {queueQ.data!.items.map((r: GovPredictionRequest) => (
                <li key={r.prediction_request_id}>
                  <button onClick={() => setSelected(r.prediction_request_id)}
                    className={`flex w-full items-center justify-between gap-2 rounded-card border p-2 text-left text-12 hover:bg-surface-2 ${
                      selected === r.prediction_request_id ? "border-primary" : "border-hairline"}`}>
                    <span className="truncate">
                      <span className="tnum text-content-dim">#{r.prediction_request_id}</span>{" "}
                      <span className="text-content">{r.model_version_label ?? `model ${r.model_version_id}`}</span>
                      <span className="text-content-dim"> · snapshot {r.feature_snapshot_id}</span>
                    </span>
                    <StatusBadge status={r.status} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <PredictionDetail detail={detailQ.data} loading={detailQ.isLoading} selected={selected}
        canWrite={canWrite} canReview={canReview}
        onRun={(id) => run.mutate(id)} runPending={run.isPending} onReviewed={refresh} />
    </div>
  );
}

function PredictionDetail({
  detail, loading, selected, canWrite, canReview, onRun, runPending, onReviewed,
}: {
  detail?: GovPredictionDetail; loading: boolean; selected: number | null;
  canWrite: boolean; canReview: boolean;
  onRun: (id: number) => void; runPending: boolean; onReviewed: () => void;
}) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const review = useMutation({
    mutationFn: (decision: "accept" | "override" | "reject") =>
      api.governance.reviewPrediction(detail!.request.prediction_request_id,
        { decision, override_reason: reason.trim() || undefined }),
    onSuccess: () => { setErr(null); onReviewed(); },
    onError: (e) => setErr(errorMessage(e)),
  });

  if (selected == null) return <SectionCard title="Prediction detail"><EmptyState icon={FlaskConical} title="Select a request" description="Pick a prediction from the queue to see its result, explanation, source versions and review it." /></SectionCard>;
  if (loading || !detail) return <SectionCard title="Prediction detail"><p className="text-12 text-content-dim">Loading…</p></SectionCard>;

  const { request: req, result, reviews, feature_snapshot: snap, answer } = detail;
  const stale = result?.is_stale || result?.superseded_by_result_id != null || (!detail.is_current && result != null);

  return (
    <SectionCard title={`Request #${req.prediction_request_id}`}
      description={`${req.model_version_label ?? ""} · ${req.status}`}>
      {stale && (
        <div className="mb-3 flex items-center gap-1.5 rounded-card border border-severity-medium/40 bg-severity-medium/5 px-3 py-2 text-12 text-severity-medium">
          <AlertTriangle className="size-4" />
          This result is stale or superseded{result?.stale_reason ? ` — ${result.stale_reason}` : ""}. Rebuild the snapshot and re-run.
        </div>
      )}

      {snap && (
        <p className="mb-2 flex items-center gap-1 text-11 text-content-dim">
          <Clock className="size-3" /> Data as-of {fmt(snap.observation_cutoff)} · snapshot #{snap.feature_snapshot_id} ({snap.quality_status})
        </p>
      )}

      {!result ? (
        <div className="flex items-center gap-2">
          <Button size="sm" disabled={!canWrite || runPending || !["queued", "failed"].includes(req.status)}
            onClick={() => onRun(req.prediction_request_id)}>
            <Play className="size-3.5" /> Run
          </Button>
          <span className="text-12 text-content-dim">No result yet.</span>
        </div>
      ) : (
        <div className="space-y-3 text-12">
          {answer && (
            <div className="rounded-card border border-hairline bg-surface-2 p-2.5">
              <p className="text-content">{answer.answer}</p>
              <p className="mt-1 text-11 text-content-dim">
                {answer.model_version} · confidence {(answer.confidence * 100).toFixed(0)}%
              </p>
            </div>
          )}
          <div>
            <span className="text-content-dim">Output:</span>{" "}
            <span className="font-mono text-11">{JSON.stringify(result.output)}</span>
          </div>
          <div>
            <span className="text-content-dim">Explanation:</span>{" "}
            <span className="font-mono text-11">{JSON.stringify(result.explanation)}</span>
          </div>
          {result.limitations && (
            <p className="rounded-card border border-hairline p-2 text-11 text-content-dim">
              <Lock className="mr-1 inline size-3" />{result.limitations}
            </p>
          )}
          {snap && Object.keys(snap.source_versions).length > 0 && (
            <div>
              <span className="text-content-dim">Source versions:</span>{" "}
              <span className="font-mono text-11">{JSON.stringify(snap.source_versions)}</span>
            </div>
          )}

          {/* reviewer action */}
          <div className="border-t border-hairline pt-2">
            <p className="mb-1 flex items-center gap-1 text-11 uppercase tracking-wide text-content-dim">
              <ShieldCheck className="size-3" /> Reviewer decision
            </p>
            {reviews.length > 0 && (
              <ul className="mb-2 space-y-0.5 text-11 text-content-dim">
                {reviews.map((rv) => (
                  <li key={rv.prediction_review_id}>
                    <CheckCircle2 className="mr-1 inline size-3 text-severity-low" />
                    {rv.decision}{rv.override_reason ? ` — ${rv.override_reason}` : ""} ({rv.reviewer_actor ?? "—"})
                  </li>
                ))}
              </ul>
            )}
            <input value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="Override/reject reason (recorded)…"
              className="mb-2 h-8 w-full rounded-control border border-hairline bg-surface px-2 text-13" />
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="primary" disabled={!canReview || review.isPending}
                onClick={() => review.mutate("accept")}>Accept</Button>
              <Button size="sm" variant="secondary" disabled={!canReview || review.isPending}
                onClick={() => review.mutate("override")}>Override</Button>
              <Button size="sm" variant="ghost" disabled={!canReview || review.isPending}
                onClick={() => review.mutate("reject")}>Reject</Button>
            </div>
            {!canReview && <p className="mt-1 text-11 text-content-dim">Review is a supervisor action.</p>}
            {err && <p className="mt-1 text-11 text-severity-high">{err}</p>}
          </div>
        </div>
      )}
    </SectionCard>
  );
}

/* ============================ Labels (leakage-safe) ===================== */
export function LabelsPanel() {
  const labelsQ = useQuery({ queryKey: ["gov", "labels"], queryFn: ({ signal }) => api.governance.labels({ page_size: 25 }, signal) });
  const d = labelsQ.data;
  return (
    <SectionCard title="Outcome labels"
      description="Training labels derived only from verified outcomes after the observation cutoff — never from the feature formula.">
      {labelsQ.isLoading ? <p className="text-12 text-content-dim">Loading…</p>
        : !d ? <ErrLine e={labelsQ.error} />
        : (
        <div className="space-y-3 text-12">
          <div className="flex flex-wrap items-center gap-2">
            {d.leakage_safe
              ? <Badge variant="low"><ShieldCheck className="size-3" /> leakage-safe</Badge>
              : <Badge variant="high"><ShieldAlert className="size-3" /> leakage detected</Badge>}
            <span className="text-content-dim">{d.total} label(s)</span>
            {Object.entries(d.splits).map(([k, v]) => <Badge key={k} variant="neutral">{k}: {v}</Badge>)}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-12">
              <thead className="text-content-dim">
                <tr className="border-b border-hairline text-left">
                  <th className="py-1.5 pr-3 font-medium">Subject</th>
                  <th className="py-1.5 pr-3 font-medium">Label</th>
                  <th className="py-1.5 pr-3 font-medium">Value</th>
                  <th className="py-1.5 pr-3 font-medium">Cutoff</th>
                  <th className="py-1.5 pr-3 font-medium">Split</th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((l) => (
                  <tr key={l.outcome_label_id} className="border-b border-hairline/60">
                    <td className="py-1.5 pr-3 text-content-dim">{l.subject_kind} {l.subject_ref_id}</td>
                    <td className="py-1.5 pr-3 text-content">{l.label_name}</td>
                    <td className="py-1.5 pr-3 text-content-dim">{l.label_value ?? "—"}</td>
                    <td className="py-1.5 pr-3 text-content-dim">{fmt(l.observation_cutoff)}</td>
                    <td className="py-1.5 pr-3"><Badge variant="neutral">{l.split_tag ?? "—"}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function ErrLine({ e }: { e: unknown }) {
  return <p className="flex items-center gap-1 text-12 text-severity-high"><AlertTriangle className="size-3" />{errorMessage(e)}</p>;
}
