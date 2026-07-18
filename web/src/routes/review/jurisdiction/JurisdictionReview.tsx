import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, Lock, MapPinned, MoveRight, RefreshCw, ShieldCheck } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import type { ContainmentIssue } from "@/api/types";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/routes/intake/components";

/* Jurisdiction review inbox (Phase 9). Canonical cases whose incident point
   fails containment against the PERSISTED, versioned boundaries are staged here
   as DataQualityIssues — never silently moved. A supervisor resolves each one
   with a reviewed, audited action: reassign to the detected district (only if
   the point actually falls inside it), record an override (keep the assigned
   district), or quarantine it out of the canonical analytics set. The demo
   view/role is UX simulation, not authentication. */

const REVIEW_ROLES = new Set(["supervisor", "super_admin"]);

export function JurisdictionReview() {
  const { role } = useRole();
  const qc = useQueryClient();
  const actor = `demo.${role}`;
  const canReview = REVIEW_ROLES.has(role);
  const [banner, setBanner] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const issuesQ = useQuery({
    queryKey: ["geo", "jurisdiction", "issues", "open"],
    queryFn: ({ signal }) => api.geo.jurisdictionIssues({ status: "open", page_size: 100 }, signal),
    enabled: role !== "policymaker",
  });
  const freshnessQ = useQuery({
    queryKey: ["geo", "jurisdiction", "freshness"],
    queryFn: ({ signal }) => api.geo.jurisdictionFreshness(signal),
    enabled: role !== "policymaker",
    retry: false,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["geo", "jurisdiction", "issues"] });
    qc.invalidateQueries({ queryKey: ["geo", "jurisdiction", "freshness"] });
  };

  const scanM = useMutation({
    mutationFn: () => api.geo.jurisdictionScan("caseversion"),
    onSuccess: (r) => {
      setErr(null);
      setBanner(`Scan ${r.run_key}: checked ${r.checked.toLocaleString()} case(s) · `
        + `${r.out_of_state} out-of-state · ${r.out_of_district} out-of-district · `
        + `${r.issues_raised} new issue(s) staged.`);
      invalidate();
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  if (role === "policymaker") {
    return (
      <div><PageHeader title="Jurisdiction review" />
        <EmptyState icon={Lock} title="Not available for this role"
          description="Jurisdiction review works on individual case records and is not available to the policymaker role (aggregate views only)." /></div>
    );
  }

  const items = issuesQ.data?.items ?? [];
  const fresh = freshnessQ.data;

  return (
    <div>
      <PageHeader title="Jurisdiction review"
        description="Cases whose location fails containment against the persisted boundaries. Each is resolved by a reviewed, audited action — nothing is moved silently." />

      {banner && <div className="mb-3 rounded-card border border-severity-low/40 bg-severity-low/5 px-3 py-2 text-13 text-content">{banner}</div>}
      {err && <div className="mb-3 flex items-center gap-1.5 rounded-card border border-severity-high/40 bg-severity-high/5 px-3 py-2 text-13 text-severity-high"><AlertTriangle className="size-4" />{err}</div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <SectionCard
            title={`Open jurisdiction issues (${issuesQ.data?.total ?? items.length})`}
            description="A mismatch blocks canonical submission until a reviewer reassigns, overrides or quarantines it.">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Button size="sm" variant="secondary" disabled={!canReview || scanM.isPending}
                onClick={() => scanM.mutate()}>
                <RefreshCw className={scanM.isPending ? "size-3.5 animate-spin" : "size-3.5"} /> Scan canonical geography
              </Button>
              {!canReview && <span className="text-12 text-content-dim">Review actions need the Supervisor demo view.</span>}
            </div>
            {issuesQ.isLoading ? (
              <p className="text-12 text-content-dim">Loading…</p>
            ) : issuesQ.error ? (
              <p className="flex items-center gap-1 text-12 text-severity-high"><AlertTriangle className="size-3" />{errorMessage(issuesQ.error)}</p>
            ) : items.length === 0 ? (
              <EmptyState icon={ShieldCheck} title="No open jurisdiction issues"
                description="Canonical geography is clean. Run a scan to re-check, or resolve new intake mismatches as they arrive." />
            ) : (
              <ul className="space-y-3">
                {items.map((it) => (
                  <IssueRow key={it.data_quality_issue_id} it={it} canReview={canReview} actor={actor}
                    onDone={(msg) => { setErr(null); setBanner(msg); invalidate(); }}
                    onError={(m) => setErr(m)} />
                ))}
              </ul>
            )}
          </SectionCard>
        </div>

        <div className="space-y-4">
          <SectionCard title="Boundary data freshness"
            description="Persisted, versioned jurisdiction geography — the same geometry the database enforces containment against.">
            {freshnessQ.isLoading ? (
              <p className="text-12 text-content-dim">Loading…</p>
            ) : fresh ? (
              <div className="space-y-2 text-12">
                <dl className="space-y-1.5">
                  {Object.entries(fresh.boundaries).map(([level, b]) => (
                    <div key={level} className="flex items-center justify-between">
                      <dt className="capitalize text-content-dim">{level}</dt>
                      <dd className="tnum text-content">
                        {b.count.toLocaleString()}
                        {b.version != null && <span className="text-content-dim"> · v{b.version}</span>}
                      </dd>
                    </div>
                  ))}
                  <div className="flex items-center justify-between border-t border-hairline pt-1.5">
                    <dt className="text-content-dim">Unit locations</dt>
                    <dd className="tnum text-content">{fresh.unit_locations.toLocaleString()}</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-content-dim">Open issues</dt>
                    <dd className="tnum text-content">{fresh.open_jurisdiction_issues}</dd>
                  </div>
                </dl>
                {fresh.last_scan && (
                  <p className="border-t border-hairline pt-1.5 text-11 text-content-dim">
                    Last scan checked {Number((fresh.last_scan as { checked?: number }).checked ?? 0).toLocaleString()} case(s)
                    {(fresh.last_scan as { at?: string }).at ? ` · ${new Date((fresh.last_scan as { at: string }).at).toLocaleString()}` : ""}.
                  </p>
                )}
                <Badge variant="neutral" className="mt-1">{fresh.environment_label}</Badge>
              </div>
            ) : (
              <p className="text-12 text-content-dim">Freshness unavailable.</p>
            )}
          </SectionCard>
          <SectionCard title="How resolution works" description="Reviewed, audited, reversible.">
            <ul className="space-y-1.5 text-12 text-content-dim">
              <li><b className="text-content">Reassign</b> — move to the detected district. Allowed only if the point actually falls inside it. Creates a new case version.</li>
              <li><b className="text-content">Override</b> — keep the assigned district with a recorded reason (e.g. cross-border case retained by order).</li>
              <li><b className="text-content">Quarantine</b> — flag the case out of canonical analytics when the coordinates themselves are wrong.</li>
            </ul>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

function IssueRow({ it, canReview, actor, onDone, onError }: {
  it: ContainmentIssue;
  canReview: boolean;
  actor: string;
  onDone: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const outOfState = it.issue_type === "invalid_jurisdiction_state";

  const act = useMutation({
    mutationFn: (v: { action: "reassign" | "override" | "quarantine"; to?: number | null }) =>
      api.geo.jurisdictionReassign({
        case_master_id: it.case_master_id!,
        to_district_id: v.to ?? null,
        action: v.action,
        reason: reason.trim() || `${v.action} via jurisdiction review`,
        data_quality_issue_id: it.data_quality_issue_id,
        actor,
      }),
    onSuccess: (r) => {
      onDone(`Case ${it.crime_no ?? it.case_master_id} ${r.action}ed — new version #${r.new_case_version_id}, `
        + `${r.issues_resolved} issue(s) resolved.`);
      qc.invalidateQueries({ queryKey: ["geo", "jurisdiction"] });
    },
    onError: (e) => onError(errorMessage(e)),
  });

  const busy = act.isPending;
  const canReassign = !outOfState && it.resolved_district_id != null;

  return (
    <li className="rounded-card border border-hairline bg-surface p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-12">
        <Badge variant={outOfState ? "high" : "medium"}>
          {outOfState ? "Outside state" : "Wrong district"}
        </Badge>
        {it.case_master_id != null && (
          <Link to={`/cases/${it.case_master_id}`} className="font-medium text-primary hover:underline">
            {it.crime_no ?? `Case #${it.case_master_id}`}
          </Link>
        )}
        <span className="text-content-dim">·</span>
        <span className="text-content-dim">
          Assigned: {it.assigned_district_name ?? it.assigned_district_id ?? "—"}
        </span>
        {it.resolved_district_name && (
          <span className="flex items-center gap-1 text-content-dim">
            <MoveRight className="size-3" /> detected: <span className="text-content">{it.resolved_district_name}</span>
          </span>
        )}
      </div>

      <input value={reason} onChange={(e) => setReason(e.target.value)}
        placeholder="Reason (recorded in the audit trail)…"
        className="mb-2 h-8 w-full rounded-control border border-hairline bg-surface-2 px-2 text-13" />

      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" disabled={!canReview || busy || !canReassign}
          title={canReassign ? undefined : "The point is not inside a detected district — use override or quarantine."}
          onClick={() => act.mutate({ action: "reassign", to: it.resolved_district_id })}>
          <MapPinned className="size-3.5" /> Reassign to detected
          {it.resolved_district_name ? ` (${it.resolved_district_name})` : ""}
        </Button>
        <Button size="sm" variant="secondary" disabled={!canReview || busy}
          onClick={() => act.mutate({ action: "override" })}>
          Override (keep assigned)
        </Button>
        <Button size="sm" variant="ghost" disabled={!canReview || busy}
          onClick={() => act.mutate({ action: "quarantine" })}>
          <Ban className="size-3.5" /> Quarantine
        </Button>
      </div>
    </li>
  );
}
