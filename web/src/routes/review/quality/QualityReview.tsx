import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ClipboardCheck, Lock } from "lucide-react";
import { api } from "@/api";
import { errorMessage } from "@/api/contracts";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard, StatusPill } from "@/routes/intake/components";

const SEV: Record<string, "neutral" | "low" | "medium" | "high" | "critical"> = {
  info: "neutral", warning: "medium", error: "high", blocker: "critical",
};

export function QualityReview() {
  const { role } = useRole();
  const navigate = useNavigate();

  const draftsQ = useQuery({
    queryKey: ["intake", "drafts", "returned_for_correction"],
    queryFn: ({ signal }) => api.intake.listDrafts({ status: "returned_for_correction", page_size: 50 }, signal),
    enabled: role !== "policymaker",
  });
  const issuesQ = useQuery({
    queryKey: ["intake", "quality", "open"],
    queryFn: ({ signal }) => api.intake.qualityIssues({ status: "open", page_size: 100 }, signal),
    enabled: role !== "policymaker",
  });

  if (role === "policymaker") {
    return (
      <div><PageHeader title="Data quality review" />
        <EmptyState icon={Lock} title="Not available for this role"
          description="The data-quality queue is not accessible to the policymaker role." /></div>
    );
  }

  const drafts = draftsQ.data?.items ?? [];
  const issues = issuesQ.data?.items ?? [];

  return (
    <div>
      <PageHeader title="Data quality review"
        description="Drafts returned for correction and the staging data-quality queue." />

      <div className="space-y-4">
        <SectionCard title={`Drafts to correct (${drafts.length})`}
          description="Submissions a reviewer returned for correction.">
          {drafts.length === 0 ? (
            <p className="text-12 text-content-dim">Nothing awaiting correction.</p>
          ) : (
            <ul className="divide-y divide-hairline">
              {drafts.map((d) => (
                <li key={d.intake_draft_id} className="flex items-center justify-between gap-2 py-2">
                  <div className="flex items-center gap-2">
                    <button className="tnum text-primary hover:underline" onClick={() => navigate(`/intake/fir/${d.draft_key}`)}>
                      {d.draft_key}
                    </button>
                    <span className="text-12 capitalize text-content-dim">{d.case_kind.replace(/_/g, " ")}</span>
                    <StatusPill status={d.status} />
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => navigate(`/intake/fir/${d.draft_key}`)}>Open</Button>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard title={`Staging data-quality issues (${issuesQ.data?.total ?? 0})`}
          description="Problems held in staging — invalid rows never reach canonical tables.">
          {issuesQ.error ? (
            <p className="flex items-center gap-1 text-12 text-severity-high"><AlertTriangle className="size-3" />{errorMessage(issuesQ.error)}</p>
          ) : issues.length === 0 ? (
            <EmptyState icon={ClipboardCheck} title="Queue clear" description="No open data-quality issues." />
          ) : (
            <div className="overflow-x-auto rounded-control border border-hairline">
              <table className="w-full text-12">
                <thead className="bg-surface-2 text-content-dim">
                  <tr><th className="px-2 py-1.5 text-left">Type</th><th className="px-2 py-1.5 text-left">Severity</th>
                    <th className="px-2 py-1.5 text-left">Status</th><th className="px-2 py-1.5 text-left">Source rec</th></tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {issues.map((i) => (
                    <tr key={i.data_quality_issue_id}>
                      <td className="px-2 py-1.5 text-content">{i.issue_type}</td>
                      <td className="px-2 py-1.5"><Badge variant={SEV[i.severity] ?? "neutral"}>{i.severity}</Badge></td>
                      <td className="px-2 py-1.5 capitalize text-content-dim">{i.status}</td>
                      <td className="px-2 py-1.5 tnum text-content-dim">{i.source_record_id ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
