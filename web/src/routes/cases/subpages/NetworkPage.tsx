import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";
import { Widget } from "@/components/widget/Widget";
import { CaseNetworkGraph } from "@/components/cases/CaseNetworkGraph";

/* Case Network sub-page (doc 01 §4.2): co-accused + name-linked cases. */
export function NetworkPage({ caseId }: { caseId: number }) {
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ["cases", "network", caseId],
    queryFn: ({ signal }) => api.cases.network(caseId, signal),
  });

  const empty = !q.isLoading && !q.error && (q.data?.nodes.length ?? 0) <= 1;

  return (
    <Widget
      title="Case network"
      contextChip={q.data ? `${q.data.linked_case_count} linked` : undefined}
      loading={q.isLoading}
      error={q.error}
      empty={empty}
      emptyLabel="No co-accused or linked cases found for this FIR."
      onRefresh={() => q.refetch()}
      info={
        <p className="text-content-dim">
          The case (centre), its accused, and other cases that share an accused by name. Click a
          linked case to open it. The full canvas lives in People &amp; Networks.
        </p>
      }
    >
      {q.data && !empty && (
        <CaseNetworkGraph data={q.data} onOpenCase={(id) => navigate(`/cases/${id}`)} />
      )}
    </Widget>
  );
}
