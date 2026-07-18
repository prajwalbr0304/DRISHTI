import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { AlertTriangle, DatabaseZap, FilePlus2, Inbox, Lock } from "lucide-react";
import { api } from "@/api";
import { ApiError, errorMessage } from "@/api/contracts";
import { cn, formatNumber } from "@/lib/utils";
import { useRole } from "@/providers/RoleProvider";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { StatusPill } from "@/routes/intake/components";
import type { IntakeReviewAction } from "@/api/endpoints/intake";

const TABS = ["all", "draft", "submitted", "approved", "returned_for_correction", "rejected"] as const;
const REVIEW_ROLES = new Set(["supervisor", "super_admin"]);

export function IntakeInbox() {
  const { role } = useRole();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState<(typeof TABS)[number]>("all");
  const [msg, setMsg] = useState<string | null>(null);
  const isReviewer = REVIEW_ROLES.has(role);

  if (role === "policymaker") {
    return (
      <div>
        <PageHeader title="Intake inbox" />
        <EmptyState icon={Lock} title="Not available for this role"
          description="Case intake is not accessible to the policymaker role, which works with aggregate views only." />
      </div>
    );
  }

  const listQ = useQuery({
    queryKey: ["intake", "drafts", tab],
    queryFn: ({ signal }) => api.intake.listDrafts({ status: tab === "all" ? undefined : tab, page_size: 50 }, signal),
    placeholderData: keepPreviousData,
  });

  const review = useMutation({
    mutationFn: ({ key, action }: { key: string; action: IntakeReviewAction }) =>
      api.intake.review(key, action, { actor: role }),
    onSuccess: (res, vars) => {
      qc.invalidateQueries({ queryKey: ["intake", "drafts"] });
      if (vars.action === "approve" && res && "case_master_id" in res) {
        setMsg(`Approved — case #${res.case_master_id} (${res.crime_no}) created.`);
      } else {
        setMsg(`Draft ${vars.action === "reject" ? "rejected" : "returned for correction"}.`);
      }
    },
    onError: (e) => {
      setMsg(e instanceof ApiError && e.status === 409
        ? "Review is disabled until Prompt 3 finalises hackathon mode."
        : errorMessage(e));
    },
  });

  const items = listQ.data?.items ?? [];

  return (
    <div>
      <PageHeader title="Intake inbox"
        description="Structured FIR/case drafts — create, validate, review and approve."
        actions={
          <>
            <Button size="sm" variant="outline" onClick={() => navigate("/imports")}>
              <DatabaseZap /> Digital & financial imports
            </Button>
            <Button size="sm" onClick={() => navigate("/intake/fir/new")}><FilePlus2 /> New FIR</Button>
          </>
        } />

      <div className="mb-3 flex flex-wrap items-center gap-1">
        {TABS.map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)}
            className={cn("rounded-control px-2.5 py-1 text-12 font-medium capitalize transition-colors",
              tab === t ? "bg-primary text-primary-fg" : "bg-surface-2 text-content-dim hover:text-content")}>
            {t.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {msg && (
        <div className="mb-3 rounded-control border border-hairline bg-surface-2 px-3 py-2 text-12 text-content">{msg}</div>
      )}

      {listQ.error ? (
        <EmptyState icon={AlertTriangle} title="Couldn't load drafts" description={errorMessage(listQ.error)}
          action={<Button variant="outline" size="sm" onClick={() => listQ.refetch()}>Retry</Button>} />
      ) : items.length === 0 && !listQ.isLoading ? (
        <EmptyState icon={Inbox} title="No drafts yet"
          description="Start a new FIR to create the first structured intake draft."
          action={<Button size="sm" onClick={() => navigate("/intake/fir/new")}><FilePlus2 /> New FIR</Button>} />
      ) : (
        <DraftTable items={items} isReviewer={isReviewer} busy={review.isPending}
          onOpen={(k) => navigate(`/intake/fir/${k}`)}
          onReview={(key, action) => { setMsg(null); review.mutate({ key, action }); }} />
      )}
    </div>
  );
}

function DraftTable({
  items, isReviewer, busy, onOpen, onReview,
}: {
  items: import("@/api/types").IntakeDraftListItem[];
  isReviewer: boolean;
  busy: boolean;
  onOpen: (key: string) => void;
  onReview: (key: string, action: IntakeReviewAction) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-card border border-hairline">
      <table className="w-full text-13">
        <thead className="bg-surface-2 text-12 text-content-dim">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Draft</th>
            <th className="px-3 py-2 text-left font-medium">Kind</th>
            <th className="px-3 py-2 text-left font-medium">Status</th>
            <th className="px-3 py-2 text-left font-medium">Crime No</th>
            <th className="px-3 py-2 text-right font-medium">Parties</th>
            <th className="px-3 py-2 text-right font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {items.map((d) => (
            <tr key={d.intake_draft_id} className="hover:bg-surface-2/50">
              <td className="px-3 py-2">
                <button type="button" onClick={() => onOpen(d.draft_key)} className="tnum text-primary hover:underline">
                  {d.draft_key}
                </button>
              </td>
              <td className="px-3 py-2 capitalize text-content-dim">{d.case_kind.replace(/_/g, " ")}</td>
              <td className="px-3 py-2"><StatusPill status={d.status} /></td>
              <td className="px-3 py-2 tnum text-content-dim">{d.crime_no ?? "—"}</td>
              <td className="px-3 py-2 text-right tnum text-content-dim">{d.party_count}</td>
              <td className="px-3 py-2">
                <div className="flex items-center justify-end gap-1.5">
                  <Button size="sm" variant="ghost" onClick={() => onOpen(d.draft_key)}>Open</Button>
                  {isReviewer && d.status === "submitted" && (
                    <>
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => onReview(d.draft_key, "approve")}>Approve</Button>
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => onReview(d.draft_key, "return")}>Return</Button>
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
